"""Integrace: pohled na firmu ze všech modulů + sebekontrola napříč moduly.

Pro každou firmu, o které některý modul něco říká:
1. posbírá důkazy (i oborové z kauzálního radaru přes obor firmy),
2. každý zváží spolehlivostí jeho role (feedback) a čerstvostí dat vůči horizontu,
3. určí postoj: PŘÍLEŽITOST (jen důkazy pro růst), RIZIKO (jen pro pokles), ROZPOR (obojí), NEVÍM (nic směrového),
4. přidá rozpory, poučení z minulých chyb (lessons), pořadí ve všech modelech a kontrolní upozornění.
Nejde o nový prediktivní model — jen o průhledné spojení uložených výstupů. Postoj nic neslibuje.
"""

import hashlib
import json
from datetime import date

from stockradar import __version__
from stockradar.hub import evidence as E
from stockradar.hub import feedback as F
from stockradar.hub import registry as R
from stockradar.timeutil import to_iso, utcnow

DIRECTIONAL = ("prilezitost", "riziko")
MODULE_NAMES = {"SIGNAL_14D": "Signály 14 dní", "SIGNAL_1M": "Signály 1 měsíc", "SIGNAL_6M": "Model 6 měsíců",
                "RAKETY_6M": "Rakety 6 m", "SMART_MONEY": "Smart money", "KAUZALNI": "Kauzální radar",
                "ENERGIE": "Energetický radar", "LEDGER": "Ledger", "KATALYZATORY": "Katalyzátor", "VYZKUM": "Výzkum",
                "XTB": "XTB"}
SHORT = {"PŘÍLEŽITOST": "P", "RIZIKO": "R", "ROZPOR": "X", "NEVÍM": "N"}
CATALYST_SOON_DAYS = 7
# Obecná poučení → kdy se týkají firmy (role důkazu, typ katalyzátoru, slova v názvu, blízký katalyzátor)
LESSON_RULES = {
    "POUCENI-RAKETY-VOLATILITA": {"role": {"RAKETY_6M:vyber", "SIGNAL_6M:vyber"}},
    "OVERENI-RAKETY-2026-10-03": {"role": {"RAKETY_6M:vyber"}},
    "CHYBA-DAT-REVERSE-SPLIT": {"role": {"RAKETY_6M:vyber"}},
    "SM-ESPP-FLIP-WIX": {"role": {"SMART_MONEY:nakup"}},
    "MECH-KLINICKA-DATA": {"katalyzator": {"CLINICAL_DATA"}, "studie": True},
    "MECH-KRYPTO-TREASURY": {"slova": ("sharplink", "bitcoin", "ethereum", "crypto", "blockchain", "digital asset")},
    "RARE": {"katalyzator_do": CATALYST_SOON_DAYS},
}


def _age_days(day: str | None, today: date) -> int | None:
    try:
        return (today - date.fromisoformat(day[:10])).days if day else None
    except ValueError:
        return None


def _short(text: str, n: int = 80) -> str:
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"


