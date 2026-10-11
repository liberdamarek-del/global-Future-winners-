"""USAspending.gov (vláda USA, zdarma, bez klíče): transakce federálních zakázek ≥ MIN_AMOUNT po měsících.

Používá se výpis TRANSAKCÍ (ne součtů zakázek): částka každé transakce je známá v den akce, takže nevzniká pohled do
budoucnosti (součet „Award Amount“ obsahuje i pozdější navýšení). Mod „0“ = nová zakázka, ostatní = úpravy/navýšení.
Ohleduplně: 1 dotaz za sekundu, stránkování jen do poklesu částky pod limit; hotové měsíce se nestahují znovu.
E-mail uživatele se sem NEPOSÍLÁ (není potřeba).
"""

import json
import time
import urllib.request
from datetime import date

from stockradar.timeutil import to_iso, utcnow

URL = "https://api.usaspending.gov/api/v2/search/spending_by_transaction/"
MIN_AMOUNT = 10_000_000
CONTRACTS = ["A", "B", "C", "D"]
FIELDS = ["Award ID", "Mod", "Recipient Name", "Action Date", "Transaction Amount", "Awarding Agency",
          "Transaction Description"]
SCHEMA = """
CREATE TABLE IF NOT EXISTS gov_tx (
    award_id    TEXT NOT NULL,
    mod         TEXT NOT NULL,
    recipient   TEXT NOT NULL,
    action_date TEXT NOT NULL,
    amount      REAL NOT NULL,
    agency      TEXT,
    description TEXT,
    PRIMARY KEY (award_id, mod, action_date, amount)
);
CREATE TABLE IF NOT EXISTS gov_tx_done (month TEXT PRIMARY KEY, n INTEGER NOT NULL, fetched_at TEXT NOT NULL);
-- cílené stažení pro menší firmy: transakce ≥ FIRM_MIN_AMOUNT přiřazené konkrétnímu symbolu (shoda začátku jména)
CREATE TABLE IF NOT EXISTS gov_tx_firm (
    symbol      TEXT NOT NULL,
    award_id    TEXT NOT NULL,
    mod         TEXT NOT NULL,
    recipient   TEXT NOT NULL,
    action_date TEXT NOT NULL,
    amount      REAL NOT NULL,
    agency      TEXT,
    description TEXT,
    PRIMARY KEY (symbol, award_id, mod, action_date, amount)
);
CREATE TABLE IF NOT EXISTS gov_firm_done (symbol TEXT PRIMARY KEY, query TEXT NOT NULL, n INTEGER NOT NULL, fetched_at TEXT NOT NULL);
"""
FIRM_MIN_AMOUNT = 1_000_000


