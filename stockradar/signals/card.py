"""Signální karta (bod 14) — místo „cena za 14 dní = X“ několik veličin a míra důvěry.

Rozhodnutí (předem daná pravidla, neladí se na testu):
  RŮST     P(+5 %) aspoň o 8 p. b. nad běžnou akcií, P(+5 %) − P(−5 %) ≥ 10 p. b., pásmo má kladný výnos nad oborem,
           důvěra ≥ 55
  POKLES   zrcadlově pro P(−5 %)
  NEVÍM    vše ostatní (malá výhoda nebo nízká důvěra) — NO-TRADE není selhání, ale výsledek (bod 8)
Důvěra 0–100 = 100 minus penalizace: málo podobných nezávislých situací v historii, vzácný tržní režim,
nepřesná kalibrace v daném pásmu, neshoda globálního a režimového modelu, chybějící data, pásmo statisticky
nerozlišitelné od náhody (p-hodnota na validaci = „šance, že jde o šum“).
"""

import math
import statistics

from stockradar.signals import model as M
from stockradar.signals import panel as P

CONF_MIN = 55
EDGE_MIN = 0.08
DIR_MIN = 0.10
ANALOG_FEATURES = ["r5", "r20", "r60", "dd252", "vol20", "volu_5_60", "rel_r20", "sec_r20", "spy_r20", "vix",
                   "eps_chg_p", "ear", "ins_n30", "acc20"]
KEY_DATA = ("eps_chg_p", "rev_yoy", "log_mcap", "ear")


class Context:
    """Statistiky z učení a validace potřebné pro důvěru (spočítané jednou)."""

    def __init__(self, panel, train_rows, val_rows, sm: M.SignalModel, val_preds_raw: dict, train_preds: list[dict]):
        self.base = {t: sum(1 for k in train_rows if panel.y[t][k] == 1) / max(1, sum(1 for k in train_rows
                                                                                       if panel.y[t][k] >= 0))
                     for t in M.TARGETS}
        self.cells: dict[tuple, set] = {}
        for k, p in zip(train_rows, train_preds):
            b = M.bisect_band(sm.bands, p["dir"])
            self.cells.setdefault((M.regime_class(panel.regime[k]), b), set()).add((M.week(panel.day[k]), panel.group[k]))
        self.cells = {key: len(v) for key, v in self.cells.items()}
        weeks: dict[str, set] = {}
        for k in list(train_rows) + list(val_rows):
            weeks.setdefault(panel.regime[k], set()).add(M.week(panel.day[k]))
        self.regime_weeks = {r: len(v) for r, v in weeks.items()}
        # chyba kalibrace po binech na validaci (před vyhlazením)
        self.cal_err = {t: [abs(p - a) for p, a in zip(sm.cal[t]["pred"], sm.cal[t]["actual"])] for t in sm.cal}

    def to_dict(self):
        return {"zaklad": self.base, "rezim_tydnu": self.regime_weeks,
                "bunky": {f"{c}|{b}": n for (c, b), n in self.cells.items()}, "chyba_kalibrace": self.cal_err}


def confidence(pred: dict, f: dict, regime_label: str | None, ctx: Context, sm: M.SignalModel) -> tuple[int, list]:
    pen = []
    cls = M.regime_class(regime_label)
    band = M.bisect_band(sm.bands, pred["dir"])
    cell = ctx.cells.get((cls, band), 0)
    if cell < 400:
        pen.append((f"málo podobných situací v historii ({cell} nezávislých případů týden × obor)",
                    round(30 * (1 - cell / 400))))
    w = ctx.regime_weeks.get(regime_label or "?", 0)
    if w < 26:
        pen.append((f"režim „{regime_label}“ byl v datech učení jen {w} týdnů", round(20 * (1 - w / 26))))
    errs = []
    for t in ("up5", "down5"):
        if t in sm.cal:
            errs.append(ctx.cal_err[t][M.cal_bin(sm.cal[t], pred["raw"][t])])
    err = statistics.fmean(errs) if errs else 0.0
    if err > 0.02:
        pen.append((f"kalibrace v tomto pásmu nepřesná (±{err * 100:.1f} p. b.)", min(20, round(400 * (err - 0.02)))))
    if pred["disagree"] > 0.03:
        pen.append((f"globální a režimový model se liší o {pred['disagree'] * 100:.1f} p. b.",
                    min(20, round(300 * (pred["disagree"] - 0.03)))))
    missing = sum(1 for k in KEY_DATA if f.get(k) is None or f.get(k) != f.get(k)) / len(KEY_DATA)
    if missing > 0.5:
        pen.append(("chybí většina fundamentálních dat (výsledky, kapitalizace)", 10))
    b = M.band_of(sm.bands, pred["dir"])
    if b.get("sum") is None or b["sum"] > 0.2:
        pen.append((f"toto pásmo se v historii od náhody statisticky nelišilo (šance na šum {b.get('sum')})", 15))
    return max(0, 100 - sum(p for _, p in pen)), pen


