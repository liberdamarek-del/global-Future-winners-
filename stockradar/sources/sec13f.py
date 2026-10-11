"""SEC Form 13F Data Sets (zdarma, www.sec.gov) → zredukované pozice správců pro výzkum E4 („nejsilnější sázky“).

Z každého balíku (~90 MB) se uloží jen to, co protokol E4 potřebuje (docs/VYZKUM.md, stanoveno předem):
  * správci: původní 13F-HR (bez dodatků) podané do 45 dní po konci čtvrtletí, 20–500 akciových pozic (bez opcí),
    u více zpráv téhož správce za čtvrtletí jen poslední včas podaná,
  * f13_top: 20 největších pozic správce s vahou w = hodnota / součet hodnot správce,
  * f13_cons: součet vah a počet držitelů přes VŠECHNY takové správce → běžná váha W = sum_w / správců
    (nezávisí na jednotkách: SEC v roce 2023 změnila hodnoty z tisíců USD na USD).
CUSIP → symbol ze souborů SEC Fails-to-Deliver (CUSIP|SYMBOL|DESCRIPTION) — jméno se ukládá kvůli kontrole párování.
E-mail jen přes `contact.http_get` (každý dotaz evidován).
"""

import csv
import io
import re
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from stockradar import contact, config
from stockradar.timeutil import to_iso, utcnow

LIST_URL = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
FTD_LIST_URL = "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"
DIR = config.PROJECT_ROOT / "data" / "sec13f"
TOP, MIN_POS, MAX_POS, DEADLINE_DAYS = 20, 20, 500, 45
SCHEMA = """
CREATE TABLE IF NOT EXISTS f13_files (name TEXT PRIMARY KEY, managers INTEGER NOT NULL, fetched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS f13_mgr (
    accession TEXT PRIMARY KEY, cik INTEGER NOT NULL, period TEXT NOT NULL, filed TEXT NOT NULL, n_pos INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS f13_top (
    accession TEXT NOT NULL, rank INTEGER NOT NULL, cusip TEXT NOT NULL, name TEXT, w REAL NOT NULL,
    PRIMARY KEY (accession, rank));
CREATE TABLE IF NOT EXISTS f13_cons (
    period TEXT NOT NULL, cusip TEXT NOT NULL, sum_w REAL NOT NULL, holders INTEGER NOT NULL, PRIMARY KEY (period, cusip));
CREATE TABLE IF NOT EXISTS f13_period (period TEXT PRIMARY KEY, managers INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS cusip_map (cusip TEXT PRIMARY KEY, symbol TEXT NOT NULL, description TEXT, seen TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ftd_files_done (name TEXT PRIMARY KEY, rows INTEGER NOT NULL, fetched_at TEXT NOT NULL);
"""
_MONTHS = {m: i + 1 for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"))}


def sec_day(s: str) -> date | None:
    """'31-JUL-2025' → date."""
    try:
        d, m, y = s.strip().split("-")
        return date(int(y), _MONTHS[m.upper()], int(d))
    except (ValueError, KeyError):
        return None


def _tsv(z: zipfile.ZipFile, name: str):
    full = next(n for n in z.namelist() if n.rsplit("/", 1)[-1].upper() == name)
    with z.open(full) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"), delimiter="\t",
                                  quoting=csv.QUOTE_NONE)


def select_filings(subs: list[dict], covers: dict[str, dict]) -> dict[str, tuple[int, str, str]]:
    """accession → (cik, období, podáno) pro původní 13F-HR podané včas; u více zpráv správce za období jen poslední."""
    best: dict[tuple[int, str], tuple[str, str]] = {}
    for r in subs:
        if (r.get("SUBMISSIONTYPE") or "").strip() != "13F-HR":
            continue
        acc = r["ACCESSION_NUMBER"].strip()
        cov = covers.get(acc) or {}
        if (cov.get("ISAMENDMENT") or "").strip().upper() == "Y":
            continue
        if "HOLDINGS" not in (cov.get("REPORTTYPE") or "").upper() and "COMBINATION" not in (cov.get("REPORTTYPE") or "").upper():
            continue
        filed, period = sec_day(r.get("FILING_DATE") or ""), sec_day(r.get("PERIODOFREPORT") or "")
        if filed is None or period is None or filed > period + timedelta(days=DEADLINE_DAYS):
            continue
        key = (int(r["CIK"]), period.isoformat())
        if key not in best or filed.isoformat() > best[key][1]:
            best[key] = (acc, filed.isoformat())
    return {acc: (cik, period, filed) for (cik, period), (acc, filed) in best.items()}


