"""Event study: co se dělo s cenou akcie po zveřejnění nákupu (bez look-ahead).

* Vstup = první závěrečná cena PO dni zveřejnění (Form 4, výkaz politika, 13D/13G) — to je cena, za kterou mohl
  nakoupit kdokoli, kdo se o nákupu dozvěděl. Pro srovnání se počítá i výnos od data samotného obchodu.
* Horizonty: 1 týden, 1, 3, 6 a 12 měsíců (5, 21, 63, 126, 252 obchodních dní); maximum a minimum do 6 měsíců.
* Srovnání: S&P 500 (SPY) a KONTROLNÍ SKUPINA — 5 náhodných akcií ze stejného oboru s podobným obratem ve stejný
  den. Kontrola odstraňuje efekt oboru a velikosti (např. „Pelosi kupuje technologie, které rostly i bez ní“).
* Statistika: průměr, medián, podíl případů lepších než kontrola, t-statistika přes kalendářní měsíce
  (události ze stejného měsíce nejsou nezávislé).
"""

import bisect
import math
import random
import statistics
from dataclasses import dataclass, field
from datetime import date

from stockradar.discovery import study

HORIZONS = {"1t": 5, "1m": 21, "3m": 63, "6m": 126, "12m": 252}
CONTROLS = 5
CAP = 5.0  # výnos se pro průměry ořízne na +500 % (rozhoduje medián)


@dataclass
class Event:
    symbol: str
    public_day: int          # ordinal dne zveřejnění
    trade_day: int | None    # ordinal dne obchodu (pokud je znám)
    kind: str
    meta: dict = field(default_factory=dict)


class Market:
    """Ceny všech akcií z cache objevování + SPY; rychlé hledání indexů a kontrolních skupin."""

    def __init__(self, data: study.Data, spy_days: list[int], spy_closes: list[float], seed: int = 5):
        self.data = data
        self.spy_days, self.spy_closes = spy_days, spy_closes
        self.seed = seed
        self.by_group: dict[str, list[str]] = {}
        for sym, s in data.secs.items():
            self.by_group.setdefault(s.group, []).append(sym)

    def idx_after(self, sym: str, day: int) -> int | None:
        b = self.data.secs[sym].prep.bars
        i = bisect.bisect_right(b.days, day)
        return i if i < len(b.days) and b.days[i] - day <= 7 else None

    def idx_on_or_before(self, sym: str, day: int) -> int | None:
        b = self.data.secs[sym].prep.bars
        i = bisect.bisect_right(b.days, day) - 1
        return i if i >= 0 and day - b.days[i] <= 7 else None

    def fwd(self, sym: str, i: int) -> dict:
        c = self.data.secs[sym].prep.bars.closes
        out = {}
        for name, n in HORIZONS.items():
            out[name] = c[i + n] / c[i] - 1 if i + n < len(c) and c[i] > 0 else None
        seg = c[i + 1:i + 127]
        if seg and c[i] > 0:
            out["max6m"], out["min6m"] = max(seg) / c[i] - 1, min(seg) / c[i] - 1
        return out

    def spy_fwd(self, day: int) -> dict:
        i = bisect.bisect_right(self.spy_days, day) - 1
        c = self.spy_closes
        return {name: (c[i + n] / c[i] - 1 if 0 <= i and i + n < len(c) else None) for name, n in HORIZONS.items()}

    def turnover(self, sym: str, i: int) -> float:
        s = self.data.secs[sym]
        rate = self.data.usd_rate(s.currency, s.prep.bars.days[i])
        return study.turnover_usd(s.prep, i, rate) if rate else 0.0

    def controls(self, sym: str, day: int) -> list[tuple[str, int]]:
        """Až CONTROLS akcií ze stejného oboru s obratem v pásmu 1/3×–3× ve stejný den (bez dané akcie)."""
        i0 = self.idx_after(sym, day)
        if i0 is None:
            return []
        t0 = self.turnover(sym, i0) or 1.0
        group = self.by_group.get(self.data.secs[sym].group, [])
        # vlastní generátor pro každou akcii a den: kontrola nezávisí na tom, kolik jiných událostí se měřilo předtím
        rng = random.Random(f"{self.seed}:{sym}:{day}")
        pool = [s for s in rng.sample(group, min(len(group), 60)) if s != sym]
        out = []
        for s in pool:
            j = self.idx_after(s, day)
            if j is None:
                continue
            t = self.turnover(s, j)
            if t > 0 and 1 / 3 <= t / t0 <= 3:
                out.append((s, j))
            if len(out) >= CONTROLS:
                break
        return out