def is_stale(e: dict, today: date) -> bool:
    """Data starší než čtvrtina horizontu (aspoň 3 dny) — u krátkých horizontů rychle ztrácí cenu."""
    age = _age_days(e.get("data_do"), today)
    return age is not None and age > max(3, (e.get("horizont") or 30) // 4)


def load_lessons(conn) -> list[dict]:
    sym = E._symbol_of(conn)
    out = []
    for r in conn.execute("SELECT * FROM lessons ORDER BY id"):
        points = json.loads(r["lessons_json"])
        out.append({"klic": r["case_key"], "nazev": r["title"], "typ": r["outcome_type"], "bod": points[0] if points else "",
                    "oprava": r["model_correction"], "firma": sym.get(r["company_id"]) if r["company_id"] else None})
    return out


def _lessons_for(tic: str, name: str, items: list[dict], lessons: list[dict]) -> list[dict]:
    roles = {e.get("role") for e in items}
    cats = {e.get("typ_katalyzatoru") for e in items if e["druh"] == "katalyzator"}
    soon = [e["dni_do"] for e in items if e["druh"] == "katalyzator" and e.get("dni_do") is not None]
    trials = any(e.get("studie") for e in items)
    low = (name or "").lower()
    out = []
    for l in lessons:
        rule = LESSON_RULES.get(l["klic"])
        hit = l["firma"] == tic
        if rule and not hit:
            hit = bool(rule.get("role", set()) & roles) or bool(rule.get("katalyzator", set()) & cats) or \
                (rule.get("studie") and trials) or any(w in low for w in rule.get("slova", ())) or \
                ("katalyzator_do" in rule and any(0 <= d <= rule["katalyzator_do"] for d in soon))
        if hit:
            out.append({"klic": l["klic"], "nazev": l["nazev"], "bod": l["bod"], "oprava": l["oprava"]})
    return out


def dossier(tic: str, items: list[dict], rel: dict, ranks: dict, sec: dict, lessons: list[dict], today: date) -> dict:
    info = sec.get(tic) or {}
    name = next((e["nazev"] for e in items if e.get("nazev")), None) or info.get("nazev")
    industry = info.get("obor") or next((e["obor"] for e in items if e.get("obor")), None)
    rows, checks = [], []
    for e in items:
        r = rel.get(e.get("role")) if e.get("role") else None
        stale = is_stale(e, today)
        w = (r["vaha"] if r else 0.0) * (0.5 if stale else 1.0) if e["druh"] in DIRECTIONAL else 0.0
        spol = r["stav"] if r else None
        adj = e.get("uprava")                       # vlastní výhrada modulu k tomuto výstupu (např. verdikt smart money)
        if adj and r:
            w = min(w, adj["strop"]) if "strop" in adj else w * adj.get("nasobek", 1.0)
            spol = adj.get("stav", spol)
            checks.append(f"{MODULE_NAMES.get(e['modul'], e['modul'])}: {adj['duvod']}")
        rows.append({"modul": e["modul"], "role": e.get("role"), "druh": e["druh"], "smer": e["smer"], "text": e["text"],
                     "stav": e["stav"], "spolehlivost": spol, "vaha": round(w, 2),
                     "t": r["t"] if r else None, "zdroj": e["zdroj"], "url": e.get("url"), "data_do": e.get("data_do"),
                     "horizont": e.get("horizont"), "zastarale": stale, "obor": e["typ"] == "obor"})
        if stale and e["druh"] in DIRECTIONAL:
            checks.append(f"{MODULE_NAMES.get(e['modul'], e['modul'])}: data z {e['data_do']} jsou starší než čtvrtina horizontu ({e['horizont']} dní) → váha poloviční")
    pro = [x for x in rows if x["druh"] in DIRECTIONAL and x["smer"] > 0]
    con = [x for x in rows if x["druh"] in DIRECTIONAL and x["smer"] < 0]
    wp, wc = round(sum(x["vaha"] for x in pro), 2), round(sum(x["vaha"] for x in con), 2)
    stance = "ROZPOR" if pro and con else "PŘÍLEŽITOST" if pro else "RIZIKO" if con else "NEVÍM"
    ver_pro = [x for x in pro if x["spolehlivost"] == "OVĚŘENO"]
    ver_con = [x for x in con if x["spolehlivost"] == "OVĚŘENO"]
    nm = lambda m: MODULE_NAMES.get(m, m)
    conflicts = [f"{nm(a['modul'])} ↑ ({_short(a['text'])}) × {nm(b['modul'])} ↓ ({_short(b['text'])})"
                 for a in pro for b in con][:4]
    # sebekontrola
    if (pro or con) and not (ver_pro or ver_con):
        checks.append("směrové důkazy jen z neověřených rolí — výhoda není prokázaná mimo vzorek")
    xtb = next((e for e in items if e["druh"] == "dostupnost"), None)
    if xtb is None:
        checks.append("dostupnost na XTB neověřena")
    elif xtb.get("xtb") != "AKCIE":
        checks.append(xtb["text"])
    for e in items:
        if e["druh"] == "katalyzator" and e.get("dni_do") is not None and 0 <= e["dni_do"] <= CATALYST_SOON_DAYS:
            checks.append(f"katalyzátor za {e['dni_do']} dní — ověř aktuální stav (poučení RARE)")
        if e["modul"] == "LEDGER" and e.get("otevrena") and ver_con:
            checks.append(f"otevřená {e['text'].split(' (')[0]} — ověřená role teď varuje před poklesem")
    if "." in tic:
        checks.append("modely 14 dní / 1 měsíc / 6 měsíců pokrývají jen akcie USA")
    pos = {m: f"{v['poradi'][tic]}/{v['celkem']}" for m, v in ranks.items() if tic in v["poradi"]}
    best = max(ver_con or ver_pro or con or pro, key=lambda x: (x["vaha"], abs(x["t"] or 0)), default=None)
    if stance == "ROZPOR":
        lead = "převažuje pokles" if wc - wp >= 0.3 else "převažuje růst" if wp - wc >= 0.3 else "vyrovnané"
        summary = f"ROZPOR ({lead}; váha pro {wp:.2f}, proti {wc:.2f})".replace(".", ",")
    elif best:
        summary = f"{stance} — {'ověřené' if (ver_pro if stance == 'PŘÍLEŽITOST' else ver_con) else 'jen neověřené signály'}" \
                  f": {rel[best['role']]['nazev'] if best.get('role') in rel else best['modul']}"
    else:
        summary = "NEVÍM — žádný směrový důkaz, jen kontext"
    order = sorted(rows, key=lambda x: (x["druh"] not in DIRECTIONAL, -x["vaha"], x["modul"]))
    chain = [f"{nm(x['modul'])}{' (obor)' if x['obor'] else ''}: {x['text']} [{x['spolehlivost'] or x['stav']}"
             f"{'' if x['t'] is None else ', t ' + str(x['t'])}, váha {x['vaha']}]" for x in order]
    return {"ticker": tic, "nazev": name, "obor": industry, "zeme": info.get("zeme"), "postoj": stance, "souhrn": summary,
            "pro": wp, "proti": wc, "overeno_pro": bool(ver_pro), "overeno_proti": bool(ver_con),
            "moduly": sorted({x["modul"] for x in rows}), "dukazy": order, "rozpory": conflicts,
            "pouceni": _lessons_for(tic, name, items, lessons), "poradi": pos, "kontrola": list(dict.fromkeys(checks)),
            "retez": chain}


def fingerprint(conn, today: date) -> str:
    """Otisk vstupů centra: nové běhy modulů, výsledky, výzkum, poučení, katalyzátory, den. Stejný otisk = nic nového."""
    parts = [today.isoformat(), __version__]
    for q in ("SELECT MAX(id) FROM signal_runs", "SELECT MAX(id) FROM discovery_runs", "SELECT MAX(id) FROM smart_money_runs",
              "SELECT MAX(id) FROM causal_runs", "SELECT MAX(id) FROM model_runs", "SELECT COUNT(*) FROM predictions",
              "SELECT COUNT(*) FROM prediction_outcomes", "SELECT COUNT(*) FROM signal_outcomes",
              "SELECT COUNT(*) FROM causal_outcomes", "SELECT MAX(id) FROM research_evidence", "SELECT COUNT(*) FROM lessons",
              "SELECT COUNT(*) FROM model_evaluations"):
        parts.append(str(conn.execute(q).fetchone()[0]))
    parts.append(json.dumps([tuple(r) for r in conn.execute("SELECT id, status, date_status, superseded_by FROM catalysts")]))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def build(conn, cache_conn, today: date, *, prev: dict | None = None) -> dict:
    ev = E.collect(conn, cache_conn, today)
    rel = F.reliability(conn)
    lessons = load_lessons(conn)
    by_firm: dict[str, list[dict]] = {}
    by_industry: dict[str, list[dict]] = {}
    for e in ev["dukazy"]:
        if e["typ"] == "firma":
            by_firm.setdefault(e["entita"], []).append(e)
        elif e["typ"] == "obor":
            by_industry.setdefault(e["entita"], []).append(e)
            for f in e.get("firmy") or []:
                by_firm.setdefault(f, [])
    sec = ev["firmy"]
    dossiers = []
    for tic, items in by_firm.items():
        ind = (sec.get(tic) or {}).get("obor") or next((e["obor"] for e in items if e.get("obor")), None)
        extra = by_industry.get((ind or "").lower(), [])
        if not items and not extra:
            continue
        dossiers.append(dossier(tic, items + extra, rel, ev["poradi"], sec, lessons, today))
    dossiers.sort(key=lambda d: (-max(d["pro"], d["proti"]), -(d["overeno_pro"] or d["overeno_proti"]), -len(d["moduly"]), d["ticker"]))
    stances = {d["ticker"]: SHORT[d["postoj"]] for d in dossiers}
    changes = []
    if prev and prev.get("postoje"):
        names = {v: k for k, v in SHORT.items()}
        for tic, s in stances.items():
            old = prev["postoje"].get(tic)
            if old != s:
                changes.append({"ticker": tic, "z": names.get(old, "nově"), "na": names[s]})
    checks = global_checks(rel, dossiers, ev)
    count = {k: sum(1 for d in dossiers if d["postoj"] == k) for k in SHORT}
    return {"vytvoreno": to_iso(utcnow()), "den": today.isoformat(), "verze": __version__, "otisk": fingerprint(conn, today),
            "pocty": {"firem": len(dossiers), "dukazu": len(ev["dukazy"]), **count,
                      "rozporu": sum(1 for d in dossiers if d["rozpory"]), "vyzkum_proslo": ev["vyzkum_proslo"]},
            "spolehlivost": list(rel.values()), "firmy": dossiers, "postoje": stances, "zmeny": changes, "kontroly": checks,
            "princip": "MODULY → DŮKAZY → SPOLEHLIVOST (testy, živé výsledky) → POHLED NA FIRMU → ROZPORY A KONTROLY"}


def global_checks(rel: dict, dossiers: list[dict], ev: dict) -> list[dict]:
    out = []
    for r in rel.values():
        if r["stav"] == "CHYBA":
            out.append({"uroven": "CHYBA", "text": f"role „{r['nazev']}“ je horší než náhoda ({r['typ']}, t {r['t']})"})
    roz = [d["ticker"] for d in dossiers if d["postoj"] == "ROZPOR"]
    if roz:
        out.append({"uroven": "VAROVÁNÍ", "text": f"rozpor mezi moduly u {len(roz)} firem: {', '.join(roz[:12])}"})
    led = [d["ticker"] for d in dossiers if any("otevřená predikce" in c for c in d["kontrola"])]
    if led:
        out.append({"uroven": "VAROVÁNÍ", "text": f"otevřené predikce v ledgeru u firem, před kterými teď varuje ověřená role: {', '.join(led)}"})
    if ev["vyzkum_proslo"]:
        out.append({"uroven": "INFO", "text": f"prošlý ruční výzkum: {ev['vyzkum_proslo']} záznamů (už se nepočítá)"})
    ver = [r["nazev"] for r in rel.values() if r["stav"] == "OVĚŘENO"]
    out.append({"uroven": "INFO", "text": "ověřené role: " + (", ".join(ver) if ver else "žádná")})
    return out


def save_run(conn, res: dict) -> int:
    summ = {k: res[k] for k in ("den", "otisk", "pocty", "postoje", "zmeny", "kontroly")}
    summ["spolehlivost"] = {r["role"]: [r["stav"], r["vaha"], r["t"]] for r in res["spolehlivost"]}
    with conn:
        cur = conn.execute("INSERT INTO hub_runs (run_at, summary_json, app_version) VALUES (?, ?, ?)",
                           (res["vytvoreno"], json.dumps(summ, ensure_ascii=False, sort_keys=True), __version__))
    return cur.lastrowid


def last_run(conn) -> tuple[int, dict] | None:
    r = conn.execute("SELECT id, summary_json FROM hub_runs ORDER BY id DESC LIMIT 1").fetchone()
    return (r[0], json.loads(r[1])) if r else None


def refresh(conn, cache_conn, *, today: date | None = None, force: bool = False) -> dict:
    """Postaví pohled (rychlé, jen čte uložené výstupy). Do paměti (`hub_runs`) zapíše jen při změně vstupů."""
    today = today or utcnow().date()
    prev = last_run(conn)
    res = build(conn, cache_conn, today, prev=prev[1] if prev else None)
    if prev and prev[1].get("otisk") == res["otisk"] and not force:
        res["beh"] = {"id": prev[0], "stav": "PŘESKOČENO", "duvod": f"vstupy beze změny od běhu #{prev[0]} — nový záznam se nezapisuje"}
        res["zmeny"] = prev[1].get("zmeny") or []
    else:
        res["beh"] = {"id": save_run(conn, res), "stav": "OK", "duvod": "nové vstupy" if prev else "první běh"}
    res["system"] = R.overview(conn, cache_conn, {r["role"]: r for r in res["spolehlivost"]})
    return res
