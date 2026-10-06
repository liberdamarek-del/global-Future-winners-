"""Data pro webový přehled (artifact čte dokumenty stav/aktualni, stav/predikce, stav/retezec)."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from stockradar import __version__, config
from stockradar import model as m
from stockradar.catalysts import date_text
from stockradar.contact import usage_summary
from stockradar.enums import label
from stockradar.timeutil import to_iso, utcnow

# db dokument má na serveru limit 256 KiB; server ho ukládá ~1,4–1,5× větší než náš kompaktní JSON
# (změřeno 2026-10-02: 155 720 B → 218 076 B). Proto hlídáme 170 KiB kompaktního textu.
DOC_LIMIT = 170 * 1024

FREE_SOURCES = [
    {"nazev": "Yahoo Finance chart API", "url": "https://query1.finance.yahoo.com/v8/finance/chart/SPY",
     "co": "Denní ceny, objemy a kurzy měn pro všechny burzy (USA, Evropa, Asie). Bez klíče.", "stav": "POUŽÍVÁ SE"},
    {"nazev": "SEC EDGAR (XBRL frames, full-index)", "url": "https://www.sec.gov/edgar/search/",
     "co": "Fundamenty US firem (tržby, zisk, počet akcií, hotovost) a všechny filingy s datem podání (8-K, emise, 13D). "
           "Vyžaduje e-mail v hlavičce — každé použití je evidované níže.", "stav": "POUŽÍVÁ SE (s e-mailem)"},
    {"nazev": "ClinicalTrials.gov API v2", "url": "https://clinicaltrials.gov/api/v2/studies",
     "co": "Studie fáze 2/3 sponzorované firmami → termíny klinických výsledků (katalyzátory biotech). Bez klíče a e-mailu.",
     "stav": "POUŽÍVÁ SE"},
    {"nazev": "Google News RSS", "url": "https://news.google.com/",
     "co": "Titulky zpráv kolem raket a u kandidátů (proč akcie vyrostla). Bez klíče.", "stav": "POUŽÍVÁ SE"},
    {"nazev": "Seznamy firem: Nasdaq screener, JPX, ASX, Wikipedie", "url": "https://www.nasdaq.com/market-activity/stocks/screener",
     "co": "Kdo je na burze (USA, Japonsko, Austrálie, Evropa, Asie, Kanada), obor, tržní kapitalizace USA.", "stav": "POUŽÍVÁ SE"},
    {"nazev": "NRC, tiskové zprávy, oborová média", "url": "https://www.nrc.gov/reactors/new-reactors/advanced.html",
     "co": "Jaderná povolení, dohody s Big Tech, milníky — denní výzkum Claude (zapisuje se jen se zdrojem).",
     "stav": "POUŽÍVÁ SE (denní výzkum)"},
]


def _accuracy(conn: sqlite3.Connection) -> list[dict]:
    """Energetický model: kolik predikcí porazilo S&P 500 po 7/14/30 dnech."""
    out = []
    for n in (7, 14, 30):
        rows = conn.execute(
            "SELECT o.result, o.excess_return_pct FROM prediction_outcomes o JOIN predictions p ON p.id = o.prediction_id"
            " WHERE o.horizon_days = ? AND p.mode = 'LIVE' AND COALESCE(p.source, 'ENERGY_MODEL') = 'ENERGY_MODEL'",
            (n,)).fetchall()
        hits = sum(1 for r in rows if r["result"] == "HIT")
        ex = [r["excess_return_pct"] for r in rows if r["excess_return_pct"] is not None]
        out.append({"dni": n, "vyhodnoceno": len(rows), "uspesnych": hits,
                    "uspesnost": round(hits / len(rows), 4) if rows else None,
                    "prumer_nad_spy": round(sum(ex) / len(ex), 2) if ex else None})
    return out


def _rocket_accuracy(conn: sqlite3.Connection) -> dict:
    """Predikce raket: rozhodnuté (HIT kdykoli, MISS po uplynutí horizontu) proti predikované šanci."""
    preds = conn.execute("SELECT id, probability_pct, base_rate_pct FROM predictions WHERE mode = 'LIVE'"
                         " AND source = 'DISCOVERY' AND COALESCE(strategy, '') <> 'SMART_MONEY'").fetchall()
    decided = hits = 0
    expected = []
    for p in preds:
        res = {r["result"] for r in conn.execute("SELECT result FROM prediction_outcomes WHERE prediction_id = ?", (p["id"],))}
        if "HIT" in res or "MISS" in res:
            decided += 1
            hits += "HIT" in res
            if p["probability_pct"] is not None:
                expected.append(p["probability_pct"] / 100)
    return {"predikci": len(preds), "rozhodnuto": decided, "zasahu": hits, "bezi": len(preds) - decided,
            "uspesnost": round(hits / decided, 4) if decided else None,
            "ocekavano": round(sum(expected) / len(expected), 4) if expected else None}


def _latest_close(conn: sqlite3.Connection, symbol: str) -> tuple[float, str] | None:
    r = conn.execute("SELECT close, date FROM price_bars WHERE symbol = ? ORDER BY date DESC LIMIT 1", (symbol,)).fetchone()
    return (r["close"], r["date"]) if r else None


def _max_since(conn: sqlite3.Connection, symbol: str, day: str) -> float | None:
    r = conn.execute("SELECT MAX(close) FROM price_bars WHERE symbol = ? AND date > ?", (symbol, day)).fetchone()
    return r[0] if r else None


def _nodes_by_company(conn) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for r in conn.execute("SELECT cc.company_id, n.name FROM company_chain cc JOIN chain_nodes n ON n.code = cc.node_code"
                          " ORDER BY n.layer, n.code"):
        out.setdefault(r["company_id"], []).append(r["name"])
    return out


def build_docs(conn: sqlite3.Connection, *, run_id: int, steps: dict, warnings: list[str], model_note: str,
               now: datetime | None = None) -> dict[str, dict]:
    now = now or utcnow()
    run = conn.execute("SELECT * FROM model_runs WHERE id = ?", (run_id,)).fetchone()
    version = conn.execute("SELECT * FROM model_versions WHERE id = ?", (run["model_version_id"],)).fetchone()
    scored = json.loads(run["scores_json"])
    weights = json.loads(version["weights_json"])
    metrics = json.loads(version["metrics_json"])
    nodes = _nodes_by_company(conn)
    symbols = {r["yahoo_symbol"]: r for r in conn.execute(
        "SELECT l.yahoo_symbol, l.company_id, c.notes FROM listings l JOIN companies c ON c.id = l.company_id"
        " WHERE l.yahoo_symbol IS NOT NULL")}
    bigtech = {}
    for r in conn.execute("SELECT * FROM relationships WHERE company_id IS NOT NULL ORDER BY announced_on DESC"):
        bigtech.setdefault(r["company_id"], []).append(
            f"{r['counterparty']}: {r['description']} ({r['announced_on']})")
    open_cats = {}
    for k in conn.execute("SELECT * FROM catalysts WHERE status IN ('UPCOMING','DELAYED','IN_PROGRESS') ORDER BY id"):
        open_cats.setdefault(k["company_id"], []).append(f"{k['description']} — {date_text(k)}")

    def card(sym: str, it: dict) -> dict:
        cid = symbols[sym]["company_id"]
        contrib = sorted(it["prispevky"].items(), key=lambda kv: kv[1], reverse=True)
        return {
            "ticker": sym, "nazev": it["nazev"], "retezec": nodes.get(cid, []), "poradi": it["poradi"],
            "skore": it["skore"], "p_beat": it["p_beat"], "p_rocket": it["p_rocket"],
            "nadvynos": it["ocekavany_nadvynos"], "q20": it["q20"], "q80": it["q80"],
            "cena": it["cena"], "mena": it["mena"], "den": it["den"], "data": it["data"],
            "zmena_1d": it["zmena_1d"], "zmena_20d": it["zmena_20d"], "zmena_120d": it["zmena_120d"],
            "duvody": [{"faktor": m.FACTORS[f]["label"], "body": v} for f, v in contrib if abs(v) >= 0.5][:6],
            "bigtech": bigtech.get(cid, []), "katalyzatory": open_cats.get(cid, []),
            "poznamka": symbols[sym]["notes"],
        }

    ranked = sorted(scored.items(), key=lambda kv: kv[1]["poradi"])
    main = conn.execute(
        "SELECT p.*, l.yahoo_symbol, c.name FROM predictions p JOIN listings l ON l.id = p.listing_id"
        " JOIN companies c ON c.id = p.company_id WHERE p.is_main_pick = 1 AND p.mode = 'LIVE' AND p.made_at >= ?"
        " ORDER BY p.made_at DESC LIMIT 1", (to_iso(now - timedelta(days=30)),)).fetchone()
    horizon_end = (now + timedelta(days=60)).date().isoformat()
    today = now.date().isoformat()
    catalysts = []
    for k in conn.execute(
            "SELECT k.*, c.name, l.yahoo_symbol FROM catalysts k JOIN companies c ON c.id = k.company_id"
            " LEFT JOIN listings l ON l.company_id = c.id AND l.is_primary = 1"
            " WHERE k.status IN ('UPCOMING','DELAYED','IN_PROGRESS') ORDER BY COALESCE(k.event_date, k.window_start, '9999')"):
        start = k["event_date"] or k["window_start"]
        end = k["event_date"] or k["window_end"]
        catalysts.append({
            "ticker": k["yahoo_symbol"], "firma": k["name"], "popis": k["description"], "datum": date_text(k),
            "jistota": label(k["date_status"]), "zdroj": k["source"], "url": k["source_url"],
            "brzy": bool(start and start <= horizon_end and (end or start) >= today),
        })

    aktualni = {
        "aktualizovano": to_iso(now), "den_dat": run["data_date"], "verze_aplikace": __version__,
        "kroky": steps, "varovani": warnings[:20],
        "main_pick": None if main is None else {
            "ticker": main["yahoo_symbol"], "nazev": main["name"], "datum": main["made_at"], "cena": main["price"],
            "mena": main["currency"], "p_beat": main["probability_pct"], "p_rocket": main["p_rocket_pct"],
            "nadvynos": main["base_move_pct"], "bull": main["bull_move_pct"], "bear": main["bear_move_pct"],
            "katalyzator": main["catalyst_text"], "katalyzator_datum": main["catalyst_date_text"],
            "duvod": main["rationale"], "riziko": main["key_risk"]},
        "kandidati": [card(s, it) for s, it in ranked[:12]],
        "vsechny": [{"ticker": s, "nazev": it["nazev"], "retezec": nodes.get(symbols[s]["company_id"], [])[:1],
                     "skore": it["skore"], "poradi": it["poradi"], "p_beat": it["p_beat"], "p_rocket": it["p_rocket"],
                     "cena": it["cena"], "mena": it["mena"], "zmena_1d": it["zmena_1d"], "zmena_20d": it["zmena_20d"],
                     "zmena_120d": it["zmena_120d"], "data": it["data"]} for s, it in ranked],
        "katalyzatory": catalysts,
        "presnost": _accuracy(conn),
        "model": {
            "verze": version["id"], "vytvoreno": version["created_at"], "duvod_verze": version["reason"],
            "dnes": model_note, "trenink": version["training_window"], "vzorku": version["n_samples"],
            "vahy": [{"faktor": f, "nazev": meta["label"], "proc": meta["why"], "prior": meta["prior"],
                      "vaha": weights.get(f), "ic": metrics.get(f, {}).get("ic"), "t": metrics.get(f, {}).get("t"),
                      "podil_dat": metrics.get(f, {}).get("data_weight")} for f, meta in m.FACTORS.items()],
            "mimo_vzorek": metrics.get("_oos", {}),
            "kalibrace": json.loads(version["calibration_json"]),
            "historie": [{"verze": r["id"], "kdy": r["created_at"], "duvod": r["reason"]} for r in conn.execute(
                "SELECT id, created_at, reason FROM model_versions ORDER BY id DESC LIMIT 15")],
        },
        "zdroje": FREE_SOURCES,
        "email": usage_summary(conn, days=14),
    }

    bench_close = conn.execute("SELECT close, date FROM price_bars WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                               (config.BENCHMARK_SYMBOL,)).fetchone()
    preds = []
    for p in conn.execute(
            "SELECT p.*, l.yahoo_symbol, c.name, c.industry FROM predictions p JOIN listings l ON l.id = p.listing_id"
            " JOIN companies c ON c.id = p.company_id WHERE p.mode = 'LIVE' ORDER BY p.made_at DESC LIMIT 300"):
        outs = {o["horizon_days"]: o for o in conn.execute(
            "SELECT * FROM prediction_outcomes WHERE prediction_id = ?", (p["id"],))}
        smart = p["strategy"] == "SMART_MONEY"
        rocket = p["source"] == "DISCOVERY" and not smart
        live = None
        last = _latest_close(conn, p["yahoo_symbol"]) if p["yahoo_symbol"] else None
        if last and bench_close and p["benchmark_price"]:
            price, day = last
            ret = price / p["price"] - 1
            top = _max_since(conn, p["yahoo_symbol"], p["made_at"][:10])
            live = {"cena": price, "den": day, "vynos": round(ret * 100, 2),
                    "nad_spy": round((ret - (bench_close["close"] / p["benchmark_price"] - 1)) * 100, 2),
                    "max_dosud": round((top / p["price"] - 1) * 100, 2) if top else None}
        results = {o["result"] for o in outs.values()}
        state = ("HIT" if "HIT" in results else "MISS" if "MISS" in results else "BĚŽÍ") if rocket else \
            (outs[max(outs)]["result"] if outs else "BĚŽÍ")
        preds.append({
            "id": p["id"], "ticker": p["yahoo_symbol"], "nazev": p["name"], "obor": p["industry"], "datum": p["made_at"],
            "cena": p["price"], "mena": p["currency"], "skore": p["score_overall_setup"], "verdikt": label(p["verdict"]),
            "main_pick": bool(p["is_main_pick"]), "p_beat": p["probability_pct"], "p_rocket": p["p_rocket_pct"],
            "p_propad": p["p_drop_pct"], "zakladni": p["base_rate_pct"], "cil": p["target_move_pct"],
            "nadvynos": p["base_move_pct"], "bull": p["bull_move_pct"], "bear": p["bear_move_pct"],
            "katalyzator": p["catalyst_text"], "katalyzator_datum": p["catalyst_date_text"],
            "duvod": p["rationale"], "riziko": p["key_risk"], "data": p["price_freshness"], "aktualne": live,
            "vysledky": {str(n): {"vynos": o["return_pct"], "nad_spy": o["excess_return_pct"], "vysledek": o["result"],
                                  "max": round((o["max_price"] / p["price"] - 1) * 100, 1) if o["max_price"] else None,
                                  "den": o["observed_at"][:10]} for n, o in outs.items()},
            "typ": "raketa" if rocket else "smart money" if smart else "energie", "horizont": p["horizon"], "stav": state,
            "konec": (datetime.fromisoformat(p["made_at"][:10]) + timedelta(days=180 if rocket or smart else 30)).date().isoformat(),
        })
    predikce = {"aktualizovano": to_iso(now), "predikce": preds, "presnost": aktualni["presnost"],
                "presnost_rakety": _rocket_accuracy(conn)}

    node_rows = conn.execute("SELECT * FROM chain_nodes ORDER BY layer, code").fetchall()
    retezec = {
        "aktualizovano": to_iso(now),
        "uzly": [{
            "kod": n["code"], "vrstva": n["layer"], "nazev": n["name"], "popis": n["description"], "horizont": n["horizon"],
            "firmy": [{"ticker": r["yahoo_symbol"], "nazev": r["name"], "stav": r["listing_status"],
                       "skore": scored.get(r["yahoo_symbol"] or "", {}).get("skore")}
                      for r in conn.execute(
                          "SELECT c.name, c.listing_status, l.yahoo_symbol FROM company_chain cc"
                          " JOIN companies c ON c.id = cc.company_id"
                          " LEFT JOIN listings l ON l.company_id = c.id AND l.is_primary = 1"
                          " WHERE cc.node_code = ? ORDER BY c.name", (n["code"],))],
        } for n in node_rows],
        "dohody": [{
            "kdo": r["counterparty"], "s_kym": r["party"], "ticker": r["yahoo_symbol"], "typ": r["rel_type"],
            "zavaznost": r["binding"], "mw": r["capacity_mw"], "usd": r["amount_usd"], "popis": r["description"],
            "datum": r["announced_on"], "zdroj": r["source"], "url": r["source_url"]}
            for r in conn.execute(
                "SELECT r.*, l.yahoo_symbol FROM relationships r"
                " LEFT JOIN listings l ON l.company_id = r.company_id AND l.is_primary = 1"
                " ORDER BY r.announced_on DESC")],
        "pre_ipo": [{"nazev": r["name"], "poznamka": r["notes"]} for r in conn.execute(
            "SELECT name, notes FROM companies WHERE listing_status IN ('PRE_IPO','PRIVATE')")],
    }
    return {"aktualni": aktualni, "predikce": predikce, "retezec": retezec}


def build_discovery_doc(conn: sqlite3.Connection) -> dict | None:
    """Dokument stav/objevy — zkrácený výtah z posledního běhu objevování (úplný výsledek je v discovery_runs)."""
    run = conn.execute("SELECT * FROM discovery_runs ORDER BY id DESC LIMIT 1").fetchone()
    if run is None:
        return None
    full = json.loads(run["result_json"])
    studie = {}
    for kind, sd in full.get("studie", {}).items():
        pop = (sd.get("test") or {}).get("populace") or {}
        studie[kind] = {"popis": sd.get("popis"), "raket": sd.get("raket"), "smerova_vyhoda": sd.get("smerova_vyhoda"),
                        "trenink_do": (sd.get("test") or {}).get("trenink_do"),
                        "zaklad": pop.get("zaklad"), "top1": pop.get("top1"), "lift_top1": pop.get("lift_top1"),
                        "auc": pop.get("auc"), "asymetrie_top1": (pop.get("asymetrie") or {}).get("top1"),
                        "lift": [{"nazev": l["nazev"], "lift": l["nejsilnejsi"]["lift"]} for l in sd.get("lift", [])[:5]]}
    rak = full.get("rakety_6m")
    if rak:
        rak = {k: v for k, v in rak.items() if not k.startswith("_")}
        rak["kandidati"] = rak.get("kandidati", [])[:12]
        rak["vahy"] = rak.get("vahy", [])[:12]
    pricny = full.get("pricny", {})
    doc = {
        "statistika": full.get("statistika"), "data_do": full.get("data_do"),
        "rakety_6m": rak, "studie": studie,
        "pricny": {k: pricny.get(k) for k in ("vysvetleno", "celkem", "planovany_termin", "signal_predem")}
                  | {"podle_priciny": pricny.get("podle_priciny", [])[:8]},
        "vitezove": [{k: w.get(k) for k in ("ticker", "nazev", "zeme", "sektor", "rust_6m", "rust_12m", "velikost",
                                             "overit_data", "pricina")} for w in full.get("vitezove", [])[:10]],
        "sektorove_vlny": [{k: w.get(k) for k in ("obor", "vitezu", "firem", "lift", "median_vynos", "zeme", "priklady")}
                           for w in full.get("sektorove_vlny", [])[:8]],
        "zname_pripady": full.get("zname_pripady", []),
        "nova_ipo": {"pocet": (full.get("nova_ipo") or {}).get("pocet"),
                     "podle_oboru": (full.get("nova_ipo") or {}).get("podle_oboru", [])[:5]},
        "beh": {"id": run["id"], "probehlo": run["run_at"], "data_do": run["data_through"], "verze": run["app_version"]},
    }
    return doc


SM_GROUPS = (  # předem daný výběr skupin pro web (úplné tabulky jsou v smart_money_runs a v docs/)
    ("insideri", "Insider: AKTIVNÍ nákup (všechny)"), ("insideri", "Insider aktivní: CFO"),
    ("insideri", "Insider aktivní: CEO"), ("insideri", "Insider aktivní: jen člen představenstva"),
    ("insideri", "Insider aktivní: 10% vlastník (fond, majitel)"), ("insideri", "Insider aktivní: 3+ insideři do 30 dní"),
    ("insideri", "Insider aktivní: hodnota ≥ 1 mil. USD"),
    ("insideri", "Insider aktivní: po propadu 30 %+ od ročního maxima"),
    ("insideri", "Insider: automatický nákup (plán 10b5-1)"), ("insideri", "Insider: přidělené akcie (odměna)"),
    ("insideri", "Insider: uplatnění opce"),
    ("politici", "Politici: AKTIVNÍ nákup (všichni)"), ("politici", "Politici: Sněmovna"), ("politici", "Politici: Senát"),
    ("politici", "Politici: nákup opcí"), ("politici", "Politici: Nancy Pelosi (většinou manžel)"),
    ("podily", "Velký podíl: 13D aktivista"), ("podily", "Velký podíl: 13G pasivní investor"),
    ("buybacky", "Buyback ≥5 % kapitalizace"), ("buybacky", "Buyback ≥ 2 % při rostoucích tržbách"),
    ("buybacky", "Buyback ≥ 2 % při klesajících tržbách"), ("buybacky", "Buyback žádný"),
)


def smart_money_conclusion(avp: dict) -> dict:
    """Předem dané pravidlo: vzorec je „potvrzený“, jen když typ nákupu porazil pasivní transakce ve stejném měsíci
    v učení 2021–24 I v testu 2025–26 a v obou s t ≥ 2. Jinak se řekne přímo, že potvrzený není."""
    def pick(rows):
        return {(r["situace"], r["skupina"]): r for r in rows}
    tr, te = pick(avp.get("uceni_2021_2024", [])), pick(avp.get("test_2025_2026", []))
    both = []
    for key, a in tr.items():
        b = te.get(key)
        if b and a["rozdil"] is not None and b["rozdil"] is not None:
            both.append({"situace": key[0], "skupina": key[1], "uceni": a["rozdil"], "t_uceni": a["t"],
                         "test": b["rozdil"], "t_test": b["t"], "n_test": b["n"]})
    ok = [x for x in both if x["uceni"] > 0 and x["test"] > 0 and (x["t_uceni"] or 0) >= 2 and (x["t_test"] or 0) >= 2]
    stable = sorted((x for x in both if x["uceni"] > 0 and x["test"] > 0), key=lambda x: min(x["uceni"], x["test"]),
                    reverse=True)
    best_hist = max(both, key=lambda x: x["t_uceni"] or 0, default=None)
    return {"potvrzeno": bool(ok), "potvrzene_typy": ok, "kladne_v_obou": stable[:5], "nejsilnejsi_v_uceni": best_hist}


def build_smart_money_doc(conn: sqlite3.Connection) -> dict | None:
    """Dokument stav/smartmoney — výtah z posledního běhu smart money."""
    run = conn.execute("SELECT * FROM smart_money_runs ORDER BY id DESC LIMIT 1").fetchone()
    if run is None:
        return None
    full = json.loads(run["result_json"])

    def row(name, st):
        a, b = st.get("6m") or {}, st.get("12m") or {}
        return {"skupina": name, "n": a.get("n"), "vynos_median": a.get("vynos_median"),
                "nad_kontrolou": a.get("nad_kontrolou_prumer"), "t": a.get("t_mesice"),
                "porazilo_spy": a.get("porazilo_spy"), "nad_kontrolou_12m": b.get("nad_kontrolou_prumer"),
                "t_12m": b.get("t_mesice"), "max": a.get("max6m_median"), "min": a.get("min6m_median")}
    srovnani = [row(name, full[sec][name]) for sec, name in SM_GROUPS if name in full.get(sec, {})]
    keep = ("ticker", "firma", "kdo", "funkce", "insideru", "typ", "zverejneno", "obchod", "hodnota_usd", "cena_nakupu",
            "cena_posledni", "cena_aktualni", "den_ceny", "pohyb_od_zverejneni", "skore", "fundament", "buyback",
            "katalyzator", "historie_nakupujiciho", "korelace_vs_pricina", "hlavni_riziko", "verdikt", "verdikt_proc")
    top = [{k: s.get(k) for k in keep} | {"form4": [o.get("url") for o in s.get("overeni", [])][:3]}
           for s in (full.get("aktualni") or {}).get("top", [])]
    pel = [p for p in full.get("pelosi", []) if p.get("trida") == "AKTIVNÍ NÁKUP" and p.get("vstup")]
    return {
        "beh": {"id": run["id"], "probehlo": run["run_at"], "data_do": run["data_through"], "verze": run["app_version"]},
        "pocty": full.get("pocty"), "zpozdeni": full.get("zpozdeni_zverejneni"),
        "zaver": smart_money_conclusion(full.get("aktivni_vs_pasivni", {})),
        "srovnani": srovnani,
        "aktivni_vs_pasivni": [r for r in full.get("aktivni_vs_pasivni", {}).get("cele_obdobi", [])
                               if r["situace"] in ("vše", "po propadu 30 %+")],
        "po_letech": full.get("insider_po_letech"),
        "vs_qqq": full.get("vs_qqq"),
        "pelosi": pel[-12:], "pelosi_pocet": len(full.get("pelosi", [])),
        "politici_osoby": [p for p in full.get("politici_osoby", []) if p.get("n")][:8],
        "politici_aktualni": (full.get("politici_aktualni") or [])[:12],
        "skore": (full.get("skore") or {}).get("test_kvintily"),
        "top": top, "kandidatu": (full.get("aktualni") or {}).get("kandidatu"),
        "nakupu": (full.get("aktualni") or {}).get("pocet_nakupu"),
    }


SIGNAL_MODELS = (("SIGNAL_14D", "h14"), ("SIGNAL_1M", "h1m"))
SIGNAL_ANALYTICS = SIGNAL_MODELS + (("SIGNAL_6M", "h6m"),)      # testy všech modelů (6 měsíců má vlastní žebříček)


def _latest_signal_run(conn, name: str):
    return conn.execute("SELECT * FROM signal_runs WHERE model_name = ? ORDER BY id DESC LIMIT 1", (name,)).fetchone()


def _trim_metrics(m):
    if not isinstance(m, dict):
        return m
    keep = ("vzorku", "nezavislych", "tydnu", "up5", "down5", "beat_sec", "big", "horni_desetina", "dolni_desetina",
            "rozhodnuti", "podle_rezimu", "_stav", "poznamka")
    return {k: m[k] for k in keep if k in m}


def _trim_card(c: dict) -> dict:
    c = dict(c)
    info = c.get("informace") or {}
    c["informace"] = {k: info.get(k) for k in ("stav", "titulku", "pribehu", "prepisu", "pribehu_7d", "novych_7d",
                                               "novost", "kvalita", "typ")} | {
        "nove": [{k: n.get(k) for k in ("poprve", "titulek", "prvni_zdroj", "kvalita", "kopii", "url")}
                 for n in (info.get("nove") or [])[:2]]}
    an = c.get("analogie") or {}
    keep_h = {str(c.get("obchodnich_dni") or 10), "60"}
    c["analogie"] = {"pocet": an.get("pocet"), "nezavislych": an.get("nezavislych"),
                     "horizonty": {h: v for h, v in (an.get("horizonty") or {}).items() if h in keep_h}}
    for k in ("pasmo", "pasmo_nezavislych", "nejistota", "sektor", "mechanismus", "ocekavany_cas", "model", "rezim",
              "pohyb_median", "nad_oborem"):
        c.pop(k, None)
    c["katalyzatory"] = (c.get("katalyzatory") or [])[:3]
    return c


def build_signals_doc(conn: sqlite3.Connection) -> dict | None:
    """Dokument stav/signaly — jak se modely testují (protokol, zamčený test, trh, mechanismy). Karty jsou v žebříčku."""
    models = {}
    for name, _ in SIGNAL_ANALYTICS:
        run = _latest_signal_run(conn, name)
        if run is None:
            continue
        full = json.loads(run["result_json"])
        models[name] = {
            "beh": {"id": run["id"], "probehlo": run["run_at"], "data_do": run["data_through"], "verze": run["app_version"],
                    "konfigurace": run["config_hash"]},
            "horizont": full.get("horizont") or "14 dní", "prah_rust": full.get("prah_rust", 0.05),
            "prah_pokles": full.get("prah_pokles", -0.05), "protokol": full.get("protokol"), "vzorky": full.get("vzorky"),
            "zaklad": full.get("zaklad"), "validace": _trim_metrics(full.get("validace")),
            "zamceny_test": _trim_metrics(full.get("zamceny_test")), "post": _trim_metrics(full.get("post")),
            "meta_model": full.get("meta_model"), "pasma": full.get("pasma"),
            "kalibrace": {t: full.get("kalibrace", {}).get(t) for t in ("up5", "down5")},
            "dnes": full.get("dnes"), "mispricing_dukaz": full.get("mispricing_dukaz"), "vahy": full.get("vahy"),
            "vysledky_karet": full.get("vysledky_karet"), "insideri_sec_do": full.get("insideri_sec_do"),
            "varovani": [_trim_card(c) for c in full.get("karty", []) if not c.get("poradi") and c.get("final") == "POKLES"][:5],
        }
        if "trh" not in models.get("_spolecne", {}):
            models["_spolecne"] = {"trh": full.get("trh"), "rezim": full.get("rezim"),
                                   "mechanismy": {k: {kk: vv for kk, vv in v.items() if kk != "nejsilnejsi_vazby"} | {
                                       "nejsilnejsi_vazby": v.get("nejsilnejsi_vazby", [])[:4]}
                                       for k, v in (full.get("mechanismy") or {}).get("obdobi", {}).items()}}
    return {"modely": models} if models else None


def _ledger_rocket(conn, ticker: str) -> dict | None:
    r = conn.execute("SELECT p.id, p.made_at, p.price, p.currency FROM predictions p JOIN listings l ON l.id = p.listing_id"
                     " WHERE l.yahoo_symbol = ? AND p.source = 'DISCOVERY' AND COALESCE(p.strategy, 'ROCKET_6M') = 'ROCKET_6M'"
                     " ORDER BY p.id DESC LIMIT 1", (ticker,)).fetchone()
    if r is None:
        return None
    last = _latest_close(conn, ticker)
    return {"id": r["id"], "den": r["made_at"][:10], "cena": r["price"], "mena": r["currency"],
            "vynos_dosud": round(last[0] / r["price"] - 1, 4) if last and r["price"] else None}


def build_zebricek_doc(conn: sqlite3.Connection) -> dict | None:
    """Dokument stav/zebricek — hlavní obrazovka: TOP 20 pro 14 dní, 1 měsíc a 6 měsíců + detail každé firmy."""
    from stockradar.signals.store import history
    out = {}
    for name, key in SIGNAL_MODELS:
        run = _latest_signal_run(conn, name)
        if run is None:
            continue
        full = json.loads(run["result_json"])
        rows = sorted((c for c in full.get("karty", []) if c.get("poradi")), key=lambda c: c["poradi"])
        test = full.get("zamceny_test") or {}
        dec = (test.get("rozhodnuti") or {})
        out[key] = {
            "model": name, "horizont": full.get("horizont") or "14 dní", "data_do": run["data_through"],
            "probehlo": run["run_at"], "prah_rust": full.get("prah_rust", 0.05), "prah_pokles": full.get("prah_pokles", -0.05),
            "akcii": (full.get("dnes") or {}).get("akcii"), "trh": "USA (data SEC)", "razeni": full.get("razeni"),
            "silnych": (full.get("dnes") or {}).get("rozhodnuti", {}).get("RŮST"),
            "zaklad": (full.get("zaklad") or {}).get("up5"),
            "xtb": full.get("xtb") or {"kontrola": False},
            "test": {"auc_rust": (test.get("up5") or {}).get("auc"), "auc_pokles": (test.get("down5") or {}).get("auc"),
                     "horni_desetina": test.get("horni_desetina"), "rust": dec.get("RŮST"), "stav": test.get("_stav")},
            "firmy": [_trim_card(c) | {"historie": [h for h in history(conn, c["ticker"]) if h["den"] < c["den_ceny"]][:4]}
                      for c in rows[:20]],
        }
    disc = conn.execute("SELECT * FROM discovery_runs ORDER BY id DESC LIMIT 1").fetchone()
    if disc is not None:
        rk = json.loads(disc["result_json"]).get("rakety_6m") or {}
        t = rk.get("test") or {}
        top = (t.get(rk.get("razeni") or "asymetrie") or {}).get("top1") or {}
        firmy = []
        xtb_list = rk.get("kandidati_xtb")       # od v0.8.0: jen akcie z nabídky XTB
        from stockradar.sources.xtb import unique_listing
        for i, c in enumerate(unique_listing(xtb_list if xtb_list is not None else rk.get("kandidati", []))[:20]):
            firmy.append({k: c.get(k) for k in ("ticker", "nazev", "zeme", "obor", "faze", "cena", "mena", "den", "p_raketa",
                                                "p_propad", "percentil", "skupina", "hist_rakety", "hist_propady",
                                                "hist_median", "hist_q20", "hist_q80", "zakladni_cetnost", "proc", "proti",
                                                "rust_3m", "rust_6m", "obrat_usd", "studie", "poradi_celkem", "xtb")}
                         | {"poradi": i + 1, "ledger": _ledger_rocket(conn, c["ticker"])})
        out["h6m"] = {"model": "ROCKET_6M", "horizont": "6 měsíců", "data_do": disc["data_through"], "probehlo": disc["run_at"],
                      "trh": "celý svět", "cil": rk.get("cil"), "propad": rk.get("propad"),
                      "xtb": {"kontrola": xtb_list is not None},
                      "test": {"obdobi": rk.get("test_obdobi"), "zaklad": t.get("zaklad"), "horni_1": top,
                               "auc": t.get("auc_raketa"), "smerova_vyhoda": rk.get("smerova_vyhoda"),
                               "stabilita": rk.get("stabilita")},
                      "firmy": firmy}
    return out or None


def build_zebricek6m_doc(conn: sqlite3.Connection) -> dict | None:
    """Dokument stav/zebricek6m — „Vítězové do 6 měsíců“ z modelu SIGNAL_6M: všechny firmy + zvlášť velké (≥ 10 mld. USD)."""
    from stockradar.signals.store import history
    run = _latest_signal_run(conn, "SIGNAL_6M")
    if run is None:
        return None
    full = json.loads(run["result_json"])
    test = full.get("zamceny_test") or {}
    cards = full.get("karty", [])
    pick = lambda key: [_trim_card(c) | {"historie": [h for h in history(conn, c["ticker"]) if h["den"] < c["den_ceny"]][:3]}
                        for c in sorted((c for c in cards if c.get(key)), key=lambda c: c[key])[:20]]
    return {"model": "SIGNAL_6M", "horizont": full.get("horizont"), "data_do": run["data_through"], "probehlo": run["run_at"],
            "prah_rust": full.get("prah_rust"), "prah_pokles": full.get("prah_pokles"), "akcii": (full.get("dnes") or {}).get("akcii"),
            "trh": "USA (data SEC)", "razeni": full.get("razeni"), "zaklad": full.get("zaklad"), "xtb": full.get("xtb"),
            "silnych": (full.get("dnes") or {}).get("rozhodnuti", {}).get("RŮST"),
            "test": {"auc_rust": (test.get("up5") or {}).get("auc"), "auc_pokles": (test.get("down5") or {}).get("auc"),
                     "zaklad_rust": (test.get("up5") or {}).get("zaklad"), "zaklad_pokles": (test.get("down5") or {}).get("zaklad"),
                     "horni_desetina": test.get("horni_desetina"), "dolni_desetina": test.get("dolni_desetina"),
                     "stav": test.get("_stav")},
            "firmy": pick("poradi"), "velke": pick("poradi_velke"),
            "vyhnout": [_trim_card(c) for c in cards if not c.get("poradi") and not c.get("poradi_velke")
                        and c.get("final") == "POKLES"][:5]}


def build_causal_doc(conn: sqlite3.Connection) -> dict | None:
    """Dokument stav/kauzalni — poslední kauzální radar (karty událostí, řetězce, příležitosti, test řetězců)."""
    r = conn.execute("SELECT * FROM causal_runs ORDER BY id DESC LIMIT 1").fetchone()
    if r is None:
        return None
    full = json.loads(r["result_json"])
    cards = []
    for c in full.get("karty", []):
        z = dict(c.get("zpravy") or {})
        z["titulky"] = (z.get("titulky") or [])[:3]
        cards.append(c | {"retez": (c.get("retez") or [])[:10], "zpravy": z, "udalosti": (c.get("udalosti") or [])[:3]})
    reg = full.get("test_retezcu") or {}
    lt = reg.get("zamceny_test") or {}
    return {"beh": {"id": r["id"], "probehlo": r["run_at"], "data_do": r["data_through"], "verze": r["app_version"]},
            "princip": full.get("princip"), "karty": cards, "prilezitosti": full.get("prilezitosti", [])[:20],
            "historie": full.get("historie"), "gdacs": full.get("gdacs"), "vysledky": full.get("vysledky"),
            "test": {"konfigurace": reg.get("konfigurace"), "pokusu": reg.get("pokusu"),
                     "vyhodnoceno": lt.get("_vyhodnoceno"),
                     "empiricke": {k: (lt.get("empiricke") or {}).get(k) for k in ("uz_v_cene_4t", "1t", "4t", "13t", "26t")},
                     "logicke_rad1": {k: (lt.get("logicke_rad1") or {}).get(k) for k in ("1t", "4t", "13t")},
                     "logicke_rad2_3": {k: (lt.get("logicke_rad2_3") or {}).get(k) for k in ("1t", "4t", "13t")},
                     "placebo": lt.get("placebo")}}


def write_causal_doc(conn: sqlite3.Connection, web_dir: Path) -> int:
    doc = build_causal_doc(conn)
    if doc is None:
        return 0
    web_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode()) > DOC_LIMIT:
        raise ValueError(f"dokument kauzalni má {len(text.encode()) // 1024} kB — překračuje limit db dokumentu")
    (web_dir / "stav_kauzalni.json").write_text(text, encoding="utf-8")
    return len(text.encode())


def write_signals_doc(conn: sqlite3.Connection, web_dir: Path) -> dict[str, int]:
    web_dir.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for name, doc in (("signaly", build_signals_doc(conn)), ("zebricek", build_zebricek_doc(conn)),
                      ("zebricek6m", build_zebricek6m_doc(conn))):
        if doc is None:
            continue
        text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
        if len(text.encode()) > DOC_LIMIT:
            raise ValueError(f"dokument {name} má {len(text.encode()) // 1024} kB — překračuje limit db dokumentu")
        (web_dir / f"stav_{name}.json").write_text(text, encoding="utf-8")
        sizes[name] = len(text.encode())
    return sizes


def write_site_data(conn: sqlite3.Connection, web_dir: Path, **kwargs) -> dict[str, int]:
    web_dir.mkdir(parents=True, exist_ok=True)
    sizes = {}
    docs = build_docs(conn, **kwargs)
    discovery = build_discovery_doc(conn)
    if discovery is not None:
        docs["objevy"] = discovery
    smart = build_smart_money_doc(conn)
    if smart is not None:
        docs["smartmoney"] = smart
    signals = build_signals_doc(conn)
    if signals is not None:
        docs["signaly"] = signals
    ranking = build_zebricek_doc(conn)
    if ranking is not None:
        docs["zebricek"] = ranking
    ranking6 = build_zebricek6m_doc(conn)
    if ranking6 is not None:
        docs["zebricek6m"] = ranking6
    causal = build_causal_doc(conn)
    if causal is not None:
        docs["kauzalni"] = causal
    for name, doc in docs.items():
        text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
        if len(text.encode()) > DOC_LIMIT:
            raise ValueError(f"dokument {name} má {len(text.encode()) // 1024} kB — překračuje limit db dokumentu")
        (web_dir / f"stav_{name}.json").write_text(text, encoding="utf-8")
        sizes[name] = len(text.encode())
    return sizes
