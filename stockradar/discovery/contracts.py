"""Experiment E3 (2026-10-11): velká federální zakázka USA → výnos akcie za 6 měsíců (studie událostí).

Hypotéza (stanovená PŘEDEM): nová zakázka (Mod 0) v hodnotě ≥ 10 % tržní hodnoty firmy (akcie ze SEC známé k danému
dni × cena) vede k lepšímu výnosu za 6 měsíců, než má kontrolní skupina (5 akcií ze stejného oboru s podobným obratem).
POTVRZENO jen při t ≥ 2 (přes kalendářní měsíce) a stejném znaménku v obou polovinách období.

Bez pohledu do budoucnosti: částka transakce je známá v den akce; vstup až první závěr ≥ 7 dní po akci (měří se
pokračování, ne samotná reakce na oznámení); tržní hodnota z akcií známých k danému dni. Párování příjemce zakázky
s firmou jen přes přesnou shodu normalizovaného jména (dceřiné firmy s jiným jménem se ztratí — přesnost před úplností).
Omezení: ceny jen dnes obchodovaných firem (zkreslení přeživších), měřeno proti kontrole ze stejného oboru.
"""

import json
import re
from datetime import date

from stockradar.discovery.fundamentals import Fundamentals
from stockradar.smartmoney import events as E
from stockradar.smartmoney.analysis import load_market

SUFFIX = re.compile(r"\b(incorporated|inc|corporation|corp|company|co|llc|l l c|ltd|limited|plc|lp|l p|holdings?|group|"
                    r"the|class [a-c]|common stock|common shares|ordinary shares|depositary shares|american)\b")
GROUPS = {"≥ 10 % hodnoty firmy (hlavní hypotéza)": (0.10, 99.0), "5–10 %": (0.05, 0.10), "2–5 %": (0.02, 0.05),
          "< 2 % (velké firmy, kontrola)": (0.0, 0.02)}
SPLIT_DAY = date(2023, 12, 31).toordinal()


def norm(name: str | None) -> str:
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = SUFFIX.sub(" ", s)
    return " ".join(s.split())


def name_index(cache_conn, symbols: set[str]) -> dict[str, str]:
    """Normalizované jméno firmy → symbol (jen jednoznačná jména)."""
    seen: dict[str, set[str]] = {}
    for sym, name in cache_conn.execute("SELECT symbol, name FROM securities"):
        if sym in symbols:
            n = norm(name)
            if len(n) >= 4:
                seen.setdefault(n, set()).add(sym)
    return {n: next(iter(s)) for n, s in seen.items() if len(s) == 1}


TARGET_INDUSTRY = ("military", "government", "aerospace", "defense", "edp services", "engineering", "construction",
                   "electronic components", "telecommunications equipment", "radio and television", "professional services",
                   "biotechnology", "industrial machinery", "environmental", "electric utilities", "nuclear", "shipbuilding",
                   "computer communications", "space", "ordnance")


def firm_key(name: str) -> str | None:
    """Klíč pro cílené hledání: první dvě slova normalizovaného jména (zachytí i dceřiné firmy „Kratos Unmanned…“
    jen když sdílí obě slova); jednoslovné jméno jen s ≥ 4 znaky."""
    words = norm(name).split()
    if not words or (len(words) == 1 and len(words[0]) < 4):
        return None
    return " ".join(words[:2])


def target_firms(cache_conn, symbols: set[str]) -> list[tuple[str, str, object]]:
    """Menší americké firmy (20 mil.–5 mld. USD) z oborů, kde jsou vládní zakázky běžné."""
    out = []
    for sym, name, ind, cap in cache_conn.execute("SELECT symbol, name, industry, market_cap_usd FROM securities"):
        if sym not in symbols or not cap or not (2e7 <= cap <= 5e9) or not any(k in (ind or "").lower() for k in TARGET_INDUSTRY):
            continue
        key = firm_key(name)
        if key:
            out.append((sym, key, (lambda k: lambda rec: (norm(rec) + " ").startswith(k + " "))(key)))
    return out


