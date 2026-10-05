"""§54: jedno tlačítko UPDATE — denní běh celého radaru.

Firmy → ceny → vyhodnocení starých predikcí → učení modelu → skóre → nové predikce → snapshot → export → web.
Každý krok má stav (DONE / CHYBA / PŘESKOČENO); chyba jednoho kroku nezastaví zbytek, pokud to jde.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from stockradar import __version__, config
from stockradar import model as m
from stockradar.ingest import update_prices
from stockradar.ledger import LedgerRuleError, PredictionInput, Scores, record_outcome, record_prediction
from stockradar.snapshots import create_snapshot
from stockradar.state_io import export_state
from stockradar.timeutil import parse_iso, to_iso, utcnow
from stockradar.universe import seed_energy_universe

EVAL_DAYS = (7, 14, 30, 90, 180, 365)  # §42: 7/14/30 dní, 3/6/12 měsíců
PREDICTION_DAYS = 30
TOP_N = 5
MIN_SCORE = 60.0
MIN_P_BEAT = 0.5
MAIN_PICK_SCORE = 70.0
MAIN_PICK_P_BEAT = 0.55
STALE_DAYS = 4


def bar_close_time(day: str) -> datetime:
    """Konzervativní čas závěrky (21:00 UTC) — dřív se pozorování nepoužije."""
    return parse_iso(f"{day}T21:00:00Z")


def first_bar_after(series: m.Series, due: datetime, now: datetime) -> int | None:
    for j, day in enumerate(series.dates):
        t = bar_close_time(day)
        if t >= due:
            return j if t <= now else None
    return None


ROCKET_LIMIT_DAYS = {"D0_14": 14, "D15_45": 45, "M6_PLUS": 180}  # do kdy musí raketa přijít


def rocket_target(p) -> float | None:
    """Cíl predikce rakety v % (None = predikce „lépe než S&P 500“ energetického modelu)."""
    if p["strategy"] == "SMART_MONEY":
        return None  # tvrzení „porazí S&P 500“, ne cíl růstu
    if p["target_move_pct"] is not None:
        return p["target_move_pct"]
    if p["source"] == "DISCOVERY":
        return 30.0 if p["horizon"] == "D0_14" else 50.0
    return None


def evaluate_predictions(conn: sqlite3.Connection, u: m.Universe, now: datetime) -> list[dict]:
    """Vyhodnotí živé predikce po 7/14/30/90/180/365 dnech. Vrací nová vyhodnocení.

    * energetický model: HIT = výnos lepší než S&P 500,
    * predikce raket: HIT = cena (denní závěr) dosáhla cíle (např. +50 %) do konce horizontu; dřív, než horizont
      uplyne a cíl ještě nebyl dosažen, se zapíše NEOVERENO (= zatím nerozhodnuto).
    """
    done = []
    bench = u.series.get(config.BENCHMARK_SYMBOL)
    rows = conn.execute(
        "SELECT p.*, l.yahoo_symbol FROM predictions p JOIN listings l ON l.id = p.listing_id"
        " WHERE p.mode = 'LIVE' AND l.yahoo_symbol IS NOT NULL AND p.benchmark_price IS NOT NULL").fetchall()
    loaded: dict[str, m.Series] = {}
    for p in rows:
        sym = p["yahoo_symbol"]
        # predikce objevů jsou mimo energetický vesmír → řadu načíst přímo z cache cen (dřív se nevyhodnotily vůbec)
        series = u.series.get(sym) or loaded.get(sym)
        if series is None:
            series = loaded[sym] = m.load_series(conn, sym)
        if not series.dates or not bench:
            continue
        made = parse_iso(p["made_at"])
        have = {r[0] for r in conn.execute("SELECT horizon_days FROM prediction_outcomes WHERE prediction_id = ?",
                                           (p["id"],))}
        target = rocket_target(p)
        limit = made + timedelta(days=ROCKET_LIMIT_DAYS.get(p["horizon"], 180))
        for n in EVAL_DAYS:
            due = made + timedelta(days=n)
            if n in have or due > now:
                continue
            j, jb = first_bar_after(series, due, now), first_bar_after(bench, due, now)
            if j is None or jb is None:
                continue
            window = [c for d, c in zip(series.dates, series.closes) if made.date().isoformat() < d <= series.dates[j]]
            price, bench_price = series.closes[j], bench.closes[jb]
            ret = price / p["price"] - 1
            excess = ret - (bench_price / p["benchmark_price"] - 1)
            if target is None:
                expected = p["base_move_pct"]
                result = "HIT" if excess > 0 else "MISS"
                deviation = (f"očekávaný nadvýnos {expected:+.1f} %, skutečný {excess * 100:+.1f} % vůči S&P 500"
                             if expected is not None else f"skutečný nadvýnos {excess * 100:+.1f} % vůči S&P 500")
            else:
                in_limit = [c for d, c in zip(series.dates, series.closes)
                            if made.date().isoformat() < d <= min(series.dates[j], limit.date().isoformat())]
                reach = (max(in_limit) / p["price"] - 1) if in_limit else 0.0
                if reach * 100 >= target:
                    result = "HIT"
                elif due >= limit:
                    result = "MISS"
                else:
                    result = "NEOVERENO"
                deviation = (f"cíl +{target:.0f} %: maximum {reach * 100:+.1f} %, teď {ret * 100:+.1f} %, "
                             f"vůči S&P 500 {excess * 100:+.1f} %"
                             + ("" if result != "NEOVERENO" else " — zatím nerozhodnuto"))
            record_outcome(
                conn, p["id"], horizon_days=n, price=price, price_source="Yahoo Finance chart API (denní závěr)",
                observed_at=max(bar_close_time(series.dates[j]), bar_close_time(bench.dates[jb])),
                result=result, max_price=max(window + [price]), min_price=min(window + [price]),
                deviation=deviation, benchmark_price=bench_price, now=now)
            done.append({"prediction_id": p["id"], "symbol": sym, "days": n, "result": result,
                         "return_pct": round(ret * 100, 2), "excess_pct": round(excess * 100, 2)})
    return done


def category_for(score: float) -> str:
    return "A" if score >= 75 else "B" if score >= 65 else "C"


def nearest_catalyst(u: m.Universe, company_id: int, day: str) -> dict | None:
    horizon_end = (datetime.fromisoformat(day) + timedelta(days=45)).date().isoformat()
    best = None
    for k in u.catalysts:
        if k["company_id"] != company_id or k["status"] not in ("UPCOMING", "DELAYED") or k["published_at"][:10] > day:
            continue
        start = k["event_date"] if k["date_status"] == "VERIFIED" else k["window_start"]
        end = k["event_date"] if k["date_status"] == "VERIFIED" else k["window_end"]
        if start is None or end < day or start > horizon_end:
            continue
        if best is None or start < best[0]:
            best = (start, k)
    return best[1] if best else None


def score_universe(u: m.Universe, version: sqlite3.Row, data_day: str, quotes: dict) -> dict[str, dict]:
    weights = json.loads(version["weights_json"])
    calibration = json.loads(version["calibration_json"])
    snap = m.factors_at(u, data_day, live=True, max_gap_days=10)
    if not snap:
        return {}
    fr = m.factor_ranks(snap)
    scores = m.composite(fr, weights)
    order = sorted(scores, key=scores.get, reverse=True)
    names = {mem["symbol"]: mem for mem in u.members}
    out = {}
    for rank, sym in enumerate(order, 1):
        s = u.series[sym]
        i = snap[sym]["i"]
        b = m.bin_for(scores[sym], calibration)

        def chg(n):
            return round((s.closes[i] / s.closes[i - n] - 1) * 100, 2) if i >= n else None

        q = quotes.get(sym, {})
        lag = (datetime.fromisoformat(data_day) - datetime.fromisoformat(s.dates[i])).days
        out[sym] = {
            "poradi": rank, "skore": round(scores[sym], 1), "nazev": names[sym]["name"],
            "company_id": names[sym]["company_id"], "mena": q.get("currency") or names[sym]["currency"],
            "cena": round(s.closes[i], 4), "den": s.dates[i],
            "zmena_1d": chg(1), "zmena_20d": chg(20), "zmena_120d": chg(120),
            "p_beat": b["p_beat"], "p_rocket": b["p_rocket"], "ocekavany_nadvynos": b["mean_excess"],
            "q20": b["q20"], "q80": b["q80"],
            "data": "FRESH" if lag <= STALE_DAYS else "STALE",
            "faktory": {f: (round(v, 4) if isinstance(v, float) else v) for f, v in snap[sym]["values"].items()},
            "prispevky": m.contributions(fr, weights, sym),
            "rank_faktoru": {f: round(fr[f][sym], 3) for f in m.FACTORS},
        }
    return out


def explain(item: dict) -> str:
    contrib = sorted(item["prispevky"].items(), key=lambda kv: kv[1], reverse=True)
    plus = [f"+{m.FACTORS[f]['label']}" for f, v in contrib[:3] if v > 0]
    minus = [f"−{m.FACTORS[f]['label']}" for f, v in contrib[::-1][:1] if v < 0]
    return ", ".join(plus + minus)


def make_predictions(conn: sqlite3.Connection, u: m.Universe, scored: dict[str, dict], run_id: int,
                     quotes: dict, now: datetime) -> tuple[list[int], list[str]]:
    created, notes = [], []
    since = to_iso(now - timedelta(days=PREDICTION_DAYS))
    bench_q = quotes.get(config.BENCHMARK_SYMBOL, {})
    bench = u.series[config.BENCHMARK_SYMBOL]
    bench_price = bench_q.get("price") or bench.closes[-1]
    eligible = [s for s, it in sorted(scored.items(), key=lambda kv: kv[1]["poradi"])
                if it["data"] == "FRESH" and it["skore"] >= MIN_SCORE and it["p_beat"] >= MIN_P_BEAT][:TOP_N]
    for pos, sym in enumerate(eligible):
        it = scored[sym]
        listing = conn.execute("SELECT id FROM listings WHERE yahoo_symbol = ? AND valid_to IS NULL", (sym,)).fetchone()
        if conn.execute("SELECT 1 FROM predictions WHERE listing_id = ? AND mode = 'LIVE' AND made_at >= ?",
                        (listing["id"], since)).fetchone():
            continue
        q = quotes.get(sym, {})
        if q.get("price") and q.get("price_time") and q["price_time"] <= now:
            price, as_of = q["price"], q["price_time"]
        else:
            price, as_of = it["cena"], min(bar_close_time(it["den"]), now)
        catalyst = nearest_catalyst(u, it["company_id"], it["den"])
        is_main = pos == 0 and it["poradi"] == 1 and it["skore"] >= MAIN_PICK_SCORE and it["p_beat"] >= MAIN_PICK_P_BEAT
        fr = it["rank_faktoru"]
        try:
            pid = record_prediction(conn, PredictionInput(
                listing_id=listing["id"], horizon="D15_45", price=price, currency=it["mena"] or "USD",
                price_as_of=as_of, price_source="Yahoo Finance chart API",
                category=category_for(it["skore"]), verdict="SPEC_BUY", is_main_pick=is_main,
                rationale=(f"Model v{run_id}: skóre {it['skore']:.0f}/100 (pořadí {it['poradi']}). "
                           f"Důvody: {explain(it)}. Predikce: za 30 dní lépe než S&P 500."),
                catalyst_id=catalyst["id"] if catalyst else None,
                probability_pct=round(it["p_beat"] * 100, 1),
                bull_move_pct=round(it["q80"] * 100, 1), base_move_pct=round(it["ocekavany_nadvynos"] * 100, 1),
                bear_move_pct=round(it["q20"] * 100, 1),
                bull_case="Horní kvintil historických výsledků při podobném skóre (nadvýnos vůči S&P 500).",
                base_case="Průměrný historický nadvýnos při podobném skóre.",
                bear_case="Dolní kvintil historických výsledků při podobném skóre.",
                key_risk="Kvantitativní signál bez fundamentální analýzy; vysoká volatilita sektoru.",
                scores=Scores(overall_setup=int(round(it["skore"])),
                              catalyst=int(round(fr["catalyst_45"] * 100)),
                              technical=int(round((fr["mom_120"] + fr["vol_surge"]) / 2 * 100)),
                              rocket=int(round((fr["volatility_60"] + fr["small_size"]) / 2 * 100))),
                benchmark_symbol=config.BENCHMARK_SYMBOL, benchmark_price=bench_price,
                p_rocket_pct=round(it["p_rocket"] * 100, 1), model_run_id=run_id, source="ENERGY_MODEL",
            ), now=now)
            created.append(pid)
        except LedgerRuleError as exc:
            notes.append(f"{sym}: predikce nezapsána — {exc}")
    return created, notes


def run_update(conn: sqlite3.Connection, *, state_dir: Path, web_dir: Path | None = None, now: datetime | None = None,
               fetch=None) -> dict:
    now = now or utcnow()
    now_iso = to_iso(now)
    steps: dict[str, str] = {}
    warnings: list[str] = []

    seeded = seed_energy_universe(conn, now=now)
    steps["Firmy a řetězec"] = "DONE" + (f" (+{seeded['companies']} firem)" if seeded["companies"] else "")

    prices = update_prices(conn, now=now, **({"fetch": fetch, "pause": 0} if fetch else {}))
    ok = prices["requested"] - len(prices["errors"])
    steps["Ceny (Yahoo)"] = f"DONE {ok}/{prices['requested']}" if ok else "CHYBA"
    warnings += [f"Ceny: {e}" for e in prices["errors"][:10]]
    from stockradar.contact import email
    steps["SEC EDGAR"] = ("TÝDNĚ (v sobotním objevování; každé použití e-mailu se eviduje)" if email()
                          else "VYPNUTO (e-mail není nastaven)")

    u = m.load_universe(conn)
    bench = u.series.get(config.BENCHMARK_SYMBOL)
    if not bench or not bench.dates:
        steps["Učení modelu"] = "CHYBA: chybí data benchmarku"
        return {"steps": steps, "warnings": warnings, "run_id": None}
    data_day = bench.dates[-1]

    evaluated = evaluate_predictions(conn, u, now)
    steps["Vyhodnocení predikcí"] = f"DONE ({len(evaluated)} nových)"

    panel = m.build_panel(u)
    weights, metrics = m.learn(panel, as_of=data_day)
    calibration = m.calibrate(panel, weights)
    metrics["_oos"] = m.out_of_sample(panel)
    window = f"{panel[0].day}..{panel[-1].day}" if panel else "žádná data"
    n_samples = sum(len(p.excess) for p in panel)
    version_id, changed, reason = m.save_version_if_changed(conn, weights, metrics, calibration, window=window,
                                                            n_samples=n_samples, now_iso=now_iso)
    steps["Učení modelu"] = f"DONE (verze {version_id}{', NOVÁ' if changed else ''})"
    version = conn.execute("SELECT * FROM model_versions WHERE id = ?", (version_id,)).fetchone()

    scored = score_universe(u, version, data_day, prices["quotes"])
    stale = [s for s, it in scored.items() if it["data"] == "STALE"]
    if stale:
        warnings.append(f"DATA STALE (starší než {STALE_DAYS} dny): {', '.join(stale)}")
    steps["Skóre"] = f"DONE ({len(scored)} firem)"

    with conn:
        cur = conn.execute(
            "INSERT INTO model_runs (run_at, data_date, model_version_id, scores_json, steps_json, warnings_json)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (now_iso, data_day, version_id,
             json.dumps({s: {k: v for k, v in it.items() if k != "rank_faktoru"} for s, it in scored.items()},
                        sort_keys=True, ensure_ascii=False),
             json.dumps(steps, ensure_ascii=False), json.dumps(warnings, ensure_ascii=False)))
    run_id = cur.lastrowid

    created, notes = make_predictions(conn, u, scored, run_id, prices["quotes"], now)
    warnings += notes
    steps["Nové predikce"] = f"DONE ({len(created)} nových)"

    last_snap = conn.execute("SELECT MAX(taken_at) FROM snapshots").fetchone()[0]
    if last_snap is None or parse_iso(last_snap) <= now - timedelta(days=7):
        create_snapshot(conn, label=f"týdenní snapshot v{__version__}", now=now)
        steps["Snapshot"] = "DONE (týdenní)"
    else:
        steps["Snapshot"] = "PŘESKOČENO (poslední do 7 dní)"

    export_state(conn, state_dir)
    steps["Export stavu"] = "DONE"

    if web_dir is not None:
        from stockradar.site import write_site_data
        steps["Data pro web"] = "DONE"
        write_site_data(conn, web_dir, run_id=run_id, steps=steps, warnings=warnings, model_note=reason, now=now)
    return {"steps": steps, "warnings": warnings, "run_id": run_id, "version_id": version_id,
            "version_changed": changed, "reason": reason, "evaluated": evaluated, "created": created,
            "data_day": data_day}
