"""Modely pro signály na 14 dní a přísný protokol testování (body 7, 8, 12, 13 zadání).

PROTOKOL (pevná data, nikdy se neposouvají podle výsledků):
  TRAIN         vzorky do 2024-06-28 — učení modelů
  VALIDATION    2024-07-19 … 2025-06-27 — výběr modelu podle režimu (meta-model), kalibrace, pásma výnosu
  LOCKED TEST   2025-07-18 … 2026-03-27 — vyhodnotí se JEDNOU pro každou konfiguraci (registr model_evaluations);
                další běh se stejnou konfigurací výsledek jen načte, nepočítá znovu
  POST          od 2026-04-17 — kalibrace finálního modelu (naučeného na TRAIN+VALIDATION+TEST) pro živé karty
  LIVE          karty zapsané do signal_forecasts; jejich výsledky se do učení NEvracejí automaticky — jen novou
                verzí modelu (nová konfigurace = nový zápis v registru, počet pokusů je vidět)
Mezi obdobími jsou 3 týdny mezera (cíl je 10 obchodních dní), aby se výsledky nepřekrývaly.

Režimy: „KLID“ (býčí klidný trh) a „STRES“ (vše ostatní). Pro každý cíl se učí globální model a model pro každou
třídu režimu; meta-model na validaci vybere, kterému věřit (globální / režimový / průměr obou).
Nezávislé případy: vzorky ve stejném týdnu a oboru nejsou nezávislé → počítá se počet různých (týden, obor)
a t-statistika přes týdny.
"""

import hashlib
import json
import math
import statistics
from concurrent.futures import ProcessPoolExecutor
from datetime import date

from stockradar.discovery import rocket, study
from stockradar.signals import panel as P

MODEL_NAME = "SIGNAL_14D"
MODEL_VERSION = "1.0"
TRAIN_END = date(2024, 6, 28).toordinal()
VAL = (date(2024, 7, 19).toordinal(), date(2025, 6, 27).toordinal())
TEST = (date(2025, 7, 18).toordinal(), date(2026, 3, 27).toordinal())
POST_START = date(2026, 4, 17).toordinal()
TARGETS = ("up5", "down5", "beat_sec", "big")
CLASSES = ("KLID", "STRES")
CAL_BINS = 10


def share_for(day: int) -> float:
    if day <= TRAIN_END:
        return 0.18
    if VAL[0] <= day <= VAL[1]:
        return 0.30
    if TEST[0] <= day <= TEST[1]:
        return 0.30
    if day >= POST_START:
        return 0.40
    return 0.0                      # mezery mezi obdobími


# Horizonty: 14 dní je původní model (konfigurace se nesmí změnit — zamčený test už proběhl); 1 měsíc je samostatný
# model se stejným protokolem, jen s delší mezerou mezi obdobími (cíl 20 obchodních dní ≈ 4 týdny).
SPECS = {
    "SIGNAL_14D": {"nazev": "14 dní", "h": P.H, "up": P.UP, "down": P.DOWN, "big": P.BIG, "gap": None,
                   "labels": dict(zip(TARGETS, ("up5", "down5", "beat_sec", "big"))), "ex_sec": "ex_sec"},
    "SIGNAL_1M": {"nazev": "1 měsíc", "h": P.H_1M, "up": P.UP_1M, "down": P.DOWN_1M, "big": P.BIG_1M, "gap": 33,
                  "labels": dict(zip(TARGETS, ("up10_20", "down10_20", "beat_sec_20", "big20_20"))), "ex_sec": "ex_sec_20"},
    # 6 měsíců: mezera ~půl roku mezi obdobími (cíle na 126 obchodních dní se nesmí překrývat); data po testu ještě
    # nemají známý výsledek → žádné období POST, kalibrace z validace prvního modelu
    "SIGNAL_6M": {"nazev": "6 měsíců", "h": P.H_6M, "up": P.UP_6M, "down": P.DOWN_6M, "big": P.BIG_6M, "gap": 185,
                  "post": False, "features": "6M", "rank": "up",
                  "labels": dict(zip(TARGETS, ("up40_126", "down25_126", "beat_sec_126", "big50_126"))),
                  "ex_sec": "ex_sec_126"},
}


