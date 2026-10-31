"""Ceny komodit z Yahoo (futures, nejbližší kontrakt; zdarma) → cache `series`; týdenní řady pro kauzální testy.

Pozor: řada nejbližšího kontraktu má skoky při přechodu na další kontrakt (roll). U většiny komodit malý šum, ale u
prasat, oceli a železné rudy skok 3–12 % (2026-10) — živé karty radaru ho u nich odečítají (`ret_ex_roll`, v0.17.6);
týdenní řady pro zamčený test řetězců se nemění.
"""

import bisect
import time
from datetime import date, timedelta

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


# ---------------------------------------------------------------- přechod na další kontrakt (roll)
# Jen komodity s ověřeným pravidlem konce obchodování a velkým skokem při přechodu (poučení #26, 2026-10-28/29:
# prasata −11,9 % 15. 10., ocel +3,2 % 30. 9. a +4,0 % 28. 10., železná ruda −4,6 % 1. 10.). Svátky se neberou
# v úvahu — proto se skok hledá na prvním i druhém obchodním dni po konci kontraktu.

def _weekdays(y: int, m: int) -> list[date]:
    d, out = date(y, m, 1), []
    while d.month == m:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _hogs_last(y: int, m: int) -> date | None:
    return _weekdays(y, m)[9] if m in (2, 4, 5, 6, 7, 8, 10, 12) else None


def _steel_last(y: int, m: int) -> date:
    last_wed = max(d for d in _weekdays(y, m) if d.weekday() == 2)
    return last_wed - timedelta(days=3 if last_wed.weekday() == 0 else 1)


def _iron_last(y: int, m: int) -> date:
    return _weekdays(y, m)[-1]


ROLL_RULES = {
    "HOGS": (_hogs_last, "CME kap. 152: konec obchodování 10. pracovní den měsíce kontraktu (únor, duben–srpen, říjen, prosinec)"),
    "STEEL": (_steel_last, "CME (COMEX) kap. 920: konec obchodování pracovní den před poslední středou měsíce"),
    "IRONORE": (_iron_last, "CME kap. 919: konec obchodování poslední (singapurský) pracovní den měsíce"),
}


def roll_jumps(bars, cid: str, start: int, end: int) -> list[dict]:
    """Skoky řady nejbližšího kontraktu při přechodu v (start, end]: na prvním nebo druhém obchodním dni po konci
    kontraktu podle pravidla burzy se vezme větší denní změna. Prázdné pro komodity bez ověřeného pravidla."""
    rule = ROLL_RULES.get(cid)
    if rule is None:
        return []
    out = []
    first = date.fromordinal(start)
    y, m = first.year, first.month
    while date(y, m, 1).toordinal() <= end:
        last = rule[0](y, m)
        if last is not None:
            i = bisect.bisect_right(bars.days, last.toordinal())        # první obchodní den po konci kontraktu
            cand = [(bars.days[k], bars.closes[k] / bars.closes[k - 1] - 1) for k in (i, i + 1)
                    if 0 < k < len(bars.days) and bars.closes[k - 1] > 0 and start < bars.days[k] <= end]
            if cand:
                d, r = max(cand, key=lambda x: abs(x[1]))
                out.append({"den": date.fromordinal(d).isoformat(), "skok": round(r, 4), "_den": d})
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def ret_ex_roll(bars, cid: str, day: int, back_days: int) -> float | None:
    """Výnos za `back_days` dní bez skoků při přechodu kontraktu (pro komodity bez pravidla totéž co `ret`)."""
    r = ret(bars, day, back_days)
    if r is None:
        return None
    for j in roll_jumps(bars, cid, day - back_days, day):
        r = (1 + r) / (1 + j["skok"]) - 1
    return r
