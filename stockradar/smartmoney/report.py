"""Celý běh smart money: data → event study → skóre → aktuální signály → JSON pro web a report.

python -m stockradar smart-money [--no-download]
"""

import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from stockradar.discovery import study
from stockradar.discovery.fundamentals import Fundamentals
from stockradar.smartmoney import analysis, current, groups, score
from stockradar.smartmoney.events import HORIZONS, ordinal, summarize, table
from stockradar.timeutil import to_iso, utcnow

RECENT_DAYS = 60
MAX_RUN_UP = 0.15      # cena od zveřejnění nákupu vzrostla o víc → „růst už proběhl“, vyřadit
MIN_PRICE = 2.0
MIN_TURNOVER = 500_000


def pct(v, d=1):
    return None if v is None else round(v * 100, d)


def info_before_test(market, fund, rows) -> dict:
    """Nákup do 10 dní po výsledcích (10-Q/10-K) nebo 8-K = insider reaguje na informaci, kterou trh už zná."""
    out = {"po_zverejneni": [], "bez_zpravy": []}
    for r in rows:
        if r["kind"] != groups.ACTIVE or not r.get("trade_day"):
            continue
        cik = fund.cik.get(r["symbol"])
        if cik is None:
            continue
        td = ordinal(r["trade_day"])
        fl = fund.filings.get(cik, {})
        after = any(td - 10 <= d <= td for k in ("REPORT", "8K") for d in fl.get(k, []))
        out["po_zverejneni" if after else "bez_zpravy"].append(r)
    return {k: {h: summarize(v, h) for h in ("1m", "6m", "12m")} for k, v in out.items()}


def disclosure_lag(rows) -> dict:
    lags = defaultdict(list)
    for r in rows:
        if r["kind"].startswith("politik:") and r.get("trade_day"):
            lags[r["meta"].get("chamber")].append(ordinal(r["public"]) - ordinal(r["trade_day"]))
        elif r["kind"] == groups.ACTIVE and r.get("trade_day"):
            lags["INSIDER"].append(ordinal(r["public"]) - ordinal(r["trade_day"]))
    return {k: {"median_dni": statistics.median(v), "n": len(v)} for k, v in lags.items() if v}


def congress_sectors(market, rows, min_n=30) -> list[dict]:
    g = defaultdict(list)
    for r in rows:
        if r["kind"] == "politik:AKTIVNÍ NÁKUP" and "(" not in (r["meta"].get("member") or ""):
            sec = market.data.secs.get(r["symbol"])
            g[(sec.meta.get("sector") or sec.meta.get("industry") or "?") if sec else "?"].append(r)
    out = []
    for name, rs in g.items():
        s = summarize(rs, "6m")
        if s.get("n", 0) >= min_n:
            out.append({"sektor": name, **s})
    return sorted(out, key=lambda x: x["nad_kontrolou_prumer"], reverse=True)


def index_series(main_conn, symbol: str = "QQQ") -> tuple[list[int], list[float]]:
    """Index pro srovnání (QQQ = Nasdaq-100, technologie). Stáhne se z Yahoo, pokud chybí."""
    rows = main_conn.execute("SELECT date, close FROM price_bars WHERE symbol = ? ORDER BY date", (symbol,)).fetchall()
    if len(rows) < 500:
        from stockradar.sources import yahoo
        yahoo.store_bars(main_conn, yahoo.fetch_chart(symbol, "5y"))
        rows = main_conn.execute("SELECT date, close FROM price_bars WHERE symbol = ? ORDER BY date", (symbol,)).fetchall()
    return [date.fromisoformat(r[0]).toordinal() for r in rows], [r[1] for r in rows]


def vs_index(idx, entry: str, ret: dict) -> dict:
    import bisect
    days, closes = idx
    i = bisect.bisect_right(days, ordinal(entry)) - 1
    out = {}
    for h, n in HORIZONS.items():
        if i >= 0 and i + n < len(closes) and ret.get(h) is not None:
            out[h] = ret[h] - (closes[i + n] / closes[i] - 1)
    return out


