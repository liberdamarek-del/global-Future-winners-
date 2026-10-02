"""Studie událostí: co předcházelo raketám, kontrolní skupina, předvídatelnost, sektorové vlny (§6–§14, §41).

Poctivost výsledků:
  * Znaky v T0 popisují stav na „dně“ před raketou — T0 je vybrané se znalostí budoucnosti, proto lift tabulky
    ukazují souvislost, ne předpověď.
  * Skutečná předvídatelnost se měří zvlášť: model naučený jen na starších datech oskóruje VŠECHNY akcie každý týden
    v pozdějším období a porovná se, kolik raket opravdu přišlo (přesnost vs. základní četnost).
  * Seznamy firem jsou dnešní (bez zkrachovalých/delistovaných) → survivorship bias, je uveden ve výstupu.
"""

import bisect
import math
import random
import statistics
from dataclasses import dataclass, field
from datetime import date

from stockradar.discovery import cache
from stockradar.discovery.features import FEATURES, Prepared, features_at, prepare, turnover_usd
from stockradar.discovery.winners import EVENT_TYPES, Event, find_events
from stockradar.sources.yahoo import fx_symbol, usd_factor

MIN_TURNOVER_USD = 250_000      # likvidita v T0 (průměr 20 dní)
MIN_PRICE_USD = 0.5
HEAT_DAYS = 28                  # kalendářní dny pro „vlnu“ v oboru / na trhu
CONTROLS_PER_EVENT = 5


@dataclass
class Sec:
    symbol: str
    meta: dict
    prep: Prepared
    currency: str | None
    group: str


@dataclass
class Data:
    secs: dict[str, Sec]
    fx: dict[str, cache.Bars]
    data_start: int
    data_end: int
    groups: dict[str, list[str]] = field(default_factory=dict)

    def usd_rate(self, currency: str | None, day: int) -> float | None:
        if not currency:
            return None
        sym = fx_symbol(currency)
        if sym is None:
            return usd_factor(currency)
        s = self.fx.get(sym)
        if s is None:
            return None
        i = bisect.bisect_right(s.days, day) - 1
        if i < 0 or day - s.days[i] > 10 or s.closes[i] <= 0:
            return None
        return usd_factor(currency) / s.closes[i]


def group_key(meta: dict) -> str:
    label = (meta.get("industry") or meta.get("sector") or "neznámý obor").strip()
    return label.lower()


def load_data(conn, *, min_bars: int = 250, symbols: list[str] | None = None) -> Data:
    metas = {r["symbol"]: dict(r) for r in conn.execute("SELECT * FROM securities")}
    fx = {}
    secs = {}
    starts = []
    for bars in cache.iter_series(conn):
        if bars.symbol.endswith("=X"):
            fx[bars.symbol] = bars
            continue
        if symbols is not None and bars.symbol not in symbols:
            continue
        if bars.symbol not in metas or len(bars.days) < min_bars:
            continue
        starts.append(bars.days[0])
        secs[bars.symbol] = bars
    data_start = min(starts) if starts else 0
    out = {}
    for sym, bars in secs.items():
        meta = metas[sym]
        out[sym] = Sec(sym, meta, prepare(bars, data_start), bars.currency, group_key(meta))
    data = Data(out, fx, data_start, max((s.prep.bars.days[-1] for s in out.values()), default=0))
    for sym, s in out.items():
        data.groups.setdefault(s.group, []).append(sym)
    return data


def liquid_at(data: Data, s: Sec, i: int) -> tuple[bool, float | None]:
    rate = data.usd_rate(s.currency, s.prep.bars.days[i])
    if rate is None:
        return False, None
    ok = turnover_usd(s.prep, i, rate) >= MIN_TURNOVER_USD and s.prep.bars.closes[i] * rate >= MIN_PRICE_USD
    return ok, rate


def scan_events(data: Data, kind: str) -> list[Event]:
    out = []
    for s in data.secs.values():
        for ev in find_events(s.prep.bars, kind):
            if ev.t0 >= 120 and liquid_at(data, s, ev.t0)[0]:
                out.append(ev)
    return out


class Heat:
    """Kolik raket (W1) skončilo v oboru / na trhu během posledních HEAT_DAYS dní — jen známé k danému dni."""

    def __init__(self, data: Data, events: list[Event]):
        self.by_group: dict[str, list[int]] = {}
        self.all: list[int] = []
        for ev in events:
            s = data.secs[ev.symbol]
            day = s.prep.bars.days[ev.end]
            self.by_group.setdefault(s.group, []).append(day)
            self.all.append(day)
        for v in self.by_group.values():
            v.sort()
        self.all.sort()
        self.sizes = {g: len(v) for g, v in data.groups.items()}
        self.total = max(len(data.secs), 1)

    @staticmethod
    def _count(days: list[int], day: int) -> int:
        return bisect.bisect_left(days, day) - bisect.bisect_left(days, day - HEAT_DAYS)

    def at(self, group: str, day: int) -> tuple[float, float]:
        g = self._count(self.by_group.get(group, []), day) / max(self.sizes.get(group, 1), 1)
        return g, self._count(self.all, day) / self.total


