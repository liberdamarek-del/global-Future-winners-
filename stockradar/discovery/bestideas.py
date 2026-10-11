"""Experiment E4 (2026-10-11): „nejsilnější sázka“ správců fondů (SEC 13F) → výnos akcie za 6 měsíců.

Protokol je zapsaný PŘEDEM v docs/VYZKUM.md (E4) a tady se jen provádí:
  * běžná váha akcie W = průměr vah přes všechny rozložené správce (20–500 pozic) v témže čtvrtletí (f13_cons),
  * nejsilnější sázka správce = mezi jeho 20 největšími pozicemi ta s největším (w − W), jen akcie z našeho vesmíru
    (CUSIP → symbol ze souborů SEC Fails-to-Deliver),
  * vstup = první závěr po 46. dni od konce čtvrtletí; jedna událost na akcii a čtvrtletí,
  * skupiny G1 (≥ 1 správce, hlavní), G2 (≥ 3 správci), G3 (G1 u firem < 2 mld. USD),
  * POTVRZENO jen při t ≥ 2 a stejném znaménku v obou polovinách (do 2023 / od 2024).
Kontrola párování CUSIP → symbol na jménech (`audit`) se dělá před pohledem na výnosy (poučení E3).
"""

import json
import math
import random
import statistics
from datetime import date, timedelta

from stockradar.discovery.contracts import norm
from stockradar.discovery.fundamentals import Fundamentals
from stockradar.smartmoney import events as E
from stockradar.smartmoney.analysis import load_market

ENTRY_DAYS = 46
SMALL_CAP = 2e9
SPLIT_DAY = date(2023, 12, 31).toordinal()
FIRST_PERIOD, LAST_PERIOD = "2021-03-31", "2026-03-31"


def symbol_for(ftd_symbol: str, universe: set[str]) -> str | None:
    """Symbol z FTD (třídy bez oddělovače: BFB) → symbol v našem vesmíru (BF-B)."""
    s = ftd_symbol.upper().replace(".", "-").replace("/", "-")
    if s in universe:
        return s
    alt = f"{s[:-1]}-{s[-1]}" if len(s) >= 2 else None
    return alt if alt in universe else None


def cusip_symbols(cache_conn, universe: set[str]) -> dict[str, tuple[str, str]]:
    out = {}
    for cusip, sym, desc in cache_conn.execute("SELECT cusip, symbol, description FROM cusip_map"):
        s = symbol_for(sym, universe)
        if s:
            out[cusip] = (s, desc or "")
    return out


def best_ideas(cache_conn, cmap: dict[str, tuple[str, str]]) -> dict[tuple[str, str], dict]:
    """(období, symbol) → {správců, max_aw, jméno_13f}; každý správce přispěje jednou akcií."""
    managers = {p: n for p, n in cache_conn.execute("SELECT period, managers FROM f13_period")}
    cons = {}
    for p, c, sw in cache_conn.execute("SELECT period, cusip, sum_w FROM f13_cons"):
        cons[(p, c)] = sw / managers[p]
    best: dict[str, tuple[float, str, str, str]] = {}
    for acc, period, cusip, name, w in cache_conn.execute(
            "SELECT t.accession, m.period, t.cusip, t.name, t.w FROM f13_top t JOIN f13_mgr m USING (accession)"
            " WHERE m.period BETWEEN ? AND ?", (FIRST_PERIOD, LAST_PERIOD)):
        if cusip not in cmap:
            continue
        aw = w - cons.get((period, cusip), 0.0)
        if acc not in best or aw > best[acc][0]:
            best[acc] = (aw, period, cusip, name or "")
    out: dict[tuple[str, str], dict] = {}
    for aw, period, cusip, name in best.values():
        sym = cmap[cusip][0]
        d = out.setdefault((period, sym), {"spravcu": 0, "max_aw": 0.0, "jmeno_13f": name, "jmeno_ftd": cmap[cusip][1]})
        d["spravcu"] += 1
        d["max_aw"] = max(d["max_aw"], aw)
    return out


def audit(cache_conn, ideas: dict, names: dict[str, str], n: int = 40, seed: int = 4) -> dict:
    """Kontrola párování na jménech: shoda prvního slova jména z 13F a z našeho seznamu firem (bez výnosů)."""
    items = sorted(ideas.items())
    rng = random.Random(seed)
    sample = rng.sample(items, min(n, len(items)))
    first = lambda s: (norm(s).split() or [""])[0][:4]
    rows = [{"symbol": sym, "obdobi": p, "13f": d["jmeno_13f"], "ftd": d["jmeno_ftd"], "nase": names.get(sym, ""),
             "shoda": first(d["jmeno_13f"]) == first(names.get(sym, ""))} for (p, sym), d in sample]
    all_ok = sum(1 for (p, sym), d in items if first(d["jmeno_13f"]) == first(names.get(sym, "")))
    return {"vzorek": rows, "shoda_prvniho_slova_vse": round(all_ok / max(len(items), 1), 3), "udalosti": len(items)}


def base_rates(market, days: list[int], universe: set[str]) -> dict:
    """Podíl +40 % a −25 % za 6 m u všech amerických akcií s obratem ≥ 1 mil. USD ve stejné dny vstupu."""
    up = down = n = 0
    for day in days:
        for sym in universe:
            i = market.idx_after(sym, day)
            if i is None or market.turnover(sym, i) < 1e6:
                continue
            r = market.fwd(sym, i).get("6m")
            if r is None:
                continue
            n += 1
            up += r >= 0.40
            down += r <= -0.25
    return {"n": n, "plus40": round(up / n, 4) if n else None, "minus25": round(down / n, 4) if n else None}


def run(cache_conn, main_conn, *, log=print, audit_only: bool = False) -> dict:
    market = load_market(cache_conn, main_conn)
    us = {s for s in market.data.secs if "." not in s}
    names = {s: n for s, n in cache_conn.execute("SELECT symbol, name FROM securities")}
    cmap = cusip_symbols(cache_conn, us)
    ideas = best_ideas(cache_conn, cmap)
    log(f"CUSIP → symbol: {len(cmap)}; událostí (akcie × čtvrtletí): {len(ideas)}")
    check = audit(cache_conn, ideas, names)
    if audit_only:
        return {"audit": check}
    fund = Fundamentals(cache_conn, us)
    rows = []
    for (period, sym), d in ideas.items():
        q_end = date.fromisoformat(period).toordinal()
        m = E.measure(market, E.Event(sym, q_end + ENTRY_DAYS, q_end, "BEST_IDEA", d))
        if not m:
            continue
        i = market.idx_after(sym, q_end + ENTRY_DAYS)
        s = market.data.secs[sym]
        rate = market.data.usd_rate(s.currency, s.prep.bars.days[i]) or 1.0
        lm = fund.features(sym, q_end + ENTRY_DAYS, s.prep.bars.closes[i] * rate).get("log_mcap")
        m.update(spravcu=d["spravcu"], mcap=math.exp(lm) if lm is not None else None, day_ord=q_end + ENTRY_DAYS)
        rows.append(m)
    groups = {"G1 ≥ 1 správce (hlavní hypotéza)": rows,
              "G2 ≥ 3 správci": [r for r in rows if r["spravcu"] >= 3],
              "G3 G1 u firem < 2 mld. USD": [r for r in rows if r["mcap"] is not None and r["mcap"] < SMALL_CAP]}
    for name in list(groups):
        groups[f"{name} · do 2023"] = [r for r in groups[name] if r["day_ord"] <= SPLIT_DAY]
        groups[f"{name} · od 2024"] = [r for r in groups[name] if r["day_ord"] > SPLIT_DAY]
    tab = E.table(groups)
    rates = {}
    for name, g in groups.items():
        rs = [r["ret"]["6m"] for r in g if r["ret"].get("6m") is not None]
        rates[name] = {"n": len(rs), "plus40": round(sum(x >= 0.40 for x in rs) / len(rs), 4) if rs else None,
                       "minus25": round(sum(x <= -0.25 for x in rs) / len(rs), 4) if rs else None}
    days = sorted({r["day_ord"] for r in rows})
    base = base_rates(market, days, us)
    main = tab["G1 ≥ 1 správce (hlavní hypotéza)"]["6m"]
    halves = [tab[f"G1 ≥ 1 správce (hlavní hypotéza) · {p}"]["6m"] for p in ("do 2023", "od 2024")]
    signs = [math.copysign(1, h.get("nad_kontrolou_prumer") or 0) for h in halves]
    same = signs[0] == signs[1] and all(h.get("nad_kontrolou_prumer") for h in halves)
    t = main.get("t_mesice")
    verdict = ("POTVRZENO" if t is not None and t >= 2 and same and main["nad_kontrolou_prumer"] > 0 else
               "VYVRÁCENO (horší než kontrola)" if t is not None and t <= -2 else "NEPOTVRZENO")
    return {"audit": {k: v for k, v in check.items() if k != "vzorek"}, "udalosti": len(rows), "tabulka": tab,
            "plus40_minus25": rates, "vsechny_akcie": base, "verdikt": verdict, "stejne_znamenko": same}


def main():
    import sys
    from stockradar.config import db_path
    from stockradar.db import open_db
    from stockradar.discovery import cache as dcache
    res = run(dcache.connect(), open_db(db_path()), audit_only="--audit" in sys.argv)
    if "tabulka" not in res:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return
    print(json.dumps({k: v for k, v in res.items() if k != "tabulka"}, ensure_ascii=False, indent=1, default=str))
    for name, per in res["tabulka"].items():
        s = per["6m"]
        if s.get("n"):
            print(f"{name:<44} n {s['n']:>6} měs {s['mesicu']:>3}  medián {s['vynos_median']:+.3f}  nad kontrolou "
                  f"{s['nad_kontrolou_prumer']:+.4f} (medián {s['nad_kontrolou_median']:+.4f}, t {s['t_mesice']})"
                  f"  porazilo {s['porazilo_kontrolu']:.2f}")


if __name__ == "__main__":
    main()
