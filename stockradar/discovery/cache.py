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
    with conn:
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
