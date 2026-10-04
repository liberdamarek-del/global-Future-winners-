"""Yahoo Finance chart API — bezplatné denní ceny a objemy (bez API klíče).

Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/<symbol>
Neoficiální rozhraní: může se změnit nebo omezit počet dotazů, proto každý údaj nese zdroj a čas stažení.
"""

import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from stockradar.timeutil import to_iso, utcnow

SOURCE = "Yahoo Finance chart API"
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval=1d"
BROWSER_UA = "Mozilla/5.0"


@dataclass(frozen=True)
class Quote:
    symbol: str
    currency: str | None
    exchange: str | None
    name: str | None
    price: float | None
    price_time: datetime | None
    bars: list[tuple[str, float, float | None]]  # (YYYY-MM-DD, close, volume)


def parse_chart(symbol: str, payload: dict) -> Quote:
    result = (payload.get("chart") or {}).get("result")
    if not result:
        error = (payload.get("chart") or {}).get("error")
        raise ValueError(f"{symbol}: Yahoo nevrátil data ({error})")
    r = result[0]
    meta = r.get("meta", {})
    offset = int(meta.get("gmtoffset") or 0)
    stamps = r.get("timestamp") or []
    quote = (r.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    bars = {}
    for i, ts in enumerate(stamps):
        close = closes[i] if i < len(closes) else None
        if close is None or close <= 0:
            continue
        day = datetime.fromtimestamp(ts + offset, tz=timezone.utc).date().isoformat()
        volume = volumes[i] if i < len(volumes) else None
        bars[day] = (day, float(close), float(volume) if volume is not None else None)
    price_time = meta.get("regularMarketTime")
    return Quote(
        symbol=symbol,
        currency=meta.get("currency"),
        exchange=meta.get("fullExchangeName") or meta.get("exchangeName"),
        name=meta.get("longName") or meta.get("shortName"),
        price=meta.get("regularMarketPrice"),
        price_time=datetime.fromtimestamp(price_time, tz=timezone.utc) if price_time else None,
        bars=[bars[d] for d in sorted(bars)],
    )


def fetch_chart(symbol: str, range_: str = "2y", *, retries: int = 3, timeout: int = 20) -> Quote:
    url = CHART_URL.format(symbol=urllib.parse.quote(symbol), range=range_)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return parse_chart(symbol, json.load(resp))
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            # 404 / „Yahoo nevrátil data“ = neplatný symbol → opakování nepomůže
            if (isinstance(exc, urllib.error.HTTPError) and exc.code == 404) or "nevrátil data" in str(exc):
                break
            # 429 = omezení počtu dotazů: počkej déle
            too_many = isinstance(exc, urllib.error.HTTPError) and exc.code == 429
            time.sleep((15 if too_many else 2) * (attempt + 1))
    raise RuntimeError(f"{symbol}: stažení z Yahoo selhalo: {last_error}")


def store_bars(conn: sqlite3.Connection, quote: Quote, *, fetched_at: datetime | None = None) -> int:
    fetched = to_iso(fetched_at or utcnow())
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO price_bars (symbol, date, close, volume, source, fetched_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(quote.symbol, d, c, v, SOURCE, fetched) for d, c, v in quote.bars],
        )
    return len(quote.bars)


SUBUNITS = {"GBp": "GBP", "GBX": "GBP", "ILA": "ILS", "ZAc": "ZAR"}  # pence, agorot, centy


def fx_symbol(currency: str) -> str | None:
    """Yahoo symbol kurzu 'jednotek měny za 1 USD'. Dílčí jednotky (GBp, ILA) se přepočítávají přes hlavní měnu."""
    cur = SUBUNITS.get(currency, currency)
    return None if cur == "USD" else f"{cur}=X"


def usd_factor(currency: str) -> float:
    """Násobek pro převod z měny kotace na základní jednotku (pence -> libry, agorot -> šekely)."""
    return 0.01 if currency in SUBUNITS else 1.0
