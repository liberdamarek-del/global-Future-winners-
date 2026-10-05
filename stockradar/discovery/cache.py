"""Kompaktní cache historie cen pro tisíce firem (zlib + array, jen standardní knihovna)."""

import array
import os
import sqlite3
import zlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from stockradar.config import PROJECT_ROOT

DEFAULT_CACHE = PROJECT_ROOT / "data" / "market_cache.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS securities (
    symbol          TEXT PRIMARY KEY,      -- Yahoo symbol
    name            TEXT,
    country         TEXT,
    exchange        TEXT,
    sector          TEXT,
    industry        TEXT,
    market_cap_usd  REAL,                  -- aktuální (ze zdroje seznamu), NE historická
    ipo_year        INTEGER,
    source          TEXT NOT NULL,
    fetched_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS news_events (
    symbol      TEXT NOT NULL,
    t0          TEXT NOT NULL,
    end_day     TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    info_json   TEXT NOT NULL,
    PRIMARY KEY (symbol, t0, end_day)
);
CREATE TABLE IF NOT EXISTS series (
    symbol      TEXT PRIMARY KEY,
    currency    TEXT,
    first_day   TEXT,
    last_day    TEXT,
    n           INTEGER,
    days        BLOB,
    closes      BLOB,
    volumes     BLOB,
    source      TEXT,
    fetched_at  TEXT NOT NULL,
    error       TEXT
);
-- SEC EDGAR (zdarma, e-mail v hlavičce — viz stockradar/contact.py)
CREATE TABLE IF NOT EXISTS sec_tickers (
    ticker      TEXT PRIMARY KEY,
    cik         INTEGER NOT NULL,
    title       TEXT,
    fetched_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sec_facts (
    cik         INTEGER NOT NULL,
    concept     TEXT NOT NULL,          -- revenue / net_income / shares / cash
    period      TEXT NOT NULL,          -- CY2025Q2 (kvartál) nebo CY2025Q2I (okamžik)
    end_day     TEXT NOT NULL,
    val         REAL NOT NULL,
    source      TEXT NOT NULL,          -- XBRL koncept, ze kterého hodnota pochází
    PRIMARY KEY (cik, concept, period)
);
CREATE TABLE IF NOT EXISTS sec_frames_done (
    tag         TEXT NOT NULL,
    period      TEXT NOT NULL,
    n           INTEGER NOT NULL,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (tag, period)
);
CREATE TABLE IF NOT EXISTS sec_filings (
    path        TEXT PRIMARY KEY,       -- edgar/data/<cik>/<accession>.txt
    cik         INTEGER NOT NULL,
    form        TEXT NOT NULL,
    filed       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sec_filings_cik ON sec_filings(cik, filed);
CREATE TABLE IF NOT EXISTS sec_index_done (
    quarter     TEXT PRIMARY KEY,       -- 2026Q3
    n           INTEGER NOT NULL,
    fetched_at  TEXT NOT NULL
);
-- ClinicalTrials.gov API v2 (zdarma, bez klíče a bez e-mailu)
CREATE TABLE IF NOT EXISTS ct_studies (
    nct         TEXT PRIMARY KEY,
    sponsor     TEXT NOT NULL,
    phase       TEXT,
    pcd         TEXT,                   -- primary completion date (YYYY-MM nebo YYYY-MM-DD)
    pcd_type    TEXT,                   -- ACTUAL / ESTIMATED
    status      TEXT,
    title       TEXT,
    conditions  TEXT,
    enrollment  INTEGER,
    results_posted TEXT,
    last_update TEXT,
    fetched_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ct_sponsor ON ct_studies(sponsor);
-- Smart money: insider transakce (SEC Form 3/4/5, strukturovaná data), politici (Sněmovna, Senát), buybacky
CREATE TABLE IF NOT EXISTS insider_tx (
    accession   TEXT NOT NULL,
    sk          INTEGER NOT NULL,
    filing_date TEXT NOT NULL,          -- kdy se nákup dozvěděla veřejnost
    trans_date  TEXT,
    issuer_cik  INTEGER,
    ticker      TEXT,
    issuer      TEXT,
    owner_cik   INTEGER,
    owner       TEXT,
    rel         TEXT,                   -- Director / Officer / TenPercentOwner / Other (může jich být víc)
    title       TEXT,                   -- funkce (CEO, CFO …)
    code        TEXT NOT NULL,          -- P nákup na trhu, A přidělení, M uplatnění opce, F daň, S prodej …
    shares      REAL,
    price       REAL,
    ad          TEXT,                   -- A nabyto / D zcizeno
    owned_after REAL,
    direct      TEXT,                   -- D přímo / I nepřímo (trust, fond …)
    plan10b51   INTEGER,                -- 1 = automatický plán 10b5-1 (pole od 2023)
    form        TEXT,
    PRIMARY KEY (accession, sk)
);
CREATE INDEX IF NOT EXISTS ix_insider_ticker ON insider_tx(ticker, filing_date);
CREATE INDEX IF NOT EXISTS ix_insider_code ON insider_tx(code, filing_date);
CREATE TABLE IF NOT EXISTS insider_done (
    quarter     TEXT PRIMARY KEY,
    n           INTEGER NOT NULL,
    fetched_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS congress_docs (
    doc_id      TEXT PRIMARY KEY,
    chamber     TEXT NOT NULL,          -- HOUSE / SENATE
    member      TEXT NOT NULL,
    filed       TEXT NOT NULL,
    url         TEXT NOT NULL,
    status      TEXT NOT NULL,          -- OK / BEZ_TEXTU (sken) / CHYBA
    n_rows      INTEGER NOT NULL DEFAULT 0,
    fetched_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS congress_tx (
    doc_id      TEXT NOT NULL,
    row         INTEGER NOT NULL,
    chamber     TEXT NOT NULL,
    member      TEXT NOT NULL,
    owner       TEXT,                   -- SP manžel/ka, JT společně, DC dítě, Self …
    filed       TEXT NOT NULL,          -- kdy se transakce dozvěděla veřejnost
    tx_date     TEXT,
    ticker      TEXT,
    asset       TEXT,
    asset_type  TEXT,                   -- ST akcie, OP opce, …
    tx_type     TEXT,                   -- P nákup, S prodej, S (partial), E výměna
    amount_min  REAL,
    amount_max  REAL,
    description TEXT,
    PRIMARY KEY (doc_id, row)
);
CREATE INDEX IF NOT EXISTS ix_congress_member ON congress_tx(member, tx_date);
CREATE TABLE IF NOT EXISTS ct_sponsor_map (
    sponsor     TEXT PRIMARY KEY,
    symbol      TEXT,                   -- NULL = sponzor nenalezen mezi kotovanými firmami
    method      TEXT NOT NULL
);
"""


def cache_path() -> Path:
    return Path(os.environ.get("STOCKRADAR_MARKET_CACHE", DEFAULT_CACHE))


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = path or cache_path()
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


@dataclass
class Bars:
    symbol: str
    currency: str | None
    days: "array.array | list[int]"      # date.toordinal()
    closes: "array.array | list[float]"
    volumes: "array.array | list[float]"

    def date(self, i: int) -> str:
        return date.fromordinal(self.days[i]).isoformat()


def _pack(values, code: str) -> bytes:
    return zlib.compress(array.array(code, values).tobytes(), 6)


def _unpack(blob: bytes, code: str) -> array.array:
    """Vrací kompaktní array (8 B na číslo) — u 13 000 firem šetří gigabajty paměti oproti seznamům."""
    a = array.array(code)
    a.frombytes(zlib.decompress(blob))
    return a


def store_series(conn: sqlite3.Connection, symbol: str, currency: str | None,
                 bars: list[tuple[str, float, float | None]], *, source: str, fetched_at: str) -> int:
    days = [date.fromisoformat(d).toordinal() for d, _, _ in bars]
    closes = [c for _, c, _ in bars]
    vols = [v or 0.0 for _, _, v in bars]
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO series (symbol, currency, first_day, last_day, n, days, closes, volumes, source,"
            " fetched_at, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (symbol, currency, bars[0][0] if bars else None, bars[-1][0] if bars else None, len(bars),
             _pack(days, "i"), _pack(closes, "d"), _pack(vols, "d"), source, fetched_at))
    return len(bars)


def store_error(conn: sqlite3.Connection, symbol: str, error: str, *, fetched_at: str) -> None:
    """Chyba stažení. Už uloženou historii NEPŘEPISUJE (dřív přechodná chyba, např. HTTP 429, smazala celou řadu)
    — řada zůstane beze změny a symbol se zkusí znovu při příštím běhu."""
    with conn:
        have = conn.execute("SELECT 1 FROM series WHERE symbol = ? AND error IS NULL AND n > 0", (symbol,)).fetchone()
        if not have:
            conn.execute("INSERT OR REPLACE INTO series (symbol, n, fetched_at, error) VALUES (?, 0, ?, ?)",
                         (symbol, fetched_at, error[:300]))


def load_series(conn: sqlite3.Connection, symbol: str) -> Bars | None:
    r = conn.execute("SELECT * FROM series WHERE symbol = ? AND error IS NULL AND n > 0", (symbol,)).fetchone()
    if r is None:
        return None
    return Bars(symbol, r["currency"], _unpack(r["days"], "i"), _unpack(r["closes"], "d"), _unpack(r["volumes"], "d"))


def iter_series(conn: sqlite3.Connection):
    for r in conn.execute("SELECT * FROM series WHERE error IS NULL AND n > 0 ORDER BY symbol"):
        yield Bars(r["symbol"], r["currency"], _unpack(r["days"], "i"), _unpack(r["closes"], "d"),
                   _unpack(r["volumes"], "d"))


def cached_news(conn: sqlite3.Connection, symbol: str, t0: str, end: str) -> dict | None:
    import json
    r = conn.execute("SELECT info_json FROM news_events WHERE symbol = ? AND t0 = ? AND end_day = ?",
                     (symbol, t0, end)).fetchone()
    return json.loads(r[0]) if r else None


def store_news(conn: sqlite3.Connection, symbol: str, t0: str, end: str, info: dict, *, fetched_at: str) -> None:
    import json
    if info.get("stav", "").startswith("DATA NEDOSTUPNÁ"):
        return  # síťovou chybu necachovat — příště zkusit znovu
    with conn:
        conn.execute("INSERT OR REPLACE INTO news_events (symbol, t0, end_day, fetched_at, info_json) VALUES (?, ?, ?, ?, ?)",
                     (symbol, t0, end, fetched_at, json.dumps(info, ensure_ascii=False)))