def qqq_test(rows, idx) -> dict:
    """Politici a Pelosi: výnos nad Nasdaq-100 (QQQ) — odpovídá na otázku, zda nejde jen o růst technologií."""
    out = {}
    for name, cond in (("Politici: aktivní nákup — technologie", lambda r: r["meta"].get("sector") == "Technology"),
                       ("Nancy Pelosi: aktivní nákup", lambda r: r["meta"].get("member") == "Nancy Pelosi"),
                       ("Nancy Pelosi: všechny nákupy vč. uplatnění opcí", None)):
        sel = [r for r in rows if r["kind"].startswith("politik:") and (
            (cond is None and r["meta"].get("member") == "Nancy Pelosi") or
            (cond is not None and r["kind"] == "politik:AKTIVNÍ NÁKUP" and cond(r)))]
        res = {}
        for h in ("1m", "6m", "12m"):
            ex = [vs_index(idx, r["entry"], r["ret"]).get(h) for r in sel]
            ex = [x for x in ex if x is not None]
            if ex:
                res[h] = {"n": len(ex), "nad_qqq_prumer": round(statistics.fmean(min(x, 5) for x in ex), 4),
                          "nad_qqq_median": round(statistics.median(ex), 4),
                          "porazilo_qqq": round(sum(1 for x in ex if x > 0) / len(ex), 4)}
        out[name] = res
    return out


def pelosi_db(rows, cache_conn, idx=None) -> list[dict]:
    """Všechny zveřejněné nákupy (manžel/ka i vlastní) — i ty, které nejdou změřit (bez tickeru, mimo data)."""
    measured = {(r["symbol"], r["trade_day"], r["meta"].get("asset_type"), r["meta"].get("amount_min")): r
                for r in rows if r["kind"].startswith("politik:") and r["meta"].get("member") == "Nancy Pelosi"}
    out, seen = [], set()
    for t in cache_conn.execute("SELECT * FROM congress_tx WHERE member = 'Nancy Pelosi' ORDER BY tx_date"):
        key = (t["ticker"], t["tx_date"], t["asset_type"], t["amount_min"], t["tx_type"])
        if key in seen:
            continue
        seen.add(key)
        m = measured.get((t["ticker"], t["tx_date"], t["asset_type"], t["amount_min"]))
        cls = analysis.classify_congress(t["tx_type"], t["description"])
        out.append({"datum_obchodu": t["tx_date"], "zverejneno": t["filed"], "kdo": t["owner"], "ticker": t["ticker"],
                    "typ_aktiva": t["asset_type"], "transakce": t["tx_type"], "trida": cls,
                    "castka": f"{int(t['amount_min']):,}–{int(t['amount_max']):,} USD".replace(",", " ")
                    if t["amount_min"] and t["amount_max"] else None,
                    "popis": t["description"], "zdroj": f"House PTR {t['doc_id']}",
                    **({f"vynos_{h}": pct(m["ret"].get(h)) for h in HORIZONS} if m else {}),
                    **({f"vs_spy_{h}": pct(m.get(f"ex_spy_{h}")) for h in HORIZONS} if m else {}),
                    **({f"vs_qqq_{h}": pct(v) for h, v in vs_index(idx, m["entry"], m["ret"]).items()} if m and idx else {}),
                    **({"max_6m": pct(m["ret"].get("max6m")), "min_6m": pct(m["ret"].get("min6m")),
                        "vstup": m["entry"], "cena_vstup": round(m["entry_price"], 2)} if m else {"merene": False})})
    return out


def next_earnings(fund: Fundamentals, symbol: str, today: int) -> str | None:
    """Odhad dalších výsledků: poslední 10-Q/10-K + ~91 dní (okno ±10 dní) → vždy ESTIMATED, nikdy přesné datum."""
    cik = fund.cik.get(symbol)
    reps = sorted(fund.filings.get(cik, {}).get("REPORT", [])) if cik is not None else []
    if not reps:
        return None
    nxt = reps[-1] + 91
    while nxt < today - 10:
        nxt += 91
    return (f"{date.fromordinal(nxt - 10).isoformat()}..{date.fromordinal(nxt + 10).isoformat()} "
            f"(ESTIMATED: poslední 10-Q/10-K {date.fromordinal(reps[-1]).isoformat()} + 3 měsíce)")