def features_of(model_name: str) -> list[str]:
    return list(P.MODEL_FEATURES_6M if SPECS[model_name].get("features") == "6M" else P.MODEL_FEATURES)


class HorizonView:
    """Pohled na panel pro jiný horizont: cíle up5/down5/beat_sec/big znamenají jeho prahy (např. ±10 % za měsíc)."""

    def __init__(self, panel, spec: dict):
        self._p = panel
        self.y = {t: panel.y[lab] for t, lab in spec["labels"].items()}
        self.ex_sec = getattr(panel, spec["ex_sec"])
        self.main_h = spec["h"]

    def __getattr__(self, name):
        return getattr(self._p, name)

    def __len__(self):
        return len(self._p)


def view(panel, model_name: str):
    return panel if model_name == "SIGNAL_14D" else HorizonView(panel, SPECS[model_name])


def split_of(day: int, gap: int | None = None, post: bool = True) -> str | None:
    """gap = mezera v kalendářních dnech před začátkem dalšího období (delší horizont → delší mezera).
    post=False: model bez období POST (6 měsíců) — test končí TEST[1], po něm nic."""
    if gap:
        if day <= min(TRAIN_END, VAL[0] - gap):
            return "TRAIN"
        if VAL[0] <= day <= min(VAL[1], TEST[0] - gap):
            return "VALIDATION"
        if TEST[0] <= day <= (TEST[1] if not post else min(TEST[1], POST_START - gap)):
            return "LOCKED_TEST"
        return "POST" if post and day >= POST_START else None
    return _split_14d(day)


def _split_14d(day: int) -> str | None:
    if day <= TRAIN_END:
        return "TRAIN"
    if VAL[0] <= day <= VAL[1]:
        return "VALIDATION"
    if TEST[0] <= day <= TEST[1]:
        return "LOCKED_TEST"
    if day >= POST_START:
        return "POST"
    return None


def regime_class(label: str | None) -> str:
    return "KLID" if label == "BÝČÍ KLIDNÝ" else "STRES"


def config_hash(features: list[str], model_name: str = "SIGNAL_14D") -> str:
    from stockradar.signals import card
    spec = SPECS[model_name]
    rules = {"conf_min": card.CONF_MIN, "edge": card.EDGE_MIN, "dir": card.DIR_MIN, "analog": card.ANALOG_FEATURES,
             "penalty_rules": "1.0"}
    cfg = {"v": MODEL_VERSION, "features": features, "rules": rules, "targets": TARGETS, "h": spec["h"], "up": spec["up"],
           "down": spec["down"], "big": spec["big"], "train_end": TRAIN_END, "val": VAL, "test": TEST, "bins": rocket.BINS,
           "l2": rocket.L2, "sweeps": rocket.SWEEPS, "universe": [P.MIN_TURNOVER, P.MIN_PRICE], "step": P.STEP_DAYS}
    if model_name != "SIGNAL_14D":            # 14 dní: přesně původní otisk (zamčený test už proběhl)
        cfg.update({"model": model_name, "gap": spec["gap"], "labels": spec["labels"]})
    if "post" in spec:                        # 6 měsíců (1 měsíc beze změny otisku)
        cfg.update({"post": spec["post"], "overlap_t": "sqrt(h/5)"})
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]


# ------------------------------------------------------------------ nezávislé případy a statistika

def week(day: int) -> int:
    return day // 7


def n_independent(panel: P.SPanel, rows) -> int:
    return len({(week(panel.day[k]), panel.group[k]) for k in rows})


def weekly_t(panel: P.SPanel, rows, values) -> float | None:
    """t-statistika průměru přes týdny (každý týden = jedno pozorování)."""
    by = {}
    for k, v in zip(rows, values):
        if v == v:
            by.setdefault(week(panel.day[k]), []).append(v)
    m = [statistics.fmean(v) for v in by.values()]
    if len(m) < 3:
        return None
    sd = statistics.stdev(m)
    # 6 měsíců: týdenní vzorky s výsledkem na 26 týdnů se překrývají → t konzervativně / sqrt(h/5)
    # (14 dní a 1 měsíc beze změny — jejich zamčené testy byly vyhodnoceny bez korekce)
    ov = math.sqrt(panel.main_h / 5) if getattr(panel, "main_h", 10) > 20 else 1.0
    return round(statistics.fmean(m) / (sd / math.sqrt(len(m))) / ov, 2) if sd > 0 else None


