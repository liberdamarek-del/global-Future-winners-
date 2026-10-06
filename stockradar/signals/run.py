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
from stockradar.sources import xtb
from stockradar.timeutil import to_iso, utcnow

MIN_CLASS_ROWS, MIN_CLASS_WEEKS = 5000, 15
TOP_RANK, TOP_DOWN = 20, 5      # žebříček TOP 20 + 5 nejslabších (varování v detailu)


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


def run(cache_conn, main_conn, *, log=print, workers: int = 4, with_news: bool = True, recent_insiders=None,
        models: tuple[str, ...] = ("SIGNAL_14D", "SIGNAL_1M", "SIGNAL_6M"), xtb_check=None) -> dict:
    """Jeden panel, víc modelů (14 dní, 1 měsíc). Každý model má vlastní konfiguraci a vlastní zamčený test.

    `xtb_check(symbol, name)` (sources.xtb.Checker.check): do žebříčku jen akcie, které XTB nabízí (uživatel 2026-10-05)."""
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
    causal = build_causal(cache_conn, data, log=lg) if any(M.SPECS[m].get("features") == "6M" for m in models) else None
    panel = P.build(data, fund, extra, regime, shares=M.share_for, log=lg, causal=causal)
    # dnešní znaky (společné pro všechny modely)
    today = data.data_end
    snap = P.snapshot(data, today)
    rf = regime.features(today)
    rlabel = regime.label(today)
    live_f = []
    for sym, j in snap["idx"].items():
        s = data.secs[sym]
        if today - s.prep.bars.days[j] > 4:
            continue
        f = P.sample(data, s, j, snap["rate"][sym], snap, fund, extra, rf, causal)
        if f is not None:
            live_f.append((sym, j, f))
    shared = {"data": data, "fund": fund, "extra": extra, "regime": regime, "today": today, "rlabel": rlabel,
              "live": live_f, "news": {}, "sm_top": smart_money_top(main_conn), "xtb_check": xtb_check}
    out = {}
    for name in models:
        out[name] = run_model(name, panel, shared, cache_conn, main_conn, log=lg, workers=workers, with_news=with_news)
    mech = mechanism.lead_lag_test(data, periods={"uceni": (data.data_start, M.TRAIN_END),
                                                  "validace_a_test": (M.VAL[0], M.TEST[1])}, log=lg)
    for r in out.values():
        r["mechanismy"] = mech
    return {"_data": data, "modely": out}