def tier(f: dict, cluster: int, ev: dict) -> int:
    """Předem dané pořadí: typ nakupujícího s kladným výsledkem v OBOU obdobích (učení 2021–24 i test 2025–26)."""
    from stockradar.smartmoney.store import SUBGROUP_OF
    good = [name for key, name in SUBGROUP_OF if f.get(key) and (ev.get(name, (0, 0))[0] or 0) > 0
            and (ev.get(name, (0, 0))[1] or 0) > 0]
    return (2 if good and cluster >= 2 else 1 if good else 0) - (1 if f.get("info_before") else 0)


def current_signals(market, fund, bb, sc, cache_conn, *, today: int, ev: dict, log=print, verify=True, top=10) -> dict:
    recent = current.fetch_recent_purchases(days=RECENT_DAYS, min_value_k=25, pages=6)
    log(f"Aktuální nákupy (openinsider, {RECENT_DAYS} dní): {len(recent)}")
    name_cik = {}
    for r in cache_conn.execute("SELECT DISTINCT owner, owner_cik FROM insider_tx WHERE code = 'P'"):
        name_cik[(r["owner"] or "").lower()] = r["owner_cik"]
    by_t = defaultdict(list)
    for r in recent:
        by_t[r["ticker"]].append(r)
    cand = []
    for sym, rs in by_t.items():
        if sym not in market.data.secs or "." in sym:
            continue
        name = rs[0]["company"]
        if "acquisition" in name.lower() or " spac" in name.lower():
            continue  # SPAC: sponzor kupuje za 10 USD, nejde o signál
        titles = " ".join(r["title"] for r in rs)
        value = sum(r["value"] or 0 for r in rs)
        public = max(ordinal(r["filed"]) for r in rs)
        trade = min(ordinal(r["trade"]) for r in rs if ordinal(r["trade"]))
        owners = sorted({r["insider"] for r in rs})
        meta = {"value": value, "cluster": len(owners), "title": titles,
                "ceo": bool(analysis.CEO.search(titles)), "cfo": bool(analysis.CFO.search(titles)),
                "director": "Dir" in titles, "ten": "10%" in titles,
                "officer": bool(re.search(r"CEO|CFO|COO|Pres|VP|Chief|GC|Officer", titles)),
                "pct": max([10.0 if r["new_position"] else (r["delta_own"] or 0) for r in rs])}
        ids = [name_cik.get(o.lower()) for o in owners if name_cik.get(o.lower())]
        f = score.event_features(market, fund, bb, sym, public, trade, meta, score.track_at(sc["track"], ids, public))
        if f is None:
            continue
        s = market.data.secs[sym]
        i_pub = market.idx_on_or_before(sym, public)
        last = len(s.prep.bars.closes) - 1
        p_pub, p_now = s.prep.bars.closes[i_pub], s.prep.bars.closes[last]
        run_up = p_now / p_pub - 1
        turnover = market.turnover(sym, last)
        if p_now < MIN_PRICE or turnover < MIN_TURNOVER or run_up > MAX_RUN_UP or (f.get("r126_before") or 0) > 0.8:
            continue
        prob = sc["model"].prob(f)
        if sc["score"](prob) < 20:
            continue  # nejslabší pětina skóre — v testu 2025–26 prokazatelně horší (42 % porazilo kontrolu)
        cand.append({"poradi_tier": tier(f, len(owners), ev),"ticker": sym, "firma": name, "kdo": owners[:4], "funkce": titles[:80], "hodnota_usd": round(value),
                     "insideru": len(owners), "zverejneno": date.fromordinal(public).isoformat(),
                     "obchod": date.fromordinal(trade).isoformat(), "cena_nakupu": round(statistics.fmean(
                         [r["price"] for r in rs if r["price"]]), 2) if any(r["price"] for r in rs) else None,
                     "cena_v_den_zverejneni": round(p_pub, 2), "cena_posledni": round(p_now, 2),
                     "den_ceny": s.prep.bars.date(last), "pohyb_od_zverejneni": pct(run_up),
                     "skore": sc["score"](prob), "znaky": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in f.items()},
                     "form4": [r["form4_url"] for r in rs if r["form4_url"]][:3], "zdroj_seznamu": rs[0]["zdroj"]})
    cand.sort(key=lambda c: (c["poradi_tier"], c["insideru"], c["skore"]), reverse=True)
    picked = []
    for c in cand:
        if len(picked) >= top:
            break
        if verify and c["form4"]:
            try:
                v = [current.verify_form4(u, cache_conn) for u in c["form4"][:2]]
            except Exception as exc:  # nedostupné ověření → nezařadit (NEOVĚŘENO)
                log(f"  {c['ticker']}: ověření Form 4 selhalo ({str(exc)[:60]})")
                continue
            s = market.data.secs[c["ticker"]]
            for x in v:  # sleva proti tržní ceně v den obchodu → zvýhodněný (zaměstnanecký) nákup
                days = [t["date"] for t in x["transakce"] if t["code"] == "P" and t["date"]]
                k = market.idx_on_or_before(c["ticker"], ordinal(min(days)[:10])) if days else None
                x["typ"] = current.form4_type(x, s.prep.bars.closes[k] if k is not None else None)
            c["overeni"] = v
            if not any(x["typ"] == "AKTIVNÍ NÁKUP" for x in v):
                c["vyrazeno"] = f"Form 4: nejde o aktivní nákup ({', '.join(sorted({x['typ'] for x in v}))})"
                log(f"  {c['ticker']}: vyřazeno — {c['vyrazeno']}")
                continue
            c["typ"] = "AKTIVNÍ NÁKUP (ověřeno ve Form 4)"
        else:
            c["typ"] = "AKTIVNÍ NÁKUP (NEOVĚŘENO ve Form 4)"
        picked.append(c)
    for c in picked:
        enrich(c, market, fund, bb, sc, cache_conn, today)
    return {"pocet_nakupu": len(recent), "kandidatu": len(cand), "top": picked}


