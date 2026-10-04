"""NAJDI RAKETU NA 6 MĚSÍCŮ — vlastní predikce: která akcie udělá ≥ +50 % během příštích ~6 měsíců.

Jak to funguje (poctivě, bez look-ahead):
  1. Panel: každých 14 dní (pátek) všechny likvidní akcie; znaky jen z dat známých k tomu dni:
     cena/objem (17 znaků), sektorová vlna (medián oboru za 6 měsíců), fundamenty SEC (tržby, ředění, velikost,
     hotovost, P/S), filingy SEC (8-K, emise, aktivisté 13D) a klinické studie (fáze 2/3 s dokončením do 180 dní).
  2. Cíl: během 126 obchodních dní cena aspoň 2 dny po sobě ≥ +50 % (raketa); zrcadlově ≤ −33 % (propad).
  3. Model: každý znak → decily → „váha důkazu“ (WoE), pak logistická regrese (souřadnicový sestup, čistý Python).
  4. Test: trénink na dnech do TRAIN_END, test na dnech od TEST_START (mezera 6 měsíců → cíle se nepřekrývají).
     Měří se: kolik raket a propadů přišlo v horním 1 % / 5 % skóre proti všem akciím, medián výnosu, kalibrace.
  5. Dnešní predikce: finální model naučený na všech dnech s už známým výsledkem; do ledgeru TOP N.
"""

import bisect
import hashlib
import math
import statistics
from array import array
from collections import Counter
from datetime import date, timedelta

from stockradar.discovery import study
from stockradar.discovery.features import FEATURES, features_at
from stockradar.discovery.fundamentals import FUND_FEATURES, Fundamentals
from stockradar.discovery.winners import phase, trailing_returns

TARGET = 0.50
DROP = 1 / 1.5 - 1           # −33 %
HORIZON = 126                # obchodních dní ≈ 6 měsíců
STEP_DAYS = 14
TRAIN_END = date(2024, 12, 31)
TEST_START = date(2025, 7, 1)
# Test stability (walk-forward): stejné pravidlo řazení, model naučený jen na starších datech, test v pozdějším pololetí.
# Mezi koncem učení a začátkem testu je vždy 6 měsíců, aby se cíle (okno 126 obchodních dní) nepřekrývaly.
WALK_FORWARD = [
    (date(2023, 6, 30), date(2024, 1, 1), date(2024, 6, 30)),
    (date(2024, 6, 30), date(2025, 1, 1), date(2025, 6, 30)),
]
MIN_FOLD_TRAIN, MIN_FOLD_TEST = 2000, 500
SAMPLE_TRAIN = 0.35          # podíl (akcie, den) v tréninku — kvůli rychlosti v čistém Pythonu
SAMPLE_TEST = 0.6
BINS = 10
L2 = 2.0
SWEEPS = 6
MIN_TURNOVER_LIVE = 1_000_000
MIN_PRICE_LIVE = 1.0

SECTOR_FEATURES = {
    "sec_r126": "Sektorová vlna: medián oboru za 6 měsíců",
    "sec_r20": "Sektorová vlna: medián oboru za měsíc",
    "rel_r126": "Síla vůči oboru (6 měsíců)",
    "mkt_r126": "Celý trh: medián za 6 měsíců",
}
ALL_FEATURES = {**FEATURES, **SECTOR_FEATURES, **FUND_FEATURES}
PRICE_ONLY = [f for f in ALL_FEATURES if f not in FUND_FEATURES]
EXTERNAL = [f for f in FUND_FEATURES]  # SEC + ClinicalTrials (pro test „s nimi / bez nich“)


def _keep(symbol: str, day: int, share: float) -> bool:
    h = int.from_bytes(hashlib.blake2b(f"{symbol}|{day}".encode(), digest_size=4).digest(), "big")
    return h / 2 ** 32 < share