def sample_features(data: Data, s: Sec, i: int, heat: Heat) -> dict | None:
    ok, rate = liquid_at(data, s, i)
    if not ok:
        return None
    f = features_at(s.prep, i, rate)
    if f is None:
        return None
    f["sector_heat"], f["market_heat"] = heat.at(s.group, s.prep.bars.days[i])
    return f


def build_case_control(data: Data, events: list[Event], kind: str, heat: Heat, *, seed: int = 7) -> list[dict]:
    """Ke každé raketě CONTROLS_PER_EVENT náhodných firem ve stejný den bez rakety (§8)."""
    rng = random.Random(seed)
    window = EVENT_TYPES[kind][0]
    ev_days: dict[str, list[int]] = {}
    for ev in events:
        ev_days.setdefault(ev.symbol, []).append(data.secs[ev.symbol].prep.bars.days[ev.t0])
    for v in ev_days.values():
        v.sort()
    symbols = list(data.secs)
    rows = []
    for ev in events:
        s = data.secs[ev.symbol]
        day = s.prep.bars.days[ev.t0]
        f = sample_features(data, s, ev.t0, heat)
        if f is None:
            continue
        rows.append({"y": 1, "symbol": ev.symbol, "day": day, "f": f, "ret": ev.ret})
        got, tries = 0, 0
        while got < CONTROLS_PER_EVENT and tries < CONTROLS_PER_EVENT * 8:
            tries += 1
            c = data.secs[rng.choice(symbols)]
            j = bisect.bisect_right(c.prep.bars.days, day) - 1
            if j < 120 or day - c.prep.bars.days[j] > 5:
                continue
            near = ev_days.get(c.symbol, [])
            k = bisect.bisect_left(near, day - 2 * window * 2)
            if k < len(near) and near[k] <= day + 2 * window * 2:
                continue  # kontrola nesmí mít raketu poblíž
            fc = sample_features(data, c, j, heat)
            if fc is None:
                continue
            rows.append({"y": 0, "symbol": c.symbol, "day": day, "f": fc, "ret": None})
            got += 1
    return rows


def lift_table(rows: list[dict], *, buckets: int = 5) -> list[dict]:
    """Pro každý znak: kvintily podle kontrolní skupiny, podíl raket v každém kvintilu vůči očekávání (lift)."""
    out = []
    controls = [r for r in rows if r["y"] == 0]
    events = [r for r in rows if r["y"] == 1]
    for feat in FEATURES:
        cvals = sorted(r["f"][feat] for r in controls if r["f"].get(feat) is not None)
        evals = [r["f"][feat] for r in events if r["f"].get(feat) is not None]
        if len(cvals) < 100 or len(evals) < 30:
            continue
        if feat == "new_listing":
            parts = [(None, 0.5, "ne"), (0.5, None, "ano")]
        else:
            edges = [cvals[int(len(cvals) * q / buckets)] for q in range(1, buckets)]
            if len(set(edges)) < len(edges):
                continue
            bounds = [None] + edges + [None]
            parts = [(bounds[k], bounds[k + 1], f"Q{k + 1}") for k in range(buckets)]
        cells = []
        for lo, hi, name in parts:
            def inside(x, lo=lo, hi=hi):
                return (lo is None or x >= lo) and (hi is None or x < hi)
            ce = sum(1 for x in evals if inside(x)) / len(evals)
            cc = sum(1 for x in cvals if inside(x)) / len(cvals)
            cells.append({"kvintil": name, "od": lo, "do": hi, "podil_raket": round(ce, 4),
                          "podil_kontrol": round(cc, 4), "lift": round(ce / cc, 2) if cc > 0 else None})
        best = max(cells, key=lambda c: c["lift"] or 0)
        out.append({"znak": feat, "nazev": FEATURES[feat], "kvintily": cells, "nejsilnejsi": best,
                    "raket": len(evals), "kontrol": len(cvals)})
    out.sort(key=lambda r: r["nejsilnejsi"]["lift"] or 0, reverse=True)
    return out


# ------------------------------------------------------------------ logistická regrese (čistý Python, IRLS)

def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        p = m[col][col] or 1e-12
        for r in range(n):
            if r != col:
                f = m[r][col] / p
                if f:
                    m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[i][n] / (m[i][i] or 1e-12) for i in range(n)]


