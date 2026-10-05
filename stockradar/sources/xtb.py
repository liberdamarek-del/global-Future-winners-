"""XTB — je akcie v nabídce brokera? (rozhodnutí uživatele 2026-10-05: do žebříčku jen firmy, které XTB nabízí)

Zdroj: veřejné vyhledávání nástrojů na xtb.com/cz (stejné, jaké používá stránka https://www.xtb.com/cz/akcie),
bez přihlášení a bez e-mailu. Neoficiální rozhraní → každý výsledek nese zdroj a čas kontroly a ukládá se do cache
(`xtb_offer` v data/market_cache.db) na `config.XTB_CHECK_MAX_AGE` (30 dní).

Stavy:
- AKCIE — skutečná akcie (XTB typ „cashstocks“) na domácí burze firmy (např. VST.US, RR.UK, NKT.DK),
  nebo na jiné burze se stejným jménem firmy (např. japonský Lasertec jako 6K8.DE v EUR) → `jina_burza`.
- CFD — XTB nabízí jen CFD (páka), ne akcii → do žebříčku nepatří.
- NE — XTB firmu nenabízí (typicky burzy v Japonsku, Austrálii, Kanadě, Koreji).
- None — nepodařilo se ověřit (chyba sítě) → firma se do žebříčku nedá, výsledek se neukládá.
"""

import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from stockradar.config import XTB_CHECK_MAX_AGE
from stockradar.timeutil import parse_iso, to_iso, utcnow

SOURCE = "xtb.com/cz — vyhledávání nástrojů"
SEARCH_URL = "https://www.xtb.com/web-api/v3/languages/cs/branches/cz/instruments?{query}"
PAGE_URL = "https://www.xtb.com/cz/akcie"
BROWSER_UA = "Mozilla/5.0"
STOCK, CFD = "cashstocks", "shares"