def p_from_t(t: float | None) -> float | None:
    """Dvoustranná p-hodnota z t (normální aproximace) = „šance, že jde o šum“."""
    if t is None:
        return None
    return round(math.erfc(abs(t) / math.sqrt(2)), 4)


# ------------------------------------------------------------------ učení

_PANEL = None   # sdílený panel pro paralelní učení (fork)


def _train_job(args):
    rows, target, feats = args
    y = _PANEL.y[target]
    rows = [k for k in rows if y[k] >= 0]
    woe = rocket.fit_woe(_PANEL, rows, y, feats)
    xs = [[woe.value(f, _PANEL.cols[f][k]) for k in rows] for f in feats]
    yy = [y[k] for k in rows]
    b0, w = rocket.fit_logistic(xs, yy)
    return rocket.Model(feats, woe, b0, w, sum(yy) / max(len(yy), 1))


def train_many(panel: P.SPanel, jobs: dict, *, workers: int = 4, log=print) -> dict:
    """jobs: klíč → (řádky, cíl, znaky). Učí paralelně (fork sdílí panel bez kopírování)."""
    global _PANEL
    _PANEL = panel
    keys = list(jobs)
    log(f"Učím {len(keys)} modelů ({workers} procesy)")
    if workers <= 1:
        return {k: _train_job(jobs[k]) for k in keys}
    import multiprocessing as mp
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("fork")) as ex:
        res = list(ex.map(_train_job, [jobs[k] for k in keys]))
    return dict(zip(keys, res))


def logloss(p: float, y: int) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


# ------------------------------------------------------------------ kalibrace (monotónní, po binech)

