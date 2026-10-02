"""Globální seznam firem ze zdrojů zdarma.

USA:        Nasdaq screener API (všechny akcie NASDAQ/NYSE/AMEX: sektor, obor, tržní kapitalizace, země)
Austrálie:  ASX — seznam všech kotovaných firem (CSV s GICS odvětvím)
Ostatní:    složení indexů z Wikipedie (Evropa, Japonsko, Hongkong, Indie, Kanada, Korea, …)

Seznamy obsahují jen DNES kotované firmy → historická analýza má survivorship bias (§60). Je to uvedeno ve výstupech.
"""

import csv
import html
import io
import json
import re
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser

from stockradar.timeutil import to_iso, utcnow

UA = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}
NASDAQ_SCREENER = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=20000&download=true"
ASX_LIST = "https://www.asx.com.au/asx/research/ASXListedCompanies.csv"
JPX_LIST = "https://www.jpx.co.jp/english/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_e.xlsx"

SKIP_NAME = re.compile(r"\b(warrants?|units?|rights?|preferred|notes due|debentures?|depositary shares? representing .*preferred)\b",
                       re.I)


def _get_bytes(url: str, timeout: int = 60) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def _get(url: str, timeout: int = 60) -> str:
    return _get_bytes(url, timeout).decode("utf-8", errors="replace")


