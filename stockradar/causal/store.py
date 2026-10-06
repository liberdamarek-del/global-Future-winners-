"""Append-only záznam kauzálního radaru: běhy, predikce oborů a jejich vyhodnocení; registr testu řetězců."""

import hashlib
import json
import math
from datetime import date

from stockradar import __version__
from stockradar.causal import chains as CH
from stockradar.causal import commodities as CM
from stockradar.causal.exposure import MIN_WEEKS, T_MIN, WINDOW
from stockradar.signals import store as sstore
from stockradar.timeutil import to_iso, utcnow

MODEL_NAME = "CAUSAL_CHAINS"


def config_hash() -> str:
    """Otisk pravidel testu řetězců: změna pravidel = nový pokus na zamčeném testu (vidět v registru)."""
    cfg = {"z_min": CH.Z_MIN, "t_min": T_MIN, "window": WINDOW, "min_weeks": MIN_WEEKS, "step": CH.STEP_W,
           "h": CH.HORIZONS_W, "commodities": [c["symbol"] for c in CM.COMMODITIES],
           "chains": {c["id"]: c["retez"] for c in CM.COMMODITIES}}
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def record_study(conn, study: dict, periods: dict[str, tuple[int, int]]) -> dict:
    """VALIDATION se zapíše (bez duplicit), LOCKED_TEST jen poprvé; vrací test z registru (ten platí)."""
    cfg = config_hash()
    for split, key in (("VALIDATION", "VALIDACE"), ("LOCKED_TEST", "TEST")):
        res = (study.get("obdobi") or {}).get(key)
        if res is None:
            continue
        lo, hi = periods[key]
        if split == "LOCKED_TEST" and sstore.locked_result(conn, MODEL_NAME, cfg) is not None:
            continue
        sstore.record_eval(conn, MODEL_NAME, cfg, split, (date.fromordinal(lo).isoformat(), date.fromordinal(hi).isoformat()),
                           {"vzorku": res.get("vazeb", 0), "nezavislych": res.get("soku", 0), **res})
    locked = sstore.locked_result(conn, MODEL_NAME, cfg)
    return {"konfigurace": cfg, "zamceny_test": locked, "pokusu": len(sstore.locked_attempts(conn, MODEL_NAME))}


def save_run(conn, result: dict, *, now=None) -> int:
    with conn:
        cur = conn.execute("INSERT INTO causal_runs (run_at, data_through, result_json, app_version) VALUES (?, ?, ?, ?)",
                           (to_iso(now or utcnow()), result["den"], json.dumps(result, ensure_ascii=False,
                                                                                separators=(",", ":")), __version__))
    return cur.lastrowid


def save_forecasts(conn, run_id: int, result: dict, *, now=None) -> list[int]:
    """Příležitosti s empirickou oporou → predikce oboru (směr nad trhem) na jejich horizont. Jen jednou za den."""
    ids = []
    made = to_iso(now or utcnow())
    with conn:
        for o in result.get("prilezitosti", []):
            if o["dukaz"] != "EMPIRICKY_I_LOGIKA" or not o.get("smer"):
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO causal_forecasts (run_id, made_at, price_date, commodity, industry, chain_order,"
                " direction, horizon_days, expected_move, priced_ratio, evidence, score, card_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, made, result["den"], o["komodita"], o["obor"], o["rad"], o["smer"], o["horizont_dni"],
                 o.get("ocekavany_pohyb"), o.get("v_cene"), o["dukaz"], o["skore"],
                 json.dumps(o, ensure_ascii=False, separators=(",", ":"))))
            if cur.rowcount:
                ids.append(cur.lastrowid)
    return ids


def evaluate(conn, weekly, *, now=None) -> list[dict]:
    """Predikce, u kterých uplynul horizont → výnos oboru nad trhem (týdenní řady) a zda šel ve směru predikce."""
    done = []
    rows = conn.execute("SELECT f.* FROM causal_forecasts f LEFT JOIN causal_outcomes o ON o.forecast_id = f.id"
                        " WHERE o.forecast_id IS NULL").fetchall()
    for f in rows:
        start = date.fromisoformat(f["price_date"]).toordinal()
        w0 = weekly.index(start)
        weeks = max(1, round(f["horizon_days"] / 7))
        series = weekly.ind.get(f["industry"])
        if w0 is None or series is None or w0 + weeks >= len(weekly.weeks):
            continue
        seg = series[w0 + 1:w0 + 1 + weeks]
        if any(v != v for v in seg):
            continue
        ex = math.fsum(seg)
        hit = int(math.copysign(1, ex) == f["direction"])
        with conn:
            conn.execute("INSERT INTO causal_outcomes (forecast_id, evaluated_at, end_date, industry_excess, hit)"
                         " VALUES (?, ?, ?, ?, ?)", (f["id"], to_iso(now or utcnow()),
                                                     date.fromordinal(weekly.weeks[w0 + weeks]).isoformat(), ex, hit))
        done.append({"id": f["id"], "obor": f["industry"], "komodita": f["commodity"], "vynos_oboru": ex, "zasah": hit})
    return done


def scorecard(conn) -> dict:
    r = conn.execute("SELECT COUNT(*), SUM(o.hit), AVG(o.industry_excess * f.direction) FROM causal_outcomes o"
                     " JOIN causal_forecasts f ON f.id = o.forecast_id").fetchone()
    waiting = conn.execute("SELECT COUNT(*) FROM causal_forecasts f LEFT JOIN causal_outcomes o ON o.forecast_id = f.id"
                           " WHERE o.forecast_id IS NULL").fetchone()[0]
    return {"vyhodnoceno": r[0] or 0, "zasahu": r[1] or 0, "prumer_ve_smeru": round(r[2], 4) if r[2] is not None else None,
            "ceka": waiting}
