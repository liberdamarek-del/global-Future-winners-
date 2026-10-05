"""Uložení běhu smart money (append-only) a zápis TOP signálů do prediction ledgeru."""

import json
import sqlite3
from datetime import datetime

from stockradar import __version__, config
from stockradar.discovery import cache
from stockradar.discovery.store import _fresh_quote, _listing_for, benchmark_price
from stockradar.ledger import LedgerRuleError, PredictionInput, Scores, record_prediction
from stockradar.timeutil import parse_iso, to_iso, utcnow

# Předem daná pravidla verdiktu (zadání: VYSOKÁ / STŘEDNÍ / NÍZKÁ signalizační hodnota)
SUBGROUP_OF = (("cfo", "CFO"), ("ten", "10% vlastník"), ("dir_only", "jen člen představenstva"), ("ceo", "CEO"))


def evidence(result: dict) -> dict[str, tuple[float, float]]:
    """Rozdíl aktivní − pasivní (6 m) pro podskupinu v učení 2021–24 a v testu 2025–26 (situace „vše“)."""
    def pick(rows):
        return {r["skupina"]: r["rozdil"] for r in rows if r["situace"] == "vše"}
    tr, te = pick(result["aktivni_vs_pasivni"]["uceni_2021_2024"]), pick(result["aktivni_vs_pasivni"]["test_2025_2026"])
    return {k: (tr.get(k), te.get(k)) for k in tr}


def verdict(sig: dict, ev: dict) -> tuple[str, str]:
    f = sig["znaky"]
    groups = [name for key, name in SUBGROUP_OF if f.get(key)]
    both = [g for g in groups if (ev.get(g, (None, None))[0] or 0) > 0 and (ev.get(g, (None, None))[1] or 0) > 0]
    neg = [g for g in groups if (ev.get(g, (None, None))[1] or 0) < 0]
    if sig["skore"] < 20 or f.get("info_before"):
        return "NÍZKÁ", ("skóre v nejslabší pětině" if sig["skore"] < 20 else
                         "nákup následoval po zveřejněných výsledcích / 8-K")
    # VYSOKÁ by vyžadovala typ nákupu s prokázanou výhodou ve všech obdobích; test 2025–26 ji nepotvrdil u žádného
    # typu se statistickou významností (t > 2), proto nejvýš STŘEDNÍ, dokud ledger neukáže opak.
    if both and sig["insideru"] >= 2 and not neg and all((ev[g][1] or 0) > 0.02 for g in both) and sig.get("t_ok"):
        return "VYSOKÁ", f"typ nakupujícího ({', '.join(both)}) měl výhodu v obou obdobích, víc insiderů"
    if both and not neg:
        return "STŘEDNÍ", f"typ nakupujícího ({', '.join(both)}) měl výhodu v obou obdobích"
    return "NÍZKÁ", "typ nákupu neměl výhodu v testu 2025–26" + (f" ({', '.join(neg)})" if neg else "")


def save_run(conn: sqlite3.Connection, result: dict, *, now: datetime | None = None) -> int:
    with conn:
        cur = conn.execute("INSERT INTO smart_money_runs (run_at, data_through, result_json, app_version) VALUES (?, ?, ?, ?)",
                           (to_iso(now or utcnow()), result["data_do"], json.dumps(result, ensure_ascii=False,
                                                                                    separators=(",", ":")), __version__))
    return cur.lastrowid


def record_signals(conn, cache_conn, result: dict, run_id: int, *, now: datetime | None = None, quote=_fresh_quote):
    now = now or utcnow()
    bench = benchmark_price(conn)
    created, notes = [], []
    if bench is None:
        return created, ["Chybí cena S&P 500 — signály nezapsány"]
    quint = result["skore"]["test_kvintily"]
    for sig in result["aktualni"]["top"]:
        q = next((x for x in quint if x["od"] <= sig["skore"] < x["do"]), None)
        bars = cache.load_series(cache_conn, sig["ticker"])
        if bars is None:
            continue
        price, as_of = bars.closes[-1], min(parse_iso(f"{bars.date(len(bars.days) - 1)}T21:00:00Z"), now)
        qq = quote(sig["ticker"])
        if qq is not None and qq.price and qq.price_time and qq.price_time <= now:
            price, as_of = qq.price, qq.price_time
        sig["cena_aktualni"] = round(price, 2)
        row = {"ticker": sig["ticker"], "nazev": sig["firma"], "mena": "USD", "zeme": "United States", "obor": None}
        listing_id = _listing_for(conn, cache_conn, row, now)
        recent = conn.execute("SELECT 1 FROM predictions WHERE listing_id = ? AND strategy = 'SMART_MONEY'"
                              " AND julianday(?) - julianday(made_at) < 180", (listing_id, to_iso(now))).fetchone()
        if recent:
            continue
        try:
            pid = record_prediction(conn, PredictionInput(
                listing_id=listing_id, horizon="M6_PLUS", price=price, currency="USD", price_as_of=as_of,
                price_source="Yahoo Finance chart API", category="C", verdict="WATCH",
                rationale=(f"Smart money (běh {run_id}): {sig['typ']} — {', '.join(sig['kdo'])} ({sig['funkce']}), "
                           f"{sig['hodnota_usd']:,} USD".replace(",", " ") + f", zveřejněno {sig['zverejneno']}. "
                           f"SMART MONEY SCORE {sig['skore']}/100, signalizační hodnota {sig['verdikt']} "
                           f"({sig['verdikt_proc']}). Predikce: za 6 měsíců lépe než S&P 500."),
                probability_pct=round(q["porazilo_spy"] * 100, 1) if q and q.get("porazilo_spy") is not None else None,
                bull_move_pct=round(q["vynos_q80"] * 100, 1) if q and q.get("vynos_q80") is not None else None,
                base_move_pct=round(q["vynos_median"] * 100, 1) if q and q.get("vynos_median") is not None else None,
                bear_move_pct=round(q["vynos_q20"] * 100, 1) if q and q.get("vynos_q20") is not None else None,
                bull_case="Horní pětina výnosu za 6 měsíců u nákupů se stejným skóre v testu 2025–26.",
                base_case="Medián výnosu za 6 měsíců u nákupů se stejným skóre v testu 2025–26.",
                bear_case="Dolní pětina — nákupy insiderů v testu 2025–26 výhodu neměly.",
                key_risk=sig["hlavni_riziko"], scores=Scores(overall_setup=int(sig["skore"])),
                benchmark_symbol=config.BENCHMARK_SYMBOL, benchmark_price=bench,
                source="DISCOVERY", strategy="SMART_MONEY", smart_money_run_id=run_id), now=now)
            created.append(pid)
        except LedgerRuleError as exc:
            notes.append(f"{sig['ticker']}: {exc}")
    return created, notes