def run_model(name, panel, sh, cache_conn, main_conn, *, log, workers, with_news) -> dict:
    spec = M.SPECS[name]
    pv = M.view(panel, name)
    data, fund, regime, today, rlabel = sh["data"], sh["fund"], sh["regime"], sh["today"], sh["rlabel"]
    feats = M.features_of(name)
    cfg = M.config_hash(feats, name)
    split = {"TRAIN": [], "VALIDATION": [], "LOCKED_TEST": [], "POST": [], "LIVE": []}
    labeled = [k for k in range(len(pv)) if pv.y["up5"][k] >= 0]
    last_labeled = max((pv.day[k] for k in labeled), default=0)
    for k in labeled:
        s = M.split_of(pv.day[k], spec["gap"], spec.get("post", True))
        if s:
            split[s].append(k)
    log(f"{name}: " + ", ".join(f"{k} {len(v)} ({M.n_independent(pv, v)} nezávislých)" for k, v in split.items() if v))
    tr, va, te, po = split["TRAIN"], split["VALIDATION"], split["LOCKED_TEST"], split["POST"]

    # 1) učení na TRAIN, meta-model a kalibrace na VALIDATION
    glob1, reg1 = fit_stage(pv, tr, feats, workers=workers, log=log)
    choice, choice_detail = meta_choice(pv, va, glob1, reg1)
    sm1 = M.SignalModel(feats, glob1, reg1, choice)
    va_preds = calibrate_model(pv, sm1, va)
    log(f"{name} meta-model: " + ", ".join(f"{k}={v['volba']}" for k, v in choice_detail.items()))
    tr_preds = [sm1.predict(pv.row(k), M.regime_class(pv.regime[k])) for k in tr]
    ctx1 = C.Context(pv, tr, va, sm1, {}, tr_preds)

    def decider(sm, ctx, rows, preds):
        ref = C.day_reference([pv.day[k] for k in rows], preds)

        def dec(pred, k):
            conf, _ = C.confidence(pred, pv.row(k), pv.regime[k], ctx, sm)
            return C.decide(pred, conf, ctx.base, sm, ref.get(pv.day[k]))
        return dec

    val_metrics = M.evaluate(pv, va, va_preds, decider(sm1, ctx1, va, va_preds))
    val_metrics["poznamka"] = "kalibrace i pásma se počítaly na těchto datech → optimistické; rozhoduje zamčený test"
    store.record_eval(main_conn, name, cfg, "VALIDATION", (_day(M.VAL[0]), _day(M.VAL[1])), val_metrics)

    # 2) LOCKED TEST — jednou pro konfiguraci
    locked = store.locked_result(main_conn, name, cfg)
    if locked is None:
        te_preds = [sm1.predict(pv.row(k), M.regime_class(pv.regime[k])) for k in te]
        test_metrics = M.evaluate(pv, te, te_preds, decider(sm1, ctx1, te, te_preds))
        store.record_eval(main_conn, name, cfg, "LOCKED_TEST", (_day(M.TEST[0]), _day(M.TEST[1])), test_metrics)
        test_metrics["_stav"] = "vyhodnoceno poprvé v tomto běhu"
        log(f"{name}: ZAMČENÝ TEST vyhodnocen poprvé a zapsán do registru")
    else:
        test_metrics = locked
        test_metrics["_stav"] = f"načteno z registru (vyhodnoceno {locked['_vyhodnoceno']}) — znovu se nepočítá"
        log(f"{name}: ZAMČENÝ TEST už vyhodnocen → jen načteno")
    gap_ev = {"validace": gap_evidence(pv, va), "test": gap_evidence(pv, te)}

    # 3) finální model: TRAIN + VALIDATION + TEST, kalibrace na POST (data po testu, model je neviděl)
    hist = tr + va + te
    glob2, reg2 = fit_stage(pv, hist, feats, choice, workers=workers, log=log)
    sm2 = M.SignalModel(feats, glob2, reg2, choice)
    po_preds = calibrate_model(pv, sm2, po) if len(po) >= 3000 else None
    if po_preds is None:                     # málo dat po testu → kalibrace z validace prvního modelu
        sm2.cal, sm2.bands = sm1.cal, sm1.bands
    hist_preds = [sm2.predict(pv.row(k), M.regime_class(pv.regime[k])) for k in hist]
    ctx2 = C.Context(pv, hist, po, sm2, {}, hist_preds)
    post_metrics = M.evaluate(pv, po, po_preds, decider(sm2, ctx2, po, po_preds)) if po_preds else {"vzorku": len(po)}
    if po_preds:
        post_metrics["poznamka"] = "finální model; kalibrace na těchto datech (rozlišení je mimo vzorek)"
        store.record_eval(main_conn, name, cfg, "POST", (_day(M.POST_START), _day(last_labeled)), post_metrics)
    log(f"{name}: finální model naučen a zkalibrován")

    # 4) dnešní žebříček a karty
    live = []
    for sym, j, f in sh["live"]:
        pred = sm2.predict(f, M.regime_class(rlabel))
        conf, pen = C.confidence(pred, f, rlabel, ctx2, sm2)
        live.append({"sym": sym, "j": j, "f": f, "pred": pred, "conf": conf, "pen": pen,
                     "contrib": C.contributions(sm2, f)})
    ref_today = {"up5": statistics.median(x["pred"]["up5"] for x in live),
                 "down5": statistics.median(x["pred"]["down5"] for x in live)} if live else None
    for x in live:
        x["dec"], x["why"] = C.decide(x["pred"], x["conf"], ctx2.base, sm2, ref_today)
    log(f"{name} dnes ({_day(today)}): {len(live)} akcií, rozhodnutí " +
        str({d: sum(1 for x in live if x["dec"] == d) for d in ("RŮST", "POKLES", "NEVÍM")}))
    dist = {g: sorted(x["contrib"][g] for x in live) for g in C.groups_for(feats)}
    gap_sorted = sorted(x["f"]["gap"] for x in live if C.finite(x["f"].get("gap")))
    # pořadí žebříčku: šance na růst, ale jen u akcií, kde model vidí víc růstu než poklesu (vybráno na VALIDACI
    # 2026-10-05 ze 3 předem daných pravidel podle týdenních TOP 20: nejvyšší šance na růst při riziku poklesu blízko
    # průměru; zamčený test se k výběru nepoužil)
    rkey, rrule = (rank_key_up, RANK_RULE_UP) if spec.get("rank") == "up" else (rank_key, RANK_RULE)
    by_dir = sorted(live, key=rkey, reverse=True)
    name_of = lambda x: data.secs[x["sym"]].meta.get("name")
    top, xtb_info = pick_tradable(by_dir, sh["xtb_check"], name_of, TOP_RANK)
    log(f"{name}: XTB — {xtb_info}")
    large = []
    if spec.get("features") == "6M":        # „další Microsoft“: zvlášť velké firmy (kapitalizace ≥ 10 mld. USD)
        big = [x for x in by_dir if (x["f"].get("log_mcap") or 0) >= LARGE_LOG_MCAP]
        large, large_info = pick_tradable(big, sh["xtb_check"], name_of, TOP_RANK)
        xtb_info["velke_firmy"] = large_info
    worst = sorted(live, key=lambda x: (x["pred"]["dir"], -x["pred"]["down5"]))
    chosen = top + [x for x in large if x not in top]
    chosen += [x for x in worst if x not in chosen][:TOP_DOWN]
    analogs = C.Analogs(pv, hist + po)
    cards = []
    for pos, x in enumerate(chosen):
        c = build_card(x, data, fund, cache_conn, main_conn, sm2, ctx2, analogs, dist, gap_sorted, rlabel,
                       today, sh["sm_top"], with_news, spec, sh["news"])
        c["poradi"] = pos + 1 if pos < len(top) else None
        c["poradi_velke"] = large.index(x) + 1 if x in large else None
        c["poradi_celkem"] = x.get("poradi_celkem")
        c["xtb"] = xtb.badge(x.get("xtb_row")) if (x in top or x in large) and sh["xtb_check"] else None
        c["model"] = name
        cards.append(c)
    log(f"{name}: karty {len(cards)}")
    return {
        "vytvoreno": to_iso(utcnow()), "data_do": _day(today), "model": name, "horizont": spec["nazev"],
        "obchodnich_dni": spec["h"], "prah_rust": spec["up"], "prah_pokles": spec["down"], "prah_prudky": spec["big"],
        "verze_modelu": M.MODEL_VERSION, "konfigurace": cfg, "razeni": rrule,
        "protokol": {"train_do": _day(M.TRAIN_END), "validace": [_day(M.VAL[0]), _day(M.VAL[1])],
                     "zamceny_test": [_day(M.TEST[0]), _day(M.TEST[1])], "post": [_day(M.POST_START), _day(last_labeled)],
                     "mezera_dni": spec["gap"] or 21, "pokusu_na_testu": store.locked_attempts(main_conn, name)},
        "vzorky": {k: {"n": len(v), "nezavislych": M.n_independent(pv, v),
                       "tydnu": len({M.week(pv.day[kk]) for kk in v})} for k, v in split.items() if v},
        "znaky": {g: [{"znak": f, "nazev": P.ALL_FEATURES[f]} for f in fs] for g, fs in C.groups_for(feats).items()},
        "meta_model": choice_detail, "kalibrace": {t: sm2.cal[t] for t in sm2.cal}, "pasma": sm2.bands,
        "zaklad": ctx2.base, "validace": val_metrics, "zamceny_test": test_metrics, "post": post_metrics,
        "mispricing_dukaz": gap_ev, "rezim": regime.describe(today),
        "dnes": {"akcii": len(live), "rozhodnuti": {d: sum(1 for x in live if x["dec"] == d) for d in ("RŮST", "POKLES", "NEVÍM")},
                 "median_p_up": round(ref_today["up5"], 4) if ref_today else None,
                 "median_p_down": round(ref_today["down5"], 4) if ref_today else None,
                 "plosny_posun_modelu": market_warning(ref_today, ctx2.base)},
        "trh": market_view(regime, today),
        "karty": cards,
        "xtb": xtb_info,
        # celé pořadí modelu (všechny dnešní akcie) — „kde je moje firma“, i když není v TOP 20
        "poradi_vse": ",".join(x["sym"] for x in by_dir),
        "vahy": {t: sorted(({"znak": f, "nazev": P.ALL_FEATURES[f], "koef": round(w, 3)}
                            for f, w in zip(sm2.glob[t].features, sm2.glob[t].w)), key=lambda x: -abs(x["koef"]))[:12]
                 for t in ("up5", "down5")},
        "insideri_sec_do": _day(sh["extra"].insider_source_end),
    }