def _label(c, i: int) -> tuple[int, int, float] | None:
    """(raketa, propad, výnos na konci okna). Raketa = 2 po sobě jdoucí závěry ≥ +50 % (odolné vůči chybnému ticku)."""
    if i + HORIZON >= len(c):
        return None
    base = c[i]
    up_hit = down_hit = 0
    prev = c[i + 1]
    for k in range(i + 2, i + HORIZON + 1):
        cur = c[k]
        lo, hi = (prev, cur) if prev < cur else (cur, prev)
        if lo / base - 1 >= TARGET:
            up_hit = 1
        if hi / base - 1 <= DROP:
            down_hit = 1
        prev = cur
    return up_hit, down_hit, c[i + HORIZON] / base - 1


class Panel:
    """Sloupcové úložiště vzorků (pro stovky tisíc řádků bez velké paměti)."""

    def __init__(self, features: list[str]):
        self.features = features
        self.cols = {f: array("d") for f in features}
        self.y_up, self.y_down = array("b"), array("b")
        self.fwd = array("d")
        self.day = array("i")
        self.sym: list[str] = []

    def add(self, symbol: str, day: int, f: dict, label):
        nan = math.nan
        for k in self.features:
            v = f.get(k)
            self.cols[k].append(nan if v is None else float(v))
        self.y_up.append(label[0] if label else -1)
        self.y_down.append(label[1] if label else -1)
        self.fwd.append(label[2] if label else nan)
        self.day.append(day)
        self.sym.append(symbol)

    def __len__(self):
        return len(self.day)

    def rows(self, pred) -> list[int]:
        return [k for k in range(len(self)) if pred(k)]


def panel_days(data: study.Data) -> list[int]:
    end = data.data_end
    first = data.data_start + 200
    d = end - (end - first) % STEP_DAYS
    days = []
    while d >= first:
        days.append(d)
        d -= STEP_DAYS
    return days[::-1]


def build_panel(data: study.Data, heat: study.Heat, fund: Fundamentals, *, log=print,
                train_share: float = SAMPLE_TRAIN, test_share: float = SAMPLE_TEST) -> Panel:
    feats = list(ALL_FEATURES)
    panel = Panel(feats)
    days = panel_days(data)
    secs = list(data.secs.values())
    ptr = [0] * len(secs)
    train_end, test_start = TRAIN_END.toordinal(), TEST_START.toordinal()
    for n, day in enumerate(days):
        # pololetí mezi učením a testem se také vzorkuje — slouží testu stability a finálnímu modelu
        share = test_share if day >= test_start else train_share
        if share <= 0:
            continue
        # 1) pro každou akcii poslední obchodní den ≤ day
        idx = {}
        for k, s in enumerate(secs):
            dd = s.prep.bars.days
            j = ptr[k]
            while j + 1 < len(dd) and dd[j + 1] <= day:
                j += 1
            ptr[k] = j
            if dd[j] <= day and day - dd[j] <= 4 and j >= 126:
                idx[s.symbol] = j
        # 2) sektorová vlna k danému dni (z likvidních akcií)
        r126, r20, groups = {}, {}, {}
        for sym, j in idx.items():
            c = data.secs[sym].prep.bars.closes
            if c[j - 126] > 0 and c[j - 20] > 0:
                r126[sym], r20[sym] = c[j] / c[j - 126] - 1, c[j] / c[j - 20] - 1
                groups.setdefault(data.secs[sym].group, []).append(sym)
        mkt = statistics.median(r126.values()) if r126 else None
        gstat = {g: (statistics.median(r126[s] for s in m), statistics.median(r20[s] for s in m))
                 for g, m in groups.items() if len(m) >= 5}
        # 3) vzorky
        for sym, j in idx.items():
            if not _keep(sym, day, share) or sym not in r126:
                continue
            s = data.secs[sym]
            f = study.sample_features(data, s, j, heat)
            if f is None:
                continue
            rate = data.usd_rate(s.currency, s.prep.bars.days[j])
            g = gstat.get(s.group)
            f["sec_r126"], f["sec_r20"] = (g[0], g[1]) if g else (None, None)
            f["rel_r126"] = r126[sym] - g[0] if g else None
            f["mkt_r126"] = mkt
            f.update(fund.features(sym, day, s.prep.bars.closes[j] * rate if rate else None))
            panel.add(sym, day, f, _label(s.prep.bars.closes, j))
        if n % 20 == 0:
            log(f"panel {study.day_str(day)}: {len(panel)} vzorků")
    return panel


