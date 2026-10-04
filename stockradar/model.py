"""Samoučící skórovací model (§55, §58, §59).

Každý den:
  1. spočítá faktory pro všechny firmy jen z dat známých k danému dni (žádný look-ahead),
  2. na historii (panel každých 5 obchodních dní) změří, které faktory skutečně předpovídaly
     30denní výkon proti S&P 500 (Spearmanova korelace = IC), novější data váží víc,
  3. přepočítá váhy: apriorní odhad × data (čím víc dat, tím víc rozhodují data),
  4. kalibruje skóre na pravděpodobnost (porazit S&P 500, „raketa“ ≥ +20 % za 30 dní),
  5. ověří model mimo vzorek: váhy naučené jen na starších datech testuje na posledních 6 měsících.

Výběr firem do radaru je dnešní (výzkum 2026-10-02), proto je historický test optimistický (selection
bias, §60). Skutečná přesnost se měří jen na živých predikcích v ledgeru.
"""

import bisect
import json
import math
import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from stockradar import config
from stockradar.sources.yahoo import fx_symbol, usd_factor
from stockradar.universe import HYPERSCALERS

HORIZON = 21            # obchodních dní ≈ 30 kalendářních
PANEL_STEP = 5          # vzorek každých 5 obchodních dní
PANEL_YEARS = 3
OOS_DATES = 26          # posledních ~6 měsíců panelu pro test mimo vzorek
N0 = 12.0               # síla apriorního odhadu (v počtu nezávislých 30denních období)
IC_FULL = 0.10          # IC 0,10 = velmi silný faktor -> cílová váha ±1
HALF_LIFE_DAYS = 365
ROCKET = 0.20           # „raketa“ = +20 % a víc za 30 dní
MIN_NAMES = 10
SCORE_BINS = [(0, 40), (40, 50), (50, 60), (60, 70), (70, 101)]

FACTORS = {
    "mom_120": {"label": "Trend 120 dní", "prior": 0.6,
                "why": "Megatrend: firmy, které trh dlouhodobě přeceňuje, často pokračují."},
    "mom_20": {"label": "Pohyb 20 dní", "prior": -0.2,
               "why": "Krátkodobé výstřely se často vracejí — nehonit (§2)."},
    "ext_50": {"label": "Odstup nad průměrem 50 dní", "prior": -0.4,
               "why": "Přepálená cena nad průměrem = horší vstup (§2)."},
    "dd_252": {"label": "Blízkost ročního maxima", "prior": 0.0,
               "why": "Bez apriorního názoru — rozhodnou data."},
    "vol_surge": {"label": "Nárůst objemu", "prior": 0.4,
                  "why": "Rostoucí obchodování naznačuje akumulaci před změnou."},
    "volatility_60": {"label": "Volatilita", "prior": 0.2,
                      "why": "Raketový růst potřebuje pohyblivou akcii (a nese vyšší riziko)."},
    "small_size": {"label": "Malá firma (odhad z obratu)", "prior": 0.3,
                   "why": "Menší firmy mají větší procentní potenciál (§22); velikost z obratu v USD."},
    "bigtech": {"label": "Dohoda s Big Tech", "prior": 0.6,
                "why": "Smlouva s Google/Microsoft/Amazon/Meta potvrzuje poptávku (Nebius test, §14)."},
    "catalyst_45": {"label": "Katalyzátor do 45 dní", "prior": 0.5,
                    "why": "Blízká událost může přecenit firmu (CAPR test, §13)."},
}


@dataclass
class Series:
    dates: list[str]
    closes: list[float]
    volumes: list[float]

    def index_at(self, day: str, max_gap_days: int = 5) -> int | None:
        """Index posledního obchodu nejpozději v daný den (a ne starší než max_gap_days)."""
        i = bisect.bisect_right(self.dates, day) - 1
        if i < 0:
            return None
        if (date.fromisoformat(day) - date.fromisoformat(self.dates[i])).days > max_gap_days:
            return None
        return i


@dataclass
class Universe:
    """Data potřebná k výpočtu faktorů (vše s časovou značkou)."""
    members: list[dict]                      # {symbol, company_id, currency, name}
    series: dict[str, Series]
    relationships: list[dict]
    catalysts: list[dict]
    fx: dict[str, Series] = field(default_factory=dict)

    def usd_rate(self, currency: str | None, day: str) -> float | None:
        if not currency:
            return None
        sym = fx_symbol(currency)
        factor = usd_factor(currency)
        if sym is None:
            return factor
        s = self.fx.get(sym)
        if s is None:
            return None
        i = s.index_at(day, max_gap_days=10)
        return factor / s.closes[i] if i is not None and s.closes[i] > 0 else None


