"""Ceny komodit z Yahoo (futures, nejbližší kontrakt; zdarma) → cache `series`; týdenní řady pro kauzální testy.

Pozor: řada nejbližšího kontraktu má skoky při přechodu na další kontrakt (roll). Pro měsíční a delší pohyby je to
malý šum, pro denní pohyby se nepoužívá.
"""

import bisect
import time

from stockradar.causal.commodities import COMMODITIES
from stockradar.discovery import cache
from stockradar.sources import yahoo
from stockradar.timeutil import to_iso, utcnow


def download(cache_conn, *, range_: str = "5y", pause: float = 0.4, fetch=None, log=print) -> dict:
    fetch = fetch or (lambda s: yahoo.fetch_chart(s, range_, retries=3))
    ok, err = [], []
    for c in COMMODITIES:
        try:
            q = fetch(c["symbol"])
            if len(q.bars) < 200:
                raise ValueError(f"málo dat ({len(q.bars)} dní)")
            cache.store_series(cache_conn, c["symbol"], q.currency, q.bars, source=yahoo.SOURCE, fetched_at=to_iso(utcnow()))
            ok.append(c["id"])
        except Exception as exc:   # jedna komodita nesmí shodit ostatní
            cache.store_error(cache_conn, c["symbol"], str(exc), fetched_at=to_iso(utcnow()))
            err.append(f"{c['id']}: {str(exc)[:80]}")
        if pause:
            time.sleep(pause)
    log(f"Komodity: staženo {len(ok)}, chyb {len(err)}" + (f" ({'; '.join(err)})" if err else ""))
    return {"ok": ok, "chyby": err}


def load(cache_conn) -> dict:
    """id komodity → Bars (jen řady, které se stáhly)."""
    out = {}
    for c in COMMODITIES:
        b = cache.load_series(cache_conn, c["symbol"])
        if b is not None and len(b.days) >= 200:
            out[c["id"]] = b
    return out


def close_at(bars, day: int) -> float | None:
    """Poslední závěr k danému dni (nejvýš 7 dní starý)."""
    i = bisect.bisect_right(bars.days, day) - 1
    if i < 0 or day - bars.days[i] > 7 or bars.closes[i] <= 0:
        return None
    return bars.closes[i]


def ret(bars, day: int, back_days: int) -> float | None:
    """Výnos za posledních `back_days` kalendářních dní k danému dni."""
    a, b = close_at(bars, day - back_days), close_at(bars, day)
    return b / a - 1 if a and b else None