def events(cache_conn, market, fund: Fundamentals) -> tuple[list[E.Event], dict]:
    us = {s for s in market.data.secs if "." not in s}
    idx = name_index(cache_conn, us)
    stats = {"transakci": 0, "novych_zakazek": 0, "sparovano": 0, "bez_hodnoty_firmy": 0}
    out = []
    rows = [(idx.get(norm(r[2])), *r) for r in cache_conn.execute(
        "SELECT award_id, mod, recipient, action_date, amount, agency, description FROM gov_tx")]
    try:                                       # cílené stažení menších firem (symbol přiřazen při stažení)
        rows += [tuple(r) for r in cache_conn.execute(
            "SELECT symbol, award_id, mod, recipient, action_date, amount, agency, description FROM gov_tx_firm")]
    except Exception:
        pass
    seen = set()
    for sym, award, mod, rec, day, amount, agency, desc in rows:
        stats["transakci"] += 1
        if mod not in ("0", "00", "000", ""):
            continue
        stats["novych_zakazek"] += 1
        if sym is None or sym not in us or (sym, award, day) in seen:
            continue
        seen.add((sym, award, day))
        stats["sparovano"] += 1
        d = date.fromisoformat(day[:10]).toordinal()
        i = market.idx_on_or_before(sym, d)
        if i is None:
            continue
        s = market.data.secs[sym]
        rate = market.data.usd_rate(s.currency, s.prep.bars.days[i]) or 1.0
        lm = fund.features(sym, d, s.prep.bars.closes[i] * rate).get("log_mcap")
        if lm is None:
            stats["bez_hodnoty_firmy"] += 1
            continue
        ratio = amount / pow(2.718281828459045, lm)
        out.append(E.Event(sym, d + 7, d, "ZAKAZKA", {"pomer": ratio, "castka": amount, "prijemce": rec, "urad": agency,
                                                     "zakazka": award, "popis": desc}))
    return out, stats


def run(cache_conn, main_conn, *, log=print) -> dict:
    market = load_market(cache_conn, main_conn)
    fund = Fundamentals(cache_conn, {s for s in market.data.secs if "." not in s})
    evs, stats = events(cache_conn, market, fund)
    log(f"Zakázky: {stats}; událostí s hodnotou firmy {len(evs)}")
    rows = []
    for e in evs:
        m = E.measure(market, e)
        if m:
            m["pomer"] = e.meta["pomer"]
            m["day_ord"] = e.public_day
            rows.append(m)
    groups = {}
    for name, (lo, hi) in GROUPS.items():
        g = [r for r in rows if lo <= r["pomer"] < hi]
        groups[name] = g
        groups[f"{name} · do 2023"] = [r for r in g if r["day_ord"] <= SPLIT_DAY]
        groups[f"{name} · od 2024"] = [r for r in g if r["day_ord"] > SPLIT_DAY]
    tab = E.table(groups)
    main = tab["≥ 10 % hodnoty firmy (hlavní hypotéza)"]["6m"]
    halves = [tab[f"≥ 10 % hodnoty firmy (hlavní hypotéza) · {p}"]["6m"] for p in ("do 2023", "od 2024")]
    same_sign = all((h.get("nad_kontrolou_prumer") or 0) > 0 for h in halves) or all((h.get("nad_kontrolou_prumer") or 0) < 0 for h in halves)
    t = main.get("t_mesice")
    verdict = ("POTVRZENO" if t is not None and t >= 2 and same_sign and main["nad_kontrolou_prumer"] > 0 else
               "VYVRÁCENO (horší než kontrola)" if t is not None and t <= -2 else "NEPOTVRZENO")
    top = sorted((r for r in rows if r["pomer"] >= 0.10), key=lambda r: -(r["ret"].get("6m") or -9))[:10]
    return {"statistika": stats, "udalosti": len(rows), "tabulka": tab, "verdikt": verdict, "stejne_znamenko_v_polovinach": same_sign,
            "priklady": [{"symbol": r["symbol"], "den": r["public"], "pomer": round(r["pomer"], 2), "vynos_6m": r["ret"].get("6m"),
                          "nad_kontrolou_6m": r.get("ex_ctrl_6m"), "prijemce": r["meta"].get("prijemce")} for r in top]}


def main():
    from stockradar.config import db_path
    from stockradar.db import open_db
    from stockradar.discovery import cache as dcache
    res = run(dcache.connect(), open_db(db_path()))
    print(json.dumps({k: v for k, v in res.items() if k != "tabulka"}, ensure_ascii=False, indent=1, default=str))
    for name, per in res["tabulka"].items():
        s = per["6m"]
        if s.get("n"):
            print(f"{name:<52} n {s['n']:>4} měs {s['mesicu']:>3}  medián {s['vynos_median']:+.3f}  nad kontrolou {s['nad_kontrolou_prumer']:+.3f}"
                  f" (medián {s['nad_kontrolou_median']:+.3f}, t {s['t_mesice']})  porazilo kontrolu {s['porazilo_kontrolu']:.2f}")


if __name__ == "__main__":
    main()