def load_series(conn: sqlite3.Connection, symbol: str) -> Series:
    rows = conn.execute("SELECT date, close, volume FROM price_bars WHERE symbol = ? ORDER BY date", (symbol,)).fetchall()
    return Series([r["date"] for r in rows], [r["close"] for r in rows], [r["volume"] or 0.0 for r in rows])


def load_universe(conn: sqlite3.Connection) -> Universe:
    members = [dict(r) for r in conn.execute(
        "SELECT l.yahoo_symbol AS symbol, l.company_id, l.currency, c.name FROM listings l"
        " JOIN companies c ON c.id = l.company_id WHERE l.yahoo_symbol IS NOT NULL AND l.valid_to IS NULL"
        " AND EXISTS (SELECT 1 FROM company_chain cc WHERE cc.company_id = l.company_id)"
        " ORDER BY l.yahoo_symbol")]
    series = {m["symbol"]: load_series(conn, m["symbol"]) for m in members}
    series[config.BENCHMARK_SYMBOL] = load_series(conn, config.BENCHMARK_SYMBOL)
    fx = {}
    for cur in {m["currency"] for m in members if m["currency"]}:
        sym = fx_symbol(cur)
        if sym:
            fx[sym] = load_series(conn, sym)
    rels = [dict(r) for r in conn.execute("SELECT company_id, counterparty, announced_on FROM relationships"
                                          " WHERE company_id IS NOT NULL")]
    cats = [dict(r) for r in conn.execute("SELECT * FROM catalysts")]
    return Universe(members, series, rels, cats, fx)


# ---------------------------------------------------------------- faktory

def price_factors(s: Series, i: int, usd_rate: float | None) -> dict[str, float | None]:
    c, v = s.closes, s.volumes

    def ret(n):
        return c[i] / c[i - n] - 1 if i >= n and c[i - n] > 0 else None

    out: dict[str, float | None] = {"mom_120": ret(120), "mom_20": ret(20)}
    out["ext_50"] = c[i] / statistics.fmean(c[i - 49:i + 1]) - 1 if i >= 49 else None
    out["dd_252"] = c[i] / max(c[max(0, i - 251):i + 1]) - 1 if i >= 59 else None
    if i >= 119:
        recent, base = statistics.fmean(v[i - 19:i + 1]), statistics.fmean(v[i - 119:i + 1])
        out["vol_surge"] = recent / base if base > 0 else None
    else:
        out["vol_surge"] = None
    if i >= 60:
        rets = [math.log(c[k] / c[k - 1]) for k in range(i - 59, i + 1) if c[k - 1] > 0]
        out["volatility_60"] = statistics.pstdev(rets) if len(rets) > 20 else None
    else:
        out["volatility_60"] = None
    if i >= 59 and usd_rate:
        turnover = statistics.fmean(c[k] * v[k] for k in range(i - 59, i + 1)) * usd_rate
        out["small_size"] = -math.log(turnover) if turnover > 0 else None
    else:
        out["small_size"] = None
    return out


def event_factors(u: Universe, company_id: int, day: str, *, live: bool) -> dict[str, float]:
    d = date.fromisoformat(day)
    bigtech = 0.0
    for r in u.relationships:
        if r["company_id"] == company_id and r["counterparty"] in HYPERSCALERS and r["announced_on"] <= day:
            age = (d - date.fromisoformat(r["announced_on"])).days
            bigtech = max(bigtech, 1.0 if age <= 365 else 0.5)
    horizon_end = (d + timedelta(days=45)).isoformat()
    excluded = {"CANCELLED", "SUPERSEDED"} | ({"OCCURRED", "IN_PROGRESS"} if live else set())
    catalyst = 0.0
    for k in u.catalysts:
        if k["company_id"] != company_id or k["status"] in excluded or k["published_at"][:10] > day:
            continue
        if k["date_status"] == "VERIFIED" and day <= k["event_date"] <= horizon_end:
            catalyst = max(catalyst, 1.0)
        elif k["date_status"] in ("ESTIMATED", "UNCERTAIN") and k["window_start"] <= horizon_end \
                and k["window_end"] >= day:
            catalyst = max(catalyst, 0.5)
    return {"bigtech": bigtech, "catalyst_45": catalyst}


def factors_at(u: Universe, day: str, *, live: bool = False, max_gap_days: int = 5) -> dict[str, dict]:
    """Syrové hodnoty faktorů pro všechny firmy s cenou k danému dni."""
    out = {}
    for m in u.members:
        s = u.series.get(m["symbol"])
        if not s or not s.dates:
            continue
        i = s.index_at(day, max_gap_days)
        if i is None:
            continue
        values = price_factors(s, i, u.usd_rate(m["currency"], s.dates[i]))
        values.update(event_factors(u, m["company_id"], day, live=live))
        out[m["symbol"]] = {"i": i, "values": values}
    return out


