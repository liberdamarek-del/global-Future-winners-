"""Experiment N-5 (od 2026-10-19): živá kalibrace signálních karet a pokrytí intervalu pohybu — statický × ACI.

Co se měří (předem dané, docs/agent_vyzkum/navrhy.jsonl N-5):
- Brier pro P(růst nad práh) a dovednost proti základní četnosti, kterou běh modelu znal předem (`zaklad.up5`);
- tabulka spolehlivosti po koších 10 p. b. (předpověď × skutečnost);
- pokrytí intervalu pohybu q20–q80 (cíl 60 %): statický interval z karty × adaptivní konformní úprava
  (ACI, Gibbs & Candès, arXiv 2106.00170) s krokem GAMMA = 0,005.

ACI je jen „ve stínu“: karty na webu se nemění. Skóre shody = |výnos − medián| / polovina šířky (q80 − q20) / 2;
statický interval = skóre ≤ 1. ACI pro týden t použije kvantil (1 − α_t) ze skóre DŘÍVĚJŠÍCH týdnů (karty jednoho týdne
se vyhodnotí najednou, takže se mezi sebou nevidí) a po týdnu upraví α_{t+1} = α_t + γ Σ (α − chyba_i).
Týden je nezávislá jednotka; vyhodnocení po 8 a 16 týdnech (kritérium v N-5), do té doby jen průběžný údaj.
"""

import json
import math
import statistics

TARGET_COVERAGE = 0.60
GAMMA = 0.005
BINS = 10


def _quantile(values: list[float], q: float) -> float:
    if q >= 1:
        return math.inf
    if q <= 0:
        return 0.0
    v = sorted(values)
    k = min(len(v) - 1, max(0, math.ceil(q * (len(v) + 1)) - 1))       # konformní kvantil s korekcí (n + 1)
    return v[k]


def rows(conn) -> list[dict]:
    """Vyhodnocené karty: model, týden predikce, P(růst), výsledek, základní četnost běhu, interval a výnos."""
    base: dict[int, dict] = {}
    out = []
    for r in conn.execute("SELECT r.id AS run_id, r.model_name, f.made_at, f.p_up, f.card_json, o.ret, o.up5"
                          " FROM signal_outcomes o JOIN signal_forecasts f ON f.id = o.forecast_id"
                          " JOIN signal_runs r ON r.id = f.run_id ORDER BY f.made_at, f.id"):
        if r["run_id"] not in base:
            res = conn.execute("SELECT result_json FROM signal_runs WHERE id = ?", (r["run_id"],)).fetchone()[0]
            base[r["run_id"]] = (json.loads(res).get("zaklad") or {})
        card = json.loads(r["card_json"])
        out.append({"model": r["model_name"], "tyden": _week(r["made_at"]),
                    "p_up": r["p_up"], "up": r["up5"], "zaklad_up": base[r["run_id"]].get("up5"), "ret": r["ret"],
                    "med": card.get("pohyb_median"), "q20": card.get("pohyb_q20"), "q80": card.get("pohyb_q80")})
    return out


def _week(made_at: str) -> int:
    from datetime import date
    return date.fromisoformat(made_at[:10]).toordinal() // 7


def reliability(items: list[dict]) -> dict:
    """Brier, dovednost proti základní četnosti a tabulka spolehlivosti pro P(růst nad práh)."""
    pairs = [(x["p_up"], x["up"], x["zaklad_up"]) for x in items if x["p_up"] is not None and x["up"] is not None]
    if not pairs:
        return {"karet": 0}
    brier = statistics.fmean((p - y) ** 2 for p, y, _ in pairs)
    ref = [(b - y) ** 2 for _, y, b in pairs if b is not None]
    table = []
    for k in range(BINS):
        lo, hi = k / BINS, (k + 1) / BINS
        b = [(p, y) for p, y, _ in pairs if lo <= p < hi or (k == BINS - 1 and p == 1.0)]
        if b:
            table.append({"kos": f"{int(lo * 100)}–{int(hi * 100)} %", "karet": len(b),
                          "predpoved": round(statistics.fmean(p for p, _ in b), 3), "skutecnost": round(statistics.fmean(y for _, y in b), 3)})
    brier_ref = statistics.fmean(ref) if len(ref) == len(pairs) else None
    return {"karet": len(pairs), "tydnu": len({x["tyden"] for x in items}),
            "predpoved_prumer": round(statistics.fmean(p for p, _, _ in pairs), 3),
            "skutecnost": round(statistics.fmean(y for _, y, _ in pairs), 3),
            "brier": round(brier, 4), "brier_zaklad": None if brier_ref is None else round(brier_ref, 4),
            "dovednost": None if not brier_ref else round(1 - brier / brier_ref, 3), "tabulka": table}


def coverage(items: list[dict], *, target: float = TARGET_COVERAGE, gamma: float = GAMMA) -> dict:
    """Pokrytí intervalu q20–q80: statické × ACI, po týdnech (jen dřívější týdny určují kvantil ACI)."""
    usable = [x for x in items if None not in (x["ret"], x["med"], x["q20"], x["q80"]) and x["q80"] > x["q20"]]
    if not usable:
        return {"karet": 0}
    alpha_goal = 1 - target
    alpha = alpha_goal
    past: list[float] = []
    hit_static = hit_aci = 0
    path = []
    for week in sorted({x["tyden"] for x in usable}):
        wk = [x for x in usable if x["tyden"] == week]
        scores = [abs(x["ret"] - x["med"]) / ((x["q80"] - x["q20"]) / 2) for x in wk]
        qhat = _quantile(past, 1 - alpha) if past else 1.0
        cov_s = sum(1 for s in scores if s <= 1.0)
        cov_a = sum(1 for s in scores if s <= qhat)
        hit_static += cov_s
        hit_aci += cov_a
        path.append({"tyden": week, "karet": len(wk), "alfa": round(alpha, 4), "kvantil": None if math.isinf(qhat) else round(qhat, 3),
                     "pokryti_staticke": round(cov_s / len(wk), 3), "pokryti_aci": round(cov_a / len(wk), 3)})
        alpha += gamma * sum(alpha_goal - (0 if s <= qhat else 1) for s in scores)
        past.extend(scores)
    n = len(usable)
    cs, ca = hit_static / n, hit_aci / n
    return {"karet": n, "tydnu": len(path), "cil": target, "pokryti_staticke": round(cs, 3), "pokryti_aci": round(ca, 3),
            "odchylka_staticka": round(abs(cs - target), 3), "odchylka_aci": round(abs(ca - target), 3), "tydny": path}


def live_calibration(conn) -> dict:
    """Model → {spolehlivost, pokryti}; prázdné, dokud nejsou vyhodnocené karty."""
    data = rows(conn)
    out = {}
    for model in sorted({x["model"] for x in data}):
        items = [x for x in data if x["model"] == model]
        out[model] = {"spolehlivost": reliability(items), "pokryti": coverage(items),
                      "pozn": "experiment N-5 od 2026-10-19; vyhodnocení po 8 a 16 týdnech, dřív jen průběžný údaj"}
    return out