def calibrate(preds: list[float], ys: list[int], panel=None, rows=None, bins: int = CAL_BINS) -> dict:
    order = sorted(range(len(preds)), key=lambda i: preds[i])
    groups = [order[b * len(order) // bins:(b + 1) * len(order) // bins] for b in range(bins)]
    groups = [g for g in groups if g]
    edges = [preds[g[-1]] for g in groups[:-1]]
    rate = [sum(ys[i] for i in g) / len(g) for g in groups]
    n = [len(g) for g in groups]
    # PAV: vynutí monotónnost (vyšší predikce nesmí mít nižší kalibrovanou šanci)
    blocks = [[r * m, m, [b]] for b, (r, m) in enumerate(zip(rate, n))]
    out = []
    for blk in blocks:
        out.append(blk)
        while len(out) > 1 and out[-2][0] / out[-2][1] > out[-1][0] / out[-1][1]:
            a = out.pop()
            out[-1] = [out[-1][0] + a[0], out[-1][1] + a[1], out[-1][2] + a[2]]
    mono = [0.0] * len(groups)
    for s, m, bs in out:
        for b in bs:
            mono[b] = s / m
    res = {"edges": edges, "rate": [round(x, 4) for x in mono], "n": n,
           "pred": [round(statistics.fmean(preds[i] for i in g), 4) for g in groups],
           "actual": [round(r, 4) for r in rate]}
    if panel is not None and rows is not None:
        res["n_indep"] = [n_independent(panel, [rows[i] for i in g]) for g in groups]
    return res


def apply_cal(cal: dict, p: float) -> float:
    """Lineární interpolace mezi středy binů (monotónní kalibrace bez skoků a shod)."""
    import bisect
    xs, ys = cal["pred"], cal["rate"]
    if p <= xs[0]:
        return ys[0]
    if p >= xs[-1]:
        return ys[-1]
    i = bisect.bisect_right(xs, p)
    x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
    return y0 + (y1 - y0) * (p - x0) / (x1 - x0) if x1 > x0 else y0


def cal_bin(cal: dict, p: float) -> int:
    import bisect
    return bisect.bisect_left(cal["edges"], p)


# ------------------------------------------------------------------ predikce s meta-modelem

class SignalModel:
    """Sada modelů: global[target], regime[(target, třída)], volba meta-modelu, kalibrace, pásma výnosu."""

    def __init__(self, features, glob, reg, choice, cal=None, bands=None, base=None, noise=None):
        self.features, self.glob, self.reg, self.choice = features, glob, reg, choice
        self.cal, self.bands, self.base, self.noise = cal or {}, bands, base or {}, noise

    def raw(self, f: dict, cls: str) -> dict:
        out = {}
        for t in TARGETS:
            g = self.glob[t].prob(f)
            r = self.reg[(t, cls)].prob(f) if (t, cls) in self.reg else g
            ch = self.choice.get((t, cls), "global")
            p = g if ch == "global" else r if ch == "rezim" else (g + r) / 2
            out[t] = {"p": p, "global": g, "rezim": r}
        return out

    def predict(self, f: dict, cls: str) -> dict:
        raw = self.raw(f, cls)
        out = {t: (apply_cal(self.cal[t], raw[t]["p"]) if t in self.cal else raw[t]["p"]) for t in TARGETS}
        up, dn = out["up5"], out["down5"]
        if up + dn > 0.98:            # P(flat) nesmí být záporné
            s = (up + dn) / 0.98
            up, dn = up / s, dn / s
        out.update({"up5": up, "down5": dn, "flat": 1 - up - dn, "dir": up - dn,
                    "disagree": statistics.fmean(abs(raw[t]["global"] - raw[t]["rezim"]) for t in TARGETS),
                    "raw": {t: raw[t]["p"] for t in TARGETS}})
        return out


def direction_bands(panel, rows, preds: list[dict]) -> dict:
    """Pásma podle směrového skóre (P(růst) − P(pokles)) → očekávaný výnos za 14 dní a šance na šum (p-hodnota)."""
    scores = [p["dir"] for p in preds]
    order = sorted(range(len(rows)), key=lambda i: scores[i])
    groups = [order[b * len(order) // 10:(b + 1) * len(order) // 10] for b in range(10)]
    all_ex = [panel.ex_sec[rows[i]] for i in range(len(rows))]
    mean_all = statistics.fmean(v for v in all_ex if v == v)
    bands = {"edges": [scores[g[-1]] for g in groups[:-1]], "pasma": []}
    for b, g in enumerate(groups):
        rr = [rows[i] for i in g]
        h = panel.main_h
        f10 = sorted(min(max(panel.fwd[h][k], -0.9), 2.0) for k in rr if panel.fwd[h][k] == panel.fwd[h][k])
        ex = [panel.ex_sec[k] - mean_all for k in rr if panel.ex_sec[k] == panel.ex_sec[k]]
        t = weekly_t(panel, [k for k in rr if panel.ex_sec[k] == panel.ex_sec[k]], ex)
        bands["pasma"].append({
            "pasmo": b + 1, "n": len(rr), "n_indep": n_independent(panel, rr),
            "vynos_prumer": round(statistics.fmean(f10), 4) if f10 else None,
            "vynos_median": round(f10[len(f10) // 2], 4) if f10 else None,
            "vynos_q20": round(f10[int(0.2 * (len(f10) - 1))], 4) if f10 else None,
            "vynos_q80": round(f10[int(0.8 * (len(f10) - 1))], 4) if f10 else None,
            "nad_oborem": round(statistics.fmean(panel.ex_sec[k] for k in rr if panel.ex_sec[k] == panel.ex_sec[k]), 4),
            "t": t, "sum": p_from_t(t)})
    return bands


def bisect_band(bands: dict, score: float) -> int:
    import bisect
    return bisect.bisect_left(bands["edges"], score)


def band_of(bands: dict, score: float) -> dict:
    import bisect
    return bands["pasma"][bisect.bisect_left(bands["edges"], score)]


# ------------------------------------------------------------------ vyhodnocení období

def evaluate(panel: P.SPanel, rows: list[int], preds: list[dict], decide=None) -> dict:
    out = {"vzorku": len(rows), "nezavislych": n_independent(panel, rows), "tydnu": len({week(panel.day[k]) for k in rows})}
    for t in TARGETS:
        y = panel.y[t]
        pairs = [(preds[i][t], y[k]) for i, k in enumerate(rows) if y[k] >= 0]
        if not pairs:
            continue
        base = sum(v for _, v in pairs) / len(pairs)
        brier = statistics.fmean((p - v) ** 2 for p, v in pairs)
        brier0 = statistics.fmean((base - v) ** 2 for _, v in pairs)
        out[t] = {"zaklad": round(base, 4), "auc": round(study.auc([p for p, _ in pairs], [v for _, v in pairs]) or 0, 4),
                  "brier": round(brier, 5), "brier_skill": round(1 - brier / brier0, 4) if brier0 > 0 else None,
                  "logloss": round(statistics.fmean(logloss(p, v) for p, v in pairs), 4)}
    # horní a dolní desetina podle směrového skóre vs všechny (týdenní t-statistika)
    order = sorted(range(len(rows)), key=lambda i: preds[i]["dir"])
    tenth = max(1, len(order) // 10)
    for name, part in (("horni_desetina", order[-tenth:]), ("dolni_desetina", order[:tenth])):
        rr = [rows[i] for i in part]
        out[name] = _bucket(panel, rr, rows)
    if decide is not None:
        groups: dict[str, list[int]] = {}
        for i, k in enumerate(rows):
            groups.setdefault(decide(preds[i], k)[0], []).append(k)
        out["rozhodnuti"] = {g: _bucket(panel, rr, rows) for g, rr in groups.items()}
    by_reg: dict[str, list[int]] = {}
    for i, k in enumerate(rows):
        by_reg.setdefault(panel.regime[k], []).append(i)
    out["podle_rezimu"] = {}
    for reg, idx in by_reg.items():
        rr = [rows[i] for i in idx]
        pp = [preds[i] for i in idx]
        ys = [(pp[j]["up5"], panel.y["up5"][k]) for j, k in enumerate(rr) if panel.y["up5"][k] >= 0]
        o = sorted(range(len(rr)), key=lambda j: pp[j]["dir"])
        top = [rr[j] for j in o[-max(1, len(o) // 10):]]
        out["podle_rezimu"][reg] = {"vzorku": len(rr), "nezavislych": n_independent(panel, rr),
                                    "tydnu": len({week(panel.day[k]) for k in rr}),
                                    "auc_up5": round(study.auc([p for p, _ in ys], [v for _, v in ys]) or 0, 4) if ys else None,
                                    "horni_desetina": _bucket(panel, top, rr)}
    return out


def _bucket(panel, rr: list[int], ref: list[int]) -> dict:
    lab = [k for k in rr if panel.y["up5"][k] >= 0]
    if not lab:
        return {"n": len(rr)}
    f10 = sorted(panel.fwd[panel.main_h][k] for k in lab)
    ref_ex = {}
    for k in ref:
        if panel.ex_sec[k] == panel.ex_sec[k]:
            ref_ex.setdefault(week(panel.day[k]), []).append(panel.ex_sec[k])
    wk_mean = {w: statistics.fmean(v) for w, v in ref_ex.items()}
    diffs = [panel.ex_sec[k] - wk_mean.get(week(panel.day[k]), 0.0) for k in lab if panel.ex_sec[k] == panel.ex_sec[k]]
    t = weekly_t(panel, [k for k in lab if panel.ex_sec[k] == panel.ex_sec[k]], diffs)
    return {"n": len(lab), "n_indep": n_independent(panel, lab),
            "up5": round(sum(panel.y["up5"][k] for k in lab) / len(lab), 4),
            "down5": round(sum(panel.y["down5"][k] for k in lab) / len(lab), 4),
            "beat_sec": round(sum(1 for k in lab if panel.y["beat_sec"][k] == 1) / len(lab), 4),
            "vynos_median": round(f10[len(f10) // 2], 4), "vynos_prumer": round(statistics.fmean(min(v, 2.0) for v in f10), 4),
            "nad_tydnem": round(statistics.fmean(diffs), 4) if diffs else None, "t": t, "sum": p_from_t(t)}
