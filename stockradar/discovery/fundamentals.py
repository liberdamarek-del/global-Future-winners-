"""Fundamenty (SEC), filingy (SEC) a klinické studie (ClinicalTrials.gov) k danému dni — bez look-ahead.

* Hodnota kvartálu (tržby, zisk, akcie, hotovost) se smí použít až od podání 10-Q/10-K/20-F, které ji zveřejnilo
  (první takové podání po konci období, nejvýš 120 dní); když podání v indexu chybí, od konce období + 60 dní.
* Filingy mají v indexu SEC přesné datum podání.
* Klinické studie: v historii se používá dnešní (často už skutečné) datum dokončení — trh znal jen tehdejší odhad.
  Proto je přínos těchto znaků v historickém testu optimistický a ve výstupu se testuje i model bez nich.
"""

import bisect
import math
from datetime import date


REPORT_FORMS = ("10-Q", "10-K", "20-F", "40-F")
LAG_FALLBACK = 60
LAG_MAX = 120

FUND_FEATURES = {
    "has_fund": "Má fundamenty z SEC (americká firma)",
    "rev_yoy": "Růst tržeb meziročně (poslední známý kvartál)",
    "rev_accel": "Zrychlení růstu tržeb (změna meziročního růstu)",
    "profitable": "Čistý zisk v posledním kvartálu > 0",
    "dilution": "Nárůst počtu akcií za rok (ředění)",
    "log_mcap": "Tržní kapitalizace (log USD)",
    "log_ps": "Cena / tržby (log, z posledního kvartálu ×4)",
    "cash_mcap": "Hotovost / tržní kapitalizace",
    "n8k_30": "Počet 8-K (důležitých oznámení) za 30 dní",
    "offer_90": "Emise akcií / prospekty (S-1, S-3, 424B) za 90 dní",
    "d13_180": "Nový velký akcionář / aktivista (13D) za 180 dní",
    "p3_180": "Studie fáze 3 s dokončením do 180 dní",
    "p2_180": "Studie fáze 2 s dokončením do 180 dní",
}


def _ord(day: str) -> int:
    if len(day) == 7:          # YYYY-MM → polovina měsíce
        day = day + "-15"
    return date.fromisoformat(day[:10]).toordinal()


