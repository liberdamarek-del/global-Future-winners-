"""SEC EDGAR — fundamenty a filingy amerických firem zdarma (vyžaduje e-mail v hlavičce, viz contact.py).

Co se stahuje (vše hromadně, aby bylo dotazů málo — každý se eviduje v email_usage):
  * company_tickers.json             ticker → CIK (1 dotaz)
  * XBRL frames                      jedna hodnota za firmu a kvartál pro celý trh (1 dotaz = 1 ukazatel × 1 kvartál)
                                     tržby, čistý zisk, počet akcií, hotovost
  * full-index master.gz             seznam všech filingů za kvartál s PŘESNÝM datem podání (1 dotaz = 1 kvartál)
                                     8-K, 10-Q/10-K, emise (S-1/S-3/424B), aktivisté (13D)

Bez look-ahead: hodnota kvartálu se smí použít až od data podání 10-Q/10-K (sec_filings), viz fundamentals.py.
"""

import json
from datetime import date

from stockradar import contact
from stockradar.timeutil import to_iso, utcnow

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FRAME_URL = "https://data.sec.gov/api/xbrl/frames/{tax}/{tag}/{unit}/{period}.json"
INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/master.gz"

# (náš ukazatel, taxonomie, XBRL tag, jednotka, okamžik?) — u tržeb se bere první dostupný tag v tomto pořadí
FRAMES = [
    ("revenue", "us-gaap", "Revenues", "USD", False),
    ("revenue", "us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD", False),
    ("revenue", "us-gaap", "SalesRevenueNet", "USD", False),
    ("net_income", "us-gaap", "NetIncomeLoss", "USD", False),
    ("shares", "dei", "EntityCommonStockSharesOutstanding", "shares", True),
    ("cash", "us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD", True),
]

# Formuláře, které se ukládají z indexu (ostatní, např. Form 4 nebo 424B2 strukturované dluhopisy bank, ne)
FORMS = {
    "8-K": "8K", "10-Q": "REPORT", "10-K": "REPORT", "20-F": "REPORT", "40-F": "REPORT",
    "S-1": "OFFER", "S-3": "OFFER", "F-1": "OFFER", "F-3": "OFFER",
    "424B1": "OFFER", "424B3": "OFFER", "424B4": "OFFER", "424B5": "OFFER",
    "SC 13D": "13D", "SCHEDULE 13D": "13D", "SC 13D/A": "13DA", "SCHEDULE 13D/A": "13DA",
    "SC 13G": "13G", "SCHEDULE 13G": "13G",
}
# Roční ukazatele (celý fiskální rok z 10-K; čtvrtletní hodnoty jsou v 10-Q kumulativní, proto roční)
ANNUAL_FRAMES = [
    ("buyback", "us-gaap", "PaymentsForRepurchaseOfCommonStock", "USD"),
]


