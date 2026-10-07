"""Registr modulů a zdrojů + deník běhů: paměť toho, co systém udělal, proč, s jakým výsledkem a co je ověřené.

Stavy (rozhodnutí uživatele 2026-10-07):
  HOTOVO/OVĚŘENO  běží včas a aspoň jedna jeho role je ověřená mimo vzorek
  NEOVĚŘENO       běží včas, ale výhoda zatím není prokázaná (výstup je jen informace)
  ROZPRACOVÁNO    ještě neběžel / čeká na první výsledky
  BLOKOVÁNO       zdroj nedostupný nebo chybí předpoklad (e-mail, data)
  CHYBA           poslední běh selhal, výstup je zastaralý, nebo role je horší než náhoda
"""

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone

from stockradar import __version__
from stockradar.causal.commodities import COMMODITIES
from stockradar.timeutil import parse_iso, to_iso, utcnow

SLACK_DAYS = 3                     # víkend + svátek
MODULES = (
    {"id": "ceny", "nazev": "Ceny akcií a seznam firem (Yahoo, Nasdaq, ASX, JPX)", "prikaz": "discover --universe --download",
     "kadence": 7, "vstupy": ()},
    {"id": "energie", "nazev": "Energetický radar (AI → elektřina → jádro)", "prikaz": "update", "kadence": 1,
     "tabulka": ("model_runs", "run_at"), "vstupy": (), "role": ("ENERGIE:vyber",)},
    {"id": "objevovani", "nazev": "Objevování vítězů + model raket 6 m", "prikaz": "discover", "kadence": 7,
     "tabulka": ("discovery_runs", "run_at"), "vstupy": ("ceny", "xtb"), "role": ("RAKETY_6M:vyber",)},
    {"id": "smart_money", "nazev": "Smart money (insideři, politici, 13D/G, buybacky)", "prikaz": "smart-money", "kadence": 7,
     "tabulka": ("smart_money_runs", "run_at"), "vstupy": ("ceny",), "role": ("SMART_MONEY:nakup",)},
    {"id": "kauzalni", "nazev": "Kauzální radar (událost → komodita → obor → firmy)", "prikaz": "causal", "kadence": 1,
     "tabulka": ("causal_runs", "run_at"), "vstupy": ("ceny",), "role": ("KAUZALNI:prilezitost",)},
    {"id": "signaly", "nazev": "Signály 14 dní / 1 měsíc / 6 měsíců", "prikaz": "signals", "kadence": 7,
     "tabulka": ("signal_runs", "run_at"), "vstupy": ("ceny", "smart_money", "kauzalni", "xtb"),
     "role": tuple(f"{m}:{k}" for m in ("SIGNAL_14D", "SIGNAL_1M", "SIGNAL_6M") for k in ("vyber", "varovani", "pokles"))},
    {"id": "xtb", "nazev": "Nabídka brokera XTB (xtb.com)", "prikaz": "signals / discover / causal", "kadence": 30, "vstupy": ()},
    {"id": "vyzkum", "nazev": "Ruční výzkum se zdroji", "prikaz": "research", "kadence": None,
     "tabulka": ("research_evidence", "recorded_at"), "vstupy": (), "role": ("VYZKUM",)},
    {"id": "zpetna_vazba", "nazev": "Vyhodnocení predikcí (3 knihy)", "prikaz": "update / signals / causal", "kadence": None,
     "vstupy": ("energie", "signaly", "kauzalni")},
    {"id": "centrum", "nazev": "Centrum důkazů a integrace", "prikaz": "hub (i automaticky po hlavních příkazech)", "kadence": 1,
     "tabulka": ("hub_runs", "run_at"), "vstupy": ("energie", "objevovani", "smart_money", "kauzalni", "signaly", "vyzkum")},
)
COMMAND_MODULE = {"update": "energie", "discover": "objevovani", "smart-money": "smart_money", "causal": "kauzalni",
                  "signals": "signaly", "hub": "centrum", "research": "vyzkum"}


# ---------------------------------------------------------------- deník

def record_run(conn, command: str, args: dict, started: datetime, status: str, summary: dict | None = None,
               error: str | None = None, finished: datetime | None = None) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO system_runs (command, args_json, started_at, finished_at, status, summary_json, error, app_version)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (command, json.dumps(args, ensure_ascii=False, sort_keys=True, default=str), to_iso(started),
             to_iso(finished or utcnow()), status, json.dumps(summary or {}, ensure_ascii=False, default=str),
             (error or None) and error[:500], __version__))
    return cur.lastrowid


