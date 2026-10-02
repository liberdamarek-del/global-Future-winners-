"""PROVEĎ GLOBAL DISCOVERY (§61): vítězové → příčiny → vzory → sektory → kandidáti → ledger.

python -m stockradar discover [--news 150]
"""

import bisect
import json
import statistics
from collections import Counter
from datetime import date, datetime, timedelta

from stockradar.discovery import cache, news, study
from stockradar.discovery.features import FEATURES
from stockradar.discovery.winners import DROP_OF, EVENT_TYPES, TRAILING, find_events, outcome_label, phase, trailing_returns
from stockradar.timeutil import to_iso, utcnow

MODEL_FEATURES = [f for f in FEATURES]
MODELS = {"W1_30": "raketa do týdne (≥ +30 % za 5 dní)", "M3_50": "raketa do 3 měsíců (≥ +50 % za 63 dní)"}
TRAIN_CUTOFF = date(2025, 4, 1)
KNOWN_CASES = {"CAPR": "CAPR test", "NBIS": "Nebius test", "MRNA": "Moderna test", "OKLO": "Oklo (AI → jádro)",
               "SMR": "NuScale (SMR)", "LEU": "Centrus (palivo)"}

WHY_TEXT = {
    "r5": "pohyb za 5 dní", "r20": "pohyb za 20 dní", "r60": "pohyb za 60 dní", "r120": "pohyb za 120 dní",
    "r250": "pohyb za rok", "dd252": "odstup od ročního maxima", "up252": "výška nad ročním minimem",
    "vol20": "volatilita", "vol_ratio": "stlačení volatility", "volu_5_60": "objem posledních 5 dní vs 60 dní",
    "volu_20_120": "objem 20 dní vs 120 dní", "turnover": "obrat (velikost)", "price": "cena za akcii",
    "max_day20": "největší denní skok za 20 dní", "new_listing": "nová firma na burze",
    "sector_heat": "rakety v oboru za poslední měsíc", "market_heat": "rakety na trhu za poslední měsíc",
}


def fmt_value(feat: str, v) -> str:
    if v is None:
        return "–"
    if feat in ("r5", "r20", "r60", "r120", "r250", "dd252", "up252", "max_day20"):
        return f"{v * 100:+.0f} %"
    if feat in ("volu_5_60", "volu_20_120", "vol_ratio"):
        return f"{v:.1f}×"
    if feat in ("sector_heat", "market_heat"):
        return f"{v * 100:.1f} %"
    if feat == "turnover":
        return f"{2.718281828 ** v / 1e6:.1f} mil. USD/den"
    if feat == "price":
        return f"{2.718281828 ** v:.2f} USD"
    if feat == "vol20":
        return f"{v * 100:.1f} % denně"
    if feat == "new_listing":
        return "ano" if v else "ne"
    return f"{v:.2f}"


def why_lists(model: study.Logit, f: dict) -> tuple[list[str], list[str]]:
    contrib = sorted(model.contributions(f).items(), key=lambda kv: kv[1], reverse=True)
    now = [f"{WHY_TEXT[k]}: {fmt_value(k, f.get(k))}" for k, v in contrib[:3] if v > 0.05]
    nope = [f"{WHY_TEXT[k]}: {fmt_value(k, f.get(k))}" for k, v in contrib[::-1][:2] if v < -0.05]
    return now, nope


def risk_flags(f: dict, trailing: dict) -> list[str]:
    flags = []
    if f.get("price") is not None and 2.718281828 ** f["price"] < 2:
        flags.append("cena pod 2 USD (penny riziko, §22)")
    if f.get("turnover") is not None and 2.718281828 ** f["turnover"] < 1e6:
        flags.append("nízká likvidita (< 1 mil. USD denně)")
    if f.get("vol20") and f["vol20"] > 0.08:
        flags.append("extrémní volatilita")
    if (trailing.get("12M") or 0) < -0.5:
        flags.append("dlouhodobý propad (−50 % a víc za rok)")
    flags.append("bez fundamentálních dat (SEC vypnutý) — ředění a hotovost NEOVĚŘENO")
    return flags