def ranks(values: dict[str, float | None]) -> dict[str, float]:
    """Percentilové pořadí 0–1 (shody průměrem); chybějící hodnota = neutrální 0,5."""
    present = sorted((v, k) for k, v in values.items() if v is not None)
    out = {k: 0.5 for k, v in values.items() if v is None}
    n = len(present)
    pos = 0
    while pos < n:
        end = pos
        while end + 1 < n and present[end + 1][0] == present[pos][0]:
            end += 1
        r = ((pos + end) / 2 + 0.5) / n
        for j in range(pos, end + 1):
            out[present[j][1]] = r
        pos = end + 1
    return out


def factor_ranks(snapshot: dict[str, dict]) -> dict[str, dict[str, float]]:
    return {f: ranks({sym: d["values"][f] for sym, d in snapshot.items()}) for f in FACTORS}


def composite(fr: dict[str, dict[str, float]], weights: dict[str, float]) -> dict[str, float]:
    total = sum(abs(w) for w in weights.values()) or 1.0
    symbols = next(iter(fr.values())).keys() if fr else []
    return {s: 50 + 100 * sum(weights[f] * (fr[f][s] - 0.5) for f in FACTORS) / total for s in symbols}


def contributions(fr: dict[str, dict[str, float]], weights: dict[str, float], symbol: str) -> dict[str, float]:
    total = sum(abs(w) for w in weights.values()) or 1.0
    return {f: round(100 * weights[f] * (fr[f][symbol] - 0.5) / total, 2) for f in FACTORS}


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


# ---------------------------------------------------------------- panel a učení

@dataclass
class PanelDate:
    day: str
    raw: dict[str, dict[str, float | None]]   # faktor -> symbol -> hodnota
    fwd: dict[str, float]                     # symbol -> 30denní výnos
    excess: dict[str, float]                  # symbol -> výnos minus S&P 500


def build_panel(u: Universe, *, end_day: str | None = None) -> list[PanelDate]:
    """Historické vzorky, u kterých je už známý 30denní výsledek (do end_day včetně)."""
    spy = u.series.get(config.BENCHMARK_SYMBOL)
    if not spy or len(spy.dates) <= HORIZON:
        return []
    last = len(spy.dates) - 1 if end_day is None else bisect.bisect_right(spy.dates, end_day) - 1
    start_day = (date.fromisoformat(spy.dates[last]) - timedelta(days=365 * PANEL_YEARS)).isoformat()
    first = bisect.bisect_left(spy.dates, start_day)
    panel = []
    for k in range(last - HORIZON, first - 1, -PANEL_STEP):
        day, fwd_day = spy.dates[k], spy.dates[k + HORIZON]
        spy_ret = spy.closes[k + HORIZON] / spy.closes[k] - 1
        snap = factors_at(u, day)
        fwd, excess = {}, {}
        for sym, d in snap.items():
            s = u.series[sym]
            j = s.index_at(fwd_day)
            if j is None or j <= d["i"]:
                continue
            r = s.closes[j] / s.closes[d["i"]] - 1
            fwd[sym], excess[sym] = r, r - spy_ret
        if len(excess) < MIN_NAMES:
            continue
        raw = {f: {sym: snap[sym]["values"][f] for sym in excess} for f in FACTORS}
        panel.append(PanelDate(day, raw, fwd, excess))
    panel.reverse()
    return panel


def learn(panel: list[PanelDate], *, as_of: str) -> tuple[dict[str, float], dict[str, dict]]:
    """Váhy = apriorní odhad smíchaný s naměřeným IC (novější data váží víc)."""
    today = date.fromisoformat(as_of)
    acc = {f: {"w": 0.0, "wic": 0.0, "wic2": 0.0, "n": 0} for f in FACTORS}
    for p in panel:
        weight = 0.5 ** ((today - date.fromisoformat(p.day)).days / HALF_LIFE_DAYS)
        target = ranks(p.excess)
        syms = list(p.excess)
        for f in FACTORS:
            vals = p.raw[f]
            known = [vals[s] for s in syms if vals[s] is not None]
            if len(known) < MIN_NAMES or len(set(known)) < 2:
                continue
            r = ranks(vals)
            ic = pearson([r[s] for s in syms], [target[s] for s in syms])
            if ic is None:
                continue
            a = acc[f]
            a["w"] += weight
            a["wic"] += weight * ic
            a["wic2"] += weight * ic * ic
            a["n"] += 1
    weights, metrics = {}, {}
    for f, meta in FACTORS.items():
        a = acc[f]
        n_eff = a["w"] * PANEL_STEP / HORIZON
        ic = a["wic"] / a["w"] if a["w"] else 0.0
        sd = math.sqrt(max(a["wic2"] / a["w"] - ic * ic, 0.0)) if a["w"] else 0.0
        t_stat = ic / (sd / math.sqrt(n_eff)) if sd > 0 and n_eff > 0 else 0.0
        target = max(-1.0, min(1.0, ic / IC_FULL))
        lam = N0 / (N0 + n_eff)
        weights[f] = round(lam * meta["prior"] + (1 - lam) * target, 4)
        metrics[f] = {"ic": round(ic, 4), "t": round(t_stat, 2), "n_dates": a["n"], "n_eff": round(n_eff, 1),
                      "prior": meta["prior"], "data_weight": round(1 - lam, 3), "weight": weights[f]}
    return weights, metrics


