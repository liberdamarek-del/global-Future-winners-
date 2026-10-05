"""Znaky nad rámec ceny: překvapení ve výsledcích, co už je v ceně, kapitálový tok. Vše jen z dat známých k danému dni.

Překvapení (bod 3 zadání): konsenzus analytiků zdarma není (NEOVĚŘENO), proto „očekávání“ = stejný kvartál
před rokem (sezónní náhodná procházka, standard v akademické literatuře o driftu po výsledcích):
  eps_chg_p  (zisk na akcii − zisk na akcii před rokem) / cena  — známé od podání 10-Q/10-K
  sue        totéž dělené směrodatnou odchylkou předchozích meziročních změn (když jsou aspoň 4)
Co už je v ceně (bod 4):
  ear        reakce akcie na výsledky: výnos od zavření před oznámením do zavření den po něm, minus S&P 500.
             Den oznámení = 8-K v 45 dnech před 10-Q/10-K s největším objemem obchodů (výsledky jdou jako 8-K).
  gap        překvapení minus reakce (kladné = výsledky lepší, než trh zatím ocenil) — hypotéza, ověřuje se testem
  drift      pohyb akcie od oznámení minus S&P 500;  news_reac  reakce na poslední 8-K do 30 dní (+ objem)
Kapitálový tok (bod 10): různí insideři s aktivním nákupem za 30 dní, hodnota nákupů za 90 dní, buyback / kapitalizace,
  nové 13G za 90 dní, akumulace objemu (podíl objemu ve dnech růstu). Short interest a opční toky: NEOVĚŘENO.
"""

import bisect
import math
import statistics
from collections import defaultdict

from stockradar.discovery.fundamentals import Fundamentals, _ord

EXTRA_FEATURES = {
    "eps_chg_p": "Překvapení: změna zisku na akcii proti stejnému kvartálu loni / cena",
    "sue": "Překvapení: standardizované (změna / běžné kolísání)",
    "ear": "Reakce trhu na poslední výsledky (3 dny, vůči S&P 500)",
    "gap": "Překvapení minus reakce trhu (co ještě není v ceně)",
    "drift": "Pohyb od oznámení výsledků vůči S&P 500",
    "days_since_ann": "Dní od oznámení výsledků",
    "news_reac": "Reakce na poslední 8-K do 30 dní (vůči S&P 500)",
    "news_vol": "Objem v den posledního 8-K / průměr 60 dní",
    "ins_n30": "Různí insideři s aktivním nákupem za 30 dní",
    "ins_val90": "Hodnota aktivních nákupů insiderů za 90 dní (log10 USD)",
    "bb_yield": "Buyback za poslední rok / kapitalizace",
    "g13_90": "Nový podíl nad 5 % (13G) za 90 dní",
    "acc20": "Akumulace: podíl objemu ve dnech růstu (20 dní)",
}
ANN_WINDOW = 45


class Spy:
    def __init__(self, days: list[int], closes: list[float]):
        self.days, self.closes = days, closes

    def ret(self, d0: int, d1: int) -> float | None:
        i = bisect.bisect_right(self.days, d0) - 1
        j = bisect.bisect_right(self.days, d1) - 1
        if i < 0 or j < 0 or self.closes[i] <= 0:
            return None
        return self.closes[j] / self.closes[i] - 1


def _quarter_key(end: int) -> int:
    from datetime import date
    d = date.fromordinal(end)
    return d.year * 4 + (d.month - 1) // 3