def journal(conn, limit: int = 15) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM system_runs ORDER BY id DESC LIMIT ?", (limit,)):
        out.append({"id": r["id"], "prikaz": r["command"], "zacatek": r["started_at"], "konec": r["finished_at"],
                    "trvani_s": round((parse_iso(r["finished_at"]) - parse_iso(r["started_at"])).total_seconds()),
                    "stav": r["status"], "souhrn": json.loads(r["summary_json"]), "chyba": r["error"]})
    return out


def _last_journal(conn) -> dict[str, dict]:
    out = {}
    for r in conn.execute("SELECT command, status, finished_at, error FROM system_runs ORDER BY id"):
        out[r["command"]] = dict(r)
    return out


# ---------------------------------------------------------------- čerstvost dat

def _one(conn, sql: str, params=()):
    """První řádek dotazu do cache; tabulky některých zdrojů vznikají až při prvním stažení → chybějící = None."""
    if conn is None:
        return None
    try:
        return conn.execute(sql, params).fetchone()
    except sqlite3.OperationalError:
        return None


def stock_data_end(cache_conn) -> str | None:
    """Poslední den cen akcií (stejně jako data modelů: jen firmy ze seznamu, aspoň rok historie)."""
    r = _one(cache_conn, "SELECT MAX(s.last_day) FROM series s JOIN securities m ON m.symbol = s.symbol WHERE s.n >= 250")
    return r[0] if r else None


def signals_unchanged(conn, cache_conn, models) -> str | None:
    """Důvod, proč signály NEPOČÍTAT znovu (stejná data, stejná verze, žádný nový vstup), jinak None."""
    end = stock_data_end(cache_conn)
    if end is None:
        return None
    sm_last = conn.execute("SELECT MAX(run_at) FROM smart_money_runs").fetchone()[0] or ""
    for m in models:
        r = conn.execute("SELECT run_at, data_through, app_version FROM signal_runs WHERE model_name = ? ORDER BY id DESC LIMIT 1",
                         (m,)).fetchone()
        if r is None or r["data_through"] != end or r["app_version"] != __version__ or sm_last > r["run_at"]:
            return None
    return f"ceny akcií se od posledního běhu nezměnily (data do {end}), verze {__version__} a vstupy stejné"


def _age(iso: str | None, now: datetime) -> float | None:
    """Stáří ve dnech; přijme čas ISO (UTC) i samotné datum."""
    if not iso:
        return None
    try:
        t = parse_iso(iso)
    except ValueError:
        try:
            t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            return None
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    return (now - t).total_seconds() / 86400


def _last_output(conn, cache_conn, m: dict) -> str | None:
    if m["id"] == "ceny":
        r = _one(cache_conn, "SELECT MAX(s.fetched_at) FROM series s JOIN securities m ON m.symbol = s.symbol")
        return r[0] if r else None
    if m["id"] == "xtb":
        r = _one(cache_conn, "SELECT MAX(checked_at) FROM xtb_offer")
        return r[0] if r else None
    if "tabulka" in m:
        table, col = m["tabulka"]
        return conn.execute(f"SELECT MAX({col}) FROM {table}").fetchone()[0]
    return None