@dataclass
class Logit:
    features: list[str]
    means: dict[str, float]
    stds: dict[str, float]
    coef: list[float]  # [intercept, ...]

    def vector(self, f: dict) -> list[float]:
        return [1.0] + [((f.get(k) if f.get(k) is not None else self.means[k]) - self.means[k]) / self.stds[k]
                        for k in self.features]

    def score(self, f: dict) -> float:
        z = sum(w * x for w, x in zip(self.coef, self.vector(f)))
        return 1 / (1 + math.exp(-max(-30, min(30, z))))

    def contributions(self, f: dict) -> dict[str, float]:
        x = self.vector(f)
        return {k: round(self.coef[i + 1] * x[i + 1], 3) for i, k in enumerate(self.features)}

    def to_dict(self) -> dict:
        return {"features": self.features, "means": self.means, "stds": self.stds, "coef": self.coef}


def fit_logit(rows: list[dict], features: list[str], *, l2: float = 1.0, iters: int = 8) -> Logit:
    means, stds = {}, {}
    for k in features:
        vals = [r["f"][k] for r in rows if r["f"].get(k) is not None]
        means[k] = statistics.fmean(vals) if vals else 0.0
        sd = statistics.pstdev(vals) if len(vals) > 1 else 1.0
        stds[k] = sd if sd > 0 else 1.0
    model = Logit(features, means, stds, [0.0] * (len(features) + 1))
    xs = [model.vector(r["f"]) for r in rows]
    ys = [r["y"] for r in rows]
    d = len(features) + 1
    for _ in range(iters):
        h = [[0.0] * d for _ in range(d)]
        g = [0.0] * d
        for x, y in zip(xs, ys):
            z = sum(w * v for w, v in zip(model.coef, x))
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            wgt = p * (1 - p)
            for a in range(d):
                g[a] += (y - p) * x[a]
                xa = wgt * x[a]
                ha = h[a]
                for b in range(a, d):
                    ha[b] += xa * x[b]
        for a in range(d):
            for b in range(a):
                h[a][b] = h[b][a]
            if a:
                h[a][a] += l2
                g[a] -= l2 * model.coef[a]
        step = _solve(h, g)
        model.coef = [w + s for w, s in zip(model.coef, step)]
        if max(abs(s) for s in step) < 1e-6:
            break
    return model


def auc(scores: list[float], labels: list[int]) -> float | None:
    pos = sum(labels)
    neg = len(labels) - pos
    if not pos or not neg:
        return None
    order = sorted(range(len(scores)), key=lambda k: scores[k])
    rank_sum, i = 0.0, 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        rank_sum += sum(avg for k in range(i, j + 1) if labels[order[k]])
        i = j + 1
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def population_test(data: Data, model: Logit, kind: str, heat: Heat, *, start_day: int, sample: int = 2500,
                    step: int = 5, seed: int = 11) -> dict:
    """Předvídatelnost v reálném světě: všechny (vzorek) akcie každý týden v testovacím období.

    Cíl: začne z daného dne raketa daného typu (max. cena v okně ≥ práh)? Výsledek: přesnost horního 1 % / 5 % / 10 %
    skóre vs. základní četnost. KONTROLA SMĚRU: stejné skupiny se měří i na propad o symetrickou velikost
    (+30 % ~ −23 %) a na průměrný výnos na konci okna — model, který jen pozná volatilní akcie, by měl rakety
    i propady stejně časté a průměrný výnos kolem nuly.
    """
    window, threshold, _ = EVENT_TYPES[kind]
    drop = 1 / (1 + threshold) - 1
    rng = random.Random(seed)
    syms = list(data.secs)
    rng.shuffle(syms)
    scored = []
    for sym in syms[:sample]:
        s = data.secs[sym]
        days, c = s.prep.bars.days, s.prep.bars.closes
        i = max(bisect.bisect_left(days, start_day), 120)
        while i + window < len(c):
            f = sample_features(data, s, i, heat)
            if f is not None:
                seg = c[i + 1:i + window + 1]
                scored.append((model.score(f), max(seg) / c[i] - 1 >= threshold, min(seg) / c[i] - 1 <= drop,
                               seg[-1] / c[i] - 1))
            i += step
    if not scored:
        return {"vzorku": 0}
    scored.sort(key=lambda t: t[0], reverse=True)

    def stats(rows):
        return {"rakety": round(sum(r[1] for r in rows) / len(rows), 5),
                "propady": round(sum(r[2] for r in rows) / len(rows), 5),
                "prumer": round(statistics.fmean(r[3] for r in rows), 5),
                "median": round(statistics.median(r[3] for r in rows), 5)}

    base = stats(scored)
    out = {"vzorku": len(scored), "zakladni_cetnost": base["rakety"], "zaklad": base,
           "prah_propadu": round(drop, 3),
           "auc": round(auc([r[0] for r in scored], [int(r[1]) for r in scored]) or 0, 4)}
    hits_total = max(sum(r[1] for r in scored), 1)
    for pct in (0.01, 0.05, 0.10):
        top = scored[:max(1, int(len(scored) * pct))]
        st = stats(top)
        key = f"top{int(pct * 100)}"
        out[key] = st
        out[f"presnost_{key}"] = st["rakety"]
        out[f"lift_{key}"] = round(st["rakety"] / base["rakety"], 2) if base["rakety"] else None
        out[f"zachyceno_{key}"] = round(sum(r[1] for r in top) / hits_total, 4)
    t1 = out["top1"]
    out["smer"] = ("model pozná hlavně VOLATILITU — rakety i propady jsou v horní skupině podobně časté"
                   if t1["propady"] >= 0.7 * t1["rakety"] else
                   "model má i SMĚROVOU výhodu — rakety jsou v horní skupině výrazně častější než propady")
    return out


