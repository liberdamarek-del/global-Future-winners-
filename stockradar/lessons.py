"""§30 + §31: učební případy a poučení.

Případy z §31 se zakládají POUZE s informacemi uvedenými v MASTER PROMPTu. Ceny, data vstupů
a původní skóre těchto případů nejsou v projektu doložené, proto se NEZAKLÁDAJÍ jako predikce
v ledgeru (§29, §71: nikdy si nevymýšlej předchozí výsledky).
"""

import json
import sqlite3
from datetime import datetime

from stockradar.companies import add_company, add_listing, change_status, find_company
from stockradar.timeutil import to_iso, utcnow

SOURCE_31 = "MASTER PROMPT §31 (uživatel, 2026-10-02)"


def add_lesson(
    conn: sqlite3.Connection,
    case_key: str,
    *,
    title: str,
    outcome_type: str,
    summary: str,
    lessons: list[str],
    source: str,
    company_id: int | None = None,
    prediction_id: int | None = None,
    model_correction: str | None = None,
    now: datetime | None = None,
) -> int:
    if not lessons:
        raise ValueError("poučení musí obsahovat alespoň jeden bod")
    with conn:
        cur = conn.execute(
            "INSERT INTO lessons (case_key, company_id, prediction_id, title, outcome_type, summary,"
            " lessons_json, model_correction, source, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (case_key, company_id, prediction_id, title, outcome_type, summary,
             json.dumps(lessons, ensure_ascii=False), model_correction, source, to_iso(now or utcnow())),
        )
    return cur.lastrowid