def read_xlsx_rows(data: bytes) -> list[list[str]]:
    """Minimální čtečka prvního listu xlsx (bez externích knihoven)."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = ["".join(t.text or "" for t in si.iter(ns + "t"))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(ns + "si")]
    rows = []
    for r in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(ns + "row"):
        vals = []
        for c in r.findall(ns + "c"):
            v = c.find(ns + "v")
            vals.append(shared[int(v.text)] if c.get("t") == "s" and v is not None else (v.text if v is not None else ""))
        rows.append(vals)
    return rows


def _num(s) -> float | None:
    try:
        return float(str(s).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def us_securities(text: str | None = None) -> list[dict]:
    rows = json.loads(text or _get(NASDAQ_SCREENER))["data"]["rows"]
    out = []
    for r in rows:
        sym = r["symbol"].strip()
        if not sym or "^" in sym or SKIP_NAME.search(r["name"] or ""):
            continue
        out.append({
            "symbol": sym.replace("/", "-"), "name": r["name"], "country": r["country"] or "US",
            "exchange": "US", "sector": r["sector"] or None, "industry": r["industry"] or None,
            "market_cap_usd": _num(r["marketCap"]) or None, "ipo_year": int(r["ipoyear"]) if r["ipoyear"] else None,
            "source": "Nasdaq screener API",
        })
    return out


def asx_securities(text: str | None = None) -> list[dict]:
    raw = text or _get(ASX_LIST)
    lines = raw.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("Company name"))
    out = []
    for row in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        code = (row.get("ASX code") or "").strip()
        if code:
            out.append({"symbol": f"{code}.AX", "name": row["Company name"].strip().title(), "country": "Australia",
                        "exchange": "ASX", "sector": None, "industry": (row.get("GICS industry group") or "").strip() or None,
                        "market_cap_usd": None, "ipo_year": None, "source": "ASX listed companies CSV"})
    return out


def jpx_securities(data: bytes | None = None) -> list[dict]:
    rows = read_xlsx_rows(data or _get_bytes(JPX_LIST))
    head = rows[0]
    out = []
    for r in rows[1:]:
        rec = dict(zip(head, r))
        segment = rec.get("Section/Products", "")
        if not any(k in segment for k in ("Prime", "Standard", "Growth")):
            continue  # ETF, REIT, PRO Market
        out.append({"symbol": f"{rec['Local Code']}.T", "name": rec.get("Name (English)"), "country": "Japan",
                    "exchange": f"TSE {segment}", "sector": rec.get("17 Sector(name)"),
                    "industry": rec.get("33 Sector(name)"), "market_cap_usd": None, "ipo_year": None,
                    "source": "JPX listed issues (xlsx)"})
    return out


class _Tables(HTMLParser):
    """Vytáhne buňky všech tabulek 'wikitable'."""

    def __init__(self):
        super().__init__()
        self.tables, self._stack, self._row, self._cell, self._in = [], [], None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            cls = dict(attrs).get("class") or ""
            self._stack.append("wikitable" in cls)
            if self._stack[-1]:
                self.tables.append([])
        elif self._stack and self._stack[-1]:
            if tag == "tr":
                self._row = []
            elif tag in ("td", "th"):
                self._cell = []
            elif tag == "sup":
                self._in += 1

    def handle_endtag(self, tag):
        if tag == "table" and self._stack:
            self._stack.pop()
        elif self._stack and self._stack[-1]:
            if tag in ("td", "th") and self._cell is not None and self._row is not None:
                self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
                self._cell = None
            elif tag == "tr" and self._row is not None:
                if self._row:
                    self.tables[-1].append(self._row)
                self._row = None
            elif tag == "sup":
                self._in = max(0, self._in - 1)

    def handle_data(self, data):
        if self._cell is not None and not self._in:
            self._cell.append(data)


# (název, URL, země, burza, funkce převodu tickeru na Yahoo symbol)
def _sfx(suffix, dot="-"):
    def convert(t):
        if not t:
            return None
        if t.upper().endswith(suffix.upper()):  # Wikipedie už uvádí Yahoo-like tvar (např. ABN.AS)
            return t.replace(" ", "-")
        return t.replace(".", dot).replace(" ", "-") + suffix
    return convert


def _num_sfx(suffix, width):
    return lambda t: (t.zfill(width) + suffix) if t and t.isdigit() else None


WIKI_INDICES = [
    ("FTSE 100", "https://en.wikipedia.org/wiki/FTSE_100_Index", "United Kingdom", "LSE", _sfx(".L")),
    ("FTSE 250", "https://en.wikipedia.org/wiki/FTSE_250_Index", "United Kingdom", "LSE", _sfx(".L")),
    ("DAX", "https://en.wikipedia.org/wiki/DAX", "Germany", "XETRA", _sfx(".DE")),
    ("MDAX", "https://en.wikipedia.org/wiki/MDAX", "Germany", "XETRA", _sfx(".DE")),
    ("SDAX", "https://en.wikipedia.org/wiki/SDAX", "Germany", "XETRA", _sfx(".DE")),
    ("TecDAX", "https://en.wikipedia.org/wiki/TecDAX", "Germany", "XETRA", _sfx(".DE")),
    ("CAC 40", "https://en.wikipedia.org/wiki/CAC_40", "France", "Euronext Paris", _sfx(".PA")),
    ("AEX", "https://en.wikipedia.org/wiki/AEX_index", "Netherlands", "Euronext Amsterdam", _sfx(".AS")),
    ("SMI", "https://en.wikipedia.org/wiki/Swiss_Market_Index", "Switzerland", "SIX", _sfx(".SW")),
    ("OMXS30", "https://en.wikipedia.org/wiki/OMX_Stockholm_30", "Sweden", "Nasdaq Stockholm", _sfx(".ST")),
    ("OMXC25", "https://en.wikipedia.org/wiki/OMX_Copenhagen_25", "Denmark", "Nasdaq Copenhagen", _sfx(".CO")),
    ("OMXH25", "https://en.wikipedia.org/wiki/OMX_Helsinki_25", "Finland", "Nasdaq Helsinki", _sfx(".HE")),
    ("OBX", "https://en.wikipedia.org/wiki/OBX_Index", "Norway", "Oslo Børs", _sfx(".OL")),
    ("FTSE MIB", "https://en.wikipedia.org/wiki/FTSE_MIB", "Italy", "Borsa Italiana", _sfx(".MI")),
    ("IBEX 35", "https://en.wikipedia.org/wiki/IBEX_35", "Spain", "BME", _sfx(".MC")),
    ("S&P/TSX 60", "https://en.wikipedia.org/wiki/S%26P/TSX_60", "Canada", "TSX", _sfx(".TO")),
    ("S&P/TSX Composite", "https://en.wikipedia.org/wiki/S%26P/TSX_Composite_Index", "Canada", "TSX", _sfx(".TO")),
    ("Hang Seng", "https://en.wikipedia.org/wiki/Hang_Seng_Index", "Hong Kong", "HKEX", _num_sfx(".HK", 4)),
    ("NIFTY 50", "https://en.wikipedia.org/wiki/NIFTY_50", "India", "NSE", _sfx(".NS")),
    ("NIFTY Next 50", "https://en.wikipedia.org/wiki/NIFTY_Next_50", "India", "NSE", _sfx(".NS")),
    ("Straits Times", "https://en.wikipedia.org/wiki/Straits_Times_Index", "Singapore", "SGX", _sfx(".SI")),
    ("TA-35", "https://en.wikipedia.org/wiki/TA-35_Index", "Israel", "TASE", _sfx(".TA")),
    ("KOSPI 200", "https://en.wikipedia.org/wiki/KOSPI_200", "South Korea", "KRX", _num_sfx(".KS", 6)),
    ("Ibovespa", "https://en.wikipedia.org/wiki/List_of_companies_listed_on_B3", "Brazil", "B3", _sfx(".SA")),
]

TICKER_HEAD = re.compile(r"^(ticker|symbol|code|epic|stock code|stock symbol|ticker symbol|sehk|tse code|nse symbol|bloomberg)",
                         re.I)
NAME_HEAD = re.compile(r"(company|name|constituent|security)", re.I)
SECTOR_HEAD = re.compile(r"(sector|industry|icb|gics)", re.I)


def _clean_ticker(t: str) -> str:
    t = html.unescape(t).strip()
    t = re.sub(r"\[.*?\]", "", t)
    if ":" in t:
        t = t.split(":")[-1]
    return t.strip().split(" (")[0].strip()


def wiki_securities(index: tuple, text: str | None = None) -> list[dict]:
    name, url, country, exchange, convert = index
    parser = _Tables()
    parser.feed(text or _get(url))
    out, seen = [], set()
    for table in parser.tables:
        if len(table) > 1 and len(table[0]) == 1:  # titulkový řádek nad záhlavím
            table = table[1:]
        if len(table) < 5:
            continue
        head = table[0]
        tcol = next((i for i, h in enumerate(head) if TICKER_HEAD.search(h)), None)
        if tcol is None:
            continue
        ncol = next((i for i, h in enumerate(head) if NAME_HEAD.search(h) and i != tcol), None)
        scol = next((i for i, h in enumerate(head) if SECTOR_HEAD.search(h)), None)
        for row in table[1:]:
            if len(row) != len(head):
                continue
            sym = convert(_clean_ticker(row[tcol]))
            if not sym or sym in seen or len(sym) > 20:
                continue
            seen.add(sym)
            out.append({"symbol": sym, "name": row[ncol] if ncol is not None else None, "country": country,
                        "exchange": exchange, "sector": row[scol] if scol is not None else None, "industry": None,
                        "market_cap_usd": None, "ipo_year": None, "source": f"Wikipedia: {name}"})
    return out


def save_securities(conn: sqlite3.Connection, rows: list[dict]) -> int:
    now = to_iso(utcnow())
    with conn:
        for r in rows:
            conn.execute(
                "INSERT INTO securities (symbol, name, country, exchange, sector, industry, market_cap_usd, ipo_year,"
                " source, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(symbol) DO UPDATE SET name = COALESCE(excluded.name, name),"
                " sector = COALESCE(excluded.sector, sector), industry = COALESCE(excluded.industry, industry),"
                " market_cap_usd = COALESCE(excluded.market_cap_usd, market_cap_usd), fetched_at = excluded.fetched_at",
                (r["symbol"], r["name"], r["country"], r["exchange"], r["sector"], r["industry"], r["market_cap_usd"],
                 r["ipo_year"], r["source"], now))
    return len(rows)


def build_universe(conn: sqlite3.Connection, *, wiki: bool = True, log=print) -> dict[str, int]:
    counts = {}
    for label, fn in (("USA (Nasdaq screener)", us_securities), ("Austrálie (ASX)", asx_securities),
                      ("Japonsko (JPX)", jpx_securities)):
        try:
            counts[label] = save_securities(conn, fn())
        except Exception as exc:  # zdroj nedostupný -> pokračovat, zapsat do logu
            counts[label] = 0
            log(f"{label}: CHYBA {exc}")
    if wiki:
        for idx in WIKI_INDICES:
            try:
                counts[f"Wikipedia: {idx[0]}"] = save_securities(conn, wiki_securities(idx))
            except Exception as exc:
                counts[f"Wikipedia: {idx[0]}"] = 0
                log(f"{idx[0]}: CHYBA {exc}")
    return counts