def decide(pred: dict, conf: int, base: dict, sm: M.SignalModel, ref: dict | None = None) -> tuple[str, str]:
    """ref = medián predikcí všech akcií v ten den: výhoda se měří proti vyššímu z (běžná akcie v historii,
    dnešní průměrná akcie) — plošný posun celého trhu (např. režim) tak nevytvoří stovky stejných signálů."""
    up, dn = pred["up5"], pred["down5"]
    ref_up = max(base["up5"], (ref or {}).get("up5", 0.0))
    ref_dn = max(base["down5"], (ref or {}).get("down5", 0.0))
    band = M.band_of(sm.bands, pred["dir"])
    if up - ref_up >= EDGE_MIN and up - dn >= DIR_MIN and (band.get("nad_oborem") or 0) > 0:
        if conf >= CONF_MIN:
            return "RŮST", "šance na +5 % výrazně nad běžnou akcií a převažuje nad šancí na pokles"
        return "NEVÍM", f"model vidí růst, ale důvěra {conf} < {CONF_MIN}"
    if dn - ref_dn >= EDGE_MIN and dn - up >= DIR_MIN and (band.get("nad_oborem") or 0) < 0:
        if conf >= CONF_MIN:
            return "POKLES", "šance na −5 % výrazně nad běžnou akcií a převažuje nad šancí na růst"
        return "NEVÍM", f"model vidí pokles, ale důvěra {conf} < {CONF_MIN}"
    return "NEVÍM", "výhoda proti běžné akcii je malá"


# ------------------------------------------------------------------ analogie (bod 11)

class Analogs:
    def __init__(self, panel: P.SPanel, rows: list[int]):
        self.panel = panel
        self.rows = [k for k in rows if panel.fwd[panel.main_h][k] == panel.fwd[panel.main_h][k]]
        self.mu, self.sd = {}, {}
        for f in ANALOG_FEATURES:
            vals = [panel.cols[f][k] for k in self.rows if panel.cols[f][k] == panel.cols[f][k]]
            self.mu[f] = statistics.fmean(vals) if vals else 0.0
            self.sd[f] = (statistics.pstdev(vals) or 1.0) if vals else 1.0
        self.vec = {k: self._z({f: panel.cols[f][k] for f in ANALOG_FEATURES}) for k in self.rows}
        self.cls = {k: M.regime_class(panel.regime[k]) for k in self.rows}

    def _z(self, f: dict) -> tuple:
        return tuple(0.0 if f.get(x) is None or f.get(x) != f.get(x) else
                     max(-4.0, min(4.0, (f[x] - self.mu[x]) / self.sd[x])) for x in ANALOG_FEATURES)

    def find(self, f: dict, regime_label: str | None, *, k: int = 40, per_cluster: int = 2, before: int | None = None):
        z = self._z(f)
        cls = M.regime_class(regime_label)
        cand = []
        for r in self.rows:
            if self.cls[r] != cls or (before is not None and self.panel.day[r] > before):
                continue
            v = self.vec[r]
            cand.append((sum((a - b) ** 2 for a, b in zip(z, v)), r))
        cand.sort()
        picked, used = [], {}
        for d, r in cand:
            key = (M.week(self.panel.day[r]), self.panel.group[r])
            if used.get(key, 0) >= per_cluster:
                continue
            used[key] = used.get(key, 0) + 1
            picked.append(r)
            if len(picked) >= k:
                break
        return picked

    def summary(self, picked: list[int]) -> dict:
        pn = self.panel
        out = {"pocet": len(picked), "nezavislych": M.n_independent(pn, picked), "horizonty": {}}
        for h in P.HORIZONS:
            v = sorted(pn.fwd[h][r] for r in picked if pn.fwd[h][r] == pn.fwd[h][r])
            if len(v) >= 5:
                out["horizonty"][str(h)] = {"n": len(v), "median": round(v[len(v) // 2], 4),
                                            "q20": round(v[int(0.2 * (len(v) - 1))], 4),
                                            "q80": round(v[int(0.8 * (len(v) - 1))], 4),
                                            "prumer": round(statistics.fmean(min(x, 2.0) for x in v), 4),
                                            "kladnych": round(sum(1 for x in v if x > 0) / len(v), 3),
                                            "nad5": round(sum(1 for x in v if x >= 0.05) / len(v), 3),
                                            "pod5": round(sum(1 for x in v if x <= -0.05) / len(v), 3)}
        from stockradar.discovery import study
        out["priklady"] = [{"ticker": pn.sym[r], "den": study.day_str(pn.day[r]),
                            "vynos": round(pn.fwd[pn.main_h][r], 4)} for r in picked[:6]]
        return out


# ------------------------------------------------------------------ skóre složek (0–100 = percentil dnešních akcií)

def contributions(sm: M.SignalModel, f: dict) -> dict[str, float]:
    """Příspěvek skupin znaků ke směru (růst − pokles) podle finálního globálního modelu."""
    cu, cd = sm.glob["up5"].contributions(f), sm.glob["down5"].contributions(f)
    return {g: sum(cu.get(x, 0.0) - cd.get(x, 0.0) for x in feats) for g, feats in P.FEATURE_GROUPS.items()}


def percentile(sorted_vals: list[float], v: float) -> int:
    """Percentil se středním pořadím pro shody (stejná hodnota u všech akcií → 50, ne 0)."""
    import bisect
    if not sorted_vals:
        return 50
    lo, hi = bisect.bisect_left(sorted_vals, v), bisect.bisect_right(sorted_vals, v)
    return int(round(100 * (lo + hi) / 2 / len(sorted_vals)))


def day_reference(days: list[int], preds: list[dict]) -> dict[int, dict]:
    """Medián P(+5 %) a P(−5 %) všech akcií v jednotlivých dnech."""
    by: dict[int, list[dict]] = {}
    for d, p in zip(days, preds):
        by.setdefault(d, []).append(p)
    return {d: {"up5": statistics.median(p["up5"] for p in ps), "down5": statistics.median(p["down5"] for p in ps)}
            for d, ps in by.items()}


def finite(v) -> bool:
    return v is not None and v == v and not math.isinf(v)
