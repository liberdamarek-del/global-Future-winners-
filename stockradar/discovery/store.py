"""Uložení běhu objevování do hlavní DB (state/ v gitu) a zápis kandidátů do prediction ledgeru (§42)."""

import json
import sqlite3
from datetime import datetime, timedelta

from stockradar import __version__, config
from stockradar.companies import find_company
from stockradar.discovery import cache
from stockradar.ledger import LedgerRuleError, PredictionInput, Scores, record_prediction
from stockradar.timeutil import parse_iso, to_iso, utcnow
from stockradar.universe import add_tracked_company

HORIZON = {"W1_30": ("D0_14", 7, 0.30), "M3_50": ("M6_PLUS", 90, 0.50)}
PER_MODEL = 5
MAX_PERCENTILE = 0.01  # do ledgeru jen horní 1 % skóre


def save_run(conn: sqlite3.Connection, result: dict, *, now: datetime | None = None) -> int:
    payload = {k: v for k, v in result.items() if not k.startswith("_")}
    with conn:
        cur = conn.execute(
            "INSERT INTO discovery_runs (run_at, data_through, stats_json, result_json, models_json, app_version)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (to_iso(now or utcnow()), result["data_do"], json.dumps(result["statistika"], ensure_ascii=False),
             json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
             json.dumps(result.get("_models", {}), separators=(",", ":")), __version__))
    return cur.lastrowid


def _listing_for(conn, cache_conn, row: dict, now) -> int:
    sym = row["ticker"]
    hit = conn.execute("SELECT id FROM listings WHERE yahoo_symbol = ? AND valid_to IS NULL", (sym,)).fetchone()
    if hit:
        return hit["id"]
    meta = cache_conn.execute("SELECT * FROM securities WHERE symbol = ?", (sym,)).fetchone()
    name = (row.get("nazev") or sym).strip()
    if find_company(conn, name) is not None:
        name = f"{name} ({sym})"
    company_id = add_tracked_company(
        conn, name, yahoo_symbol=sym, exchange=(meta["exchange"] if meta else None) or "NEOVĚŘENO",
        currency=row.get("mena") or "NEOVĚŘENO", nodes=[], country=row.get("zeme"),
        sector=meta["sector"] if meta else None, industry=row.get("obor"),
        notes="Přidáno globálním objevováním (pre-winner kandidát); fundamenty NEOVĚŘENO.",
        reason="Globální objevování — kandidát se znaky, které předcházely raketám", now=now)
    return conn.execute("SELECT id FROM listings WHERE company_id = ?", (company_id,)).fetchone()["id"]


def benchmark_price(conn) -> float | None:
    r = conn.execute("SELECT close FROM price_bars WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                     (config.BENCHMARK_SYMBOL,)).fetchone()
    return r["close"] if r else None


def record_candidates(conn: sqlite3.Connection, cache_conn, result: dict, run_id: int, *,
                      now: datetime | None = None) -> tuple[list[int], list[str]]:
    now = now or utcnow()
    bench = benchmark_price(conn)
    created, notes = [], []
    if bench is None:
        return created, ["Chybí cena S&P 500 (SPY) — kandidáti nezapsáni; spusť nejdřív `update`."]
    for kind, rows in result["kandidati"].items():
        horizon, days, threshold = HORIZON[kind]
        if not result["studie"][kind].get("smerova_vyhoda"):
            notes.append(f"{kind}: model nemá směrovou výhodu v testu mimo vzorek — kandidáti do ledgeru nezapsáni "
                         "(je lepší nemít tip než slabý tip, §36).")
            continue
        # jen PER_MODEL nejlepších kandidátů běhu; kdo už má otevřenou predikci, se nepřeskakuje dalším v pořadí
        for row in [r for r in rows if r["percentil"] <= MAX_PERCENTILE][:PER_MODEL]:
            listing_id = _listing_for(conn, cache_conn, row, now)
            since = to_iso(now - timedelta(days=days))
            if conn.execute("SELECT 1 FROM predictions WHERE listing_id = ? AND mode = 'LIVE' AND made_at >= ?",
                            (listing_id, since)).fetchone():
                continue
            bars = cache.load_series(cache_conn, row["ticker"])
            if bars is None:
                continue
            as_of = min(parse_iso(f"{bars.date(len(bars.days) - 1)}T21:00:00Z"), now)
            presnost = row.get("historicka_presnost")
            try:
                pid = record_prediction(conn, PredictionInput(
                    listing_id=listing_id, horizon=horizon, price=bars.closes[-1], currency=bars.currency or "NEOVĚŘENO",
                    price_as_of=as_of, price_source="Yahoo Finance chart API (denní závěr)",
                    category="C", verdict="WATCH",
                    rationale=(f"Globální objevování (běh {run_id}): {result['studie'][kind]['popis']}. "
                               f"Skóre v horním {row['percentil'] * 100:.1f} % ze všech firem, fáze {row['faze']}. "
                               f"Proč teď: {'; '.join(row['proc_ted']) or '—'}."),
                    p_rocket_pct=round(presnost * 100, 2) if presnost is not None else None,
                    bull_case=f"Raketa {('≥ +30 % do týdne' if kind == 'W1_30' else '≥ +50 % do 3 měsíců')}.",
                    bear_case="Signál vyprchá; vysoce volatilní akcie mohou stejně snadno spadnout.",
                    key_risk="; ".join(row["proc_ne"][:3]),
                    scores=Scores(rocket=int(round((1 - row["percentil"]) * 100))),
                    benchmark_symbol=config.BENCHMARK_SYMBOL, benchmark_price=bench,
                    source="DISCOVERY", discovery_run_id=run_id,
                ), now=now)
                created.append(pid)
            except LedgerRuleError as exc:
                notes.append(f"{row['ticker']}: {exc}")
    return created, notes