# Identita firem je odvozena z tickerů uvedených v §31. Tržní data (cena, market cap, XTB) NEJSOU načtena.
NOTE_UNVERIFIED = "Identita odvozena z tickeru v §31. Cena, market cap, katalyzátory a XTB zatím neověřeny."
MASTER_PROMPT_CASES = [
    {
        "case_key": "CAPR", "title": "CAPR — velmi dobrý praktický zásah", "outcome_type": "HIT",
        "company": {"name": "Capricor Therapeutics", "country": "US", "sector": "Healthcare",
                    "industry": "Biotech"},
        "listing": ("CAPR", "NASDAQ", "USD"),
        "radar_status": "REFERENCE",
        "summary": "Velmi dobrý praktický zásah. Referenční případ PŘED katalyzátorem (§13).",
        "lessons": [
            "FDA/klinický katalyzátor může způsobit obrovský pohyb.",
            "Po katalyzátoru je situace úplně jiná.",
            "Pozdější vstup není totéž jako původní vstup.",
        ],
        "model_correction": "CAPR TEST (§13) pro každého kandidáta. CAPR samotný nebrat jako nový tip, "
                            "pokud je jeho katalyzátor za námi (§76).",
    },
    {
        "case_key": "NEBIUS", "title": "Nebius — dobrý zásah", "outcome_type": "HIT",
        "company": {"name": "Nebius Group", "country": "NL", "sector": "Technology",
                    "industry": "AI infrastructure"},
        "listing": ("NBIS", "NASDAQ", "USD"),
        "radar_status": "REFERENCE",
        "summary": "Dobrý zásah.",
        "lessons": [
            "AI infrastructure může generovat obrovský růst.",
            "Hledej nové firmy v celém AI infrastructure řetězci.",
        ],
        "model_correction": "NEBIUS TEST (§14) + analýza celého hodnotového řetězce AI (§25, §42).",
    },
    {
        "case_key": "UNITREE", "title": "Unitree Robotics — významná chyba screeningu", "outcome_type": "MISS",
        "company": {"name": "Unitree Robotics", "country": "CN", "sector": "Technology",
                    "industry": "Humanoid robotics", "listing_status": "UNKNOWN",
                    "notes": "Ticker, burza a stav listingu nejsou v projektu ověřeny — doplnit po ověření."},
        "listing": None,
        "radar_status": "REFERENCE",
        "summary": "Významná chyba screeningu.",
        "lessons": [
            "Sledovat humanoidní robotiku.",
            "Sledovat Čínu.",
            "Sledovat IPO.",
            "Sledovat nové sektory.",
            "Ale po extrémním IPO pohybu firmu automaticky nehonit.",
        ],
        "model_correction": "IPO / pre-IPO radar (§23, §40) a robotický řetězec (§43) jako stálá součást "
                            "screeningu, včetně asijských trhů.",
    },
    {
        "case_key": "MODERNA", "title": "Moderna — významná chyba screeningu", "outcome_type": "MISS",
        "company": {"name": "Moderna", "country": "US", "sector": "Healthcare", "industry": "mRNA platform"},
        "listing": ("MRNA", "NASDAQ", "USD"),
        "radar_status": "REFERENCE",
        "summary": "Významná chyba screeningu.",
        "lessons": [
            "Sledovat i velké firmy.",
            "Hledat „fundamental inflection“.",
            "Sledovat nové léčivé platformy.",
            "Nestačí soustředit se na microcap biotech.",
        ],
        "model_correction": "MODERNA TEST (§12) pro každého kandidáta; screening neomezovat velikostí firmy.",
    },
    {
        "case_key": "XSPRAY", "title": "XSPRAY — doporučeno bez ověření XTB", "outcome_type": "PROCESS_ERROR",
        "company": {"name": "Xspray Pharma", "country": "SE", "sector": "Healthcare", "industry": "Pharma"},
        "listing": ("XSPRAY", "NASDAQ_STOCKHOLM", "SEK"),
        "radar_status": "NEOVERENO",
        "summary": "Chyba: doporučeno bez správného ověření XTB dostupnosti.",
        "lessons": ["XTB kontrola musí být před doporučením."],
        "model_correction": "Vynuceno v kódu: spekulativní BUY / MAIN PICK nelze zapsat do ledgeru bez "
                            "XTB kontroly se stavem ANO, ne starší 30 dní (DB trigger predictions_xtb_gate).",
    },
    {
        "case_key": "RARE", "title": "RARE — katalyzátor příliš blízko / již probíhal",
        "outcome_type": "PROCESS_ERROR",
        "company": {"name": "Ultragenyx Pharmaceutical", "country": "US", "sector": "Healthcare",
                    "industry": "Rare disease biotech"},
        "listing": ("RARE", "NASDAQ", "USD"),
        "radar_status": "REFERENCE",
        "summary": "Chyba: katalyzátor byl příliš blízko / již probíhal.",
        "lessons": ["Vždy kontrolovat aktuální regulatorní stav."],
        "model_correction": "Vynuceno v kódu: spekulativní BUY nelze navázat na katalyzátor ve stavu "
                            "IN_PROGRESS / OCCURRED ani na katalyzátor s uplynulým datem.",
    },
    {
        "case_key": "BEAM", "title": "BEAM — zajímavý kandidát", "outcome_type": "WATCH",
        "company": {"name": "Beam Therapeutics", "country": "US", "sector": "Healthcare",
                    "industry": "Base editing"},
        "listing": ("BEAM", "NASDAQ", "USD"),
        "radar_status": "WATCH",
        "summary": "Zajímavý kandidát.",
        "lessons": [
            "Sledovat BEAM-302.",
            "Sledovat BEAM-101.",
            "Sledovat další klinická data.",
            "Sledovat cash runway.",
            "Sledovat regulatorní strategii.",
        ],
        "model_correction": None,
    },
    {
        "case_key": "TLX", "title": "TLX — zajímavý event-driven případ", "outcome_type": "WATCH",
        "company": {"name": "Telix Pharmaceuticals", "country": "AU", "sector": "Healthcare",
                    "industry": "Radiopharmaceuticals"},
        "listing": ("TLX", "ASX", "AUD"),
        "radar_status": "WATCH",
        "summary": "Zajímavý event-driven případ.",
        "lessons": ["Zajímavý event-driven případ — sledovat."],
        "model_correction": None,
    },
    {
        "case_key": "SLS", "title": "SLS — event-driven kandidát, méně přesný timing", "outcome_type": "WATCH",
        "company": {"name": "SELLAS Life Sciences Group", "country": "US", "sector": "Healthcare",
                    "industry": "Oncology biotech"},
        "listing": ("SLS", "NASDAQ", "USD"),
        "radar_status": "WATCH",
        "summary": "Zajímavý event-driven kandidát, ale timing může být méně přesný.",
        "lessons": ["Timing katalyzátoru může být méně přesný."],
        "model_correction": "Nejistý timing se zapisuje jako ESTIMATED/UNCERTAIN (okno), nikdy jako přesné "
                            "datum — vynuceno v DB (§10).",
    },
]


def seed_master_prompt_cases(conn: sqlite3.Connection, *, now: datetime | None = None) -> list[str]:
    """Založí případy z §31 (idempotentně). Vrací klíče nově založených případů."""
    now = now or utcnow()
    existing = {r["case_key"] for r in conn.execute("SELECT case_key FROM lessons")}
    created = []
    for case in MASTER_PROMPT_CASES:
        if case["case_key"] in existing:
            continue
        company = find_company(conn, case["company"]["name"])
        company_fields = {"notes": NOTE_UNVERIFIED, **case["company"]}
        company_id = company["id"] if company else add_company(conn, **company_fields, now=now)
        if case["listing"] and not company:
            ticker, exchange, currency = case["listing"]
            add_listing(conn, company_id, ticker, exchange, currency=currency, is_primary=True, now=now)
        change_status(conn, company_id, "radar_status", case["radar_status"],
                      reason=f"{SOURCE_31}: {case['summary']}", source=SOURCE_31, now=now)
        add_lesson(conn, case["case_key"], title=case["title"], outcome_type=case["outcome_type"],
                   summary=case["summary"], lessons=case["lessons"], source=SOURCE_31,
                   company_id=company_id, model_correction=case["model_correction"], now=now)
        created.append(case["case_key"])
    return created
