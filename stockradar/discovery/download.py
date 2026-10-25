"""Hromadné stažení historie cen (Yahoo chart API, zdarma). Lze přerušit a znovu spustit — pokračuje kde skončilo.

python -m stockradar.discovery.download [--threads 3] [--rate 3] [--max-age-days 6]
"""

import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from stockradar.discovery import cache
from stockradar.sources import yahoo
from stockradar.timeutil import parse_iso, to_iso, utcnow


class RateLimiter:
    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second
        self.lock = threading.Lock()
        self.next_at = time.monotonic()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            delay = self.next_at - now
            self.next_at = max(now, self.next_at) + self.interval
        if delay > 0:
            time.sleep(delay)


def last_session_close(now):
    """Závěrka poslední UKONČENÉ seance v New Yorku (16:15 místního času, UTC). Během obchodování předchozí seance."""
    from stockradar.discovery.diary import session_day
    from stockradar.update import bar_close_time
    d = session_day(now) or session_day(now.replace(hour=0, minute=0, second=0, microsecond=0))
    return parse_iso(to_iso(bar_close_time(d.isoformat())))


def pending_symbols(conn, *, max_age_days: int, now) -> list[str]:
    """Symboly ke stažení: chybí, jsou starší než `max_age_days`, nebo byly staženy před závěrkou poslední seance.
    Poslední podmínka platí od 2026-10-25: týdenní běh na GitHubu stáhl jen 4 z 13 281 symbolů, protože obnovená cache
    ze zkušebního běhu 23. 10. byla „mladší než 6 dní“ — ceny pak končily 22. 10. a karty z 9. 10. se nevyhodnotily."""
    cutoff = to_iso(max(now - timedelta(days=max_age_days), last_session_close(now)))
    retry_errors = to_iso(now - timedelta(days=7))
    rows = conn.execute(
        "SELECT s.symbol FROM securities s LEFT JOIN series r ON r.symbol = s.symbol"
        " WHERE r.symbol IS NULL OR (r.error IS NULL AND r.fetched_at < ?) OR (r.error IS NOT NULL AND r.fetched_at < ?)"
        " ORDER BY s.symbol", (cutoff, retry_errors)).fetchall()
    return [r[0] for r in rows]


def run(*, threads: int = 3, rate: float = 3.0, max_age_days: int = 6, range_: str = "5y", limit: int | None = None,
        log=print, fetch=None) -> dict:
    conn = cache.connect()
    now = utcnow()
    todo = pending_symbols(conn, max_age_days=max_age_days, now=now)[:limit]
    limiter = RateLimiter(rate)
    fetch = fetch or (lambda s: yahoo.fetch_chart(s, range_, retries=3))
    ok = err = 0
    started = time.monotonic()
    log(f"Ke stažení: {len(todo)} symbolů ({threads} vlákna, {rate}/s)")

    def task(sym):
        limiter.wait()
        try:
            return sym, fetch(sym), None
        except Exception as exc:  # síť / neznámý symbol — zapíše se jako chyba
            return sym, None, exc

    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = [pool.submit(task, s) for s in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            stamp = to_iso(utcnow())
            sym, quote, exc = fut.result()
            if exc is None and len(quote.bars) < 5:
                exc = ValueError("málo dat")
            if exc is None:
                cache.store_series(conn, sym, quote.currency, quote.bars, source=yahoo.SOURCE, fetched_at=stamp)
                ok += 1
            else:
                cache.store_error(conn, sym, str(exc), fetched_at=stamp)
                err += 1
            if i % 250 == 0 or i == len(todo):
                rate_now = i / max(time.monotonic() - started, 1e-6)
                log(f"{i}/{len(todo)} hotovo, OK {ok}, chyb {err}, {rate_now:.2f}/s")
    return {"requested": len(todo), "ok": ok, "errors": err}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--rate", type=float, default=3.0)
    ap.add_argument("--max-age-days", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    print(run(threads=a.threads, rate=a.rate, max_age_days=a.max_age_days, limit=a.limit,
              log=lambda m: print(f"[{to_iso(utcnow())}] {m}", flush=True)))


if __name__ == "__main__":
    main()
