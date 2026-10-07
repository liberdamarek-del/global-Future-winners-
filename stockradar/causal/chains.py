"""Historické učení kauzálních řetězců: ŠOK KOMODITY → EKONOMICKÝ DOPAD (citlivost oboru) → OBOR → POHYB AKCIÍ.

Událost = šok komodity: výnos za 4 týdny aspoň Z_MIN směrodatných odchylek od běžného kolísání (z-skóre).
Pro každý obor s prokázanou vazbou (|t| bety ≥ 2, spočítáno JEN z minulých týdnů) model očekává směr
sign(beta × výnos komodity). Měří se:
  - co už trh započítal: skutečný pohyb oboru za stejné 4 týdny / očekávaný pohyb (beta × výnos komodity),
  - co přijde potom: výnos oboru nad trhem za 1, 2, 4, 13, 26 týdnů (≈ 7, 14, 30, 90, 180 dní) ve směru očekávání.
Logické řetězce z `commodities.py` (řád 1–3) se testují zvlášť se směrem z ekonomické logiky.
Kontrola: stejné šoky přiřazené NÁHODNÝM oborům s náhodným směrem (placebo, 200×). Rozhodnutí o kroku každé
4 týdny (šoky se nepřekrývají); t-statistiky jsou konzervativně sníženy o překryv výsledkových oken.
"""

import math
import random
import statistics

from stockradar.causal import commodities as CM
from stockradar.causal.exposure import T_MIN, Exposure, shock

Z_MIN = 1.5
HORIZONS_W = (1, 2, 4, 13, 26)
STEP_W = 4
N_PLACEBO = 200


def _future(series: list[float], w: int, h: int) -> float | None:
    seg = series[w + 1:w + 1 + h]
    if len(seg) < h or any(v != v for v in seg):
        return None
    return math.fsum(seg)


def _past(series: list[float], w: int, k: int = 4) -> float | None:
    seg = series[w - k + 1:w + 1]
    if len(seg) < k or any(v != v for v in seg):
        return None
    return math.fsum(seg)


def events(ex: Exposure, w: int, *, z_min: float = Z_MIN) -> list[dict]:
    """Šoky komodit ke týdnu w a obory, kterých se týkají (empiricky i logicky)."""
    wk = ex.weekly
    out = []
    for cid in wk.comm:
        sh = shock(wk, cid, w)
        if sh is None or abs(sh[1]) < z_min:
            continue
        r, z = sh
        for g in wk.ind:
            beta, t = ex.beta[(g, cid)][w]
            logic = CM.chain_for(cid, g)
            emp = beta == beta and t == t and abs(t) >= T_MIN
            if not emp and logic is None:
                continue
            past = _past(wk.ind[g], w)
            exp_move = beta * r if beta == beta else None
            out.append({"w": w, "komodita": cid, "vynos": r, "z": z, "obor": g, "beta": beta, "t": t, "emp": emp,
                        "rad": logic[0] if logic else None, "smer_logika": logic[1] if logic else None,
                        "oceneno": past, "ocekavano": exp_move})
    return out


def _stats(vals_by_week: dict[int, list[float]], h: int) -> dict:
    m = [statistics.fmean(v) for v in vals_by_week.values() if v]
    if len(m) < 3:
        return {"n_tydnu": len(m)}
    sd = statistics.stdev(m)
    t = statistics.fmean(m) / (sd / math.sqrt(len(m))) if sd > 0 else None
    adj = t / math.sqrt(max(1.0, h / STEP_W)) if t is not None else None    # překryv oken (konzervativně)
    n = sum(len(v) for v in vals_by_week.values())
    return {"n": n, "n_tydnu": len(m), "prumer": round(statistics.fmean(m), 4), "t": round(adj, 2) if adj is not None else None,
            "sum": round(math.erfc(abs(adj) / math.sqrt(2)), 4) if adj is not None else None}