def calibrate(panel: list[PanelDate], weights: dict[str, float]) -> list[dict]:
    buckets = {b: [] for b in SCORE_BINS}
    for p in panel:
        scores = composite({f: ranks(p.raw[f]) for f in FACTORS}, weights)
        for sym, sc in scores.items():
            for lo, hi in SCORE_BINS:
                if lo <= sc < hi:
                    buckets[(lo, hi)].append((p.excess[sym], p.fwd[sym]))
                    break
    out = []
    for (lo, hi), rows in buckets.items():
        n = len(rows)
        ex = sorted(e for e, _ in rows)
        out.append({
            "od": lo, "do": hi, "n": n,
            "p_beat": round((sum(1 for e in ex if e > 0) + 1) / (n + 2), 4),
            "p_rocket": round((sum(1 for _, f in rows if f >= ROCKET) + 1) / (n + 2), 4),
            "mean_excess": round(statistics.fmean(ex), 4) if n else 0.0,
            "q20": round(ex[int(0.2 * (n - 1))], 4) if n else 0.0,
            "q80": round(ex[int(0.8 * (n - 1))], 4) if n else 0.0,
        })
    return out


def bin_for(score: float, calibration: list[dict]) -> dict:
    for b in calibration:
        if b["od"] <= score < b["do"]:
            return b
    return calibration[-1]


def out_of_sample(panel: list[PanelDate]) -> dict:
    """Váhy naučené jen na starších datech, test na posledních OOS_DATES vzorcích."""
    if len(panel) <= OOS_DATES + 20:
        return {"poznamka": "málo historie pro test mimo vzorek"}
    train, test = panel[:-OOS_DATES], panel[-OOS_DATES:]
    weights, _ = learn(train, as_of=train[-1].day)
    ics, hits, excess = [], [], []
    for p in test:
        scores = composite({f: ranks(p.raw[f]) for f in FACTORS}, weights)
        rs, rx = ranks(scores), ranks(p.excess)
        ic = pearson([rs[s] for s in scores], [rx[s] for s in scores])
        if ic is not None:
            ics.append(ic)
        top = sorted(scores, key=scores.get, reverse=True)[:5]
        hits += [p.excess[s] > 0 for s in top]
        excess += [p.excess[s] for s in top]
    return {
        "obdobi": f"{test[0].day}..{test[-1].day}",
        "ic": round(statistics.fmean(ics), 4) if ics else None,
        "top5_uspesnost": round(sum(hits) / len(hits), 4) if hits else None,
        "top5_prumer_nad_spy": round(statistics.fmean(excess), 4) if excess else None,
        "vzorku": len(hits),
    }


# ---------------------------------------------------------------- verze modelu

def latest_version(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM model_versions ORDER BY id DESC LIMIT 1").fetchone()


def describe_change(old: dict[str, float] | None, new: dict[str, float]) -> str:
    if old is None:
        return "První verze: apriorní váhy upravené podle historie (panel každých 5 dní, 3 roky)."
    diffs = sorted(((abs(new[f] - old.get(f, 0.0)), f) for f in new), reverse=True)[:3]
    parts = [f"{FACTORS[f]['label']} {old.get(f, 0.0):+.2f} → {new[f]:+.2f}" for d, f in diffs if d >= 0.005]
    return "Nová data změnila váhy: " + "; ".join(parts) if parts else "Beze změny vah."


def save_version_if_changed(conn: sqlite3.Connection, weights, metrics, calibration, *, window: str, n_samples: int,
                            now_iso: str, min_change: float = 0.02) -> tuple[int, bool, str]:
    prev = latest_version(conn)
    old = json.loads(prev["weights_json"]) if prev else None
    if old is not None and max(abs(weights[f] - old.get(f, 0.0)) for f in weights) < min_change:
        return prev["id"], False, "Váhy se změnily méně než o 0,02 — verze modelu zůstává."
    reason = describe_change(old, weights)
    with conn:
        cur = conn.execute(
            "INSERT INTO model_versions (created_at, weights_json, metrics_json, calibration_json, training_window,"
            " n_samples, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now_iso, json.dumps(weights, sort_keys=True), json.dumps(metrics, sort_keys=True, ensure_ascii=False),
             json.dumps(calibration, sort_keys=True), window, n_samples, reason))
    return cur.lastrowid, True, reason