def pick_tradable(ordered: list[dict], check, name_of, n: int, max_checks: int = 600) -> tuple[list[dict], dict]:
    """Prvních `n` firem v pořadí modelu, které XTB nabízí jako akcie (bez kontroly = prvních n). Pořadí se nemění,
    jen se přeskočí firmy mimo nabídku; každá vybraná nese své celkové pořadí (`poradi_celkem`)."""
    for pos, x in enumerate(ordered, 1):
        x.setdefault("poradi_celkem", pos)          # u podseznamu (velké firmy) zůstává pořadí v celém modelu
    if check is None:
        return ordered[:n], {"kontrola": False}
    chosen, skipped = [], {"NE": 0, "CFD": 0, "NEOVĚŘENO": 0}
    for x in ordered[:max_checks]:
        if len(chosen) >= n:
            break
        row = check(x["sym"], name_of(x))
        if row and row["status"] == "AKCIE":
            x["xtb_row"] = row
            chosen.append(x)
        else:
            skipped[row["status"] if row else "NEOVĚŘENO"] += 1
    return chosen, {"kontrola": True, "prohledano": sum(skipped.values()) + len(chosen), "vybrano": len(chosen),
                    "preskoceno": skipped}


LARGE_LOG_MCAP = math.log(10e9)


def build_causal(cache_conn, data, *, log=print):
    from stockradar.causal.chains import build_features
    return build_features(cache_conn, data, log=log)