def feedback_status(conn, now: datetime) -> dict:
    """Kolik predikcí už je vyhodnoceno ve všech třech knihách a kdy přijde další vyhodnocení."""
    done = {"ledger": conn.execute("SELECT COUNT(DISTINCT prediction_id) FROM prediction_outcomes").fetchone()[0],
            "signaly": conn.execute("SELECT COUNT(*) FROM signal_outcomes").fetchone()[0],
            "kauzalni": conn.execute("SELECT COUNT(*) FROM causal_outcomes").fetchone()[0]}
    due = []
    for d, h in conn.execute("SELECT f.price_date, f.horizon_days FROM signal_forecasts f LEFT JOIN signal_outcomes o"
                             " ON o.forecast_id = f.id WHERE o.forecast_id IS NULL"):
        due.append(date.fromisoformat(d) + timedelta(days=h * 7 // 5 + 1))       # obchodní dny → kalendářní
    for d, h in conn.execute("SELECT f.price_date, f.horizon_days FROM causal_forecasts f LEFT JOIN causal_outcomes o"
                             " ON o.forecast_id = f.id WHERE o.forecast_id IS NULL"):
        due.append(date.fromisoformat(d) + timedelta(days=h))
    for (made,) in conn.execute("SELECT p.made_at FROM predictions p WHERE p.mode = 'LIVE' AND NOT EXISTS"
                                " (SELECT 1 FROM prediction_outcomes o WHERE o.prediction_id = p.id)"):
        due.append(parse_iso(made).date() + timedelta(days=7))
    nxt = min(due).isoformat() if due else None
    total = sum(done.values())
    return {"vyhodnoceno": done, "ceka": len(due), "dalsi": nxt,
            "stav": "HOTOVO" if total else "ROZPRACOVÁNO",
            "duvod": (f"vyhodnoceno: ledger {done['ledger']}, signální karty {done['signaly']}, kauzální {done['kauzalni']}; "
                      f"čeká {len(due)}" if total else
                      f"zatím nic vyhodnoceno (čeká {len(due)} predikcí); první vyhodnocení {nxt or '–'}")}


def modules_status(conn, cache_conn, reliability: dict, now: datetime | None = None) -> list[dict]:
    now = now or utcnow()
    last_j = _last_journal(conn)
    by_cmd = {v: k for k, v in COMMAND_MODULE.items()}
    out, state = [], {}
    for m in MODULES:
        if m["id"] == "zpetna_vazba":
            fb = feedback_status(conn, now)
            row = {"stav": fb["stav"], "duvod": fb["duvod"], "posledni": None}
        else:
            last = _last_output(conn, cache_conn, m)
            j = last_j.get(by_cmd.get(m["id"], ""))
            age = _age(last, now)
            roles = [reliability[r] for r in m.get("role", ()) if r in reliability]
            if j and j["status"] == "CHYBA" and (last is None or j["finished_at"] > last):
                row = {"stav": "CHYBA", "duvod": f"poslední běh {j['finished_at']} skončil chybou: {j['error'] or '?'}"}
            elif last is None:
                row = {"stav": "ROZPRACOVÁNO", "duvod": "zatím neběžel" if m["kadence"] else "zatím žádný záznam"}
            elif m["kadence"] and age > m["kadence"] + SLACK_DAYS:
                row = {"stav": "CHYBA", "duvod": f"zastaralé: poslední výstup před {age:.0f} dny, má běžet každých {m['kadence']} dní"}
            elif any(r["stav"] == "CHYBA" for r in roles):
                row = {"stav": "CHYBA", "duvod": "horší než náhoda: " + ", ".join(r["nazev"] for r in roles if r["stav"] == "CHYBA")}
            elif any(r["stav"] == "OVĚŘENO" for r in roles):
                row = {"stav": "HOTOVO/OVĚŘENO", "duvod": "ověřeno: " + ", ".join(
                    f"{r['nazev']} (t {r['t']})" if r["t"] is not None else r["nazev"] for r in roles if r["stav"] == "OVĚŘENO")}
            elif roles:
                row = {"stav": "NEOVĚŘENO", "duvod": "běží včas, ale výhoda zatím není prokázaná mimo vzorek"}
            else:
                row = {"stav": "HOTOVO", "duvod": "běží včas"}
            row["posledni"] = last
            row["stari_dni"] = None if age is None else round(age, 1)
        bad_in = [i for i in m["vstupy"] if state.get(i) in ("CHYBA", "BLOKOVÁNO")]
        if bad_in:
            row["duvod"] += f" · vstup v potížích: {', '.join(bad_in)}"
        state[m["id"]] = row["stav"]
        out.append({"id": m["id"], "nazev": m["nazev"], "prikaz": m["prikaz"], "kadence_dni": m["kadence"],
                    "vstupy": list(m["vstupy"]), "role": list(m.get("role", ())), **row})
    return out


def sources_status(conn, cache_conn, now: datetime | None = None) -> list[dict]:
    """Bezplatné zdroje: dostupnost a čerstvost (z cache a posledních běhů)."""
    from stockradar.contact import email
    now = now or utcnow()
    out = []

    def add(nazev, stav, detail):
        out.append({"zdroj": nazev, "stav": stav, "detail": detail})

    if cache_conn is not None:
        end = stock_data_end(cache_conn)
        a = _age(end, now)
        add("Yahoo — ceny akcií", "ROZPRACOVÁNO" if end is None else "CHYBA" if a > 10 else "OK",
            f"data do {end}" if end else "zatím nestaženo (python -m stockradar discover --universe --download)")
        rows = {}
        for c in COMMODITIES:
            r = _one(cache_conn, "SELECT n FROM series WHERE symbol = ?", (c["symbol"],))
            rows[c["symbol"]] = r[0] if r else 0
        missing = [f"{c['nazev']} ({c['symbol']})" for c in COMMODITIES if not rows[c["symbol"]]]
        add("Yahoo — komodity", "ROZPRACOVÁNO" if len(missing) == len(COMMODITIES) else "BLOKOVÁNO" if missing else "OK",
            f"chybí: {', '.join(missing[:6])}{' …' if len(missing) > 6 else ''} (Yahoo nevrací data nebo ještě nestaženo)"
            if missing else f"{len(COMMODITIES)} řad")
        sec = (_one(cache_conn, "SELECT MAX(fetched_at) FROM sec_index_done") or [None])[0]
        add("SEC EDGAR (fundamenty, filingy)", "BLOKOVÁNO" if email() is None else "OK" if sec else "ROZPRACOVÁNO",
            "chybí e-mail v data/kontakt.txt" if email() is None else f"staženo {sec}")
        q = (_one(cache_conn, "SELECT MAX(quarter) FROM insider_done") or [None])[0]
        add("SEC Form 4 — čtvrtletní sady", "OK" if q else "ROZPRACOVÁNO",
            f"poslední čtvrtletí {q}; SEC je zveřejňuje se zpožděním → čerstvé nákupy z openinsider (přehled Form 4)"
            if q else "zatím nestaženo (python -m stockradar smart-money)")
        ct = _one(cache_conn, "SELECT COUNT(*), MAX(fetched_at) FROM ct_studies") or (0, None)
        add("ClinicalTrials.gov", "OK" if ct[0] else "ROZPRACOVÁNO", f"{ct[0]} studií, staženo {ct[1] or '–'}")
        x = _one(cache_conn, "SELECT COUNT(*), MAX(checked_at) FROM xtb_offer") or (0, None)
        add("xtb.com — nabídka akcií", "OK" if x[0] else "ROZPRACOVÁNO", f"{x[0]} ověřených firem, naposledy {x[1] or '–'}")
    r = conn.execute("SELECT result_json FROM causal_runs ORDER BY id DESC LIMIT 1").fetchone()
    if r:
        res = json.loads(r[0])
        g = res.get("gdacs") or {}
        add("GDACS (OSN + EU) — přírodní katastrofy", "CHYBA" if g.get("chyba") else "OK",
            g.get("chyba") or f"{g.get('udalosti', 0)} výstrah, navázané komodity: {', '.join(g.get('navazane_komodity') or []) or 'žádné'}")
        p = res.get("pulsy") or {}
        bad = [k for k, v in p.items() if v is None]
        add("Google News RSS — zprávy o narušení", "CHYBA" if p and len(bad) == len(p) else "OK" if p else "ROZPRACOVÁNO",
            f"{len(p) - len(bad)} z {len(p)} komodit" + (f"; nedostupné: {', '.join(bad)}" if bad else ""))
    add("GDELT — světové zprávy", "BLOKOVÁNO", "HTTP 429 ze sdílené adresy serveru (zjištěno 2026-10-06) → nepoužito")
    return out


SUMMARY_KEYS = ("HOTOVO/OVĚŘENO", "HOTOVO", "NEOVĚŘENO", "ROZPRACOVÁNO", "BLOKOVÁNO", "CHYBA")


def overview(conn, cache_conn, reliability: dict, now: datetime | None = None) -> dict:
    mods = modules_status(conn, cache_conn, reliability, now)
    srcs = sources_status(conn, cache_conn, now)
    count = {k: sum(1 for m in mods if m["stav"] == k) for k in SUMMARY_KEYS}
    return {"moduly": mods, "zdroje": srcs, "pocty": {k: v for k, v in count.items() if v},
            "denik": journal(conn), "verze": __version__}