def enrich(c, market, fund, bb, sc, cache_conn, today):
    f = c["znaky"]
    sym = c["ticker"]
    c["fundament"] = {"rust_trzeb": pct(f.get("rev_yoy")), "cena_trzby": round(math.exp(f["log_ps"]), 1) if f.get("log_ps") is not None else None,
                      "hotovost_kapitalizace": pct(f.get("cash_mcap")), "redeni_rok": pct(f.get("dilution"))}
    c["buyback"] = (f"{pct(f['buyback_yield'])} % kapitalizace za poslední rok (SEC)" if f.get("buyback_yield") else
                    "žádný vykázaný" if f.get("buyback_yield") == 0 else "NEOVĚŘENO (firma nepodává XBRL)")
    trials = fund.upcoming_trials(cache_conn, sym, today)
    c["katalyzator"] = ([f"Studie {t['phase']} {t['nct']}: dokončení {t['pcd']} ({t['pcd_type']})" for t in trials[:2]]
                        or [x for x in [next_earnings(fund, sym, today)] if x] or ["NEOVĚŘENO"])
    c["historie_nakupujiciho"] = (f"{pct(f['track'])} % nad kontrolou v průměru předchozích nákupů (6 m)"
                                  if f.get("track") is not None else "NEOVĚŘENO (méně než 2 změřené předchozí nákupy)")
    c["po_zverejnene_informaci"] = bool(f.get("info_before"))
    c["korelace_vs_pricina"] = (
        "Nákup přišel do 10 dní po výsledcích nebo 8-K: insider spíš reaguje na informaci, kterou trh už zná."
        if f.get("info_before") else
        "V 10 dnech před nákupem nebyly výsledky ani 8-K: nákup může nést vlastní informaci, ale v datech 2025–26 "
        "to výhodu nepřineslo — NEOVĚŘENO.")
    c["hlavni_riziko"] = "; ".join(x for x in [
        "malá likvidita" if (f.get("log_turnover") or 9) < 6.5 else None,
        f"ředění {pct(f['dilution'])} % za rok" if (f.get("dilution") or 0) > 0.1 else None,
        f"akcie {pct(f['dd52'])} % pod ročním maximem" if (f.get("dd52") or 0) < -0.3 else None,
        "ztrátová firma" if f.get("rev_yoy") is not None and (f.get("cash_mcap") or 0) > 0.5 else None,
    ] if x) or "běžné tržní riziko"



