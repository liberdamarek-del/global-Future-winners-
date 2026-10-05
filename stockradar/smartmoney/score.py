"""SMART MONEY SCORE 0–100 pro aktivní nákupy insiderů.

Model se učí na historii (kdo, kolik, v jaké situaci, fundament, buyback, 13D, katalyzátor, předchozí úspěšnost
nakupujícího) a odhaduje šanci, že akcie během 6 měsíců porazí kontrolní skupinu ze stejného oboru a velikosti.
Učení: zveřejnění do TRAIN_END; test: od TEST_START (model ty nákupy neviděl). Skóre = percentil předpovědi mezi
nákupy v učení (50 = průměrný nákup insidera, ne „50 % šance“).
Short interest: zdarma a historicky není k dispozici → NEOVĚŘENO, ve skóre není.
"""

import bisect
import math
import statistics
from collections import defaultdict
from datetime import date

from stockradar.discovery import rocket
from stockradar.discovery.fundamentals import Fundamentals
from stockradar.smartmoney.analysis import CEO, CFO
from stockradar.smartmoney.events import Market, ordinal

QUINTILES = ((0, 20), (20, 40), (40, 60), (60, 80), (80, 101))
TRAIN_END = date(2024, 12, 31).toordinal()
TEST_START = date(2025, 1, 1).toordinal()
FEATURES = {
    "dd52": "Odstup od ročního maxima v den zveřejnění",
    "r126_before": "Pohyb akcie za 6 měsíců před nákupem",
    "log_value": "Velikost nákupu (log USD)",
    "cluster": "Počet různých insiderů nakupujících do 30 dní",
    "ceo": "Nakupuje CEO", "cfo": "Nakupuje CFO",
    "dir_only": "Nakupuje jen člen představenstva", "ten": "Nakupuje 10% vlastník (fond, majitel)",
    "pct": "Navýšení vlastní pozice (podíl)",
    "log_turnover": "Velikost firmy (denní obrat, log USD)",
    "rev_yoy": "Růst tržeb meziročně", "log_ps": "Cena / tržby (log)", "cash_mcap": "Hotovost / kapitalizace",
    "dilution": "Ředění za rok", "buyback_yield": "Buyback za poslední rok / kapitalizace",
    "d13_180": "13D (velký podíl s aktivním záměrem) za 180 dní", "p3_180": "Studie fáze 3 do 180 dní",
    "n8k_30": "Počet 8-K za 30 dní", "info_before": "Nákup do 10 dní po výsledcích / 8-K (trh informaci znal)",
    "track": "Předchozí úspěšnost téhož nakupujícího (průměr nad kontrolou)",
}


class Buybacks:
    def __init__(self, cache_conn, fund: Fundamentals):
        self.fund = fund
        self.by_cik = defaultdict(list)
        reports = {cik: per.get("REPORT", []) for cik, per in fund.filings.items()}
        for r in cache_conn.execute("SELECT cik, end_day, val FROM sec_facts WHERE concept = 'buyback'"):
            end = ordinal(r["end_day"])
            rep = [d for d in reports.get(r["cik"], []) if end < d <= end + 120]
            self.by_cik[r["cik"]].append((rep[0] if rep else end + 90, r["val"]))
        for v in self.by_cik.values():
            v.sort()

    def last(self, symbol: str, day: int) -> float | None:
        cik = self.fund.cik.get(symbol)
        if cik is None:
            return None
        known = [v for d, v in self.by_cik.get(cik, []) if d <= day]
        return known[-1] if known else 0.0


def event_features(market: Market, fund: Fundamentals, bb: Buybacks, symbol: str, public_day: int,
                   trade_day: int | None, meta: dict, track: float | None) -> dict | None:
    if symbol not in market.data.secs:
        return None
    i = market.idx_on_or_before(symbol, public_day)
    if i is None or i < 126:
        return None
    s = market.data.secs[symbol]
    c = s.prep.bars.closes
    rate = market.data.usd_rate(s.currency, s.prep.bars.days[i])
    price_usd = c[i] * rate if rate else None
    f = fund.features(symbol, public_day, price_usd)
    title = meta.get("title") or ""
    out = {
        "dd52": c[i] / max(c[max(0, i - 251):i + 1]) - 1, "r126_before": c[i] / c[i - 126] - 1,
        "log_value": math.log10(meta["value"]) if meta.get("value") and meta["value"] > 0 else None,
        "cluster": float(meta.get("cluster") or 1),
        "ceo": 1.0 if meta.get("ceo") or CEO.search(title) else 0.0,
        "cfo": 1.0 if meta.get("cfo") or CFO.search(title) else 0.0,
        "dir_only": 1.0 if meta.get("director") and not meta.get("officer") and not meta.get("ten") else 0.0,
        "ten": 1.0 if meta.get("ten") and not meta.get("officer") and not meta.get("director") else 0.0,
        "pct": min(float(meta.get("pct") or 0.0), 10.0),
        "log_turnover": math.log10(market.turnover(symbol, i)) if market.turnover(symbol, i) > 0 else None,
        "rev_yoy": f.get("rev_yoy"), "log_ps": f.get("log_ps"), "cash_mcap": f.get("cash_mcap"),
        "dilution": f.get("dilution"), "d13_180": f.get("d13_180"), "p3_180": f.get("p3_180"), "n8k_30": f.get("n8k_30"),
        "track": track,
    }
    last_bb = bb.last(symbol, public_day)
    out["buyback_yield"] = (last_bb / math.exp(f["log_mcap"])) if last_bb is not None and f.get("log_mcap") else None
    cik = fund.cik.get(symbol)
    if cik is not None and trade_day:
        fl = fund.filings.get(cik, {})
        out["info_before"] = 1.0 if any(trade_day - 10 <= d <= trade_day for kind in ("REPORT", "8K")
                                        for d in fl.get(kind, [])) else 0.0
    else:
        out["info_before"] = None
    return out