def measure(market: Market, ev: Event) -> dict | None:
    if ev.symbol not in market.data.secs:
        return None
    i = market.idx_after(ev.symbol, ev.public_day)
    if i is None:
        return None
    s = market.data.secs[ev.symbol]
    c = s.prep.bars.closes
    entry_day = s.prep.bars.days[i]
    r = market.fwd(ev.symbol, i)
    spy = market.spy_fwd(entry_day)
    ctrl = [market.fwd(cs, j) for cs, j in market.controls(ev.symbol, ev.public_day)]
    out = {"symbol": ev.symbol, "kind": ev.kind, "public": study.day_str(ev.public_day), "entry": study.day_str(entry_day),
           "entry_price": c[i], "meta": ev.meta, "ret": r, "spy": spy}
    for h in HORIZONS:
        out[f"ex_spy_{h}"] = (min(r[h], CAP) - spy[h]) if r.get(h) is not None and spy.get(h) is not None else None
        cv = [x[h] for x in ctrl if x.get(h) is not None]
        out[f"ex_ctrl_{h}"] = (min(r[h], CAP) - statistics.fmean(min(v, CAP) for v in cv)) if r.get(h) is not None and cv else None
    # výnos od data obchodu (co získal sám nakupující) a pohyb mezi obchodem a zveřejněním
    if ev.trade_day:
        k = market.idx_on_or_before(ev.symbol, ev.trade_day)
        if k is not None and c[k] > 0:
            out["move_trade_to_public"] = c[i] / c[k] - 1
            out["ret_from_trade_6m"] = c[k + 126] / c[k] - 1 if k + 126 < len(c) else None
    # stav před nákupem: odstup od ročního maxima a pohyb za 6 měsíců
    if i >= 126:
        out["dd52"] = c[i] / max(c[max(0, i - 251):i + 1]) - 1
        out["r126_before"] = c[i] / c[i - 126] - 1
    out["turnover"] = market.turnover(ev.symbol, i)
    return out


def summarize(rows: list[dict], h: str = "6m") -> dict:
    """Statistika jedné skupiny událostí pro horizont h."""
    xs = [r for r in rows if r.get(f"ex_ctrl_{h}") is not None]
    if not xs:
        return {"n": 0}
    ex_c = [r[f"ex_ctrl_{h}"] for r in xs]
    ex_s = [r[f"ex_spy_{h}"] for r in xs if r.get(f"ex_spy_{h}") is not None]
    raw = [min(r["ret"][h], CAP) for r in xs]
    months: dict[str, list[float]] = {}
    for r in xs:
        months.setdefault(r["public"][:7], []).append(r[f"ex_ctrl_{h}"])
    mm = [statistics.fmean(v) for v in months.values()]
    t = (statistics.fmean(mm) / (statistics.stdev(mm) / math.sqrt(len(mm)))) if len(mm) >= 3 and statistics.stdev(mm) > 0 else None
    return {
        "n": len(xs), "mesicu": len(mm),
        "vynos_prumer": round(statistics.fmean(raw), 4), "vynos_median": round(statistics.median(raw), 4),
        "nad_spy_prumer": round(statistics.fmean(ex_s), 4) if ex_s else None,
        "nad_spy_median": round(statistics.median(ex_s), 4) if ex_s else None,
        "porazilo_spy": round(sum(1 for v in ex_s if v > 0) / len(ex_s), 4) if ex_s else None,
        "nad_kontrolou_prumer": round(statistics.fmean(ex_c), 4),
        "nad_kontrolou_median": round(statistics.median(ex_c), 4),
        "porazilo_kontrolu": round(sum(1 for v in ex_c if v > 0) / len(ex_c), 4),
        "t_mesice": round(t, 2) if t is not None else None,
        "max6m_median": round(statistics.median(r["ret"]["max6m"] for r in xs if r["ret"].get("max6m") is not None), 4)
        if any(r["ret"].get("max6m") is not None for r in xs) else None,
        "min6m_median": round(statistics.median(r["ret"]["min6m"] for r in xs if r["ret"].get("min6m") is not None), 4)
        if any(r["ret"].get("min6m") is not None for r in xs) else None,
    }


def table(groups: dict[str, list[dict]]) -> dict:
    """Pro každou skupinu statistika po 1 týdnu, 1, 3, 6 a 12 měsících."""
    return {name: {h: summarize(rows, h) for h in HORIZONS} for name, rows in groups.items()}


def ordinal(day: str | None) -> int | None:
    try:
        return date.fromisoformat(day).toordinal() if day else None
    except ValueError:
        return None