def ensure_fx(conn, currencies: set[str], log=print) -> None:
    from stockradar.sources.yahoo import fetch_chart, fx_symbol
    for cur in sorted(c for c in currencies if c):
        sym = fx_symbol(cur)
        if not sym or cache.load_series(conn, sym) is not None:
            continue
        try:
            q = fetch_chart(sym, "5y")
            cache.store_series(conn, sym, q.currency, q.bars, source="Yahoo Finance chart API", fetched_at=to_iso(utcnow()))
        except Exception as exc:
            log(f"Kurz {sym}: {exc}")


def run_discovery(cache_conn, *, news_events: int = 120, news_winners: int = 40, news_candidates: int = 10, log=print,
                  fetch_news=None, now: datetime | None = None) -> dict:
    now = now or utcnow()
    currencies = {r[0] for r in cache_conn.execute("SELECT DISTINCT currency FROM series WHERE error IS NULL")}
    ensure_fx(cache_conn, currencies, log)
    data = study.load_data(cache_conn)
    log(f"Načteno {len(data.secs)} firem s ≥ 250 dny historie")
    end_day = study.day_str(data.data_end)

    # --- 1. dnešní vítězové (§2) ---
    trailing = {s: trailing_returns(sec.prep.bars) for s, sec in data.secs.items()
                if data.data_end - sec.prep.bars.days[-1] <= 7}
    winner_counts = {k: {f"+{int(t * 100)} %": sum(1 for r in trailing.values() if (r.get(k) or -9) >= t) for t in ths}
                     for k, (_, ths) in TRAILING.items()}

    # --- 2. historické rakety ---
    events = {kind: study.scan_events(data, kind) for kind in ("W1_30", "M1_50", "M3_50", "M6_100")}
    log("Události: " + ", ".join(f"{k} {len(v)}" for k, v in events.items()))
    heat = study.Heat(data, events["W1_30"])

    # --- 3. studie: kontrolní skupina, lift, model, test předvídatelnosti ---
    models, studies = {}, {}
    cutoff = TRAIN_CUTOFF.toordinal()
    for kind in MODELS:
        rows = study.build_case_control(data, events[kind], kind, heat)
        lifts = study.lift_table(rows)
        train = [r for r in rows if r["day"] < cutoff]
        test = [r for r in rows if r["day"] >= cutoff]
        oos = study.fit_logit(train, MODEL_FEATURES)
        test_auc = study.auc([oos.score(r["f"]) for r in test], [r["y"] for r in test]) if test else None
        # zrcadlový model propadů → asymetrie (raketa minus propad)
        dkind = DROP_OF[kind]
        drops = study.scan_events(data, dkind)
        drows = study.build_case_control(data, drops, dkind, heat, seed=13)
        oos_drop = study.fit_logit([r for r in drows if r["day"] < cutoff], MODEL_FEATURES)
        pop = study.population_test(data, oos, kind, heat, start_day=cutoff, drop_model=oos_drop)
        final = study.fit_logit(rows, MODEL_FEATURES)
        final_drop = study.fit_logit(drows, MODEL_FEATURES)
        models[kind] = (final, oos, pop, final_drop)
        directional = pop.get("asymetrie", {}).get("smerova_vyhoda", False)
        studies[kind] = {
            "popis": MODELS[kind], "raket": sum(r["y"] for r in rows), "kontrol": sum(1 - r["y"] for r in rows),
            "propadu": sum(r["y"] for r in drows), "smerova_vyhoda": directional,
            "lift": lifts[:10],
            "lift_propady": study.lift_table(drows)[:6],
            "vahy": sorted(({"znak": k, "nazev": FEATURES[k], "koef": round(final.coef[i + 1], 3)}
                            for i, k in enumerate(final.features)), key=lambda x: abs(x["koef"]), reverse=True),
            "test": {"trenink_do": TRAIN_CUTOFF.isoformat(), "auc_kontrolni_vzorek": round(test_auc, 4) if test_auc else None,
                     "populace": pop},
        }
        log(f"{kind}: AUC test {test_auc}, směrová výhoda {directional}, asymetrie {pop.get('asymetrie')}")

    # --- 4. příčiny raket ze zpráv ---
    recent_cut = data.data_end - 730
    big = sorted((e for e in events["W1_30"] if data.secs[e.symbol].prep.bars.days[e.t0] >= recent_cut
                  and study.liquid_at(data, data.secs[e.symbol], e.t0)[0]), key=lambda e: e.ret, reverse=True)
    explained = []
    seen = set()
    fetch_kwargs = {"fetch": fetch_news} if fetch_news else {}
    for ev in big:
        if len(explained) >= news_events:
            break
        if ev.symbol in seen:
            continue
        seen.add(ev.symbol)
        sec = data.secs[ev.symbol]
        b = sec.prep.bars
        info = cache.cached_news(cache_conn, ev.symbol, b.date(ev.t0), b.date(ev.end)) if not fetch_news else None
        if info is None:
            info = news.explain_event(sec.meta.get("name") or ev.symbol, date.fromordinal(b.days[ev.t0]),
                                      date.fromordinal(b.days[ev.end]), symbol=ev.symbol, pause=0 if fetch_news else 1.0,
                                      **fetch_kwargs)
            cache.store_news(cache_conn, ev.symbol, b.date(ev.t0), b.date(ev.end), info, fetched_at=to_iso(utcnow()))
        explained.append(event_row(data, ev, info))
    cause_stats = summarize_causes(explained)
    log(f"Příčiny z titulků: {len(explained)} událostí")

    # 6M vítězové s příčinou (§55 A)
    top6 = sorted((s for s in trailing if (trailing[s].get("6M") or 0) >= 0.3 and
                   study.liquid_at(data, data.secs[s], len(data.secs[s].prep.bars.days) - 1)[0]),
                  key=lambda s: trailing[s]["6M"], reverse=True)
    sizes = {}
    for s in top6:
        sec = data.secs[s]
        i = len(sec.prep.bars.days) - 1
        rate = data.usd_rate(sec.currency, sec.prep.bars.days[i])
        sizes[s] = size_bucket(sec.meta, study.turnover_usd(sec.prep, i, rate))
    big_names = [s for s in top6 if sizes[s] in ("large", "mid")][:news_winners // 2]
    small_names = [s for s in top6 if sizes[s] in ("small", "micro")][:news_winners - len(big_names)]
    top_winners = []
    for s in big_names + small_names:
        sec = data.secs[s]
        b = sec.prep.bars
        i = len(b.days) - 1
        start = max(i - 126, 0)
        t0 = min(range(start, i + 1), key=lambda k: b.closes[k])
        info = cache.cached_news(cache_conn, s, b.date(t0), b.date(i)) if not fetch_news else None
        if info is None:
            info = news.explain_event(sec.meta.get("name") or s, date.fromordinal(b.days[t0]), date.fromordinal(b.days[i]),
                                      symbol=s, pause=0 if fetch_news else 1.0, **fetch_kwargs)
            cache.store_news(cache_conn, s, b.date(t0), b.date(i), info, fetched_at=to_iso(utcnow()))
        w1 = [e for e in events["W1_30"] if e.symbol == s and e.end >= start]
        top_winners.append({
            "ticker": s, "nazev": sec.meta.get("name"), "zeme": sec.meta.get("country"),
            "sektor": sec.meta.get("industry") or sec.meta.get("sector"),
            "rust_6m": round(trailing[s]["6M"], 3), "rust_12m": _r(trailing[s].get("12M")),
            "velikost": sizes[s], "overit_data": trailing[s]["6M"] > 5,
            "charakter": "skokový (týdenní rakety)" if w1 else "postupný",
            "pricina": info.get("hlavni_pricina"), "pricina_stav": info.get("stav"),
            "titulky": info.get("titulky", [])[:3],
        })

    # --- 5. nová IPO (§29, poučení Unitree) — firmy s kotací kratší než 12 měsíců ---
    ipo_rows = []
    first_cut = study.day_str(data.data_end - 365)
    data_start = study.day_str(data.data_start + 30)
    for r in cache_conn.execute(
            "SELECT s.symbol, s.name, s.country, s.sector, s.industry, r.first_day, r.last_day FROM series r"
            " JOIN securities s ON s.symbol = r.symbol WHERE r.error IS NULL AND r.first_day >= ? AND r.first_day > ?",
            (first_cut, data_start)):
        bars = cache.load_series(cache_conn, r["symbol"])
        if bars is None or len(bars.closes) < 10 or study.anomalous(bars):
            continue
        ipo_rows.append({"ticker": r["symbol"], "nazev": r["name"], "zeme": r["country"],
                         "obor": r["industry"] or r["sector"], "od": r["first_day"],
                         "od_kotace": round(bars.closes[-1] / bars.closes[0] - 1, 3),
                         "max_od_kotace": round(max(bars.closes) / bars.closes[0] - 1, 3)})
    ipo_by_group = Counter((r["obor"] or "neuvedeno").lower() for r in ipo_rows)
    ipo_rows.sort(key=lambda r: r["od_kotace"], reverse=True)

    # --- 6. sektorové vlny a skupiny společného pohybu (§13–§14) ---
    waves = study.sector_waves(data, trailing)
    for w in waves:
        w["nove_na_burze_12m"] = ipo_by_group.get((w["obor"] or "").lower(), 0)
    clusters = study.comovement_clusters(data, top6[:300])
    cluster_rows = [{"firmy": [{"ticker": s, "nazev": data.secs[s].meta.get("name"),
                                "obor": data.secs[s].meta.get("industry") or data.secs[s].meta.get("sector"),
                                "zeme": data.secs[s].meta.get("country"), "rust_6m": _r(trailing[s].get("6M"))}
                               for s in c[:12]],
                     "velikost": len(c), "obory": Counter(data.secs[s].meta.get("industry") or data.secs[s].meta.get("sector")
                                                          for s in c).most_common(3),
                     "zeme": sorted({data.secs[s].meta.get("country") or "?" for s in c})}
                    for c in sorted(clusters, key=len, reverse=True)[:12]]

    # --- 7. kandidáti dnes (§55 E) + čerstvé zprávy (WHY NOW z titulků posledních 30 dní) ---
    candidates = score_today(data, models, heat, trailing, events)
    today = date.fromordinal(data.data_end)
    for kind, rows in candidates.items():
        for row in rows[:news_candidates]:
            q, lang, relevant = news.search_plan(row["nazev"] or row["ticker"], row["ticker"])
            if q is None:
                continue
            try:
                heads = [h for h in (fetch_news or news.fetch_headlines)(q, today - timedelta(days=30),
                                                                         today + timedelta(days=1), lang=lang)
                         if relevant(h)]
            except Exception as exc:
                row["zpravy"] = {"stav": "DATA NEDOSTUPNÁ", "duvod": str(exc)[:100]}
                continue
            finally:
                if not fetch_news:
                    import time
                    time.sleep(1.0)
            row["zpravy"] = {"stav": "AUTO (z titulků, neověřeno ručně)" if heads else "žádné titulky za 30 dní",
                             "pocet": len(heads), "pricny": news.classify(heads)[:3], "titulky": heads[-3:]}

    # --- 7. známé případy (§44) ---
    known = known_case_tests(data, models, heat, events)

    run_stats = {
        "firem_v_seznamu": cache_conn.execute("SELECT COUNT(*) FROM securities").fetchone()[0],
        "firem_s_daty": len(data.secs), "vyrazeno_chyba_dat": len(data.rejected), "zemi": len({s.meta.get("country") for s in data.secs.values()}),
        "oboru": len(data.groups), "dokumentu_titulku": sum(e["titulku_celkem"] for e in explained),
        "obdobi_dat": f"{study.day_str(data.data_start)}..{end_day}",
        "rakety": {k: len(v) for k, v in events.items()}, "nova_ipo_12m": len(ipo_rows),
        "vitezu_dnes": winner_counts, "sektorovych_vln": len([w for w in waves if w["z"] >= 3]),
        "skupin_spolecneho_pohybu": len(clusters),
        "omezeni": ["Seznamy firem jsou dnešní — chybí zkrachovalé a delistované firmy (survivorship bias, §60).",
                    "Fundamenty (tržby, marže, FCF, ředění) nejsou k dispozici zdarma bez e-mailu pro SEC → NEOVĚŘENO.",
                    "Příčiny raket jsou automaticky odvozené z titulků zpráv (Google News) — označeno AUTO.",
                    "Obory pocházejí z různých klasifikací (Nasdaq, JPX, ASX GICS, Wikipedie) — nejsou plně sjednocené.",
                    "Řady s denním skokem nad 50× jsou vyřazené jako chyba dat; průměry výnosů jsou oříznuté na +500 %."],
    }
    return {
        "probehlo": to_iso(now), "data_do": end_day, "statistika": run_stats,
        "vitezove": top_winners, "studie": studies, "pricny": cause_stats, "rakety_vysvetlene": explained[:80],
        "sektorove_vlny": waves[:25], "skupiny": cluster_rows, "kandidati": candidates, "zname_pripady": known,
        "nova_ipo": {"pocet": len(ipo_rows), "podle_oboru": ipo_by_group.most_common(10), "nejlepsi": ipo_rows[:15],
                     "nejhorsi": ipo_rows[-5:][::-1]},
        "_models": {k: {"raketa": m[0].to_dict(), "propad": m[3].to_dict()} for k, m in models.items()},
    }


SIZE_BUCKETS = [(10e9, "large"), (2e9, "mid"), (300e6, "small"), (0, "micro")]


def size_bucket(meta: dict, turnover_usd: float) -> str:
    """§60: velké a malé firmy se nesměšují. Tržní kapitalizace (USA), jinak odhad z obratu (~0,5 % kapitalizace denně)."""
    cap = meta.get("market_cap_usd") or turnover_usd * 200
    return next(name for limit, name in SIZE_BUCKETS if cap >= limit)


def _r(v, nd=3):
    return round(v, nd) if isinstance(v, (int, float)) else None


def event_row(data: study.Data, ev, info: dict) -> dict:
    sec = data.secs[ev.symbol]
    b = sec.prep.bars
    heads = info.get("titulky", [])
    return {
        "ticker": ev.symbol, "nazev": sec.meta.get("name"), "zeme": sec.meta.get("country"),
        "obor": sec.meta.get("industry") or sec.meta.get("sector"), "t0": b.date(ev.t0), "konec": b.date(ev.end),
        "rust": round(ev.ret, 3), "vrchol": round(ev.peak_ret, 3), "po_3m": outcome_label(ev.held),
        "pricina": info.get("hlavni_pricina"), "kod": info.get("kod"), "stav": info.get("stav"),
        "planovany_termin": info.get("planovany_termin"), "signaly_predem": info.get("signaly_predem", []),
        "titulku_pred": info.get("titulku_pred", 0), "titulku_behem": info.get("titulku_behem", 0),
        "titulku_celkem": info.get("titulku_pred", 0) + info.get("titulku_behem", 0), "titulky": heads[:3],
    }


def summarize_causes(rows: list[dict]) -> dict:
    found = [r for r in rows if r.get("pricina")]
    by = Counter(r["pricina"] for r in found)
    out = []
    for cause, n in by.most_common():
        sub = [r for r in found if r["pricina"] == cause]
        kept = sum(1 for r in sub if r["po_3m"] == "UDRŽEL")
        judged = sum(1 for r in sub if r["po_3m"] in ("UDRŽEL", "VYFOUKL", "ČÁSTEČNĚ"))
        out.append({"pricina": cause, "pocet": n, "podil": round(n / len(found), 3),
                    "udrzelo_3m": round(kept / judged, 3) if judged else None,
                    "median_rust": round(statistics.median(r["rust"] for r in sub), 3),
                    "priklady": [r["ticker"] for r in sub[:5]]})
    return {
        "vysvetleno": len(found), "celkem": len(rows),
        "bez_zprav": sum(1 for r in rows if not r.get("pricina")),
        "planovany_termin": sum(1 for r in found if r.get("planovany_termin")),
        "signal_predem": sum(1 for r in rows if r.get("titulku_pred", 0) > 0),
        "podle_priciny": out,
    }


def score_today(data: study.Data, models: dict, heat: study.Heat, trailing: dict, events: dict, *, top: int = 25) -> dict:
    out = {}
    recent = {}
    for e in events["W1_30"] + events["M1_50"]:
        sec = data.secs[e.symbol]
        if data.data_end - sec.prep.bars.days[e.end] <= 14:
            recent[e.symbol] = True
    feats = {}
    for s, sec in data.secs.items():
        i = len(sec.prep.bars.days) - 1
        if data.data_end - sec.prep.bars.days[i] > 7:
            continue
        f = study.sample_features(data, sec, i, heat)
        if f is not None:
            feats[s] = f
    for kind, (final, oos, pop, final_drop) in models.items():
        up = {s: final.score(f) for s, f in feats.items()}
        down = {s: final_drop.score(f) for s, f in feats.items()}
        scores = {s: up[s] - down[s] for s in feats}  # asymetrie: šance na raketu minus šance na propad
        asym = pop.get("asymetrie", {})
        ranked = sorted(scores, key=scores.get, reverse=True)
        pct = {s: (k + 1) / len(ranked) for k, s in enumerate(ranked)}
        rows = []
        for s in ranked:
            ph = phase(trailing.get(s, {}), recent.get(s, False))
            if ph not in ("EARLY", "DEVELOPING"):
                continue
            sec = data.secs[s]
            f = feats[s]
            now, nope = why_lists(final, f)
            bucket = "top1" if pct[s] <= 0.01 else "top5" if pct[s] <= 0.05 else "top10" if pct[s] <= 0.10 else None
            rows.append({
                "ticker": s, "nazev": sec.meta.get("name"), "zeme": sec.meta.get("country"),
                "obor": sec.meta.get("industry") or sec.meta.get("sector"), "faze": ph,
                "skore": round(scores[s], 4), "skore_raketa": round(up[s], 4), "skore_propad": round(down[s], 4),
                "percentil": round(pct[s], 4),
                "historicky_lift": asym.get(f"lift_{bucket}") if bucket else None,
                "historicka_presnost": asym.get(bucket, {}).get("rakety") if bucket else None,
                "historicke_propady": asym.get(bucket, {}).get("propady") if bucket else None,
                "historicky_median": asym.get(bucket, {}).get("median") if bucket else None,
                "zakladni_cetnost": pop.get("zakladni_cetnost"), "smerova_vyhoda": asym.get("smerova_vyhoda", False),
                "cena": round(sec.prep.bars.closes[-1], 4), "mena": sec.currency, "den": sec.prep.bars.date(len(sec.prep.bars.days) - 1),
                "rust_3m": _r(trailing.get(s, {}).get("3M")), "rust_6m": _r(trailing.get(s, {}).get("6M")),
                "proc_ted": now, "proc_ne": nope + risk_flags(f, trailing.get(s, {})),
                "potvrzeni": "Objem a cena dál rostou, v oboru přibývají rakety, objeví se konkrétní zpráva (kontrakt, výsledky, schválení).",
                "vyvraceni": "Cena spadne pod minimum posledních 20 dní nebo zájem v oboru vyprchá bez fundamentální zprávy.",
            })
            if len(rows) >= top:
                break
        out[kind] = rows
    return out


def known_case_tests(data: study.Data, models: dict, heat: study.Heat, events: dict) -> list[dict]:
    """§44: našel by systém známé vítěze předem? Skóre modelu NAUČENÉHO JEN NA STARŠÍCH DATECH 5 dní před T0."""
    out = []
    oos_drop = None
    for sym, label in KNOWN_CASES.items():
        sec = data.secs.get(sym)
        if sec is None:
            out.append({"ticker": sym, "test": label, "vysledek": "NEOVĚŘENO — firma není v datech"})
            continue
        evs = sorted([e for e in events["M3_50"] if e.symbol == sym], key=lambda e: e.ret, reverse=True)
        if not evs:
            out.append({"ticker": sym, "test": label,
                        "vysledek": f"V datech ({study.day_str(data.data_start)}–{study.day_str(data.data_end)}) žádná raketa ≥ +50 % za 3 měsíce"})
            continue
        ev = evs[0]
        oos = models["M3_50"][1]
        i = max(ev.t0 - 5, 120)
        f = study.sample_features(data, sec, i, heat)
        pop = models["M3_50"][2]
        out.append({"ticker": sym, "test": label, "t0": sec.prep.bars.date(ev.t0), "rust": round(ev.ret, 3),
                    "skore_5_dni_pred": round(oos.score(f), 4) if f else None,
                    "poznamka": ("Model naučený do " + TRAIN_CUTOFF.isoformat() +
                                 (" — událost je až po tréninku (poctivý test)." if ev.t0 and sec.prep.bars.days[ev.t0] >= TRAIN_CUTOFF.toordinal()
                                  else " — událost je v tréninkovém období (není nezávislý test).")),
                    "zakladni_cetnost": pop.get("zakladni_cetnost")})
    return out
