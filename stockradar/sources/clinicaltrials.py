"""ClinicalTrials.gov API v2 — klinické studie fáze 2/3 sponzorované firmami (zdarma, bez klíče, bez e-mailu).

Primary completion date (PCD) = kdy studie posbírá data pro hlavní cíl; výsledky (topline) firmy obvykle oznamují
0–3 měsíce po PCD. Odhadované PCD (ESTIMATED) je proto okno katalyzátoru, nikdy přesné datum (§10).
Sponzor se páruje s kotovanou firmou podle normalizovaného jména (ct_sponsor_map, metoda párování je uložená).
"""

import json
import re
import time
import urllib.parse
import urllib.request

from stockradar.timeutil import to_iso, utcnow

API = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = ("NCTId,LeadSponsorName,Phase,PrimaryCompletionDate,PrimaryCompletionDateType,OverallStatus,BriefTitle,"
          "Condition,EnrollmentCount,ResultsFirstPostDate,LastUpdatePostDate")
QUERY = ("AREA[LeadSponsorClass]INDUSTRY AND (AREA[Phase]PHASE3 OR AREA[Phase]PHASE2) "
         "AND AREA[PrimaryCompletionDate]RANGE[{start},{end}]")
STUDY_URL = "https://clinicaltrials.gov/study/{nct}"


def _get(params: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(f"{API}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def parse_study(s: dict) -> dict:
    p = s.get("protocolSection", {})
    ident, status = p.get("identificationModule", {}), p.get("statusModule", {})
    pcd = status.get("primaryCompletionDateStruct", {})
    return {
        "nct": ident.get("nctId"), "title": ident.get("briefTitle"),
        "sponsor": p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name") or "",
        "phase": "/".join(p.get("designModule", {}).get("phases", []) or []),
        "pcd": pcd.get("date"), "pcd_type": pcd.get("type"),
        "status": status.get("overallStatus"),
        "conditions": "; ".join(p.get("conditionsModule", {}).get("conditions", []) or [])[:300],
        "enrollment": (p.get("designModule", {}).get("enrollmentInfo") or {}).get("count"),
        "results_posted": (status.get("resultsFirstPostDateStruct") or {}).get("date"),
        "last_update": (status.get("lastUpdatePostDateStruct") or {}).get("date"),
    }


def fetch_studies(cache_conn, *, start: str = "2021-01-01", end: str = "2028-12-31", get=_get, pause: float = 0.5,
                  log=print) -> int:
    params = {"filter.advanced": QUERY.format(start=start, end=end), "fields": FIELDS, "pageSize": "1000"}
    total, token = 0, None
    now = to_iso(utcnow())
    while True:
        page = get(dict(params, **({"pageToken": token} if token else {})))
        rows = [parse_study(s) for s in page.get("studies", [])]
        with cache_conn:
            cache_conn.executemany(
                "INSERT OR REPLACE INTO ct_studies (nct, sponsor, phase, pcd, pcd_type, status, title, conditions,"
                " enrollment, results_posted, last_update, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(r["nct"], r["sponsor"], r["phase"], r["pcd"], r["pcd_type"], r["status"], r["title"], r["conditions"],
                  r["enrollment"], r["results_posted"], r["last_update"], now) for r in rows if r["nct"]])
        total += len(rows)
        token = page.get("nextPageToken")
        if not token:
            break
        if pause:
            time.sleep(pause)
    log(f"ClinicalTrials.gov: {total} studií fáze 2/3")
    return total


SUFFIX = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|ag|sa|se|nv|bv|spa|s\.?a|"
                    r"gmbh|kk|k\.k|holdings?|group|the|class [a-c]|common stock|ordinary shares|"
                    r"american depositary shares?|ads|adr)\b\.?", re.I)


def norm_name(name: str | None) -> str:
    n = (name or "").lower().replace("&", " and ")
    n = re.sub(r"\(.*?\)", " ", n)
    n = SUFFIX.sub(" ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


# Dceřiné společnosti a jiná jména sponzorů → kotovaná mateřská firma (ověřené vlastnictví)
ALIASES = {
    "merck sharp and dohme": "MRK", "glaxosmithkline": "GSK", "janssen research and development": "JNJ",
    "janssen pharmaceutical k": "JNJ", "alexion pharmaceuticals": "AZN", "celgene": "BMY", "modernatx": "MRNA",
    "sanofi pasteur a sanofi": "SNY", "genentech": "ROG.SW", "hoffmann la roche": "ROG.SW",
    "astrazeneca": "AZN", "novartis pharmaceuticals": "NVS", "bristol myers squibb": "BMY",
    "telix pharmaceuticals pty": "TLX", "beigene": "ONC", "regeneron pharmaceuticals": "REGN",
}

GENERIC = re.compile(r"\b(pharmaceuticals?|pharma|therapeutics|biosciences?|biotherapeutics|biotech|bio)\b")


def _short(key: str) -> str:
    return re.sub(r"\s+", " ", GENERIC.sub(" ", key)).strip()


def build_sponsor_map(cache_conn) -> dict:
    """Páruje sponzory studií s kotovanými firmami: přesná shoda normalizovaného jména, jinak shoda bez obecných
    slov (pharma, therapeutics …), jen když je jednoznačná."""
    names: dict[str, list[str]] = {}
    for r in cache_conn.execute("SELECT symbol, name FROM securities WHERE name IS NOT NULL"):
        key = norm_name(r["name"])
        if len(key) >= 4:
            names.setdefault(key, []).append(r["symbol"])
    # u dvojího listingu (např. ADR + domácí burza) má přednost americký (bez přípony)
    pick = {k: sorted(v, key=lambda s: ("." in s, len(s)))[0] for k, v in names.items()}
    by_short: dict[str, set[str]] = {}
    for k, sym in pick.items():
        sk = _short(k)
        if len(sk) >= 5:
            by_short.setdefault(sk, set()).add(sym)
    matched = 0
    sponsors = [r[0] for r in cache_conn.execute("SELECT DISTINCT sponsor FROM ct_studies")]
    with cache_conn:
        for sp in sponsors:
            key = norm_name(sp)
            sym, method = pick.get(key), "přesná shoda jména"
            if sym is None and key in ALIASES:
                sym, method = ALIASES[key], "ruční alias (dceřiná firma)"
            if sym is None:
                cands = by_short.get(_short(key), set())
                sym, method = (next(iter(cands)), "shoda bez obecných slov") if len(cands) == 1 else (None, "nenalezeno")
            cache_conn.execute("INSERT OR REPLACE INTO ct_sponsor_map (sponsor, symbol, method) VALUES (?, ?, ?)",
                               (sp, sym, method))
            matched += sym is not None
    return {"sponzoru": len(sponsors), "sparovano": matched}


def refresh(cache_conn, *, log=print) -> dict:
    n = fetch_studies(cache_conn, log=log)
    return {"studii": n, **build_sponsor_map(cache_conn), "stav": "DONE"}
