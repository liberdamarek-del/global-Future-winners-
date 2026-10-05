"""Append-only záznam: registr vyhodnocení modelů, běhy signálů, karty a jejich výsledky po 10 obchodních dnech."""

import bisect
import json
import statistics
from datetime import date

from stockradar import __version__
from stockradar.discovery import study
from stockradar.signals import panel as P
from stockradar.timeutil import to_iso, utcnow


def locked_result(conn, model_name: str, cfg: str) -> dict | None:
    r = conn.execute("SELECT * FROM model_evaluations WHERE model_name = ? AND config_hash = ? AND split = 'LOCKED_TEST'",
                     (model_name, cfg)).fetchone()
    return {**json.loads(r["metrics_json"]), "_vyhodnoceno": r["evaluated_at"], "_id": r["id"]} if r else None


def record_eval(conn, model_name, cfg, split, period, metrics: dict, *, now=None) -> int | None:
    """Zápis do registru; stejná konfigurace, část a období se nezapisuje znovu (LOCKED_TEST hlídá i databáze)."""
    if split != "LOCKED_TEST" and conn.execute(
            "SELECT 1 FROM model_evaluations WHERE model_name = ? AND config_hash = ? AND split = ? AND period_end = ?",
            (model_name, cfg, split, period[1])).fetchone():
        return None
    with conn:
        cur = conn.execute(
            "INSERT INTO model_evaluations (model_name, config_hash, split, period_start, period_end, n_samples,"
            " n_independent, metrics_json, evaluated_at, app_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (model_name, cfg, split, period[0], period[1], metrics.get("vzorku", 0), metrics.get("nezavislych", 0),
             json.dumps(metrics, ensure_ascii=False, separators=(",", ":")), to_iso(now or utcnow()), __version__))
    return cur.lastrowid


def locked_attempts(conn, model_name: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT config_hash, evaluated_at, app_version FROM model_evaluations WHERE model_name = ? AND split = 'LOCKED_TEST'"
        " ORDER BY id", (model_name,))]


def save_run(conn, result: dict, model_name: str, cfg: str, *, now=None) -> int:
    with conn:
        cur = conn.execute("INSERT INTO signal_runs (run_at, data_through, model_name, config_hash, result_json, app_version)"
                           " VALUES (?, ?, ?, ?, ?, ?)",
                           (to_iso(now or utcnow()), result["data_do"], model_name, cfg,
                            json.dumps(result, ensure_ascii=False, separators=(",", ":")), __version__))
    return cur.lastrowid


def save_forecasts(conn, run_id: int, cards: list[dict], *, now=None) -> list[int]:
    """Karta pro stejnou akcii a stejný den cen se zapíše jen jednou (opakovaný běh nezdvojí vyhodnocení)."""
    ids = []
    made = to_iso(now or utcnow())
    with conn:
        for c in cards:
            h = c.get("obchodnich_dni") or P.H
            if conn.execute("SELECT 1 FROM signal_forecasts WHERE symbol = ? AND price_date = ? AND horizon_days = ?",
                            (c["ticker"], c["den_ceny"], h)).fetchone():
                continue
            cur = conn.execute(
                "INSERT INTO signal_forecasts (run_id, made_at, symbol, name, price, price_date, currency, horizon_days,"
                " regime, p_up, p_down, p_flat, p_beat_sector, p_big, expected_move, expected_low, expected_high,"
                " confidence, decision, card_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, made, c["ticker"], c.get("firma"), c["cena"], c["den_ceny"], "USD", h, c["rezim"],
                 c["p_up"], c["p_down"], c["p_flat"], c.get("p_obor"), c.get("p_prudky"), c.get("ocekavany_pohyb"),
                 c.get("pohyb_q20"), c.get("pohyb_q80"), c["duvera"], c["final"],
                 json.dumps(c, ensure_ascii=False, separators=(",", ":"))))
            ids.append(cur.lastrowid)
    return ids