class Fundamentals:
    """Načte SEC a ClinicalTrials data z cache a odpovídá na dotazy (symbol, den) → znaky."""

    def __init__(self, cache_conn, symbols):
        symbols = set(symbols)
        tick = {r["ticker"]: r["cik"] for r in cache_conn.execute("SELECT ticker, cik FROM sec_tickers")}
        self.cik = {s: tick[s] for s in symbols if s in tick}        # US symboly v Yahoo = ticker SEC
        ciks = set(self.cik.values())
        self.filings: dict[int, dict[str, list[int]]] = {}
        reports: dict[int, list[int]] = {}
        for r in cache_conn.execute("SELECT cik, form, filed FROM sec_filings"):
            if r["cik"] not in ciks:
                continue
            d = _ord(r["filed"])
            form = r["form"]
            if form in REPORT_FORMS:
                reports.setdefault(r["cik"], []).append(d)
                self.filings.setdefault(r["cik"], {}).setdefault("REPORT", []).append(d)
            kind = ("8K" if form == "8-K" else "OFFER" if form.startswith(("S-", "F-", "424B")) else
                    "13D" if "13D" in form and not form.endswith("/A") else None)
            if kind:
                self.filings.setdefault(r["cik"], {}).setdefault(kind, []).append(d)
        for per in self.filings.values():
            for v in per.values():
                v.sort()
        for v in reports.values():
            v.sort()
        # fakta: cik -> ukazatel -> seřazené [(dostupné_od, konec_obdobi, hodnota)]
        self.facts: dict[int, dict[str, list[tuple[int, int, float]]]] = {}
        for r in cache_conn.execute("SELECT cik, concept, end_day, val FROM sec_facts"):
            if r["cik"] not in ciks:
                continue
            end = _ord(r["end_day"])
            rep = reports.get(r["cik"], [])
            k = bisect.bisect_right(rep, end)
            avail = rep[k] if k < len(rep) and rep[k] - end <= LAG_MAX else end + LAG_FALLBACK
            self.facts.setdefault(r["cik"], {}).setdefault(r["concept"], []).append((avail, end, r["val"]))
        for per in self.facts.values():
            for v in per.values():
                v.sort(key=lambda t: t[1])
        # klinické studie podle symbolu
        self.trials: dict[str, dict[str, list[int]]] = {}
        for r in cache_conn.execute(
                "SELECT m.symbol, s.phase, s.pcd FROM ct_studies s JOIN ct_sponsor_map m ON m.sponsor = s.sponsor"
                " WHERE m.symbol IS NOT NULL AND s.pcd IS NOT NULL AND s.status NOT IN ('WITHDRAWN','TERMINATED')"):
            if r["symbol"] not in symbols:
                continue
            key = "p3" if "PHASE3" in (r["phase"] or "") else "p2"
            self.trials.setdefault(r["symbol"], {}).setdefault(key, []).append(_ord(r["pcd"]))
        for per in self.trials.values():
            for v in per.values():
                v.sort()

    # ------------------------------------------------------------------ dotazy
    @staticmethod
    def _count(days: list[int], lo: int, hi: int) -> int:
        """Počet dnů v intervalu (lo, hi]."""
        return bisect.bisect_right(days, hi) - bisect.bisect_right(days, lo)

    def _known(self, series: list[tuple[int, int, float]], day: int) -> list[tuple[int, int, float]]:
        return [t for t in series if t[0] <= day]

    @staticmethod
    def _near(known: list[tuple[int, int, float]], end: int, tol: int = 25) -> float | None:
        best = None
        for _, e, v in known:
            if abs(e - end) <= tol and (best is None or abs(e - end) < best[0]):
                best = (abs(e - end), v)
        return best[1] if best else None

    def features(self, symbol: str, day: int, price_usd: float | None) -> dict[str, float | None]:
        out: dict[str, float | None] = dict.fromkeys(FUND_FEATURES)
        trials = self.trials.get(symbol)
        out["p3_180"] = float(self._count(trials.get("p3", []), day, day + 180)) if trials else 0.0
        out["p2_180"] = float(self._count(trials.get("p2", []), day, day + 180)) if trials else 0.0
        cik = self.cik.get(symbol)
        if cik is None:
            out["has_fund"] = 0.0
            return out
        fl = self.filings.get(cik, {})
        out["n8k_30"] = float(self._count(fl.get("8K", []), day - 30, day))
        out["offer_90"] = float(self._count(fl.get("OFFER", []), day - 90, day))
        out["d13_180"] = float(self._count(fl.get("13D", []), day - 180, day))
        facts = self.facts.get(cik, {})
        rev = self._known(facts.get("revenue", []), day)
        out["has_fund"] = 1.0 if rev or facts.get("shares") else 0.0
        rev_q = None
        if rev:
            _, end, rev_q = rev[-1]
            ago = self._near(rev, end - 365)
            if ago and ago > 0 and rev_q is not None:
                out["rev_yoy"] = max(-1.0, min(10.0, rev_q / ago - 1))
                prev = self._near(rev, end - 91)
                prev_ago = self._near(rev, end - 91 - 365)
                if prev is not None and prev_ago and prev_ago > 0:
                    out["rev_accel"] = max(-5.0, min(5.0, out["rev_yoy"] - max(-1.0, min(10.0, prev / prev_ago - 1))))
        ni = self._known(facts.get("net_income", []), day)
        if ni:
            out["profitable"] = 1.0 if ni[-1][2] > 0 else 0.0
        sh = self._known(facts.get("shares", []), day)
        shares = sh[-1][2] if sh else None
        if sh and shares and shares > 0:
            ago = self._near(sh, sh[-1][1] - 365, tol=50)
            if ago and ago > 0:
                out["dilution"] = max(-0.5, min(5.0, shares / ago - 1))
        if shares and price_usd and shares > 0:
            mcap = shares * price_usd
            if mcap > 1e5:
                out["log_mcap"] = math.log(mcap)
                if rev_q and rev_q > 0:
                    out["log_ps"] = max(-5.0, min(10.0, math.log(mcap / (rev_q * 4))))
                cash = self._known(facts.get("cash", []), day)
                if cash:
                    out["cash_mcap"] = max(0.0, min(5.0, cash[-1][2] / mcap))
        return out

    def upcoming_trials(self, cache_conn, symbol: str, day: int, horizon: int = 180) -> list[dict]:
        """Studie fáze 2/3 firmy s dokončením v příštích `horizon` dnech (pro katalyzátory a web)."""
        rows = []
        for r in cache_conn.execute(
                "SELECT s.* FROM ct_studies s JOIN ct_sponsor_map m ON m.sponsor = s.sponsor WHERE m.symbol = ?"
                " AND s.pcd IS NOT NULL AND s.status NOT IN ('WITHDRAWN','TERMINATED') ORDER BY s.pcd", (symbol,)):
            d = _ord(r["pcd"])
            if day < d <= day + horizon:
                rows.append(dict(r))
        return rows