class Extra:
    """Předpočítá pro každou firmu oznámení výsledků, překvapení a insidery; dotaz features(sym, bars, i)."""

    def __init__(self, cache_conn, fund: Fundamentals, spy: Spy, bars_of, *, recent_insiders: list[dict] | None = None):
        self.fund, self.spy, self.bars_of = fund, spy, bars_of
        # --- oznámení výsledků a překvapení
        self.ann: dict[str, list[tuple]] = {}          # sym -> [(známé_od, den_oznámení, eps_chg, sue, eps)]
        for sym, cik in fund.cik.items():
            ann = self._announcements(sym, cik)
            if ann:
                self.ann[sym] = ann
        # --- insideři: aktivní nákupy (kód P, bez plánu 10b5-1, bez prodeje do 10 dní) podle dne podání
        from stockradar.smartmoney.analysis import classify_insider, sales_after, sold_within
        from stockradar.smartmoney.events import ordinal
        sales = sales_after(cache_conn)
        self.ins: dict[str, list[tuple[int, object, float]]] = defaultdict(list)
        last_sec = 0
        for r in cache_conn.execute("SELECT ticker, filing_date, trans_date, issuer_cik, owner_cik, shares, price, plan10b51"
                                    " FROM insider_tx WHERE code = 'P' AND ticker IS NOT NULL"):
            d = ordinal(r["filing_date"])
            if d is None:
                continue
            last_sec = max(last_sec, d)
            sold = sold_within(sales, r["owner_cik"], r["issuer_cik"], ordinal(r["trans_date"]))
            if classify_insider("P", r["plan10b51"], r["price"], sold, r["shares"]) != "AKTIVNÍ NÁKUP":
                continue
            self.ins[r["ticker"]].append((d, r["owner_cik"], (r["shares"] or 0) * (r["price"] or 0)))
        # po konci čtvrtletních sad SEC: čerstvé nákupy z openinsider (sekundární přehled Form 4)
        self.insider_source_end = last_sec
        for r in recent_insiders or []:
            d = ordinal(r.get("filed"))
            if d is None or d <= last_sec:
                continue
            self.ins[r["ticker"]].append((d, r.get("insider"), r.get("value") or 0.0))
        for v in self.ins.values():
            v.sort(key=lambda t: t[0])
        # --- 13G a buybacky
        self.g13: dict[int, list[int]] = defaultdict(list)
        for r in cache_conn.execute("SELECT cik, filed FROM sec_filings WHERE form IN ('SC 13G','SCHEDULE 13G')"):
            self.g13[r["cik"]].append(_ord(r["filed"]))
        for v in self.g13.values():
            v.sort()
        self.bb: dict[int, list[tuple[int, float]]] = defaultdict(list)
        reports = {cik: per.get("REPORT", []) for cik, per in fund.filings.items()}
        for r in cache_conn.execute("SELECT cik, end_day, val FROM sec_facts WHERE concept = 'buyback'"):
            end = _ord(r["end_day"])
            rep = [d for d in reports.get(r["cik"], []) if end < d <= end + 120]
            self.bb[r["cik"]].append((rep[0] if rep else end + 90, r["val"] or 0.0))
        for v in self.bb.values():
            v.sort()

    # ------------------------------------------------------------------ výsledky
    def _announcements(self, sym: str, cik: int) -> list[tuple]:
        facts = self.fund.facts.get(cik, {})
        ni, sh = facts.get("net_income", []), facts.get("shares", [])
        if not ni or not sh:
            return []
        reports = self.fund.filings.get(cik, {}).get("REPORT", [])
        eights = self.fund.filings.get(cik, {}).get("8K", [])
        bars = self.bars_of(sym)
        eps_by_q = {}
        for avail, end, val in ni:
            k = bisect.bisect_left([e for _, e, _ in sh], end - 30)
            near = [(abs(e - end), v) for _, e, v in sh[max(0, k - 2):k + 3] if abs(e - end) <= 60 and v and v > 0]
            if near and val is not None:
                eps_by_q[_quarter_key(end)] = (avail, end, val / min(near)[1])
        out = []
        diffs: list[tuple[int, float]] = []
        for q in sorted(eps_by_q):
            avail, end, eps = eps_by_q[q]
            prev = eps_by_q.get(q - 4)
            if prev is None:
                continue
            diff = eps - prev[2]
            past = [d for qq, d in diffs if q - 12 <= qq < q]
            sue = None
            if len(past) >= 4:
                sd = statistics.pstdev(past)
                sue = max(-10.0, min(10.0, diff / sd)) if sd > 0 else None
            diffs.append((q, diff))
            ann = self._ann_day(avail, reports, eights, bars)
            out.append((avail, ann, diff, sue, eps))
        return out

    @staticmethod
    def _ann_day(avail: int, reports: list[int], eights: list[int], bars) -> int:
        """Den oznámení: 8-K v 45 dnech před podáním 10-Q/10-K s největším objemem; jinak den podání."""
        cands = [d for d in eights if avail - ANN_WINDOW <= d <= avail]
        if not cands or bars is None:
            return avail
        best, best_v = avail, -1.0
        for d in cands:
            i = bisect.bisect_left(bars.days, d)         # první obchodní den ≥ 8-K (podání po zavření → další den)
            for j in (i, i + 1):
                if 60 <= j < len(bars.days) and bars.days[j] - d <= 4:
                    avg = sum(bars.volumes[j - 60:j]) / 60
                    v = bars.volumes[j] / avg if avg > 0 else 0.0
                    if v > best_v:
                        best, best_v = d, v
        return best

    def _reaction(self, bars, d: int, day: int) -> tuple[float | None, float | None]:
        """(výnos od zavření před d do zavření den po d minus S&P 500, objem / průměr) — jen když je známý k `day`."""
        i0 = bisect.bisect_left(bars.days, d) - 1
        i1 = i0 + 2
        if i0 < 60 or i1 >= len(bars.days) or bars.days[i1] > day or bars.closes[i0] <= 0:
            return None, None
        r = bars.closes[i1] / bars.closes[i0] - 1
        s = self.spy.ret(bars.days[i0], bars.days[i1])
        avg = sum(bars.volumes[i0 - 60:i0]) / 60
        vol = max(bars.volumes[i0 + 1], bars.volumes[i1]) / avg if avg > 0 else None
        return (r - s if s is not None else None), vol

    # ------------------------------------------------------------------ dotaz
    def features(self, sym: str, bars, i: int, price_usd: float | None, log_mcap: float | None) -> dict:
        day = bars.days[i]
        out = dict.fromkeys(EXTRA_FEATURES)
        # výsledky
        ann = self.ann.get(sym)
        if ann:
            known = [a for a in ann if a[0] <= day]
            if known:
                avail, ad, diff, sue, eps = known[-1]
                if day - avail <= 120:
                    price = bars.closes[i]
                    out["eps_chg_p"] = max(-1.0, min(1.0, diff / price)) if price > 0 else None
                    out["sue"] = sue
                    ear, _ = self._reaction(bars, ad, day)
                    out["ear"] = ear
                    out["days_since_ann"] = float(day - ad)
                    if out["eps_chg_p"] is not None and ear is not None:
                        out["gap"] = max(-3.0, min(3.0, out["eps_chg_p"] * 20)) - max(-3.0, min(3.0, ear * 10))
                    j = bisect.bisect_left(bars.days, ad) - 1
                    if 0 <= j < i and bars.closes[j] > 0:
                        s = self.spy.ret(bars.days[j], day)
                        out["drift"] = bars.closes[i] / bars.closes[j] - 1 - (s or 0.0)
        cik = self.fund.cik.get(sym)
        if cik is not None:
            eights = self.fund.filings.get(cik, {}).get("8K", [])
            k = bisect.bisect_right(eights, day - 2) - 1      # 8-K, jehož reakce (den po) už je známá
            if k >= 0 and day - eights[k] <= 30:
                out["news_reac"], out["news_vol"] = self._reaction(bars, eights[k], day)
            g = self.g13.get(cik, [])
            out["g13_90"] = float(bisect.bisect_right(g, day) - bisect.bisect_right(g, day - 90))
            bb = [v for d, v in self.bb.get(cik, []) if d <= day]
            if log_mcap is not None:
                out["bb_yield"] = max(0.0, min(0.5, (bb[-1] if bb else 0.0) / math.exp(log_mcap)))
        # insideři
        ins = self.ins.get(sym)
        if ins is not None or cik is not None:
            lst = ins or []
            lo = bisect.bisect_right([d for d, _, _ in lst], day - 90)
            recent = [(d, o, v) for d, o, v in lst[lo:] if d <= day]
            val90 = sum(v for _, _, v in recent)
            out["ins_n30"] = float(len({o for d, o, _ in recent if d > day - 30}))
            out["ins_val90"] = math.log10(val90) if val90 > 0 else 0.0
        # akumulace objemu
        if i >= 21:
            up = sum(bars.volumes[k] for k in range(i - 19, i + 1) if bars.closes[k] > bars.closes[k - 1])
            tot = sum(bars.volumes[k] for k in range(i - 19, i + 1))
            out["acc20"] = up / tot if tot > 0 else None
        return out