RANK_RULE = "šance na růst; jen akcie, kde model vidí víc růstu než poklesu; při stejné šanci menší riziko poklesu"


def rank_key(x: dict) -> tuple:
    """Pravidlo vybrané na VALIDACI (docs/SIGNALS_2026-10-05.md, kap. 7): kalibrovaná šance na růst, jen když je vyšší
    než šance na pokles; při shodě (kalibrace je v horním pásmu plochá) rozhoduje rozdíl růst − pokles, tj. menší
    riziko poklesu. Řazení podle surového skóre vybíralo nejrozkolísanější akcie a na validaci ověřené nebylo."""
    p = x["pred"]
    return (p["up5"] if p["up5"] > p["down5"] else -1.0, p["dir"])


RANK_RULE_UP = ("šance na růst o 40 % (pořadí podle skóre modelu); POZOR: u těchto firem je vyšší i riziko poklesu — "
                "na validaci TOP 20 týdně: +40 % ve 14 % případů (běžně 6,5 %), −25 % ve 38 % (běžně 21 %)")


def rank_key_up(x: dict) -> tuple:
    """6 měsíců (vybráno na VALIDACI 2026-10-06 z 5 předem daných pravidel): jediné pravidlo, které zvýšilo šanci na
    +40 % (2,2× základ); žádné pravidlo nezvýšilo šanci bez vyššího rizika pádu → riziko se vždy ukazuje vedle."""
    p = x["pred"]
    return (p["up5"], p["raw"]["up5"])


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
               with_news, spec=None, news_cache=None) -> dict:
    sym, f, pred = x["sym"], x["f"], x["pred"]
    s = data.secs[sym]
    band = M.band_of(sm.bands, pred["dir"])
    picked = analogs.find(f, rlabel, before=today - 15)
    an = analogs.summary(picked)
    cats = catalysts_for(sym, fund, cache_conn, main_conn, today)
    score = {g: C.percentile(dist[g], x["contrib"][g]) for g in dist}
    mis = C.percentile(gap_sorted, f["gap"]) if C.finite(f.get("gap")) else None
    smi = sm_top.get(sym)
    spec = spec or M.SPECS["SIGNAL_14D"]
    if not with_news:
        info = {"stav": "nezjišťováno"}
    elif news_cache is not None and sym in news_cache:
        info = news_cache[sym]
    else:
        info = news.for_symbol(s.meta.get("name") or sym, sym, date.fromordinal(today))
        if news_cache is not None:
            news_cache[sym] = info
    j = x["j"]
    c = s.prep.bars.closes
    card = {
        "ticker": sym, "firma": s.meta.get("name"), "obor": s.group, "sektor": s.meta.get("sector"),
        "zeme": s.meta.get("country"), "horizont": spec["nazev"], "obchodnich_dni": spec["h"],
        "prah_rust": spec["up"], "prah_pokles": spec["down"], "prah_prudky": spec["big"],
        "cena": round(c[j], 4), "den_ceny": s.prep.bars.date(j), "rezim": rlabel,
        "p_up": round(pred["up5"], 4), "p_down": round(pred["down5"], 4), "p_flat": round(pred["flat"], 4),
        "p_obor": round(pred["beat_sec"], 4), "p_prudky": round(pred["big"], 4),
        "potencial": (an["horizonty"].get(str(spec["h"])) or {}).get("q80"),
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
        "katalyzatory": cats[:4], "ocekavany_cas": (cats[0]["okno"] if cats and (cats[0]["dni_do"] or 99) <= spec["h"] * 3
                                                     else f"horizont {spec['h']} obchodních dní"),
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
