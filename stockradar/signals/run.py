"""Celý běh signálního enginu: panel → učení → validace → zamčený test → finální model → karty → záznam."""

import math
import statistics
import time
from datetime import date

from stockradar.discovery import study
from stockradar.discovery.fundamentals import Fundamentals
from stockradar.signals import card as C
from stockradar.signals import mechanism, news
from stockradar.signals import model as M
from stockradar.signals import panel as P
from stockradar.signals import store
from stockradar.signals.extra import Extra, Spy
from stockradar.signals.regime import Regime, load_series, market_view
from stockradar.timeutil import to_iso, utcnow

MIN_CLASS_ROWS, MIN_CLASS_WEEKS = 5000, 15
TOP_UP, TOP_DOWN = 12, 5


def _day(d: int) -> str:
    return study.day_str(d)


def _labeled(panel, rows, t="up5"):
    return [k for k in rows if panel.y[t][k] >= 0]


def fit_stage(panel, rows, feats, choice=None, *, workers, log):
    """Globální model a modely tříd režimu pro každý cíl (u finálu jen ty, které meta-model vybral)."""
    jobs = {}
    for t in M.TARGETS:
        jobs[("g", t)] = (rows, t, feats)
        for c in M.CLASSES:
            rr = [k for k in rows if M.regime_class(panel.regime[k]) == c]
            weeks = len({M.week(panel.day[k]) for k in rr})
            if len(rr) < MIN_CLASS_ROWS or weeks < MIN_CLASS_WEEKS:
                continue
            if choice is not None and choice.get((t, c), "global") == "global":
                continue
            jobs[("r", t, c)] = (rr, t, feats)
    res = M.train_many(panel, jobs, workers=workers, log=log)
    glob = {t: res[("g", t)] for t in M.TARGETS}
    reg = {(k[1], k[2]): m for k, m in res.items() if k[0] == "r"}
    return glob, reg


def meta_choice(panel, rows, glob, reg) -> tuple[dict, dict]:
    """Na validaci: pro každý cíl a třídu režimu model s nejnižší log-ztrátou (globální / režimový / průměr)."""
    choice, detail = {}, {}
    for t in M.TARGETS:
        for c in M.CLASSES:
            rr = [k for k in rows if panel.y[t][k] >= 0 and M.regime_class(panel.regime[k]) == c]
            if not rr:
                continue
            ll = {"global": [], "rezim": [], "prumer": []}
            for k in rr:
                f = panel.row(k)
                g = glob[t].prob(f)
                y = panel.y[t][k]
                ll["global"].append(M.logloss(g, y))
                if (t, c) in reg:
                    r = reg[(t, c)].prob(f)
                    ll["rezim"].append(M.logloss(r, y))
                    ll["prumer"].append(M.logloss((g + r) / 2, y))
            scores = {k: statistics.fmean(v) for k, v in ll.items() if v}
            best = min(scores, key=scores.get)
            choice[(t, c)] = best
            detail[f"{t}|{c}"] = {"volba": best, "logloss": {k: round(v, 5) for k, v in scores.items()},
                                  "vzorku": len(rr), "nezavislych": M.n_independent(panel, rr)}
    return choice, detail


def calibrate_model(panel, sm: M.SignalModel, rows) -> list[dict]:
    raw = {t: [] for t in M.TARGETS}
    idx = {t: [] for t in M.TARGETS}
    for k in rows:
        r = sm.raw(panel.row(k), M.regime_class(panel.regime[k]))
        for t in M.TARGETS:
            if panel.y[t][k] >= 0:
                raw[t].append(r[t]["p"])
                idx[t].append(k)
    sm.cal = {t: M.calibrate(raw[t], [panel.y[t][k] for k in idx[t]], panel, idx[t]) for t in M.TARGETS}
    preds = [sm.predict(panel.row(k), M.regime_class(panel.regime[k])) for k in rows]
    sm.bands = M.direction_bands(panel, rows, preds)
    return preds