def study(ex: Exposure, periods: dict[str, tuple[int, int]], *, log=print, seed: int = 7) -> dict:
    wk = ex.weekly
    rng = random.Random(seed)
    groups = list(wk.ind)
    res = {"pravidla": {"z_min": Z_MIN, "t_min": T_MIN, "krok_tydnu": STEP_W, "horizonty_tydnu": HORIZONS_W,
                        "okno_bety_tydnu": 78, "placebo": N_PLACEBO}, "obdobi": {}}
    all_ev = []
    for w in range(30, len(wk.weeks), STEP_W):
        all_ev += events(ex, w)
    log(f"Šoky komodit: {len({(e['w'], e['komodita']) for e in all_ev})} (týden × komodita), vazeb {len(all_ev)}")
    for name, (lo, hi) in periods.items():
        ev = [e for e in all_ev if lo <= wk.weeks[e["w"]] <= hi]
        shocks = sorted({(e["w"], e["komodita"]) for e in ev})
        out = {"soku": len(shocks), "vazeb": len(ev)}
        for label, sel, sign_of in (
                ("empiricke", lambda e: e["emp"], lambda e: math.copysign(1, e["beta"] * e["vynos"])),
                ("logicke_rad1", lambda e: e["rad"] == 1, lambda e: e["smer_logika"] * math.copysign(1, e["vynos"])),
                ("logicke_rad2_3", lambda e: e["rad"] in (2, 3), lambda e: e["smer_logika"] * math.copysign(1, e["vynos"]))):
            rows = [e for e in ev if sel(e)]
            block = {"vazeb": len(rows)}
            for h in HORIZONS_W:
                by_w: dict[int, list[float]] = {}
                for e in rows:
                    f = _future(wk.ind[e["obor"]], e["w"], h)
                    if f is not None:
                        by_w.setdefault(e["w"], []).append(sign_of(e) * f)
                block[f"{h}t"] = _stats(by_w, h)
            # co už bylo v ceně: ve směru očekávání za stejné 4 týdny
            by_w0: dict[int, list[float]] = {}
            for e in rows:
                if e["oceneno"] is not None:
                    by_w0.setdefault(e["w"], []).append(sign_of(e) * e["oceneno"])
            block["uz_v_cene_4t"] = _stats(by_w0, 1)
            out[label] = block
        # podle toho, kolik už bylo v ceně (jen empirické vazby): málo vs hodně započítáno
        emp = [e for e in ev if e["emp"] and e["ocekavano"] and e["oceneno"] is not None]
        for part, cond in (("malo_v_cene", lambda q: q < 0.5), ("hodne_v_cene", lambda q: q >= 0.5)):
            for h in (4, 13, 26):
                by_w = {}
                for e in emp:
                    q = e["oceneno"] / e["ocekavano"] if e["ocekavano"] else None
                    f = _future(wk.ind[e["obor"]], e["w"], h)
                    if q is not None and cond(q) and f is not None:
                        by_w.setdefault(e["w"], []).append(math.copysign(1, e["ocekavano"]) * f)
                out.setdefault("podle_oceneni", {}).setdefault(part, {})[f"{h}t"] = _stats(by_w, h)
        # placebo: stejné šoky, náhodný obor a náhodný směr
        plac = {}
        for h in (4, 13, 26):
            means = []
            for _ in range(N_PLACEBO):
                vals = []
                for (w, _cid) in shocks:
                    g = rng.choice(groups)
                    f = _future(wk.ind[g], w, h)
                    if f is not None:
                        vals.append(rng.choice((-1, 1)) * f)
                if vals:
                    means.append(statistics.fmean(vals))
            plac[f"{h}t"] = {"prumer": round(statistics.fmean(means), 4), "sd": round(statistics.pstdev(means), 4)} if means else {}
        out["placebo"] = plac
        res["obdobi"][name] = out
        e13 = out["empiricke"].get("13t", {})
        log(f"{name}: šoků {len(shocks)}, empirické vazby {out['empiricke']['vazeb']}: za 13 týdnů {e13.get('prumer')} (t {e13.get('t')})")
    return res


def wind(ex: Exposure, group: str, day: int, weeks_back: int) -> tuple[float | None, float | None]:
    """„Kauzální vítr“ oboru ke dni: očekávaný pohyb z komodit (Σ beta × výnos komodity přes prokázané vazby) a jeho
    část, která se v ceně oboru ještě NEPROJEVILA (očekávané − skutečné). Jen z dat do daného dne."""
    wk = ex.weekly
    w = wk.index(day)
    if w is None or w < weeks_back or group not in wk.ind:
        return None, None
    exp = 0.0
    used = 0
    for cid, series in wk.comm.items():
        beta, t = ex.beta[(group, cid)][w]
        if beta != beta or t != t or abs(t) < T_MIN:
            continue
        seg = series[w - weeks_back + 1:w + 1]
        if any(v != v for v in seg):
            continue
        exp += beta * (math.prod(1 + v for v in seg) - 1)
        used += 1
    if not used:
        return 0.0, 0.0
    real = _past(wk.ind[group], w, weeks_back)
    return exp, (exp - real) if real is not None else None


class CausalFeatures:
    """Znaky pro panel signálů: kauzální vítr oboru ke dni (paměť pro stejný obor a týden)."""

    def __init__(self, ex: Exposure):
        self.ex = ex
        self._memo: dict[tuple[str, int], dict] = {}

    def features(self, group: str, day: int) -> dict:
        w = self.ex.weekly.index(day)
        key = (group, w if w is not None else -1)
        hit = self._memo.get(key)
        if hit is None:
            w4, _ = wind(self.ex, group, day, 4)
            w13, gap13 = wind(self.ex, group, day, 13)
            hit = {"wind4": w4, "wind13": w13, "wind13_gap": gap13}
            self._memo[key] = hit
        return hit


def build_features(cache_conn, data, *, log=print) -> CausalFeatures | None:
    """Ceny komodit z cache → týdenní řady → citlivosti → poskytovatel znaků (None, když komodity chybí).
    Řady a citlivosti sdílí s příkazem `causal` přes paměť výpočtů (memo) — při stejných datech se nepočítají znovu."""
    from stockradar.causal import data as cdata, memo
    if len(cdata.load(cache_conn)) < 5:
        log("Kauzální znaky: chybí ceny komodit (spusť `python -m stockradar causal --download`)")
        return None
    ex, _, _ = memo.load_or_build(cache_conn, data=data, log=log)
    return CausalFeatures(ex)
