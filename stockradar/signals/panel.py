"""Historický panel pro signály na 14 dní (10 obchodních dní).

Vzorek = akcie × den (každý týden v pátek), jen americké akcie (SEC fundamenty, insideři, výsledky) s obratem
≥ 1 mil. USD/den a cenou ≥ 2 USD. Znaky jen z dat známých k tomu dni. Výsledky (cíle) se počítají z cen PO tom dni:
  up5       výnos za 10 obchodních dní ≥ +5 %          down5   ≤ −5 %
  big       během 10 dní pohyb aspoň ±10 % (prudký pohyb)
  beat_sec  výnos lepší než medián oboru ve stejném okně (relativní síla — bod 9)
  fwd_*     výnos po 1, 5, 10, 20, 60, 120 obchodních dnech (pro analogie — bod 11)
Každý vzorek nese obor a týden → počet NEZÁVISLÝCH případů = počet různých (týden, obor) (bod 13).
"""

import hashlib
import math
import statistics
from array import array

from stockradar.discovery import study
from stockradar.discovery.features import features_at
from stockradar.discovery.fundamentals import FUND_FEATURES
from stockradar.signals.extra import EXTRA_FEATURES
from stockradar.signals.mechanism import MECH_FEATURES, mech_feature
from stockradar.signals.regime import REGIME_FEATURES, label_from

H = 10                          # obchodních dní ≈ 14 kalendářních
UP, DOWN, BIG = 0.05, -0.05, 0.10
HORIZONS = (1, 5, 10, 20, 60, 120)
STEP_DAYS = 7
MIN_TURNOVER, MIN_PRICE = 1_000_000, 2.0

PRICE_FEATURES = {
    "r5": "Pohyb za týden", "r20": "Pohyb za měsíc", "r60": "Pohyb za 3 měsíce", "r120": "Pohyb za 6 měsíců",
    "r250": "Pohyb za rok", "dd252": "Odstup od ročního maxima", "up252": "Výška nad ročním minimem",
    "vol20": "Volatilita 20 dní", "vol_ratio": "Stlačení volatility (20 d / 120 d)", "volu_5_60": "Objem 5 dní / 60 dní",
    "volu_20_120": "Objem 20 dní / 120 dní", "turnover": "Denní obrat (log USD)", "price": "Cena (log USD)",
    "max_day20": "Největší denní skok za 20 dní",
}
RS_FEATURES = {
    "rel_r5": "Síla vůči oboru za týden", "rel_r20": "Síla vůči oboru za měsíc", "rel_r60": "Síla vůči oboru za 3 měsíce",
    "sec_r20": "Obor za měsíc (medián)", "sec_r60": "Obor za 3 měsíce (medián)", "mkt_r20": "Celý trh za měsíc (medián)",
}
# Znaky celého trhu (režim, medián trhu) jsou v panelu jen pro analogie a analýzu, NE v modelu akcií: v jednom týdnu
# mají všechny akcie stejnou hodnotu, takže „tisíce vzorků“ jsou ve skutečnosti jen desítky nezávislých období (bod 13).
FEATURE_GROUPS = {
    "technika": list(PRICE_FEATURES) + [f for f in RS_FEATURES if f != "mkt_r20"],
    "fundament": [f for f in FUND_FEATURES if f not in ("n8k_30", "offer_90", "d13_180", "p3_180", "p2_180")]
                 + ["eps_chg_p", "sue"],
    "katalyzator": ["n8k_30", "offer_90", "p3_180", "p2_180", "ear", "gap", "drift", "days_since_ann", "news_reac",
                    "news_vol"],
    "kapital": ["ins_n30", "ins_val90", "bb_yield", "g13_90", "d13_180", "acc20"],
    "mechanismus": list(MECH_FEATURES),
}
ALL_FEATURES = {**PRICE_FEATURES, **RS_FEATURES, **REGIME_FEATURES, **FUND_FEATURES, **EXTRA_FEATURES, **MECH_FEATURES}
MODEL_FEATURES = [f for g in FEATURE_GROUPS.values() for f in g]
LABELS = ("up5", "down5", "big", "beat_sec")


def keep(symbol: str, day: int, share: float) -> bool:
    h = int.from_bytes(hashlib.blake2b(f"S|{symbol}|{day}".encode(), digest_size=4).digest(), "big")
    return h / 2 ** 32 < share


class SPanel:
    def __init__(self, features: list[str]):
        self.features = features
        self.cols = {f: array("d") for f in features}
        self.y = {k: array("b") for k in LABELS}
        self.fwd = {h: array("d") for h in HORIZONS}
        self.ex_sec = array("d")
        self.day = array("i")
        self.sym: list[str] = []
        self.group: list[str] = []
        self.regime: list[str] = []

    def __len__(self):
        return len(self.day)

    def add(self, sym, day, group, regime, f: dict, lab: dict | None):
        nan = math.nan
        for k in self.features:
            v = f.get(k)
            self.cols[k].append(nan if v is None else float(v))
        for k in LABELS:
            self.y[k].append(-1 if lab is None or lab.get(k) is None else int(lab[k]))
        for h in HORIZONS:
            v = lab.get(f"fwd_{h}") if lab else None
            self.fwd[h].append(nan if v is None else v)
        self.ex_sec.append(nan if lab is None or lab.get("ex_sec") is None else lab["ex_sec"])
        self.day.append(day)
        self.sym.append(sym)
        self.group.append(group)
        self.regime.append(regime or "?")

    def row(self, k: int) -> dict:
        return {f: self.cols[f][k] for f in self.features}