def run(cache_conn, main_conn, *, log=print, verify=True, csv_dir=None) -> dict:
    res = analysis.run(cache_conn, main_conn, log=log)
    market, fund, rows = res["market"], res["fund"], res["rows"]
    if csv_dir is not None:  # každý případ zvlášť (zadání §2): všechny události + samostatně politici
        log(f"CSV: {analysis.export_csv(rows, csv_dir / 'smart_money_udalosti.csv', fund)} událostí, "
            f"{analysis.export_csv(rows, csv_dir / 'smart_money_politici.csv', fund, ('politik:',))} obchodů politiků")
    bb = score.Buybacks(cache_conn, fund)
    ins = groups.insider_groups(rows)
    out = {"vytvoreno": to_iso(utcnow()), "data_do": study.day_str(market.data.data_end)}
    out["pocty"] = dict(Counter(r["kind"] for r in rows))
    out["insideri"] = table(ins)
    train = [r for r in rows if r["public"] < "2025-01-01"]
    test = [r for r in rows if r["public"] >= "2025-01-01"]
    out["aktivni_vs_pasivni"] = {"cele_obdobi": groups.active_vs_passive(rows, "6m"),
                                 "uceni_2021_2024": groups.active_vs_passive(train, "6m"),
                                 "test_2025_2026": groups.active_vs_passive(test, "6m"),
                                 "cele_12m": groups.active_vs_passive(rows, "12m")}
    out["insider_po_letech"] = {y: summarize(v, "6m") for y, v in groups.by_year(
        [r for r in rows if r["kind"] == groups.ACTIVE]).items()}
    out["po_zverejneni"] = info_before_test(market, fund, rows)
    out["podily"] = table(groups.stake_groups(rows))
    out["buybacky"] = table(groups.buyback_groups(rows))
    out["politici"] = table(groups.congress_groups(rows))
    out["politici_osoby"] = sorted(({"osoba": k, **summarize(v, "6m")} for k, v in groups.by_member(rows).items()),
                                   key=lambda x: x.get("nad_kontrolou_prumer") or 0, reverse=True)
    out["politici_sektory"] = congress_sectors(market, rows)
    out["zpozdeni_zverejneni"] = disclosure_lag(rows)
    for r in rows:  # sektor pro rozdělení politiků (technologie vs ostatní)
        if r["kind"].startswith("politik:"):
            sec = market.data.secs.get(r["symbol"])
            r["meta"]["sector"] = sec.meta.get("sector") if sec else None
    idx = index_series(main_conn, "QQQ")
    out["pelosi"] = pelosi_db(rows, cache_conn, idx)
    out["vs_qqq"] = qqq_test(rows, idx)
    sc = score.fit(market, fund, bb, rows, log=log)
    out["skore"] = {"test_kvintily": sc["test_kvintily"], "vahy": sc["vahy"], "uceni": sc["uceni"], "test": sc["test"]}
    from stockradar.smartmoney.store import evidence, verdict
    ev = evidence(out)
    out["aktualni"] = current_signals(market, fund, bb, sc, cache_conn, today=market.data.data_end, ev=ev, log=log,
                                      verify=verify)
    out["politici_aktualni"] = recent_congress(rows, cache_conn, market)
    for sig in out["aktualni"]["top"]:
        sig["verdikt"], sig["verdikt_proc"] = verdict(sig, ev)
    return out


def recent_congress(rows, cache_conn, market, days: int = 60) -> list[dict]:
    cut = (date.today() - timedelta(days=days)).isoformat()
    out = []
    for t in cache_conn.execute("SELECT * FROM congress_tx WHERE tx_type = 'P' AND filed >= ? AND ticker IS NOT NULL"
                                " ORDER BY filed DESC", (cut,)):
        sec = market.data.secs.get(t["ticker"])
        price = None
        if sec:
            i = market.idx_on_or_before(t["ticker"], ordinal(t["tx_date"]) or 0)
            last = len(sec.prep.bars.closes) - 1
            price = {"obchod": round(sec.prep.bars.closes[i], 2) if i is not None else None,
                     "posledni": round(sec.prep.bars.closes[last], 2), "den": sec.prep.bars.date(last)}
        out.append({"politik": t["member"], "kdo": t["owner"], "ticker": t["ticker"], "obchod": t["tx_date"],
                    "zverejneno": t["filed"], "typ_aktiva": t["asset_type"],
                    "trida": analysis.classify_congress(t["tx_type"], t["description"]),
                    "castka_od": t["amount_min"], "castka_do": t["amount_max"], "popis": t["description"], "ceny": price,
                    "zdroj": f"{t['chamber']} PTR {t['doc_id']}"})
    return out