# ------------------------------------------------------------------ sektorové vlny a skupiny společného pohybu

def sector_waves(data: Data, trailing: dict[str, dict], *, key: str = "6M", threshold: float = 0.5,
                 min_winners: int = 4) -> list[dict]:
    """Obory s neobvykle vysokým podílem vítězů (§13–§14: více měřitelných důkazů, ne jen zájem médií)."""
    total = [s for s in data.secs if trailing.get(s, {}).get(key) is not None]
    winners = {s for s in total if trailing[s][key] >= threshold}
    base = len(winners) / max(len(total), 1)
    recent_ipo_cut = data.data_end - 365
    out = []
    for g, members in data.groups.items():
        known = [s for s in members if s in trailing and trailing[s].get(key) is not None]
        w = [s for s in known if s in winners]
        if len(w) < min_winners or len(known) < 8:
            continue
        share = len(w) / len(known)
        z = (share - base) / math.sqrt(max(base * (1 - base) / len(known), 1e-9))
        ipos = sum(1 for s in members if data.secs[s].prep.bars.days[0] > max(recent_ipo_cut, data.data_start + 30))
        countries = sorted({data.secs[s].meta.get("country") or "?" for s in w})
        out.append({"obor": data.secs[members[0]].meta.get("industry") or data.secs[members[0]].meta.get("sector") or g,
                    "vitezu": len(w), "firem": len(known), "podil": round(share, 3), "lift": round(share / base, 2) if base else None,
                    "z": round(z, 2), "median_vynos": round(statistics.median(trailing[s][key] for s in w), 3),
                    "nove_na_burze_12m": ipos, "zeme": countries[:8],
                    "priklady": sorted(w, key=lambda s: trailing[s][key], reverse=True)[:6]})
    out.sort(key=lambda r: r["z"], reverse=True)
    return out


def comovement_clusters(data: Data, symbols: list[str], *, days: int = 126, min_corr: float = 0.5,
                        min_size: int = 3) -> list[list[str]]:
    """Skupiny vítězů, kteří se pohybují spolu (téma, které ještě nemusí mít název sektoru, §13)."""
    end = data.data_end
    calendar = list(range(end - int(days * 1.45), end + 1))
    series = {}
    for sym in symbols:
        b = data.secs[sym].prep.bars
        k0 = bisect.bisect_left(b.days, calendar[0])
        closes = {b.days[k]: b.closes[k] for k in range(max(k0 - 1, 0), len(b.days))}
        rets, last = {}, None
        for d in calendar:
            if d in closes:
                if last:
                    rets[d] = math.log(closes[d] / last) if last > 0 and closes[d] > 0 else 0.0
                last = closes[d]
        series[sym] = rets
    syms = [s for s in symbols if len(series[s]) > days * 0.6]

    def corr(a, b):
        common = [d for d in series[a] if d in series[b]]
        if len(common) < days * 0.5:
            return 0.0
        return pearson([series[a][d] for d in common], [series[b][d] for d in common]) or 0.0

    unassigned, clusters = set(syms), []
    for seed in syms:
        if seed not in unassigned:
            continue
        members = [seed] + [s for s in syms if s != seed and s in unassigned and corr(seed, s) >= min_corr]
        if len(members) >= min_size:
            clusters.append(members)
            unassigned -= set(members)
    return clusters


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return None if sx == 0 or sy == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def day_str(ordinal: int) -> str:
    return date.fromordinal(ordinal).isoformat()