def evaluate_forecasts(conn, data: study.Data, *, now=None) -> list[dict]:
    """Karty, u kterých už uplynulo 10 obchodních dní → výsledek (výnos, proti oboru, Brierovo skóre)."""
    done = []
    rows = conn.execute("SELECT f.* FROM signal_forecasts f LEFT JOIN signal_outcomes o ON o.forecast_id = f.id"
                        " WHERE o.forecast_id IS NULL").fetchall()
    snaps: dict[int, dict] = {}
    for f in rows:
        s = data.secs.get(f["symbol"])
        if s is None:
            continue
        b = s.prep.bars
        d0 = date.fromisoformat(f["price_date"]).toordinal()
        i = bisect.bisect_right(b.days, d0) - 1
        if i < 0 or i + f["horizon_days"] >= len(b.days) or b.closes[i] <= 0:
            continue
        j = i + f["horizon_days"]
        r = b.closes[j] / b.closes[i] - 1
        hi = max(b.closes[i + 1:j + 1]) / b.closes[i] - 1
        lo = min(b.closes[i + 1:j + 1]) / b.closes[i] - 1
        if d0 not in snaps:
            snaps[d0] = P.snapshot(data, d0)
        card = json.loads(f["card_json"])
        key = "f10" if f["horizon_days"] == P.H else "f20" if f["horizon_days"] == P.H_1M else None
        sec = snaps[d0]["med"].get(s.group, {}).get(key) if key else None
        up_t, dn_t, big_t = card.get("prah_rust", P.UP), card.get("prah_pokles", P.DOWN), card.get("prah_prudky", P.BIG)
        up5, dn5 = int(r >= up_t), int(r <= dn_t)
        beat = int(r - sec > 0) if sec is not None else None
        big = int(max(hi, -lo) >= big_t)
        brier = statistics.fmean([(f["p_up"] - up5) ** 2, (f["p_down"] - dn5) ** 2])
        with conn:
            conn.execute("INSERT INTO signal_outcomes (forecast_id, evaluated_at, end_date, end_price, ret, sector_ret, up5,"
                         " down5, beat_sector, big, brier) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (f["id"], to_iso(now or utcnow()), b.date(j), b.closes[j], r, sec, up5, dn5, beat, big, brier))
        done.append({"id": f["id"], "ticker": f["symbol"], "vynos": r, "rozhodnuti": f["decision"]})
    return done


def history(conn, symbol: str, limit: int = 6) -> list[dict]:
    """Historie hodnocení firmy: dřívější karty (všechny horizonty) a jak dopadly."""
    rows = conn.execute("SELECT f.price_date, f.horizon_days, f.decision, f.p_up, f.p_down, f.confidence, f.card_json,"
                        " o.ret, o.up5 FROM signal_forecasts f LEFT JOIN signal_outcomes o ON o.forecast_id = f.id"
                        " WHERE f.symbol = ? ORDER BY f.price_date DESC, f.horizon_days LIMIT ?", (symbol, limit)).fetchall()
    out = []
    for r in rows:
        card = json.loads(r["card_json"])
        out.append({"den": r["price_date"], "horizont": card.get("horizont"), "poradi": card.get("poradi"),
                    "p_up": r["p_up"], "p_down": r["p_down"], "rozhodnuti": r["decision"], "duvera": r["confidence"],
                    "vysledek": r["ret"], "dosazeno": r["up5"]})
    return out


def scorecard(conn, horizon_days: int | None = None) -> dict:
    """Jak dopadly dřívější karty: podle rozhodnutí RŮST / POKLES / NEVÍM (volitelně jen jeden horizont)."""
    rows = conn.execute("SELECT f.decision, f.p_up, f.p_down, f.confidence, f.horizon_days, o.* FROM signal_forecasts f"
                        " JOIN signal_outcomes o ON o.forecast_id = f.id").fetchall()
    if horizon_days is not None:
        rows = [r for r in rows if r["horizon_days"] == horizon_days]
    out = {}
    for dec in ("RŮST", "POKLES", "NEVÍM"):
        rr = [r for r in rows if r["decision"] == dec]
        if not rr:
            continue
        out[dec] = {"karet": len(rr), "vynos_median": round(statistics.median(r["ret"] for r in rr), 4),
                    "up5": round(statistics.fmean(r["up5"] for r in rr), 3),
                    "down5": round(statistics.fmean(r["down5"] for r in rr), 3),
                    "porazilo_obor": round(statistics.fmean(r["beat_sector"] for r in rr if r["beat_sector"] is not None), 3)
                    if any(r["beat_sector"] is not None for r in rr) else None,
                    "brier": round(statistics.fmean(r["brier"] for r in rr), 4),
                    "predpoved_up5": round(statistics.fmean(r["p_up"] for r in rr), 3)}
    out["celkem_vyhodnoceno"] = len(rows)
    out["ceka"] = conn.execute("SELECT COUNT(*) FROM signal_forecasts f LEFT JOIN signal_outcomes o ON o.forecast_id = f.id"
                               " WHERE o.forecast_id IS NULL").fetchone()[0]
    return out
