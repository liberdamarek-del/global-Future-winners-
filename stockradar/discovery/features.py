"""Znaky (features) firmy k okamžiku T0 — počítají se JEN z dat dostupných do T0 včetně (§9, §41: bez look-ahead).

Každý znak je O(1) díky průběžným součtům, takže jde spočítat pro tisíce firem a desetitisíce okamžiků.
"""

import array
import math
from collections import deque
from dataclasses import dataclass

from stockradar.discovery.cache import Bars

FEATURES = {
    "r5": "Pohyb 5 dní před T0",
    "r20": "Pohyb 20 dní před T0",
    "r60": "Pohyb 60 dní před T0",
    "r120": "Pohyb 120 dní před T0",
    "r250": "Pohyb 250 dní před T0",
    "dd252": "Odstup od ročního maxima",
    "up252": "Výška nad ročním minimem",
    "vol20": "Volatilita 20 dní",
    "vol_ratio": "Stlačení volatility (20 d / 120 d)",
    "volu_5_60": "Objem 5 dní / 60 dní",
    "volu_20_120": "Objem 20 dní / 120 dní",
    "turnover": "Denní obrat v USD (log)",
    "price": "Cena v USD (log)",
    "max_day20": "Největší denní skok za 20 dní",
    "new_listing": "Nová firma na burze (< 1 rok v datech)",
    "sector_heat": "Rakety v oboru za posledních 20 dní (podíl)",
    "market_heat": "Rakety na celém trhu za posledních 20 dní (podíl)",
}


@dataclass
class Prepared:
    bars: Bars
    cum_c: array.array
    cum_v: array.array
    cum_cv: array.array
    cum_lr: array.array
    cum_lr2: array.array
    rmax: array.array
    rmin: array.array
    data_start_ordinal: int


def _prefix(values) -> array.array:
    out, s = array.array("d", [0.0]), 0.0
    for v in values:
        s += v
        out.append(s)
    return out


def _rolling(values, window: int, take_max: bool) -> array.array:
    out, dq = array.array("d"), deque()
    for i, v in enumerate(values):
        while dq and ((values[dq[-1]] <= v) if take_max else (values[dq[-1]] >= v)):
            dq.pop()
        dq.append(i)
        if dq[0] <= i - window:
            dq.popleft()
        out.append(values[dq[0]])
    return out


def prepare(bars: Bars, data_start_ordinal: int) -> Prepared:
    c, v = bars.closes, bars.volumes
    lr = [0.0] + [math.log(c[k] / c[k - 1]) if c[k - 1] > 0 and c[k] > 0 else 0.0 for k in range(1, len(c))]
    return Prepared(bars, _prefix(c), _prefix(v), _prefix(a * b for a, b in zip(c, v)), _prefix(lr),
                    _prefix(x * x for x in lr), _rolling(c, 252, True), _rolling(c, 252, False), data_start_ordinal)


def _mean(cum, i, n):
    return (cum[i + 1] - cum[i + 1 - n]) / n


def _std(p: Prepared, i: int, n: int) -> float:
    m = _mean(p.cum_lr, i, n)
    return math.sqrt(max(_mean(p.cum_lr2, i, n) - m * m, 0.0))


def features_at(p: Prepared, i: int, usd_rate: float | None) -> dict[str, float | None] | None:
    """Znaky k indexu i (poslední známý den). None, když chybí dost historie nebo kurz."""
    c = p.bars.closes
    if i < 120 or usd_rate is None or c[i] <= 0:
        return None

    def ret(n):
        return c[i] / c[i - n] - 1 if i >= n and c[i - n] > 0 else None

    vol120 = _std(p, i, 120)
    v60, v120 = _mean(p.cum_v, i, 60), _mean(p.cum_v, i, 120)
    turnover = _mean(p.cum_cv, i, 20) * usd_rate
    max_day = max(c[k] / c[k - 1] - 1 for k in range(i - 19, i + 1)) if all(c[k - 1] > 0 for k in range(i - 19, i + 1)) else None
    return {
        "r5": ret(5), "r20": ret(20), "r60": ret(60), "r120": ret(120), "r250": ret(250),
        "dd252": c[i] / p.rmax[i] - 1 if p.rmax[i] > 0 else None,
        "up252": c[i] / p.rmin[i] - 1 if p.rmin[i] > 0 else None,
        "vol20": _std(p, i, 20),
        "vol_ratio": _std(p, i, 20) / vol120 if vol120 > 0 else None,
        "volu_5_60": _mean(p.cum_v, i, 5) / v60 if v60 > 0 else None,
        "volu_20_120": _mean(p.cum_v, i, 20) / v120 if v120 > 0 else None,
        "turnover": math.log(turnover) if turnover > 0 else None,
        "price": math.log(c[i] * usd_rate),
        "max_day20": max_day,
        "new_listing": 1.0 if (p.bars.days[0] - p.data_start_ordinal > 30 and p.bars.days[i] - p.bars.days[0] < 365) else 0.0,
    }


def turnover_usd(p: Prepared, i: int, usd_rate: float | None, n: int = 20) -> float:
    if usd_rate is None or i < n:
        return 0.0
    return _mean(p.cum_cv, i, n) * usd_rate