def gap_evidence(panel, rows) -> dict:
    """Bod 3–4: mají akcie s „výsledky lepšími, než trh ocenil“ (gap) v dalších 14 dnech lepší výsledek?"""
    rr = [k for k in rows if panel.cols["gap"][k] == panel.cols["gap"][k] and panel.ex_sec[k] == panel.ex_sec[k]]
    if len(rr) < 500:
        return {"n": len(rr)}
    rr.sort(key=lambda k: panel.cols["gap"][k])
    q = len(rr) // 5
    top, bot = rr[-q:], rr[:q]
    mean_all = statistics.fmean(panel.ex_sec[k] for k in rr)
    diffs = [panel.ex_sec[k] - mean_all for k in top]
    t = M.weekly_t(panel, top, diffs)
    return {"n": len(rr), "nezavislych": M.n_independent(panel, rr),
            "horni_petina_nad_oborem": round(statistics.fmean(panel.ex_sec[k] for k in top), 4),
            "dolni_petina_nad_oborem": round(statistics.fmean(panel.ex_sec[k] for k in bot), 4),
            "t_horni": t, "sum": M.p_from_t(t)}


def catalysts_for(sym, fund, cache_conn, main_conn, today: int) -> list[dict]:
    out = []
    cik = fund.cik.get(sym)
    if cik is not None:
        reps = fund.filings.get(cik, {}).get("REPORT", [])
        last = max((d for d in reps if d <= today), default=None)
        if last is not None:
            lo, hi = last + 80, last + 100
            while hi < today:
                lo, hi = lo + 91, hi + 91
            out.append({"typ": "výsledky (10-Q/10-K)", "okno": f"{_day(lo)} … {_day(hi)}", "jistota": "ESTIMATED",
                        "duvera": 60, "dni_do": max(0, lo - today), "zdroj": f"poslední podání {_day(last)} + ~3 měsíce"})
    for t in fund.upcoming_trials(cache_conn, sym, today, 90):
        out.append({"typ": f"klinická studie {t.get('phase')}", "okno": t.get("pcd"), "jistota": t.get("pcd_type") or "ESTIMATED",
                    "duvera": 50, "dni_do": date.fromisoformat(t["pcd"][:10] if len(t["pcd"]) >= 10 else t["pcd"] + "-15")
                    .toordinal() - today, "zdroj": f"ClinicalTrials.gov {t.get('nct')}"})
    for r in main_conn.execute(
            "SELECT c.description, c.date_status, c.event_date, c.window_start, c.window_end, c.source_url"
            " FROM catalysts c JOIN listings l ON l.company_id = c.company_id"
            " WHERE l.yahoo_symbol = ? AND c.status = 'UPCOMING'", (sym,)):
        okno = r["event_date"] or f"{r['window_start']} … {r['window_end']}"
        conf = {"VERIFIED": 90, "ESTIMATED": 60, "UNCERTAIN": 40}.get(r["date_status"], 30)
        out.append({"typ": r["description"], "okno": okno, "jistota": r["date_status"], "duvera": conf,
                    "dni_do": None, "zdroj": r["source_url"]})
    out.sort(key=lambda c: (c["dni_do"] is None, c["dni_do"] if c["dni_do"] is not None else 0))
    return out