def reduce_holdings(rows, chosen: dict[str, tuple[int, str, str]]) -> tuple[list, list, dict, dict]:
    """Řádky INFOTABLE → (správci, top pozice, konsenzus {(období, cusip): [sum_w, držitelů]}, správců za období)."""
    pos: dict[str, dict[str, list]] = {}
    for r in rows:
        acc = (r.get("ACCESSION_NUMBER") or "").strip()
        if acc not in chosen or (r.get("SSHPRNAMTTYPE") or "").strip().upper() != "SH" or (r.get("PUTCALL") or "").strip():
            continue
        try:
            v = float(r.get("VALUE") or 0)
        except ValueError:
            continue
        cusip = (r.get("CUSIP") or "").strip().upper()
        if v <= 0 or len(cusip) != 9:
            continue
        d = pos.setdefault(acc, {})
        cur = d.setdefault(cusip, [0.0, (r.get("NAMEOFISSUER") or "").strip()[:60]])
        cur[0] += v
    managers, top, cons, per_period = [], [], {}, {}
    for acc, d in pos.items():
        if not (MIN_POS <= len(d) <= MAX_POS):
            continue
        cik, period, filed = chosen[acc]
        total = sum(v for v, _ in d.values())
        managers.append((acc, cik, period, filed, len(d)))
        per_period[period] = per_period.get(period, 0) + 1
        ws = sorted(((v / total, c, n) for c, (v, n) in d.items()), reverse=True)
        for w, c, _ in ws:
            k = cons.setdefault((period, c), [0.0, 0])
            k[0] += w
            k[1] += 1
        top += [(acc, i, c, n, w) for i, (w, c, n) in enumerate(ws[:TOP])]
    return managers, top, cons, per_period


def store_reduced(cache_conn, name: str, managers, top, cons, per_period) -> None:
    with cache_conn:
        cache_conn.executemany("INSERT OR REPLACE INTO f13_mgr VALUES (?, ?, ?, ?, ?)", managers)
        cache_conn.executemany("INSERT OR REPLACE INTO f13_top VALUES (?, ?, ?, ?, ?)", top)
        cache_conn.executemany(
            "INSERT INTO f13_cons VALUES (?, ?, ?, ?) ON CONFLICT(period, cusip) DO UPDATE SET"
            " sum_w = sum_w + excluded.sum_w, holders = holders + excluded.holders",
            [(p, c, sw, h) for (p, c), (sw, h) in cons.items()])
        cache_conn.executemany(
            "INSERT INTO f13_period VALUES (?, ?) ON CONFLICT(period) DO UPDATE SET managers = managers + excluded.managers",
            list(per_period.items()))
        cache_conn.execute("INSERT OR REPLACE INTO f13_files VALUES (?, ?, ?)", (name, len(managers), to_iso(utcnow())))


def reduce_zip(cache_conn, path: Path) -> int:
    z = zipfile.ZipFile(path)
    covers = {r["ACCESSION_NUMBER"].strip(): r for r in _tsv(z, "COVERPAGE.TSV")}
    chosen = select_filings(list(_tsv(z, "SUBMISSION.TSV")), covers)
    managers, top, cons, per_period = reduce_holdings(_tsv(z, "INFOTABLE.TSV"), chosen)
    store_reduced(cache_conn, path.name, managers, top, cons, per_period)
    return len(managers)