def _post(payload: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "stockradar-research"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def month_bounds(y: int, m: int) -> tuple[str, str]:
    start = date(y, m, 1)
    end = date(y + (m == 12), m % 12 + 1, 1)
    return start.isoformat(), date.fromordinal(end.toordinal() - 1).isoformat()


def fetch_month(y: int, m: int, *, post=_post, pause: float = 1.0, min_amount: float = MIN_AMOUNT,
                max_pages: int = 40) -> list[tuple]:
    a, b = month_bounds(y, m)
    rows, page = [], 1
    while page <= max_pages:
        d = post({"filters": {"award_type_codes": CONTRACTS, "time_period": [{"start_date": a, "end_date": b}]},
                  "fields": FIELDS, "limit": 100, "page": page, "sort": "Transaction Amount", "order": "desc"})
        res = d.get("results") or []
        for r in res:
            amt = r.get("Transaction Amount") or 0
            if amt >= min_amount and r.get("Recipient Name") and r.get("Action Date"):
                rows.append((r.get("Award ID") or "?", str(r.get("Mod") or ""), r["Recipient Name"], r["Action Date"],
                             float(amt), r.get("Awarding Agency"), (r.get("Transaction Description") or "")[:200]))
        if pause:
            time.sleep(pause)
        if not res or not (d.get("page_metadata") or {}).get("hasNext") or (res[-1].get("Transaction Amount") or 0) < min_amount:
            break
        page += 1
    return rows


def download(cache_conn, start: date, end: date, *, post=_post, pause: float = 1.0, log=print) -> dict:
    cache_conn.executescript(SCHEMA)
    done = {r[0] for r in cache_conn.execute("SELECT month FROM gov_tx_done")}
    y, m = start.year, start.month
    fetched = total = 0
    while (y, m) <= (end.year, end.month):
        key = f"{y}-{m:02d}"
        current = (y, m) == (utcnow().year, utcnow().month)
        if key not in done or current:
            try:
                rows = fetch_month(y, m, post=post, pause=pause)
            except Exception as exc:                      # jeden měsíc nesmí shodit ostatní
                log(f"USAspending {key}: {str(exc)[:120]}")
            else:
                with cache_conn:
                    cache_conn.executemany("INSERT OR IGNORE INTO gov_tx VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
                    cache_conn.execute("INSERT OR REPLACE INTO gov_tx_done VALUES (?, ?, ?)", (key, len(rows), to_iso(utcnow())))
                fetched += 1
                total += len(rows)
                log(f"USAspending {key}: {len(rows)} transakcí ≥ {MIN_AMOUNT / 1e6:.0f} mil. USD")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return {"mesicu": fetched, "transakci": total}


def fetch_firm(query: str, accept, *, post=_post, pause: float = 1.0, start: str = "2021-01-01", end: str = "2026-09-30",
               max_pages: int = 5) -> list[tuple]:
    """Transakce ≥ FIRM_MIN_AMOUNT, jejichž příjemce odpovídá dotazu; `accept(recipient)` rozhodne o přesné shodě."""
    rows, page = [], 1
    while page <= max_pages:
        d = post({"filters": {"award_type_codes": CONTRACTS, "recipient_search_text": [query],
                              "time_period": [{"start_date": start, "end_date": end}]},
                  "fields": FIELDS, "limit": 100, "page": page, "sort": "Transaction Amount", "order": "desc"})
        res = d.get("results") or []
        for r in res:
            amt = r.get("Transaction Amount") or 0
            if amt >= FIRM_MIN_AMOUNT and r.get("Action Date") and accept(r.get("Recipient Name") or ""):
                rows.append((r.get("Award ID") or "?", str(r.get("Mod") or ""), r["Recipient Name"], r["Action Date"],
                             float(amt), r.get("Awarding Agency"), (r.get("Transaction Description") or "")[:200]))
        if pause:
            time.sleep(pause)
        if not res or not (d.get("page_metadata") or {}).get("hasNext") or (res[-1].get("Transaction Amount") or 0) < FIRM_MIN_AMOUNT:
            break
        page += 1
    return rows


def download_firms(cache_conn, firms: list[tuple[str, str, object]], *, post=_post, pause: float = 1.0, log=print) -> dict:
    """firms: [(symbol, dotaz, accept)] — hotové firmy se znovu nestahují."""
    cache_conn.executescript(SCHEMA)
    done = {r[0] for r in cache_conn.execute("SELECT symbol FROM gov_firm_done")}
    n_firms = n_rows = 0
    for i, (sym, query, accept) in enumerate(firms):
        if sym in done:
            continue
        try:
            rows = fetch_firm(query, accept, post=post, pause=pause)
        except Exception as exc:
            log(f"USAspending {sym}: {str(exc)[:100]}")
            continue
        with cache_conn:
            cache_conn.executemany("INSERT OR IGNORE INTO gov_tx_firm VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [(sym, *r) for r in rows])
            cache_conn.execute("INSERT OR REPLACE INTO gov_firm_done VALUES (?, ?, ?, ?)", (sym, query, len(rows), to_iso(utcnow())))
        n_firms += 1
        n_rows += len(rows)
        if i % 50 == 0:
            log(f"USAspending firmy: {i}/{len(firms)}, transakcí zatím {n_rows}")
    return {"firem": n_firms, "transakci": n_rows}