def fwd_labels(c, i: int) -> dict | None:
    out = {f"fwd_{h}": (c[i + h] / c[i] - 1 if i + h < len(c) and c[i] > 0 else None) for h in HORIZONS}
    if out["fwd_10"] is None:
        return out if any(v is not None for v in out.values()) else None
    r = out["fwd_10"]
    hi = max(c[i + 1:i + H + 1]) / c[i] - 1
    lo = min(c[i + 1:i + H + 1]) / c[i] - 1
    out.update({"up5": r >= UP, "down5": r <= DOWN, "big": max(hi, -lo) >= BIG})
    return out


def is_us(symbol: str) -> bool:
    return "." not in symbol and not symbol.startswith("^")


def panel_days(data: study.Data, step: int = STEP_DAYS) -> list[int]:
    end = data.data_end
    first = data.data_start + 260
    d = end - (end - first) % step
    out = []
    while d >= first:
        out.append(d)
        d -= step
    return out[::-1]


def snapshot(data: study.Data, day: int, ptr: dict | None = None) -> dict:
    """Pro den: index posledního obchodního dne každé likvidní US akcie a mediány oborů (dnes i dopředu)."""
    idx, rate_of = {}, {}
    for sym, s in data.secs.items():
        if not is_us(sym):
            continue
        dd = s.prep.bars.days
        j = (ptr or {}).get(sym, 0)
        while j + 1 < len(dd) and dd[j + 1] <= day:
            j += 1
        if ptr is not None:
            ptr[sym] = j
        if dd[j] > day or day - dd[j] > 4 or j < 252:
            continue
        rate = data.usd_rate(s.currency, dd[j])
        if rate is None or s.prep.bars.closes[j] * rate < MIN_PRICE:
            continue
        if study.turnover_usd(s.prep, j, rate) < MIN_TURNOVER:
            continue
        idx[sym], rate_of[sym] = j, rate
    per_group: dict[str, dict[str, list[float]]] = {}
    for sym, j in idx.items():
        s = data.secs[sym]
        c = s.prep.bars.closes
        g = per_group.setdefault(s.group, {"r5": [], "r20": [], "r60": [], "f10": []})
        for n, key in ((5, "r5"), (20, "r20"), (60, "r60")):
            if c[j - n] > 0:
                g[key].append(c[j] / c[j - n] - 1)
        if j + H < len(c) and c[j] > 0:
            g["f10"].append(c[j + H] / c[j] - 1)
    med = {g: {k: (statistics.median(v) if len(v) >= 5 else None) for k, v in vals.items()} for g, vals in per_group.items()}
    allr20 = [data.secs[s].prep.bars.closes[j] / data.secs[s].prep.bars.closes[j - 20] - 1 for s, j in idx.items()
              if data.secs[s].prep.bars.closes[j - 20] > 0]
    return {"idx": idx, "rate": rate_of, "med": med, "mkt_r20": statistics.median(allr20) if allr20 else None}


def sample(data, s, j, rate, snap, fund, extra, regime_f) -> dict | None:
    f = features_at(s.prep, j, rate)
    if f is None:
        return None
    f.pop("new_listing", None)
    c = s.prep.bars.closes
    m = snap["med"].get(s.group, {})
    for n, key in ((5, "r5"), (20, "r20"), (60, "r60")):
        own = c[j] / c[j - n] - 1 if c[j - n] > 0 else None
        f[f"rel_{key}"] = own - m[key] if own is not None and m.get(key) is not None else None
    f["sec_r20"], f["sec_r60"], f["mkt_r20"] = m.get("r20"), m.get("r60"), snap["mkt_r20"]
    f["mech_up_r20"] = mech_feature(s.group, snap["med"])
    f.update(regime_f)
    day = s.prep.bars.days[j]
    fu = fund.features(s.symbol, day, c[j] * rate)
    f.update(fu)
    f.update(extra.features(s.symbol, s.prep.bars, j, c[j] * rate, fu.get("log_mcap")))
    return f


def build(data: study.Data, fund, extra, regime, *, shares: dict, log=print) -> SPanel:
    """shares: funkce den → podíl vzorkovaných akcií (víc v obdobích pro validaci a test)."""
    panel = SPanel(list(ALL_FEATURES))
    ptr: dict[str, int] = {}
    days = panel_days(data)
    for n, day in enumerate(days):
        share = shares(day)
        snap = snapshot(data, day, ptr)
        rf = regime.features(day)
        rlabel = label_from(rf)
        for sym, j in snap["idx"].items():
            if share <= 0 or not keep(sym, day, share):
                continue
            s = data.secs[sym]
            f = sample(data, s, j, snap["rate"][sym], snap, fund, extra, rf)
            if f is None:
                continue
            lab = fwd_labels(s.prep.bars.closes, j)
            if lab is not None and lab.get("fwd_10") is not None:
                m10 = snap["med"].get(s.group, {}).get("f10")
                if m10 is not None:
                    lab["ex_sec"] = lab["fwd_10"] - m10
                    lab["beat_sec"] = lab["ex_sec"] > 0
            panel.add(sym, day, s.group, rlabel, f, lab)
        if n % 25 == 0:
            log(f"panel {study.day_str(day)}: {len(panel)} vzorků")
    return panel