def run(cache_conn, main_conn, *, log=print, workers: int = 4, with_news: bool = True, recent_insiders=None) -> dict:
    t0 = time.time()
    lg = lambda m: log(f"[{round(time.time() - t0)} s] {m}")
    data = study.load_data(cache_conn)
    us = {s for s in data.secs if P.is_us(s)}
    fund = Fundamentals(cache_conn, us)
    spy = load_series(main_conn, "SPY")
    extra = Extra(cache_conn, fund, Spy(spy.days, spy.values),
                  lambda s: data.secs[s].prep.bars if s in data.secs else None, recent_insiders=recent_insiders)
    regime = Regime.from_db(main_conn)
    lg(f"Data: {len(data.secs)} firem, z toho US {len(us)}; insideři ze SEC do {_day(extra.insider_source_end)}")
    panel = P.build(data, fund, extra, regime, shares=M.share_for, log=lg)
    feats = list(P.MODEL_FEATURES)
    cfg = M.config_hash(feats)
    split = {"TRAIN": [], "VALIDATION": [], "LOCKED_TEST": [], "POST": [], "LIVE": []}
    last_labeled = max((panel.day[k] for k in range(len(panel)) if panel.y["up5"][k] >= 0), default=0)
    for k in range(len(panel)):
        s = M.split_of(panel.day[k])
        if s and panel.y["up5"][k] >= 0:
            split[s].append(k)
    lg("Rozdělení: " + ", ".join(f"{k} {len(v)} ({M.n_independent(panel, v)} nezávislých)" for k, v in split.items() if v))
    tr, va, te, po = split["TRAIN"], split["VALIDATION"], split["LOCKED_TEST"], split["POST"]

    # 1) učení na TRAIN, meta-model a kalibrace na VALIDATION
    glob1, reg1 = fit_stage(panel, tr, feats, workers=workers, log=lg)
    choice, choice_detail = meta_choice(panel, va, glob1, reg1)
    sm1 = M.SignalModel(feats, glob1, reg1, choice)
    va_preds = calibrate_model(panel, sm1, va)
    lg("Meta-model: " + ", ".join(f"{k}={v['volba']}" for k, v in choice_detail.items()))
    tr_preds = [sm1.predict(panel.row(k), M.regime_class(panel.regime[k])) for k in tr]
    ctx1 = C.Context(panel, tr, va, sm1, {}, tr_preds)

    def decider(sm, ctx, rows, preds):
        ref = C.day_reference([panel.day[k] for k in rows], preds)

        def dec(pred, k):
            f = panel.row(k)
            conf, _ = C.confidence(pred, f, panel.regime[k], ctx, sm)
            return C.decide(pred, conf, ctx.base, sm, ref.get(panel.day[k]))
        return dec

    val_metrics = M.evaluate(panel, va, va_preds, decider(sm1, ctx1, va, va_preds))
    val_metrics["poznamka"] = "kalibrace i pásma se počítaly na těchto datech → optimistické; rozhoduje zamčený test"
    store.record_eval(main_conn, M.MODEL_NAME, cfg, "VALIDATION", (_day(M.VAL[0]), _day(M.VAL[1])), val_metrics)

    # 2) LOCKED TEST — jednou pro konfiguraci
    locked = store.locked_result(main_conn, M.MODEL_NAME, cfg)
    if locked is None:
        te_preds = [sm1.predict(panel.row(k), M.regime_class(panel.regime[k])) for k in te]
        test_metrics = M.evaluate(panel, te, te_preds, decider(sm1, ctx1, te, te_preds))
        store.record_eval(main_conn, M.MODEL_NAME, cfg, "LOCKED_TEST", (_day(M.TEST[0]), _day(M.TEST[1])), test_metrics)
        test_metrics["_stav"] = "vyhodnoceno poprvé v tomto běhu"
        lg("ZAMČENÝ TEST vyhodnocen poprvé a zapsán do registru")
    else:
        test_metrics = locked
        test_metrics["_stav"] = f"načteno z registru (vyhodnoceno {locked['_vyhodnoceno']}) — znovu se nepočítá"
        lg("ZAMČENÝ TEST: konfigurace už vyhodnocena → jen načteno")
    gap_ev = {"validace": gap_evidence(panel, va), "test": gap_evidence(panel, te)}

    # 3) finální model: TRAIN + VALIDATION + TEST, kalibrace na POST (data po testu, model je neviděl)
    hist = tr + va + te
    glob2, reg2 = fit_stage(panel, hist, feats, choice, workers=workers, log=lg)
    sm2 = M.SignalModel(feats, glob2, reg2, choice)
    po_preds = calibrate_model(panel, sm2, po) if len(po) >= 3000 else None
    if po_preds is None:                     # málo dat po testu → kalibrace z validace prvního modelu
        sm2.cal, sm2.bands = sm1.cal, sm1.bands
    hist_preds = [sm2.predict(panel.row(k), M.regime_class(panel.regime[k])) for k in hist]
    ctx2 = C.Context(panel, hist, po, sm2, {}, hist_preds)
    post_metrics = M.evaluate(panel, po, po_preds, decider(sm2, ctx2, po, po_preds)) if po_preds else {"vzorku": len(po)}
    if po_preds:
        post_metrics["poznamka"] = "finální model; kalibrace na těchto datech (rozlišení je mimo vzorek)"
        store.record_eval(main_conn, M.MODEL_NAME, cfg, "POST", (_day(M.POST_START), _day(last_labeled)), post_metrics)
    lg("Finální model naučen a zkalibrován")

    # 4) dnešní karty
    today = data.data_end
    snap = P.snapshot(data, today)
    rf = regime.features(today)
    rlabel = regime.label(today)
    live = []
    for sym, j in snap["idx"].items():
        s = data.secs[sym]
        if today - s.prep.bars.days[j] > 4:
            continue
        f = P.sample(data, s, j, snap["rate"][sym], snap, fund, extra, rf)
        if f is None:
            continue
        pred = sm2.predict(f, M.regime_class(rlabel))
        conf, pen = C.confidence(pred, f, rlabel, ctx2, sm2)
        live.append({"sym": sym, "j": j, "f": f, "pred": pred, "conf": conf, "pen": pen,
                     "contrib": C.contributions(sm2, f)})
    ref_today = {"up5": statistics.median(x["pred"]["up5"] for x in live),
                 "down5": statistics.median(x["pred"]["down5"] for x in live)} if live else None
    for x in live:
        x["dec"], x["why"] = C.decide(x["pred"], x["conf"], ctx2.base, sm2, ref_today)
    lg(f"Dnes ({_day(today)}): {len(live)} akcií, rozhodnutí " +
       str({d: sum(1 for x in live if x["dec"] == d) for d in ("RŮST", "POKLES", "NEVÍM")}))
    dist = {g: sorted(x["contrib"][g] for x in live) for g in P.FEATURE_GROUPS}
    gap_sorted = sorted(x["f"]["gap"] for x in live if C.finite(x["f"].get("gap")))
    by_dir = sorted(live, key=lambda x: x["pred"]["dir"], reverse=True)
    chosen = [x for x in by_dir if x["dec"] == "RŮST"][:TOP_UP]
    if len(chosen) < TOP_UP:                       # doplnit nejsilnější NEVÍM, ať je vidět, proč model odmítl
        chosen += [x for x in by_dir if x not in chosen][:TOP_UP - len(chosen)]
    chosen += [x for x in reversed(by_dir) if x not in chosen][:TOP_DOWN]
    sm_top = smart_money_top(main_conn)
    analogs = C.Analogs(panel, hist + po)
    cards = []
    for x in chosen:
        cards.append(build_card(x, data, fund, cache_conn, main_conn, sm2, ctx2, analogs, dist, gap_sorted, rlabel,
                                today, sm_top, with_news))
    lg(f"Karty: {len(cards)}")
    mech = mechanism.lead_lag_test(data, periods={"uceni": (data.data_start, M.TRAIN_END),
                                                  "validace_a_test": (M.VAL[0], M.TEST[1])}, log=lg)
    result = {
        "vytvoreno": to_iso(utcnow()), "data_do": _day(today), "model": M.MODEL_NAME, "verze_modelu": M.MODEL_VERSION,
        "konfigurace": cfg, "protokol": {"train_do": _day(M.TRAIN_END), "validace": [_day(M.VAL[0]), _day(M.VAL[1])],
                                         "zamceny_test": [_day(M.TEST[0]), _day(M.TEST[1])],
                                         "post": [_day(M.POST_START), _day(last_labeled)],
                                         "pokusu_na_testu": store.locked_attempts(main_conn, M.MODEL_NAME)},
        "vzorky": {k: {"n": len(v), "nezavislych": M.n_independent(panel, v),
                       "tydnu": len({M.week(panel.day[kk]) for kk in v})} for k, v in split.items() if v},
        "znaky": {g: [{"znak": f, "nazev": P.ALL_FEATURES[f]} for f in fs] for g, fs in P.FEATURE_GROUPS.items()},
        "meta_model": choice_detail, "kalibrace": {t: sm2.cal[t] for t in sm2.cal}, "pasma": sm2.bands,
        "zaklad": ctx2.base, "validace": val_metrics, "zamceny_test": test_metrics, "post": post_metrics,
        "mispricing_dukaz": gap_ev, "rezim": regime.describe(today), "mechanismy": mech,
        "dnes": {"akcii": len(live), "rozhodnuti": {d: sum(1 for x in live if x["dec"] == d) for d in ("RŮST", "POKLES", "NEVÍM")},
                 "median_p_up": round(ref_today["up5"], 4) if ref_today else None,
                 "median_p_down": round(ref_today["down5"], 4) if ref_today else None,
                 "plosny_posun_modelu": market_warning(ref_today, ctx2.base)},
        "trh": market_view(regime, today),
        "karty": cards,
        "vahy": {t: sorted(({"znak": f, "nazev": P.ALL_FEATURES[f], "koef": round(w, 3)}
                            for f, w in zip(sm2.glob[t].features, sm2.glob[t].w)), key=lambda x: -abs(x["koef"]))[:12]
                 for t in ("up5", "down5")},
        "insideri_sec_do": _day(extra.insider_source_end),
    }
    result["_data"] = data
    return result