def owner_track_records(rows: list[dict]) -> dict:
    """Pro každou osobu seřazené (den, kdy byl známý výsledek 6 m, nadvýnos) — k výpočtu historie bez look-ahead."""
    rec = defaultdict(list)
    for r in rows:
        if r["kind"] != "insider:AKTIVNÍ NÁKUP" or r.get("ex_ctrl_6m") is None:
            continue
        known = ordinal(r["entry"]) + 183
        for oid in (r["meta"].get("owner_ids") or []):
            rec[str(oid)].append((known, r["ex_ctrl_6m"]))
    for v in rec.values():
        v.sort()
    return rec


def track_at(rec: dict, owner_ids, day: int) -> float | None:
    vals = []
    for oid in owner_ids or []:
        lst = rec.get(str(oid), [])
        k = bisect.bisect_right(lst, (day, float("inf")))
        vals += [x for _, x in lst[:k]]
    return statistics.fmean(vals) if len(vals) >= 2 else None


def fit(market: Market, fund: Fundamentals, bb: Buybacks, rows: list[dict], *, log=print) -> dict:
    active = [r for r in rows if r["kind"] == "insider:AKTIVNÍ NÁKUP"]
    rec = owner_track_records(rows)
    feats = list(FEATURES)
    panel = rocket.Panel(feats)
    kept = []
    for r in active:
        pub = ordinal(r["public"])
        f = event_features(market, fund, bb, r["symbol"], pub, ordinal(r.get("trade_day")), r["meta"],
                           track_at(rec, r["meta"].get("owner_ids"), pub))
        if f is None:
            continue
        y = r.get("ex_ctrl_6m")
        panel.add(r["symbol"], pub, f, (1 if y is not None and y > 0 else 0, 0, y if y is not None else math.nan)
                  if y is not None else None)
        kept.append(r)
    labeled = [k for k in range(len(panel)) if panel.y_up[k] >= 0]
    tr = [k for k in labeled if panel.day[k] <= TRAIN_END]
    te = [k for k in labeled if panel.day[k] >= TEST_START]
    log(f"Skóre: {len(tr)} nákupů k učení, {len(te)} k testu")
    model = rocket.train(panel, tr, "up", feats)
    probs_tr = sorted(model.prob({f: panel.cols[f][k] for f in feats}) for k in tr)

    def score(p: float) -> int:
        return int(round(100 * bisect.bisect_left(probs_tr, p) / max(len(probs_tr), 1)))

    test = []
    for k in te:
        p = model.prob({f: panel.cols[f][k] for f in feats})
        r = kept[k]
        test.append((score(p), panel.fwd[k], panel.y_up[k], r.get("ex_spy_6m"), r["ret"].get("6m")))
    quint = []
    for lo, hi in QUINTILES:
        part = [t for t in test if lo <= t[0] < hi]
        if part:
            raw = sorted(min(t[4], 5) for t in part if t[4] is not None)
            spy = [t[3] for t in part if t[3] is not None]
            quint.append({"skore": f"{lo}–{min(hi, 100)}", "od": lo, "do": hi, "n": len(part),
                          "nad_kontrolou_prumer": round(statistics.fmean(min(t[1], 5) for t in part), 4),
                          "nad_kontrolou_median": round(statistics.median(t[1] for t in part), 4),
                          "porazilo_kontrolu": round(sum(t[2] for t in part) / len(part), 4),
                          "porazilo_spy": round(sum(1 for v in spy if v > 0) / len(spy), 4) if spy else None,
                          "vynos_q20": round(raw[int(0.2 * (len(raw) - 1))], 4) if raw else None,
                          "vynos_median": round(raw[len(raw) // 2], 4) if raw else None,
                          "vynos_q80": round(raw[int(0.8 * (len(raw) - 1))], 4) if raw else None})
    weights = sorted(({"znak": f, "nazev": FEATURES[f], "koef": round(w, 3)} for f, w in zip(model.features, model.w)),
                     key=lambda x: abs(x["koef"]), reverse=True)
    return {"model": model, "score": score, "track": rec, "test_kvintily": quint, "vahy": weights,
            "uceni": len(tr), "test": len(te)}