# přípona Yahoo → přípona XTB (burzy, na kterých XTB nabízí akcie; ověřeno 2026-10-05 dotazy RR.UK, NKT.DK, FRO.NO…)
SUFFIX = {"": "US", "L": "UK", "DE": "DE", "PA": "FR", "MI": "IT", "MC": "ES", "AS": "NL", "BR": "BE", "LS": "PT",
          "CO": "DK", "ST": "SE", "OL": "NO", "HE": "FI", "SW": "CH", "WA": "PL"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS xtb_offer (
    symbol      TEXT PRIMARY KEY,      -- Yahoo symbol
    status      TEXT NOT NULL CHECK (status IN ('AKCIE', 'CFD', 'NE')),
    xtb_symbol  TEXT,
    xtb_name    TEXT,
    currency    TEXT,
    other_exchange INTEGER NOT NULL DEFAULT 0,
    query       TEXT NOT NULL,
    source      TEXT NOT NULL,
    checked_at  TEXT NOT NULL
);
"""

_LEGAL = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|ag|sa|se|nv|n\.v|ab|asa|a/s|"
                    r"holdings?|group|the|class [a-c]|common stock|ordinary shares|common shares)\b\.?", re.I)


def xtb_symbol(symbol: str) -> str | None:
    """VST → VST.US, RR.L → RR.UK, BRK-B → BRKB.US; burzy mimo nabídku XTB (.T, .AX, .TO, .KS …) → None."""
    base, _, suf = symbol.rpartition(".") if "." in symbol else (symbol, "", "")
    xs = SUFFIX.get(suf.upper())
    if xs is None or not base:
        return None
    return f"{base.replace('-', '').upper()}.{xs}"


def norm_name(name: str | None) -> str:
    """„Lasertec Corporation“ i „Lasertec Corp“ → „lasertec“ (porovnání firmy na jiné burze)."""
    s = _LEGAL.sub(" ", (name or "").lower().replace(",", " ").replace("&", " and "))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _search(query: str, *, timeout: int = 20) -> list[dict]:
    url = SEARCH_URL.format(query=urllib.parse.urlencode({"query": query}))
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")).get("items") or []


def classify(items: list[dict], xsym: str | None, name: str | None) -> dict:
    """Výsledek vyhledávání → stav. Domácí burza: přesná shoda symbolu. Jiná burza: akcie se stejným jménem firmy."""
    if xsym:
        exact = [i for i in items if (i.get("symbol") or "").upper() == xsym.upper()]
        stock = next((i for i in exact if i.get("typeSlug") == STOCK), None)
        if stock:
            return {"status": "AKCIE", "xtb_symbol": stock["symbol"], "xtb_name": stock.get("name"),
                    "currency": stock.get("currencyCode"), "other_exchange": 0}
        if any(i.get("typeSlug") == CFD for i in exact):
            return {"status": "CFD", "xtb_symbol": xsym, "xtb_name": exact[0].get("name"), "currency": None,
                    "other_exchange": 0}
        return {"status": "NE", "xtb_symbol": None, "xtb_name": None, "currency": None, "other_exchange": 0}
    want = norm_name(name)
    if want:
        for i in items:
            if i.get("typeSlug") == STOCK and want in (norm_name(i.get("name")), norm_name(i.get("companyName"))):
                return {"status": "AKCIE", "xtb_symbol": i["symbol"], "xtb_name": i.get("name"),
                        "currency": i.get("currencyCode"), "other_exchange": 1}
    return {"status": "NE", "xtb_symbol": None, "xtb_name": None, "currency": None, "other_exchange": 0}


class Checker:
    """Ověřuje firmy proti nabídce XTB s cache; po 5 chybách sítě za sebou přestane zkoušet (zbytek = neověřeno)."""

    def __init__(self, cache_conn: sqlite3.Connection, *, search=_search, pause: float = 0.3,
                 max_age=XTB_CHECK_MAX_AGE, now: datetime | None = None):
        cache_conn.executescript(SCHEMA)
        self.conn, self.search, self.pause, self.max_age = cache_conn, search, pause, max_age
        self.now = now or utcnow()
        self.requests = self.cached = self.errors = 0
        self._fails = 0
        self.down = False

    def _cached(self, symbol: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM xtb_offer WHERE symbol = ?", (symbol,)).fetchone()
        if r is None or self.now - parse_iso(r["checked_at"]) > self.max_age:
            return None
        return dict(r)

    def check(self, symbol: str, name: str | None = None) -> dict | None:
        hit = self._cached(symbol)
        if hit:
            self.cached += 1
            return hit
        if self.down:
            return None
        xsym = xtb_symbol(symbol)
        query = xsym or norm_name(name)          # „Lasertec Corporation“ XTB nenajde, „lasertec“ ano
        if not query:
            res = {"status": "NE", "xtb_symbol": None, "xtb_name": None, "currency": None, "other_exchange": 0}
        else:
            try:
                items = self.search(query)
                self._fails = 0
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                self.errors += 1
                self._fails += 1
                self.down = self._fails >= 5
                return None
            finally:
                self.requests += 1
                if self.pause:
                    time.sleep(self.pause)
            res = classify(items, xsym, name)
        row = {"symbol": symbol, **res, "query": query or "-", "source": SOURCE, "checked_at": to_iso(self.now)}
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO xtb_offer (symbol, status, xtb_symbol, xtb_name, currency,"
                              " other_exchange, query, source, checked_at) VALUES (:symbol, :status, :xtb_symbol,"
                              " :xtb_name, :currency, :other_exchange, :query, :source, :checked_at)", row)
        return row

    def tradable(self, symbol: str, name: str | None = None) -> bool:
        r = self.check(symbol, name)
        return bool(r) and r["status"] == "AKCIE"

    def summary(self) -> dict:
        return {"zdroj": SOURCE, "stranka": PAGE_URL, "dotazu": self.requests, "z_cache": self.cached,
                "chyb": self.errors, "nedostupne": self.down, "overeno": to_iso(self.now)}


def badge(row: dict | None) -> dict:
    """Stručný údaj pro kartu firmy na webu."""
    if not row:
        return {"stav": "NEOVĚŘENO"}
    return {"stav": row["status"], "symbol": row.get("xtb_symbol"), "mena": row.get("currency"),
            "jina_burza": bool(row.get("other_exchange")), "overeno": row.get("checked_at")}
