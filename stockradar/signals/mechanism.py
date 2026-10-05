"""Bod 2 zadání: „událost → mechanismus → obor → dodavatelé → firmy“, ne jen pozitivní/negativní zpráva.

Graf je předem daný z ekonomické logiky (ne vybraný podle výsledků). Vrstva k je „proti proudu“ vrstvy k+1:
když vrstva k roste (poptávka, ceny), mechanismus předpokládá, že to se zpožděním pocítí vrstva k+1.
Test (poctivý): pro každou vazbu A → B se změří, zda pohyb oboru A za poslední měsíc předpovídá výnos oboru B
v dalších 10 obchodních dnech (nad trhem). Stejný test se udělá pro 300 NÁHODNÝCH dvojic oborů — vazba z grafu
má smysl jen tehdy, když je lepší než náhodné dvojice. Kroky po 14 dnech, aby se výsledná okna nepřekrývala
(počet nezávislých pozorování = počet dvoutýdnů).
"""

import math
import random
import statistics

from stockradar.signals import panel as P

MECHANISMS = [
    {"id": "AI_ENERGIE", "nazev": "Výdaje na AI → čipy a servery → elektrotechnika a stavba → elektřina → suroviny",
     "zdroj": "řetězec AI → elektřina → jádro (docs/MASTER_PROMPT.md, výzkum projektu 2026-10-02)",
     "vrstvy": [["semiconductors", "computer manufacturing", "computer peripheral equipment",
                 "computer communications equipment"],
                ["electrical products", "electronic components", "industrial machinery/components",
                 "engineering & construction", "water sewer pipeline comm & power line construction"],
                ["electric utilities: central", "power generation", "natural gas distribution", "oil/gas transmission"],
                ["other metals and minerals", "metal mining"]]},
    {"id": "ROPA", "nazev": "Těžba ropy a plynu → služby a stroje pro těžbu → námořní doprava",
     "zdroj": "ekonomická logika: investice těžařů jsou tržby dodavatelů",
     "vrstvy": [["oil & gas production", "integrated oil companies"],
                ["oilfield services/equipment", "oil and gas field machinery"], ["marine transportation"]]},
    {"id": "STAVBA", "nazev": "Stavebnictví → stavební materiály a stroje → těžba nerostů",
     "zdroj": "ekonomická logika: dodavatelský řetězec výstavby",
     "vrstvy": [["homebuilding", "engineering & construction"],
                ["building products", "building materials", "retail: building materials", "construction/ag equipment/trucks"],
                ["mining & quarrying of nonmetallic minerals (no fuels)", "steel/iron ore"]]},
]
STEP = 14
N_RANDOM = 300


def edges() -> list[tuple[str, str, str]]:
    out = []
    for m in MECHANISMS:
        for a_layer, b_layer in zip(m["vrstvy"], m["vrstvy"][1:]):
            out += [(m["id"], a, b) for a in a_layer for b in b_layer]
    return out


def upstream_of() -> dict[str, list[str]]:
    up: dict[str, list[str]] = {}
    for _, a, b in edges():
        up.setdefault(b, []).append(a)
    return up


UPSTREAM = upstream_of()
MECH_FEATURES = {"mech_up_r20": "Mechanismus: obory proti proudu (dodavatelský řetězec) za měsíc"}


def mech_feature(group: str, med: dict) -> float | None:
    ups = [med[g]["r20"] for g in UPSTREAM.get(group, []) if g in med and med[g].get("r20") is not None]
    return statistics.fmean(ups) if ups else None


def series(data, days: list[int]) -> dict[int, dict]:
    """Pro každý den: medián oboru za měsíc (signál) a medián výnosu oboru za 10 dní nad trhem (výsledek)."""
    out = {}
    for day in days:
        snap = P.snapshot(data, day)
        fwd_all = []
        per = {}
        for sym, j in snap["idx"].items():
            c = data.secs[sym].prep.bars.closes
            if j + P.H < len(c) and c[j] > 0:
                f = c[j + P.H] / c[j] - 1
                fwd_all.append(f)
                per.setdefault(data.secs[sym].group, []).append(f)
        mkt = statistics.median(fwd_all) if fwd_all else None
        out[day] = {"sig": {g: m.get("r20") for g, m in snap["med"].items()},
                    "out": {g: statistics.median(v) - mkt for g, v in per.items() if len(v) >= 5 and mkt is not None}}
    return out


def _t(xs: list[float], ys: list[float]) -> tuple[float | None, int]:
    n = len(xs)
    if n < 15:
        return None, n
    r = statistics.correlation(xs, ys) if statistics.pstdev(xs) > 0 and statistics.pstdev(ys) > 0 else 0.0
    if abs(r) >= 1:
        return None, n
    return r * math.sqrt((n - 2) / (1 - r * r)), n


def pair_t(ser: dict, days: list[int], a: str, b: str) -> tuple[float | None, int]:
    xs, ys = [], []
    for d in days:
        s, o = ser[d]["sig"].get(a), ser[d]["out"].get(b)
        if s is not None and o is not None:
            xs.append(s)
            ys.append(o)
    return _t(xs, ys)


def lead_lag_test(data, *, periods: dict[str, tuple[int, int]], log=print) -> dict:
    days = [d for d in P.panel_days(data, STEP)]
    ser = series(data, days)
    groups = sorted({g for d in days for g in ser[d]["out"]})
    rng = random.Random(11)
    rand_pairs = [tuple(rng.sample(groups, 2)) for _ in range(N_RANDOM)] if len(groups) >= 2 else []
    res = {"kroku": len(days), "obdobi": {}}
    for name, (lo, hi) in periods.items():
        dd = [d for d in days if lo <= d <= hi]
        ed = []
        for mid, a, b in edges():
            t, n = pair_t(ser, dd, a, b)
            if t is not None:
                ed.append({"mechanismus": mid, "z": a, "do": b, "t": round(t, 2), "n": n})
        rt = [t for t in (pair_t(ser, dd, a, b)[0] for a, b in rand_pairs) if t is not None]
        mech = {}
        for m in MECHANISMS:
            ts = [e["t"] for e in ed if e["mechanismus"] == m["id"]]
            if ts:
                mean_t = statistics.fmean(ts)
                pct = sum(1 for x in rt if x < mean_t) / len(rt) if rt else None
                mech[m["id"]] = {"vazeb": len(ts), "prumer_t": round(mean_t, 2), "kladnych": sum(1 for x in ts if x > 0),
                                 "percentil_vs_nahodne": round(pct, 3) if pct is not None else None}
        res["obdobi"][name] = {"dvoutydnu": len(dd), "mechanismy": mech,
                               "nahodne_prumer_t": round(statistics.fmean(rt), 2) if rt else None,
                               "nahodne_sd_t": round(statistics.pstdev(rt), 2) if rt else None,
                               "nejsilnejsi_vazby": sorted(ed, key=lambda e: -abs(e["t"]))[:8]}
        log(f"Mechanismy {name}: {mech}")
    return res
