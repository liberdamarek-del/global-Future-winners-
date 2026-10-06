"""Citlivost oborů na komodity (beta) jen z minulých týdnů — bez pohledu do budoucnosti.

Týdenní mřížka (pátky). Výnos oboru = medián týdenních výnosů jeho likvidních amerických akcií MINUS medián celého
trhu (odstraní se pohyb trhu). Beta oboru g na komoditu c v týdnu w = regrese výnosů oboru na výnosy komodity
za posledních WINDOW týdnů (včetně w), t-statistika bety → „prokázaná“ vazba, když |t| ≥ T_MIN.
"""

import math
import statistics
from dataclasses import dataclass, field

from stockradar.causal import data as cdata
from stockradar.discovery import study
from stockradar.signals import panel as P

WINDOW, MIN_WEEKS, T_MIN, MIN_STOCKS = 78, 52, 2.0, 5


@dataclass
class Weekly:
    weeks: list[int]                                   # den (ordinal) konce týdne
    ind: dict[str, list[float]]                        # obor → týdenní výnos nad trhem (nan = chybí)
    comm: dict[str, list[float]]                       # komodita → týdenní výnos
    n_stocks: dict[str, int] = field(default_factory=dict)

    def index(self, day: int) -> int | None:
        """Poslední týden ≤ day."""
        lo, hi = 0, len(self.weeks) - 1
        if not self.weeks or day < self.weeks[0]:
            return None
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.weeks[mid] <= day:
                lo = mid
            else:
                hi = mid - 1
        return lo


def week_grid(data: study.Data) -> list[int]:
    end = data.data_end
    out, d = [], end
    while d >= data.data_start + 14:
        out.append(d)
        d -= 7
    return out[::-1]


def build_weekly(data: study.Data, commodities: dict, *, log=print) -> Weekly:
    weeks = week_grid(data)
    nan = math.nan
    per: dict[str, list[list[float]]] = {}
    market: list[list[float]] = [[] for _ in weeks]
    for sym, s in data.secs.items():
        if not P.is_us(sym):
            continue
        b = s.prep.bars
        j = 0
        prev = None
        rows = per.setdefault(s.group, [[] for _ in weeks])
        for w, day in enumerate(weeks):
            while j + 1 < len(b.days) and b.days[j + 1] <= day:
                j += 1
            if b.days[j] > day or day - b.days[j] > 4:
                prev = None
                continue
            c = b.closes[j]
            if prev is not None and prev > 0 and c >= P.MIN_PRICE and j >= 20 and \
                    statistics.fmean(b.closes[k] * (b.volumes[k] or 0) for k in range(j - 19, j + 1)) >= P.MIN_TURNOVER:
                r = c / prev - 1
                if -0.6 < r < 1.5:                     # chyby dat (neupravené splity) ven
                    rows[w].append(r)
                    market[w].append(r)
            prev = c
    mkt = [statistics.median(m) if len(m) >= 50 else nan for m in market]
    ind, n_st = {}, {}
    for g, rows in per.items():
        series = [(statistics.median(r) - mkt[w]) if len(r) >= MIN_STOCKS and mkt[w] == mkt[w] else nan
                  for w, r in enumerate(rows)]
        if sum(1 for v in series if v == v) >= MIN_WEEKS:
            ind[g] = series
            n_st[g] = max(len(r) for r in rows)
    comm = {}
    for cid, bars in commodities.items():
        comm[cid] = [(cdata.ret(bars, day, 7) if cdata.ret(bars, day, 7) is not None else nan) for day in weeks]
    log(f"Týdenní řady: {len(weeks)} týdnů, {len(ind)} oborů, {len(comm)} komodit")
    return Weekly(weeks, ind, comm, n_st)


def rolling_beta(y: list[float], x: list[float], window: int = WINDOW, min_n: int = MIN_WEEKS) -> list[tuple]:
    """Pro každý týden w: (beta, t) z posledních `window` týdnů (jen týdny, kde jsou obě hodnoty), jinak (nan, nan)."""
    nan = math.nan
    out = []
    buf = []
    sx = sy = sxx = sxy = syy = 0.0
    n = 0
    for w in range(len(y)):
        a, b = x[w], y[w]
        ok = a == a and b == b
        buf.append((a, b) if ok else None)
        if ok:
            sx += a; sy += b; sxx += a * a; sxy += a * b; syy += b * b
            n += 1
        if len(buf) > window:
            old = buf.pop(0)
            if old is not None:
                a0, b0 = old
                sx -= a0; sy -= b0; sxx -= a0 * a0; sxy -= a0 * b0; syy -= b0 * b0
                n -= 1
        if n < min_n:
            out.append((nan, nan))
            continue
        vx = sxx - sx * sx / n
        cxy = sxy - sx * sy / n
        vy = syy - sy * sy / n
        if vx <= 1e-12:
            out.append((nan, nan))
            continue
        beta = cxy / vx
        resid = max(vy - beta * cxy, 1e-18)
        se = math.sqrt(resid / (n - 2) / vx)
        out.append((beta, beta / se if se > 0 else nan))
    return out


@dataclass
class Exposure:
    weekly: Weekly
    beta: dict[tuple[str, str], list[tuple]]           # (obor, komodita) → [(beta, t) po týdnech]

    def at(self, group: str, day: int) -> dict[str, tuple[float, float]]:
        """Citlivosti oboru ke dni (jen známé z minulosti)."""
        w = self.weekly.index(day)
        if w is None:
            return {}
        out = {}
        for cid in self.weekly.comm:
            bt = self.beta.get((group, cid))
            if bt and bt[w][0] == bt[w][0]:
                out[cid] = bt[w]
        return out


def build_exposure(weekly: Weekly) -> Exposure:
    beta = {}
    for g, y in weekly.ind.items():
        for cid, x in weekly.comm.items():
            beta[(g, cid)] = rolling_beta(y, x)
    return Exposure(weekly, beta)


def shock(weekly: Weekly, cid: str, w: int, weeks_back: int = 4, sd_weeks: int = 52) -> tuple[float, float] | None:
    """(výnos komodity za posledních `weeks_back` týdnů, z-skóre vůči její běžné kolísavosti) ke týdnu w."""
    x = weekly.comm[cid]
    if w < weeks_back + 20:
        return None
    seg = x[w - weeks_back + 1:w + 1]
    if any(v != v for v in seg):
        return None
    r = math.prod(1 + v for v in seg) - 1
    hist = []
    for k in range(max(weeks_back, w - sd_weeks), w - weeks_back + 1):
        s2 = x[k - weeks_back + 1:k + 1]
        if all(v == v for v in s2):
            hist.append(math.prod(1 + v for v in s2) - 1)
    if len(hist) < 20:
        return None
    sd = statistics.pstdev(hist)
    return (r, r / sd) if sd > 0 else None