# ------------------------------------------------------------------ WoE + logistická regrese

class WoE:
    def __init__(self, edges: dict[str, list[float]], woe: dict[str, list[float]]):
        self.edges, self.woe = edges, woe  # woe[f][0] = chybějící hodnota, [1..] = biny

    def bin(self, f: str, v: float) -> int:
        if v is None or v != v:
            return 0
        return 1 + bisect.bisect_right(self.edges[f], v)

    def value(self, f: str, v) -> float:
        return self.woe[f][self.bin(f, v)]

    def to_dict(self):
        return {"edges": self.edges, "woe": self.woe}


def fit_woe(panel: Panel, rows: list[int], y: array, features: list[str]) -> WoE:
    edges, woe = {}, {}
    pos = sum(y[k] for k in rows)
    neg = len(rows) - pos
    for f in features:
        col = panel.cols[f]
        vals = sorted(col[k] for k in rows if col[k] == col[k])
        e = sorted(set(vals[int(len(vals) * q / BINS)] for q in range(1, BINS))) if len(vals) >= 200 else []
        edges[f] = e
        nb = len(e) + 2
        cnt_p, cnt_n = [0] * nb, [0] * nb
        w = WoE({f: e}, {})
        for k in rows:
            b = w.bin(f, col[k])
            if y[k]:
                cnt_p[b] += 1
            else:
                cnt_n[b] += 1
        woe[f] = [round(math.log(((cnt_p[b] + 0.5) / (pos + 0.5 * nb)) / ((cnt_n[b] + 0.5) / (neg + 0.5 * nb))), 5)
                  for b in range(nb)]
    return WoE(edges, woe)


def _sig(z: float) -> float:
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


def fit_logistic(xs: list[list[float]], y: list[int], *, l2: float = L2, sweeps: int = SWEEPS) -> tuple[float, list[float]]:
    """Souřadnicový Newtonův sestup pro logistickou regresi s L2 (sloupcová data, O(n·d) na průchod)."""
    n, d = len(y), len(xs)
    rate = (sum(y) + 0.5) / (n + 1)
    b0, w = math.log(rate / (1 - rate)), [0.0] * d
    z = [b0] * n
    for _ in range(sweeps):
        for j in range(-1, d):
            p = [_sig(v) for v in z]
            if j < 0:
                g = sum(y) - sum(p)
                h = sum(q * (1 - q) for q in p) or 1e-9
                step = g / h
                b0 += step
                z = [v + step for v in z]
                continue
            x = xs[j]
            g = sum((yy - q) * xx for yy, q, xx in zip(y, p, x)) - l2 * w[j]
            h = sum(q * (1 - q) * xx * xx for q, xx in zip(p, x)) + l2
            step = g / h
            w[j] += step
            z = [v + step * xx for v, xx in zip(z, x)]
    return b0, w


class Model:
    def __init__(self, features: list[str], woe: WoE, b0: float, w: list[float], base_rate: float):
        self.features, self.woe, self.b0, self.w, self.base_rate = features, woe, b0, w, base_rate

    def margin(self, f: dict) -> float:
        return self.b0 + sum(wj * self.woe.value(k, f.get(k)) for k, wj in zip(self.features, self.w))

    def prob(self, f: dict) -> float:
        return _sig(self.margin(f))

    def contributions(self, f: dict) -> dict[str, float]:
        return {k: wj * self.woe.value(k, f.get(k)) for k, wj in zip(self.features, self.w)}

    def to_dict(self):
        return {"features": self.features, "b0": self.b0, "w": self.w, "base_rate": self.base_rate, **self.woe.to_dict()}


def target_array(panel: Panel, target: str) -> array:
    if target == "up":
        return panel.y_up
    if target == "down":
        return panel.y_down
    # „hold“: raketa, která vydržela — na konci 6 měsíců cena aspoň +50 %
    return array("b", [1 if v == v and v >= TARGET else 0 for v in panel.fwd])


def train(panel: Panel, rows: list[int], target: str, features: list[str]) -> Model:
    y = target_array(panel, target)
    woe = fit_woe(panel, rows, y, features)
    xs = [[woe.value(f, panel.cols[f][k]) for k in rows] for f in features]
    yy = [y[k] for k in rows]
    b0, w = fit_logistic(xs, yy)
    return Model(features, woe, b0, w, sum(yy) / max(len(yy), 1))


def _row(panel: Panel, k: int, features: list[str]) -> dict:
    return {f: panel.cols[f][k] for f in features}


# ------------------------------------------------------------------ test mimo vzorek

def _stats(panel: Panel, ks: list[int]) -> dict:
    if not ks:
        return {"n": 0}
    fwd = sorted(min(panel.fwd[k], 5.0) for k in ks)
    q = lambda p: round(fwd[min(len(fwd) - 1, int(p * len(fwd)))], 4)
    return {"n": len(ks), "rakety": round(sum(panel.y_up[k] for k in ks) / len(ks), 4),
            "propady": round(sum(panel.y_down[k] for k in ks) / len(ks), 4),
            "median": q(0.5), "prumer": round(statistics.fmean(fwd), 4), "q20": q(0.2), "q80": q(0.8)}