def market_warning(ref: dict | None, base: dict) -> str:
    """Plošný posun celého trhu (typicky vlivem režimu) se hlásí zvlášť, ne jako signál u každé akcie."""
    if not ref:
        return "NEOVĚŘENO"
    d_up, d_dn = ref["up5"] - base["up5"], ref["down5"] - base["down5"]
    if d_dn >= 0.05 and d_dn > d_up:
        return f"model čeká u průměrné akcie vyšší riziko poklesu než obvykle (P(−5 %) {ref['down5']:.0%} vs běžně {base['down5']:.0%})"
    if d_up >= 0.05 and d_up > d_dn:
        return f"model čeká u průměrné akcie vyšší šanci na růst než obvykle (P(+5 %) {ref['up5']:.0%} vs běžně {base['up5']:.0%})"
    return "trh bez výrazného plošného posunu"


def smart_money_top(main_conn) -> dict:
    import json
    r = main_conn.execute("SELECT result_json FROM smart_money_runs ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return {}
    res = json.loads(r[0])
    return {s["ticker"]: {"skore": s["skore"], "verdikt": s["verdikt"], "kdo": s["funkce"], "zverejneno": s["zverejneno"]}
            for s in (res.get("aktualni") or {}).get("top", [])}


def build_card(x, data, fund, cache_conn, main_conn, sm, ctx, analogs, dist, gap_sorted, rlabel, today, sm_top,
               with_news) -> dict:
    sym, f, pred = x["sym"], x["f"], x["pred"]
    s = data.secs[sym]
    band = M.band_of(sm.bands, pred["dir"])
    picked = analogs.find(f, rlabel, before=today - 15)
    an = analogs.summary(picked)
    cats = catalysts_for(sym, fund, cache_conn, main_conn, today)
    score = {g: C.percentile(dist[g], x["contrib"][g]) for g in dist}
    mis = C.percentile(gap_sorted, f["gap"]) if C.finite(f.get("gap")) else None
    smi = sm_top.get(sym)
    info = news.for_symbol(s.meta.get("name") or sym, sym, date.fromordinal(today)) if with_news else {"stav": "nezjišťováno"}
    j = x["j"]
    c = s.prep.bars.closes
    card = {
        "ticker": sym, "firma": s.meta.get("name"), "obor": s.group, "sektor": s.meta.get("sector"),
        "cena": round(c[j], 4), "den_ceny": s.prep.bars.date(j), "rezim": rlabel,
        "p_up": round(pred["up5"], 4), "p_down": round(pred["down5"], 4), "p_flat": round(pred["flat"], 4),
        "p_obor": round(pred["beat_sec"], 4), "p_prudky": round(pred["big"], 4),
        "ocekavany_pohyb": band.get("vynos_prumer"), "pohyb_median": band.get("vynos_median"),
        "pohyb_q20": band.get("vynos_q20"), "pohyb_q80": band.get("vynos_q80"), "nad_oborem": band.get("nad_oborem"),
        "sance_sum": band.get("sum"), "pasmo": band.get("pasmo"), "pasmo_nezavislych": band.get("n_indep"),
        "duvera": x["conf"], "nejistota": 100 - x["conf"], "penalizace": [{"duvod": r, "body": b} for r, b in x["pen"]],
        "final": x["dec"], "proc": x["why"],
        "skore": {"fundament": score["fundament"], "technika": score["technika"], "kapitalovy_tok": score["kapital"],
                  "katalyzator": score["katalyzator"], "mechanismus": score["mechanismus"]},
        "mispricing": mis, "smart_money": smi,
        "insideri": {"nakupujicich_30d": f.get("ins_n30"), "hodnota_90d_log10": f.get("ins_val90")},
        "prekvapeni": {"eps_chg_p": f.get("eps_chg_p"), "sue": f.get("sue"), "reakce_trhu": f.get("ear"),
                       "drift": f.get("drift"), "dni_od_vysledku": f.get("days_since_ann")},
        "relativni_sila": {"vuci_oboru_tyden": f.get("rel_r5"), "vuci_oboru_mesic": f.get("rel_r20"),
                           "obor_mesic": f.get("sec_r20"), "akcie_mesic": f.get("r20")},
        "katalyzatory": cats[:4], "ocekavany_cas": (cats[0]["okno"] if cats and (cats[0]["dni_do"] or 99) <= 30
                                                     else f"horizont {P.H} obchodních dní"),
        "analogie": an, "informace": info,
        "mechanismus": [m["nazev"] for m in mechanism.MECHANISMS if any(s.group in lay for lay in m["vrstvy"])],
    }
    for k, v in list(card.items()):
        if isinstance(v, float) and not math.isfinite(v):
            card[k] = None
    return card


def clean(obj):
    """JSON bez NaN/∞ (SQLite json_valid je odmítá)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj
