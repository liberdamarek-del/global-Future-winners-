"""Experiment E4 (2026-10-11): „nejsilnější sázka“ správců fondů (SEC 13F) → výnos akcie za 6 měsíců.

Protokol je zapsaný PŘEDEM v docs/VYZKUM.md (E4) a tady se jen provádí:
  * běžná váha akcie W = průměr vah přes všechny rozložené správce (20–500 pozic) v témže čtvrtletí (f13_cons),
  * nejsilnější sázka správce = mezi jeho 20 největšími pozicemi ta s největším (w − W), jen akcie z našeho vesmíru
    (CUSIP → symbol ze souborů SEC Fails-to-Deliver),
  * vstup = první závěr po 46. dni od konce čtvrtletí; jedna událost na akcii a čtvrtletí,
  * skupiny G1 (≥ 1 správce, hlavní), G2 (≥ 3 správci), G3 (G1 u firem < 2 mld. USD),
  * POTVRZENO jen při t ≥ 2 a stejném znaménku v obou polovinách (do 2023 / od 2024).
Kontrola párování CUSIP → symbol na jménech (`audit`) se dělá před pohledem na výnosy (poučení E3). Při ní se ukázalo,
že náš seznam firem obsahuje i uzavřené fondy (Nuveen, PIMCO…) → podle protokolu („fondy vypadnou“) se vyřadí podle
jména (FUND_NAME) ještě před výpočtem výnosů.
"""

import json
import math
import re
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
FUND_NAME = re.compile(r"\b(fund|funds|etf|municipal|muni|income trust)\b", re.I)


def is_fund(name: str | None, industry: str | None = None) -> bool:
    """Uzavřený fond podle jména; „Income Trust“ u realitních REIT (Office Properties Income Trust) fondem není."""
    m = FUND_NAME.search(name or "")
    return bool(m) and not (m.group(1).lower() == "income trust" and "real estate" in (industry or "").lower())


def symbol_for(ftd_symbol: str, universe: set[str]) -> str | None:
    """Symbol z FTD (třídy bez oddělovače: BFB) → symbol v našem vesmíru (BF-B)."""
    s = ftd_symbol.upper().replace(".", "-").replace("/", "-")
    if s in universe:
        return s
    alt = f"{s[:-1]}-{s[-1]}" if len(s) >= 2 else None
    return alt if alt in universe else None


def _first(name: str) -> str:
    return (norm(name).split() or [""])[0][:4]


def cusip_symbols(cache_conn, universe: set[str]) -> dict[str, tuple[str, str]]:
    """CUSIP → (symbol, popis). Ticker se po zániku firmy přiděluje znovu (Barnes Group „B“ → Barrick „B“ 2025), ceny
    jsou podle dnešního tickeru → u symbolu platí jen jeho nejnovější CUSIP a starší CUSIP jen se stejným prvním slovem
    jména (nový CUSIP téže firmy); přejmenování se stejným CUSIP (Square → Block) zůstává."""
    by_sym: dict[str, list[tuple[str, str, str]]] = {}
    for cusip, sym, desc, seen in cache_conn.execute("SELECT cusip, symbol, description, seen FROM cusip_map"):
        s = symbol_for(sym, universe)
        if s:
            by_sym.setdefault(s, []).append((seen, cusip, desc or ""))
    out = {}
    for s, items in by_sym.items():
        items.sort()
        latest = items[-1]
        for seen, cusip, desc in items:
            if cusip == latest[1] or _first(desc) == _first(latest[2]):
                out[cusip] = (s, desc)
    return out


GENERIC = {"capital", "financial", "finl", "bank", "bancorp", "bancshares", "energy", "international", "intl", "global",
           "american", "national", "first", "systems", "sys", "technologies", "technology", "tech", "resources",
           "industries", "inds", "services", "svcs", "trust", "realty", "properties", "partners", "pharmaceuticals", "pharma",
           "therapeutics", "health", "healthcare", "medical", "communications", "solutions", "mining", "gold", "oil",
           "gas", "investment", "invt", "mortgage", "insurance", "new", "united", "general", "data", "software", "acquisition",
           "brands", "biosciences", "bio", "sciences", "products", "enterprises", "worldwide", "com", "shs", "ord", "adr",
           "sponsored", "ads", "spdr", "ishares", "etf", "index", "and", "of", "de", "del"}


def _tokens(name: str) -> set[str]:
    return {t for t in norm(name).split() if len(t) >= 3 and t not in GENERIC}


def names_agree(a: str, refs: list[str]) -> bool:
    """Shodne se jméno z 13F s některým referenčním jménem? (slovo ≥ 3 znaky, jedno je začátkem druhého;
    obecná slova jako „capital“ se nepočítají). Prázdné jméno z 13F = nelze ověřit → nepřijmout."""
    ta = _tokens(a)
    for ref in refs:
        for t in _tokens(ref):
            if any(x.startswith(t) or t.startswith(x) for x in ta):
                return True
    return False


def best_ideas(cache_conn, cmap: dict[str, tuple[str, str]], names: dict[str, str] | None = None,
               stats: dict | None = None) -> dict[tuple[str, str], dict]:
    """(období, symbol) → {správců, max_aw, jméno_13f}; každý správce přispěje jednou akcií.

    Kontrola chyb správců (2026-10-11, na jménech, před výnosy): správce občas uvede u ETF nebo jiné firmy cizí CUSIP
    („SPDR S&P 500“ s CUSIP Sherwin-Williams) → chybně označená pozice má nízkou běžnou váhu a vypadala by jako
    „nejsilnější sázka“. Pozice se přijme jen když jméno z 13F odpovídá našemu jménu firmy, popisu z FTD nebo
    nejčastějšímu jménu, pod kterým tento CUSIP v daném čtvrtletí uvádějí aspoň 2 správci (přejmenování zůstávají)."""
    names = names or {}
    stats = stats if stats is not None else {}
    managers = {p: n for p, n in cache_conn.execute("SELECT period, managers FROM f13_period")}
    out: dict[tuple[str, str], dict] = {}
    periods = [p for p in sorted(managers) if p >= FIRST_PERIOD]
    for period in periods:
        cons = {c: sw / managers[period] for c, sw in cache_conn.execute(
            "SELECT cusip, sum_w FROM f13_cons WHERE period = ?", (period,))}
        rows = cache_conn.execute(
            "SELECT t.accession, t.cusip, t.name, t.w FROM f13_top t JOIN f13_mgr m USING (accession) WHERE m.period = ?",
            (period,)).fetchall()
        counts: dict[str, dict[str, int]] = {}
        for _, cusip, name, _ in rows:
            if cusip in cmap and name:
                k = counts.setdefault(cusip, {})
                k[norm(name)] = k.get(norm(name), 0) + 1
        # nejčastější jméno CUSIP platí jen když ho používají aspoň 2 správci (jinak by chyba jediného správce
        # potvrdila sama sebe: „ALPHABET INC-C“ s CUSIP Global Net Lease)
        common = {}
        for c, k in counts.items():
            nm, cnt = max(k.items(), key=lambda kv: kv[1])
            if cnt >= 2:
                common[c] = nm
        best: dict[str, tuple[float, str, str]] = {}
        for acc, cusip, name, w in rows:
            if cusip not in cmap:
                continue
            sym, desc = cmap[cusip]
            if not names_agree(name or "", [names.get(sym, ""), desc, common.get(cusip, "")]):
                stats["odmitnuto_jmeno"] = stats.get("odmitnuto_jmeno", 0) + 1
                continue
            stats["prijato"] = stats.get("prijato", 0) + 1
            aw = w - cons.get(cusip, 0.0)
            if acc not in best or aw > best[acc][0]:
                best[acc] = (aw, cusip, name or "")
        for aw, cusip, name in best.values():
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
    first = _first
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


def _mcap_now(market, fund, sym: str) -> float | None:
    s = market.data.secs.get(sym)
    if s is None or not s.prep.bars.days:
        return None
    i = len(s.prep.bars.days) - 1
    rate = market.data.usd_rate(s.currency, s.prep.bars.days[i]) or 1.0
    lm = fund.features(sym, s.prep.bars.days[i], s.prep.bars.closes[i] * rate).get("log_mcap")
    return math.exp(lm) if lm is not None else None


def nw_t(xs: list[float], lag: int = 1) -> float | None:
    """t-statistika průměru s korekcí Newey-West: 6měsíční výnosy sousedních čtvrtletí se z poloviny překrývají,
    takže obyčejné t přes měsíce je nadsazené."""
    n = len(xs)
    if n < 4:
        return None
    m = statistics.fmean(xs)
    d = [x - m for x in xs]
    var = sum(v * v for v in d) / n
    for l in range(1, lag + 1):
        var += 2 * (1 - l / (lag + 1)) * sum(d[i] * d[i - l] for i in range(l, n)) / n
    return m / math.sqrt(var / n) if var > 0 else None


def monthly(rows: list[dict], h: str = "6m") -> list[tuple[str, float, int]]:
    by: dict[str, list[float]] = {}
    for r in rows:
        if r.get(f"ex_ctrl_{h}") is not None:
            by.setdefault(r["public"][:7], []).append(r[f"ex_ctrl_{h}"])
    return [(k, statistics.fmean(v), len(v)) for k, v in sorted(by.items())]


def current_list(ideas: dict, names: dict[str, str], today: date, mcap_of=None, max_cap: float = SMALL_CAP) -> dict:
    """Aktuální nejsilnější sázky na MALÉ firmy (skupina G3, < 2 mld. USD podle dnešní ceny): poslední čtvrtletí, jehož
    zprávy už jsou veřejné (konec + 46 dní ≤ dnes). Velké firmy (AAPL je „nejsilnější sázkou“ stovek malých správců)
    uživateli nic nového neřeknou a jejich výhoda od 2024 mizí."""
    periods = sorted({p for p, _ in ideas if date.fromisoformat(p) + timedelta(days=ENTRY_DAYS) <= today})
    if not periods:
        return {"obdobi": None, "seznam": []}
    last = periods[-1]
    items = []
    for (p, sym), d in ideas.items():
        if p != last:
            continue
        cap = mcap_of(sym) if mcap_of else None
        if cap is None or cap >= max_cap:
            continue
        items.append({"symbol": sym, "nazev": names.get(sym), "spravcu": d["spravcu"], "max_aw": round(d["max_aw"], 4),
                      "mcap_mld": round(cap / 1e9, 2)})
    items.sort(key=lambda x: (-x["spravcu"], -x["max_aw"]))
    return {"obdobi": last, "zverejneno_do": (date.fromisoformat(last) + timedelta(days=ENTRY_DAYS)).isoformat(),
            "skupina": "G3 (firmy < 2 mld. USD)", "vsech_sazek": sum(1 for p, _ in ideas if p == last), "seznam": items}


def run(cache_conn, main_conn, *, log=print, audit_only: bool = False, today: date | None = None) -> dict:
    market = load_market(cache_conn, main_conn)
    us = {s for s in market.data.secs if "." not in s}
    names, industry = {}, {}
    for s, n, ind in cache_conn.execute("SELECT symbol, name, industry FROM securities"):
        names[s], industry[s] = n, ind
    funds = {s for s in us if is_fund(names.get(s), industry.get(s))}
    cmap = cusip_symbols(cache_conn, us - funds)
    name_stats: dict = {}
    ideas = best_ideas(cache_conn, cmap, names, name_stats)
    log(f"CUSIP → symbol: {len(cmap)} (vyřazeno fondů {len(funds)}); kontrola jmen pozic {name_stats}; "
        f"událostí (akcie × čtvrtletí): {len(ideas)}")
    check = audit(cache_conn, ideas, names)
    check["kontrola_jmen_pozic"] = name_stats
    if audit_only:
        return {"audit": check}
    fund = Fundamentals(cache_conn, us)
    rows = []
    for (period, sym), d in ideas.items():
        if period > LAST_PERIOD:          # studie podle protokolu E4; novější čtvrtletí jen do aktuálního seznamu
            continue
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
    robust = {}
    for name in ("G1 ≥ 1 správce (hlavní hypotéza)", "G2 ≥ 3 správci", "G3 G1 u firem < 2 mld. USD"):
        series = monthly(groups[name])
        t_nw = nw_t([m for _, m, _ in series])
        robust[name] = {"t_newey_west": None if t_nw is None else round(t_nw, 2),
                        "mesice": [(k, round(m, 4), n) for k, m, n in series]}
    end = max((s.prep.bars.days[-1] for s in market.data.secs.values() if s.prep.bars.days), default=None)
    return {"audit": {k: v for k, v in check.items() if k != "vzorek"}, "udalosti": len(rows), "tabulka": tab,
            "plus40_minus25": rates, "vsechny_akcie": base, "verdikt": verdict, "stejne_znamenko": same,
            "robustnost": robust, "aktualni": current_list(ideas, names, today or date.today(), lambda sym: _mcap_now(market, fund, sym)),
            "data_do": date.fromordinal(end).isoformat() if end else None}


def save_run(conn, res: dict) -> int:
    from stockradar import __version__
    from stockradar.timeutil import to_iso, utcnow
    slim = {k: v for k, v in res.items() if k != "tabulka"}
    slim["tabulka_6m"] = {name: per["6m"] for name, per in res["tabulka"].items()}
    with conn:
        cur = conn.execute("INSERT INTO fund_runs (run_at, data_through, period, result_json, app_version) VALUES (?, ?, ?, ?, ?)",
                           (to_iso(utcnow()), res.get("data_do") or "", (res.get("aktualni") or {}).get("obdobi") or "",
                            json.dumps(slim, ensure_ascii=False, default=str), __version__))
    return cur.lastrowid


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