def evaluate(panel: Panel, test: list[int], up: Model, down: Model, hold: Model | None = None) -> dict:
    pu = {k: up.prob(_row(panel, k, up.features)) for k in test}
    pdn = {k: down.prob(_row(panel, k, down.features)) for k in test}
    ph = {k: hold.prob(_row(panel, k, hold.features)) for k in test} if hold else None
    base = _stats(panel, test)
    out = {"vzorku": len(test), "dnu": len({panel.day[k] for k in test}), "zaklad": base,
           "auc_raketa": round(study.auc([pu[k] for k in test], [panel.y_up[k] for k in test]) or 0, 4),
           "auc_propad": round(study.auc([pdn[k] for k in test], [panel.y_down[k] for k in test]) or 0, 4)}
    rankings = {"raketa": lambda k: pu[k], "asymetrie": lambda k: pu[k] - pdn[k],
                "pomer": lambda k: math.log(pu[k] / max(pdn[k], 1e-6))}
    if ph is not None:
        rankings["vydrzi"] = lambda k: ph[k]
        rankings["vydrzi_asym"] = lambda k: ph[k] - pdn[k]
    for name, key in rankings.items():
        order = sorted(test, key=key, reverse=True)
        res = {}
        for pct in (0.01, 0.05, 0.10):
            res[f"top{int(pct * 100)}"] = _stats(panel, order[:max(1, int(len(order) * pct))])
        out[name] = res
    # kalibrace: decily predikované šance na raketu vs skutečnost
    order = sorted(test, key=lambda k: pu[k])
    cal = []
    for b in range(10):
        part = order[b * len(order) // 10:(b + 1) * len(order) // 10]
        if part:
            cal.append({"decil": b + 1, "predikce": round(statistics.fmean(pu[k] for k in part), 4),
                        "skutecnost": round(sum(panel.y_up[k] for k in part) / len(part), 4)})
    out["kalibrace"] = cal
    return out


RANKINGS = ("raketa", "asymetrie", "pomer", "vydrzi", "vydrzi_asym")


def rank_key(name: str, pu: float, pdn: float, ph: float | None) -> float:
    if name == "raketa":
        return pu
    if name == "asymetrie":
        return pu - pdn
    if name == "pomer":
        return math.log(pu / max(pdn, 1e-6))
    if name == "vydrzi":
        return ph
    return ph - pdn


def choose_ranking(ev: dict) -> str:
    """Předem daná pravidla: řazení s největším rozdílem (rakety − propady) v horním 1 %, při shodě vyšší medián."""
    def key(name):
        t = ev[name]["top1"]
        return (round(t["rakety"] - t["propady"], 3), t["median"])
    return max((r for r in RANKINGS if r in ev), key=key)


def walk_forward(panel: Panel, labeled: list[int], features: list[str], ranking: str, *, log=print) -> list[dict]:
    """Drží výhoda i v jiných obdobích? Pro každé pololetí z WALK_FORWARD: učení jen na starších datech, test
    předem zvoleného řazení (žádný výběr podle výsledku), horní 1 % a 5 % proti všem akciím."""
    out = []
    for train_end, test_start, test_end in WALK_FORWARD:
        a, b, c = train_end.toordinal(), test_start.toordinal(), test_end.toordinal()
        tr = [k for k in labeled if panel.day[k] <= a]
        te = [k for k in labeled if b <= panel.day[k] <= c]
        if len(tr) < MIN_FOLD_TRAIN or len(te) < MIN_FOLD_TEST:
            continue
        up, down = train(panel, tr, "up", features), train(panel, tr, "down", features)
        hold = train(panel, tr, "hold", features) if ranking.startswith("vydrzi") else None
        ev = evaluate(panel, te, up, down, hold)
        row = {"uceni_do": train_end.isoformat(), "test": f"{test_start.isoformat()}..{test_end.isoformat()}",
               "vzorku": len(te), "zaklad": ev["zaklad"], "top1": ev[ranking]["top1"], "top5": ev[ranking]["top5"],
               "auc_raketa": ev["auc_raketa"]}
        row["vyhoda"] = bool(row["top1"]["rakety"] > row["zaklad"]["rakety"]
                             and row["top1"]["rakety"] > row["top1"]["propady"])
        out.append(row)
        log(f"Stabilita {row['test']}: raketa {row['top1']['rakety']} vs {row['zaklad']['rakety']}, "
            f"propad {row['top1']['propady']}")
    return out


def directional_edge(ev: dict, ranking: str) -> bool:
    t, b = ev[ranking]["top1"], ev["zaklad"]
    return t["rakety"] > t["propady"] and t["rakety"] >= 1.5 * b["rakety"] and t["median"] >= b["median"]


# ------------------------------------------------------------------ celý běh

def run(cache_conn, data: study.Data, heat: study.Heat, events: dict, *, top_n: int = 10, log=print) -> dict:
    fund = Fundamentals(cache_conn, data.secs.keys())
    log(f"Fundamenty SEC: {len(fund.cik)} firem s CIK, klinické studie u {len(fund.trials)} firem")
    panel = build_panel(data, heat, fund, log=log)
    labeled = [k for k in range(len(panel)) if panel.y_up[k] >= 0]
    train_end, test_start = TRAIN_END.toordinal(), TEST_START.toordinal()
    tr = [k for k in labeled if panel.day[k] <= train_end]
    te = [k for k in labeled if panel.day[k] >= test_start]
    log(f"Panel: {len(panel)} vzorků, trénink {len(tr)}, test {len(te)}")
    feats = list(ALL_FEATURES)
    up, down, hold = train(panel, tr, "up", feats), train(panel, tr, "down", feats), train(panel, tr, "hold", feats)
    ev = evaluate(panel, te, up, down, hold)
    up_p, down_p = train(panel, tr, "up", PRICE_ONLY), train(panel, tr, "down", PRICE_ONLY)
    ev_price = evaluate(panel, te, up_p, down_p)
    ranking = choose_ranking(ev)
    edge = directional_edge(ev, ranking)
    stability = walk_forward(panel, labeled, feats, ranking, log=log)
    log(f"Test: AUC {ev['auc_raketa']} (jen cena {ev_price['auc_raketa']}), řazení {ranking}, směrová výhoda {edge}")

    # finální model: všechny dny se známým výsledkem (víc dat, novější režim trhu)
    final_up, final_down = train(panel, labeled, "up", feats), train(panel, labeled, "down", feats)
    final_hold = train(panel, labeled, "hold", feats) if ranking.startswith("vydrzi") else None
    candidates = score_today(data, heat, fund, final_up, final_down, ev, ranking, events, cache_conn, top_n=top_n,
                             hold=final_hold)
    return {
        "popis": "Raketa do 6 měsíců: cena během 126 obchodních dní aspoň 2 dny po sobě ≥ +50 %",
        "cil": TARGET, "propad": round(DROP, 3), "horizont_dni": HORIZON,
        "trenink": f"{study.day_str(min(panel.day[k] for k in tr))}..{TRAIN_END.isoformat()}" if tr else None,
        "test_obdobi": f"{TEST_START.isoformat()}..{study.day_str(max(panel.day[k] for k in te))}" if te else None,
        "vzorku": {"panel": len(panel), "trenink": len(tr), "test": len(te)},
        "test": ev, "test_jen_cena": ev_price, "razeni": ranking, "smerova_vyhoda": edge, "stabilita": stability,
        "vahy": sorted(({"znak": f, "nazev": ALL_FEATURES[f], "koef": round(w, 3)} for f, w in zip(final_up.features, final_up.w)),
                       key=lambda r: abs(r["koef"]), reverse=True),
        "kandidati": candidates,
        "_model": {"raketa": final_up.to_dict(), "propad": final_down.to_dict(),
                   **({"vydrzi": final_hold.to_dict()} if final_hold else {})},
    }


# srozumitelné názvy pro vysvětlení (hodnoty se zobrazují v USD / %, ne v logaritmu)
WHY = {**ALL_FEATURES, "price": "Cena za akcii", "turnover": "Denní obrat", "log_mcap": "Tržní kapitalizace",
       "log_ps": "Cena / tržby"}


def _fmt(f: str, v) -> str:
    if v is None or v != v:
        return "–"
    if f in ("r5", "r20", "r60", "r120", "r250", "dd252", "up252", "max_day20", "sec_r126", "sec_r20", "rel_r126",
             "mkt_r126", "rev_yoy", "dilution"):
        return f"{v * 100:+.0f} %"
    if f == "rev_accel":
        return f"{v * 100:+.0f} p. b."
    if f in ("log_mcap", "turnover"):
        return f"{math.exp(v) / 1e6:,.0f} mil. USD".replace(",", " ")
    if f == "log_ps":
        return f"{math.exp(v):.1f}×"
    if f == "price":
        return f"{math.exp(v):.2f} USD"
    if f == "cash_mcap":
        return f"{v * 100:.0f} %"
    if f in ("has_fund", "profitable", "new_listing"):
        return "ano" if v else "ne"
    if f in ("n8k_30", "offer_90", "d13_180", "p3_180", "p2_180"):
        return f"{v:.0f}"
    if f in ("volu_5_60", "volu_20_120", "vol_ratio"):
        return f"{v:.1f}×"
    if f == "vol20":
        return f"{v * 100:.1f} % denně"
    if f in ("sector_heat", "market_heat"):
        return f"{v * 100:.1f} %"
    return f"{v:.2f}"


def score_today(data, heat, fund, up: Model, down: Model, ev: dict, ranking: str, events: dict, cache_conn, *,
                top_n: int, hold: Model | None = None) -> list[dict]:
    end = data.data_end
    recent = {e.symbol for kind in ("W1_30", "M1_50") for e in events.get(kind, [])
              if end - data.secs[e.symbol].prep.bars.days[e.end] <= 14}
    # sektorová vlna dnes
    r126, r20, groups, last = {}, {}, {}, {}
    for s in data.secs.values():
        j = len(s.prep.bars.days) - 1
        if end - s.prep.bars.days[j] > 7 or j < 126:
            continue
        c = s.prep.bars.closes
        if c[j - 126] > 0 and c[j - 20] > 0:
            last[s.symbol] = j
            r126[s.symbol], r20[s.symbol] = c[j] / c[j - 126] - 1, c[j] / c[j - 20] - 1
            groups.setdefault(s.group, []).append(s.symbol)
    mkt = statistics.median(r126.values()) if r126 else None
    gstat = {g: (statistics.median(r126[x] for x in m), statistics.median(r20[x] for x in m))
             for g, m in groups.items() if len(m) >= 5}
    scored = []
    for sym, j in last.items():
        s = data.secs[sym]
        f = study.sample_features(data, s, j, heat)
        if f is None:
            continue
        rate = data.usd_rate(s.currency, s.prep.bars.days[j])
        g = gstat.get(s.group)
        f["sec_r126"], f["sec_r20"] = (g[0], g[1]) if g else (None, None)
        f["rel_r126"] = r126[sym] - g[0] if g else None
        f["mkt_r126"] = mkt
        f.update(fund.features(sym, end, s.prep.bars.closes[j] * rate if rate else None))
        pu, pdn = up.prob(f), down.prob(f)
        ph = hold.prob(f) if hold else None
        scored.append((rank_key(ranking, pu, pdn, ph), sym, j, f, pu, pdn, rate))
    scored.sort(reverse=True)
    n = len(scored)
    out, per_group = [], Counter()
    for pos, (key, sym, j, f, pu, pdn, rate) in enumerate(scored):
        s = data.secs[sym]
        trailing = trailing_returns(s.prep.bars)
        ph = phase(trailing, sym in recent)
        turnover = math.exp(f["turnover"]) if f.get("turnover") is not None else 0
        price_usd = s.prep.bars.closes[j] * rate if rate else 0
        if ph not in ("EARLY", "DEVELOPING") or turnover < MIN_TURNOVER_LIVE or price_usd < MIN_PRICE_LIVE:
            continue
        if per_group[s.group] >= 3:
            continue  # rozložení rizika: max. 3 firmy z jednoho oboru
        per_group[s.group] += 1
        pct = (pos + 1) / n
        bucket = "top1" if pct <= 0.01 else "top5" if pct <= 0.05 else "top10"
        hist = ev[ranking].get(bucket, {})
        main = hold if hold is not None else up
        contrib = sorted(((k, v) for k, v in main.contributions(f).items() if f.get(k) is not None and f.get(k) == f.get(k)),
                         key=lambda kv: kv[1], reverse=True)
        trials = fund.upcoming_trials(cache_conn, sym, end) if f.get("p3_180") or f.get("p2_180") else []
        out.append({
            "ticker": sym, "nazev": s.meta.get("name"), "zeme": s.meta.get("country"),
            "obor": s.meta.get("industry") or s.meta.get("sector"), "faze": ph,
            "cena": round(s.prep.bars.closes[j], 4), "mena": s.currency, "den": s.prep.bars.date(j),
            "p_raketa": round(pu, 4), "p_propad": round(pdn, 4), "percentil": round(pct, 4), "skupina": bucket,
            "hist_rakety": hist.get("rakety"), "hist_propady": hist.get("propady"), "hist_median": hist.get("median"),
            "hist_q20": hist.get("q20"), "hist_q80": hist.get("q80"), "zakladni_cetnost": ev["zaklad"]["rakety"],
            "proc": [f"{WHY[k]}: {_fmt(k, f.get(k))}" for k, v in contrib[:4] if v > 0.02],
            "proti": [f"{WHY[k]}: {_fmt(k, f.get(k))}" for k, v in contrib[::-1][:2] if v < -0.02],
            "rust_3m": round(trailing["3M"], 3) if trailing.get("3M") is not None else None,
            "rust_6m": round(trailing["6M"], 3) if trailing.get("6M") is not None else None,
            "obrat_usd": round(turnover), "fundamenty": bool(f.get("has_fund")),
            "studie": [{"nct": t["nct"], "faze": t["phase"], "dokonceni": t["pcd"], "typ": t["pcd_type"],
                        "nazev": (t["title"] or "")[:140]} for t in trials[:4]],
        })
        if len(out) >= top_n:
            break
    return out
