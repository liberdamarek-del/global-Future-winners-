"""Stažení bezplatných dat do cache (price_bars). Cache není zdroj pravdy — dá se kdykoli stáhnout znovu."""

import sqlite3
import time
from collections.abc import Callable
from datetime import datetime

from stockradar import config
from stockradar.sources import yahoo
from stockradar.timeutil import utcnow

MIN_HISTORY_BARS = 400  # méně než tohle v cache -> stáhnout delší historii (učení modelu)


def tracked_symbols(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT l.id AS listing_id, l.company_id, l.yahoo_symbol AS symbol, l.currency, c.name"
        " FROM listings l JOIN companies c ON c.id = l.company_id"
        " WHERE l.yahoo_symbol IS NOT NULL AND l.valid_to IS NULL ORDER BY l.yahoo_symbol"
    ).fetchall()


def fx_symbols(conn: sqlite3.Connection) -> list[str]:
    currencies = {r["currency"] for r in tracked_symbols(conn) if r["currency"]}
    return sorted({s for s in (yahoo.fx_symbol(c) for c in currencies) if s})


def update_prices(
    conn: sqlite3.Connection,
    *,
    fetch: Callable[[str, str], yahoo.Quote] = lambda s, r: yahoo.fetch_chart(s, r),
    pause: float = 0.4,
    now: datetime | None = None,
) -> dict:
    """Stáhne ceny všech sledovaných symbolů, benchmarku a kurzů. Chyba jednoho symbolu nezastaví ostatní."""
    now = now or utcnow()
    symbols = [r["symbol"] for r in tracked_symbols(conn)] + [config.BENCHMARK_SYMBOL] + fx_symbols(conn)
    quotes: dict[str, dict] = {}
    errors: list[str] = []
    for symbol in dict.fromkeys(symbols):
        have = conn.execute("SELECT COUNT(*) FROM price_bars WHERE symbol = ?", (symbol,)).fetchone()[0]
        try:
            quote = fetch(symbol, "5y" if have < MIN_HISTORY_BARS else "3mo")
        except Exception as exc:  # síť / změna API — zaznamenat a pokračovat
            errors.append(f"{symbol}: {exc}")
            continue
        yahoo.store_bars(conn, quote, fetched_at=now)
        quotes[symbol] = {
            "currency": quote.currency, "price": quote.price,
            "price_time": quote.price_time, "name": quote.name, "exchange": quote.exchange,
        }
        if pause:
            time.sleep(pause)
    return {"quotes": quotes, "errors": errors, "requested": len(dict.fromkeys(symbols))}
