"""Tržní režim k danému dni — jen z dat známých do toho dne (S&P 500, VIX, výnos 10letých dluhopisů USA).

Pravidla jsou předem daná (ne laděná podle výsledků):
  ŠOK VOLATILITY  VIX ≥ 30, nebo S&P 500 za 5 dní −5 % a víc
  MEDVĚDÍ         S&P 500 pod 200denním průměrem a aspoň −10 % od ročního maxima
  BÝČÍ VOLATILNÍ  S&P 500 nad 200denním průměrem a VIX ≥ 20
  BÝČÍ KLIDNÝ     S&P 500 nad 200denním průměrem a VIX < 20
  BEZ TRENDU      ostatní (pod průměrem, ale bez velkého propadu)
Doplňkové štítky: sazby rostou / klesají (10letý výnos za 60 dní ±0,25 p. b.), sezóna výsledků (10.–50. den
po konci kvartálu, kdy firmy zveřejňují čísla).
"""

import bisect
import math
import statistics
from dataclasses import dataclass
from datetime import date

REGIMES = ("ŠOK VOLATILITY", "MEDVĚDÍ", "BÝČÍ VOLATILNÍ", "BÝČÍ KLIDNÝ", "BEZ TRENDU")
VIX_SHOCK, VIX_HIGH = 30.0, 20.0
SHOCK_5D = -0.05
BEAR_DD = -0.10
RATES_MOVE = 0.25


@dataclass
class Series:
    days: list[int]
    values: list[float]

    def idx(self, day: int, max_gap: int = 7) -> int | None:
        i = bisect.bisect_right(self.days, day) - 1
        return i if i >= 0 and day - self.days[i] <= max_gap else None


def load_series(main_conn, symbol: str) -> Series:
    rows = main_conn.execute("SELECT date, close FROM price_bars WHERE symbol = ? AND close > 0 ORDER BY date",
                             (symbol,)).fetchall()
    return Series([date.fromisoformat(r[0]).toordinal() for r in rows], [float(r[1]) for r in rows])