def zip_links(html: str, first_year: int = 2021) -> list[str]:
    """Odkazy na balíky s podáními od `first_year` (staré názvy 2021q1…2023q4, nové 01jun2024-31aug2024)."""
    out = []
    for link in sorted(set(re.findall(r'href="([^"]*form13f[^"]*\.zip)"', html, re.I))):
        name = link.rsplit("/", 1)[-1].lower()
        m = re.match(r"(\d{4})q\d_form13f\.zip", name) or re.match(r"\d{2}[a-z]{3}(\d{4})-", name)
        if m and int(m.group(1)) >= first_year:
            out.append(link if link.startswith("http") else "https://www.sec.gov" + link)
    return out


def download(cache_conn, *, first_year: int = 2021, keep_zip: bool = False, log=print) -> dict:
    """Stáhne a zredukuje chybějící balíky (hotové se nestahují znovu); zip se po zredukování smaže."""
    cache_conn.executescript(SCHEMA)
    done = {r[0] for r in cache_conn.execute("SELECT name FROM f13_files")}
    html = contact.http_get(LIST_URL, "seznam datových sad 13F (výzkum E4)").decode("utf-8", "replace")
    DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for url in zip_links(html, first_year):
        name = url.rsplit("/", 1)[-1]
        if name in done:
            continue
        path = DIR / name
        if not path.exists():
            path.write_bytes(contact.http_get(url, "datové sady 13F (výzkum E4)", timeout=900))
        managers = reduce_zip(cache_conn, path)
        n += 1
        log(f"13F {name}: {managers} správců")
        if not keep_zip:
            path.unlink()
    return {"baliku": n}


def parse_ftd(text: str, day: str) -> list[tuple[str, str, str, str]]:
    out = []
    for line in text.splitlines()[1:]:
        parts = line.split("|")
        if len(parts) >= 5 and len(parts[1].strip()) == 9 and parts[2].strip():
            out.append((parts[1].strip().upper(), parts[2].strip().upper(), parts[4].strip()[:60], day))
    return out


def download_cusip_map(cache_conn, months: list[str], *, log=print) -> dict:
    """CUSIP → symbol z FTD souborů (první polovina měsíců `months`, např. ['202103', …]); novější soubor přepíše starší."""
    cache_conn.executescript(SCHEMA)
    done = {r[0] for r in cache_conn.execute("SELECT name FROM ftd_files_done")}
    html = contact.http_get(FTD_LIST_URL, "seznam souborů Fails-to-Deliver (výzkum E4)").decode("utf-8", "replace")
    links = {l.rsplit("/", 1)[-1].lower(): l for l in re.findall(r'href="([^"]*cnsfails[^"]*\.zip)"', html, re.I)}
    n = 0
    for ym in sorted(months):
        name = f"cnsfails{ym}a.zip"
        if name in done or name not in links:
            continue
        url = links[name] if links[name].startswith("http") else "https://www.sec.gov" + links[name]
        z = zipfile.ZipFile(io.BytesIO(contact.http_get(url, "Fails-to-Deliver (výzkum E4, CUSIP → symbol)", timeout=300)))
        text = z.read(z.namelist()[0]).decode("latin-1")
        rows = parse_ftd(text, f"{ym[:4]}-{ym[4:]}")
        with cache_conn:
            cache_conn.executemany("INSERT OR REPLACE INTO cusip_map VALUES (?, ?, ?, ?)", rows)
            cache_conn.execute("INSERT OR REPLACE INTO ftd_files_done VALUES (?, ?, ?)", (name, len(rows), to_iso(utcnow())))
        n += 1
        log(f"FTD {name}: {len(rows)} řádků")
    return {"souboru": n}


def main():
    from stockradar.discovery import cache as dcache
    cc = dcache.connect()
    months = [f"{y}{m:02d}" for y in range(2021, 2027) for m in (3, 6, 9, 12) if (y, m) <= (2026, 9)]
    print(download_cusip_map(cc, months), flush=True)
    print(download(cc), flush=True)


if __name__ == "__main__":
    main()