def quarters(start: date, end: date) -> list[tuple[int, int]]:
    out, y, q = [], start.year, (start.month - 1) // 3 + 1
    while (y, q) <= (end.year, (end.month - 1) // 3 + 1):
        out.append((y, q))
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


def fetch_tickers(cache_conn) -> int:
    data = json.loads(contact.http_get(TICKERS_URL, "seznam tickerů a CIK (company_tickers.json)"))
    now = to_iso(utcnow())
    with cache_conn:
        for row in data.values():
            cache_conn.execute("INSERT OR REPLACE INTO sec_tickers (ticker, cik, title, fetched_at) VALUES (?, ?, ?, ?)",
                               (row["ticker"].upper().replace(".", "-"), int(row["cik_str"]), row["title"], now))
    return len(data)


def parse_frame(payload: dict) -> list[tuple[int, str, float]]:
    return [(int(r["cik"]), r["end"], float(r["val"])) for r in payload.get("data", []) if r.get("val") is not None]


def fetch_frames(cache_conn, *, start: date, end: date, refresh_recent: int = 3, log=print) -> dict:
    """Stáhne chybějící kvartály (a vždy posledních `refresh_recent`, kam přibývají nová podání)."""
    qs = quarters(start, end)
    recent = set(qs[-refresh_recent:])
    done = {(r[0], r[1]) for r in cache_conn.execute("SELECT tag, period FROM sec_frames_done")}
    fetched = errors = 0
    for concept, tax, tag, unit, instant in FRAMES:
        for y, q in qs:
            period = f"CY{y}Q{q}" + ("I" if instant else "")
            if (tag, period) in done and (y, q) not in recent:
                continue
            url = FRAME_URL.format(tax=tax, tag=tag, unit=unit, period=period)
            try:
                rows = parse_frame(json.loads(contact.http_get(url, f"fundamenty: {concept} (XBRL frames)")))
            except Exception as exc:  # 404 = pro tento tag a kvartál data nejsou
                if "404" not in str(exc):
                    errors += 1
                    log(f"SEC {tag} {period}: {exc}")
                elif (y, q) not in recent:
                    # starý kvartál bez dat už data nedostane → zapsat jako hotové, ať se e-mail neposílá znovu
                    with cache_conn:
                        cache_conn.execute("INSERT OR REPLACE INTO sec_frames_done (tag, period, n, fetched_at)"
                                           " VALUES (?, ?, 0, ?)", (tag, period, to_iso(utcnow())))
                continue
            with cache_conn:
                for cik, end_day, val in rows:
                    # první tag v pořadí FRAMES má přednost — pozdější tagy jen doplní chybějící firmy
                    cache_conn.execute(
                        "INSERT INTO sec_facts (cik, concept, period, end_day, val, source) VALUES (?, ?, ?, ?, ?, ?)"
                        " ON CONFLICT(cik, concept, period) DO UPDATE SET end_day = excluded.end_day, val = excluded.val"
                        " WHERE sec_facts.source = excluded.source",
                        (cik, concept, period.rstrip("I"), end_day, val, tag))
                cache_conn.execute("INSERT OR REPLACE INTO sec_frames_done (tag, period, n, fetched_at) VALUES (?, ?, ?, ?)",
                                   (tag, period, len(rows), to_iso(utcnow())))
            fetched += 1
    return {"dotazu": fetched, "chyb": errors}


def fetch_annual(cache_conn, *, start_year: int = 2020, end_year: int | None = None, log=print) -> dict:
    """Roční fakta (např. skutečně vyplacené zpětné odkupy akcií z výkazu peněžních toků)."""
    end_year = end_year or utcnow().year - 1
    done = {(r[0], r[1]) for r in cache_conn.execute("SELECT tag, period FROM sec_frames_done")}
    fetched = 0
    for concept, tax, tag, unit in ANNUAL_FRAMES:
        for y in range(start_year, end_year + 1):
            period = f"CY{y}"
            if (tag, period) in done and y < end_year:
                continue
            try:
                rows = parse_frame(json.loads(contact.http_get(FRAME_URL.format(tax=tax, tag=tag, unit=unit, period=period),
                                                               f"fundamenty: {concept} (XBRL frames, roční)")))
            except Exception as exc:
                log(f"SEC {tag} {period}: {str(exc)[:80]}")
                continue
            with cache_conn:
                cache_conn.executemany(
                    "INSERT OR REPLACE INTO sec_facts (cik, concept, period, end_day, val, source) VALUES (?, ?, ?, ?, ?, ?)",
                    [(cik, concept, period, end_day, val, tag) for cik, end_day, val in rows])
                cache_conn.execute("INSERT OR REPLACE INTO sec_frames_done (tag, period, n, fetched_at) VALUES (?, ?, ?, ?)",
                                   (tag, period, len(rows), to_iso(utcnow())))
            fetched += 1
    return {"dotazu": fetched}


def parse_master(text: str) -> list[tuple[str, int, str, str]]:
    out = []
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) != 5 or not parts[0].isdigit():
            continue
        cik, _name, form, filed, path = parts
        if form in FORMS:
            out.append((path, int(cik), form, filed))
    return out


def fetch_index(cache_conn, *, start: date, end: date, refresh_recent: int = 1, log=print) -> dict:
    qs = quarters(start, end)
    recent = set(qs[-refresh_recent:])
    done = {r[0] for r in cache_conn.execute("SELECT quarter FROM sec_index_done")}
    fetched = rows_total = 0
    for y, q in qs:
        key = f"{y}Q{q}"
        if key in done and (y, q) not in recent:
            continue
        try:
            raw = contact.http_get(INDEX_URL.format(year=y, q=q), "seznam filingů s datem podání (full-index)")
        except Exception as exc:
            log(f"SEC index {key}: {exc}")
            continue
        rows = parse_master(raw.decode("latin-1"))
        with cache_conn:
            cache_conn.executemany("INSERT OR IGNORE INTO sec_filings (path, cik, form, filed) VALUES (?, ?, ?, ?)", rows)
            cache_conn.execute("INSERT OR REPLACE INTO sec_index_done (quarter, n, fetched_at) VALUES (?, ?, ?)",
                               (key, len(rows), to_iso(utcnow())))
        fetched += 1
        rows_total += len(rows)
    return {"dotazu": fetched, "filingu": rows_total}


def refresh(cache_conn, *, start: date = date(2021, 1, 1), end: date | None = None, log=print) -> dict:
    """Celá obnova SEC dat. Bez nastaveného e-mailu vrátí stav VYPNUTO a nic neodešle."""
    if contact.email() is None:
        return {"stav": "VYPNUTO — e-mail není nastaven"}
    end = end or utcnow().date()
    out = {"tickeru": fetch_tickers(cache_conn)}
    out["frames"] = fetch_frames(cache_conn, start=start, end=end, log=log)
    out["index"] = fetch_index(cache_conn, start=start, end=end, log=log)
    out["rocni"] = fetch_annual(cache_conn, log=log)
    out["stav"] = "DONE"
    return out