def earnings_season(day: int) -> bool:
    d = date.fromordinal(day)
    q_end = date(d.year, ((d.month - 1) // 3) * 3 + 1, 1).toordinal() - 1   # konec předchozího kvartálu
    return 10 <= day - q_end <= 50


class Regime:
    def __init__(self, spy: Series, vix: Series | None = None, tnx: Series | None = None):
        self.spy, self.vix, self.tnx = spy, vix, tnx

    @classmethod
    def from_db(cls, main_conn) -> "Regime":
        vix, tnx = load_series(main_conn, "^VIX"), load_series(main_conn, "^TNX")
        return cls(load_series(main_conn, "SPY"), vix if vix.days else None, tnx if tnx.days else None)

    def features(self, day: int) -> dict[str, float | None]:
        """Znaky režimu pro model (číselné) — None, když chybí data."""
        out = dict.fromkeys(("spy_r5", "spy_r20", "spy_dd", "spy_ma200", "vix", "vix_chg20", "tnx_chg60",
                             "earn_season"))
        out["earn_season"] = 1.0 if earnings_season(day) else 0.0
        i = self.spy.idx(day)
        c = self.spy.values
        if i is not None and i >= 200:
            out["spy_r5"] = c[i] / c[i - 5] - 1
            out["spy_r20"] = c[i] / c[i - 20] - 1
            out["spy_dd"] = c[i] / max(c[max(0, i - 251):i + 1]) - 1
            out["spy_ma200"] = c[i] / statistics.fmean(c[i - 199:i + 1]) - 1
        if self.vix is not None:
            j = self.vix.idx(day)
            if j is not None:
                out["vix"] = self.vix.values[j]
                if j >= 20:
                    out["vix_chg20"] = self.vix.values[j] - self.vix.values[j - 20]
        if self.tnx is not None:
            j = self.tnx.idx(day)
            if j is not None and j >= 60:
                out["tnx_chg60"] = self.tnx.values[j] - self.tnx.values[j - 60]
        return out

    def label(self, day: int) -> str | None:
        f = self.features(day)
        return label_from(f)

    def describe(self, day: int) -> dict:
        f = self.features(day)
        tags = []
        if f["tnx_chg60"] is not None:
            tags.append("sazby rostou" if f["tnx_chg60"] >= RATES_MOVE else
                        "sazby klesají" if f["tnx_chg60"] <= -RATES_MOVE else "sazby beze změny")
        if f["earn_season"]:
            tags.append("sezóna výsledků")
        return {"rezim": label_from(f), "stitky": tags, "znaky": {k: (round(v, 4) if isinstance(v, float) else v)
                                                                   for k, v in f.items()}}


def label_from(f: dict) -> str | None:
    if f.get("spy_ma200") is None:
        return None
    vix = f.get("vix")
    if (vix is not None and vix >= VIX_SHOCK) or (f.get("spy_r5") is not None and f["spy_r5"] <= SHOCK_5D):
        return "ŠOK VOLATILITY"
    if f["spy_ma200"] < 0 and (f.get("spy_dd") or 0) <= BEAR_DD:
        return "MEDVĚDÍ"
    if f["spy_ma200"] >= 0:
        return "BÝČÍ VOLATILNÍ" if vix is not None and vix >= VIX_HIGH else "BÝČÍ KLIDNÝ"
    return "BEZ TRENDU"


REGIME_FEATURES = {
    "spy_r5": "S&P 500 za týden", "spy_r20": "S&P 500 za měsíc", "spy_dd": "S&P 500 od ročního maxima",
    "spy_ma200": "S&P 500 nad/pod 200denním průměrem", "vix": "Index strachu VIX", "vix_chg20": "Změna VIX za měsíc",
    "tnx_chg60": "Změna výnosu 10letých dluhopisů USA za 3 měsíce", "earn_season": "Sezóna výsledků",
}


def _fwd(spy: Series, i: int, h: int = 10) -> float | None:
    return spy.values[i + h] / spy.values[i] - 1 if i + h < len(spy.values) and spy.values[i] > 0 else None


def market_view(reg: Regime, day: int, *, step: int = 14, h: int = 10) -> dict:
    """Bod 7 a 13: co historicky následovalo po stejném režimu — na úrovni CELÉHO TRHU, kde je nezávislé pozorování
    jen jedno za období (každých 14 dní, okna se nepřekrývají). Znaky trhu proto nejsou v modelu jednotlivých akcií:
    pro S&P 500 je za 4 roky jen ~100 nezávislých dvoutýdnů a jen pár epizod (např. růst sazeb hlavně 2022)."""
    spy = reg.spy
    rows = []
    d = day - step
    while d > spy.days[0] + 300:
        i = spy.idx(d)
        if i is not None:
            r = _fwd(spy, i, h)
            if r is not None:
                f = reg.features(d)
                rows.append((label_from(f), f, r))
        d -= step
    if not rows:
        return {"stav": "NEOVĚŘENO"}
    allr = [r for _, _, r in rows]
    mu = statistics.fmean(allr)
    cur = reg.features(day)
    lab = label_from(cur)

    def bucket(name, pred):
        part = [r for l, f, r in rows if pred(l, f)]
        if not part:
            return {"skupina": name, "obdobi": 0}
        t = None
        if len(part) >= 3 and statistics.pstdev(part) > 0:
            t = (statistics.fmean(part) - mu) / (statistics.stdev(part) / math.sqrt(len(part)))
        return {"skupina": name, "obdobi": len(part), "sp500_10d_prumer": round(statistics.fmean(part), 4),
                "kladnych": round(sum(1 for r in part if r > 0) / len(part), 3), "t_vs_vse": round(t, 2) if t is not None else None}

    rates = cur.get("tnx_chg60")
    rate_tag = None if rates is None else ("up" if rates >= RATES_MOVE else "down" if rates <= -RATES_MOVE else "flat")
    out = {"rezim": lab, "obdobi_celkem": len(rows), "sp500_10d_prumer": round(mu, 4),
           "podle_rezimu": [bucket(r, lambda l, f, r=r: l == r) for r in REGIMES],
           "stejny_rezim": bucket(lab or "?", lambda l, f: l == lab)}
    if rate_tag:
        out["stejne_sazby"] = bucket({"up": "sazby rostou", "down": "sazby klesají", "flat": "sazby beze změny"}[rate_tag],
                                     lambda l, f: f.get("tnx_chg60") is not None and (
                                         (f["tnx_chg60"] >= RATES_MOVE) if rate_tag == "up" else
                                         (f["tnx_chg60"] <= -RATES_MOVE) if rate_tag == "down" else
                                         (abs(f["tnx_chg60"]) < RATES_MOVE)))
    sig = [b for b in (out["stejny_rezim"], out.get("stejne_sazby")) if b and b.get("t_vs_vse") is not None
           and abs(b["t_vs_vse"]) >= 2 and b["obdobi"] >= 15]
    out["zaver"] = ("NEVÍM — v historii se tento režim od průměru trhu statisticky nelišil (málo nezávislých období)"
                    if not sig else "; ".join(f"{b['skupina']}: S&P 500 za 10 dní v průměru {b['sp500_10d_prumer']:+.1%} "
                                               f"({b['obdobi']} období, t {b['t_vs_vse']})" for b in sig))
    return out
