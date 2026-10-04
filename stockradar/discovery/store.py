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


ROCKET_HORIZON_DAYS = 180
TOO_LATE_JUMP = 0.25  # cena od posledního závěru v cache vyskočila o 25 % a víc → raketa už startuje, nezapisovat


def _fresh_quote(symbol: str):
    from stockradar.sources import yahoo
    try:
        return yahoo.fetch_chart(symbol, "5d", retries=2)
    except Exception:  # bez čerstvé ceny se použije poslední závěr z cache
        return None


def _trial_catalysts(conn, company_id: int, row: dict, now: datetime) -> int | None:
    """Klinické studie s blížícím se dokončením → katalyzátory (odhad = okno PCD … PCD + 90 dní), automaticky."""
    from stockradar.catalysts import add_catalyst
    from stockradar.sources.clinicaltrials import STUDY_URL
    first = None
    existing = {r["source_url"]: r["id"] for r in conn.execute(
        "SELECT id, source_url FROM catalysts WHERE company_id = ? AND status IN ('UPCOMING','DELAYED')", (company_id,))}
    for t in row.get("studie", []):
        url = STUDY_URL.format(nct=t["nct"])
        if url in existing:
            first = first or existing[url]
            continue
        pcd = t["dokonceni"] if len(t["dokonceni"]) == 10 else t["dokonceni"] + "-01"
        end = (datetime.fromisoformat(pcd) + timedelta(days=90)).date().isoformat()
        cid = add_catalyst(
            conn, company_id, "CLINICAL_DATA",
            f"Výsledky studie {t['faze']} ({t['nct']}): {t['nazev']} — dokončení hlavního cíle "
            f"{t['dokonceni']} ({t['typ'] or 'typ neuveden'}), výsledky obvykle do 3 měsíců",
            date_status="ESTIMATED", window=(pcd, end), source=f"ClinicalTrials.gov {t['nct']} (automaticky)",
            source_url=url, now=now)
        first = first or cid
    return first


def record_rockets(conn: sqlite3.Connection, cache_conn, rockets: dict, run_id: int, *, now: datetime | None = None,
                   quote=_fresh_quote) -> tuple[list[int], list[str]]:
    """Zapíše dnešní predikce raket na 6 měsíců do ledgeru (zdroj DISCOVERY, cíl +50 %)."""
    now = now or utcnow()
    bench = benchmark_price(conn)
    if bench is None:
        return [], ["Chybí cena S&P 500 (SPY) — predikce raket nezapsány; spusť nejdřív `update`."]
    created, notes = [], []
    edge = rockets.get("smerova_vyhoda", False)
    since = to_iso(now - timedelta(days=ROCKET_HORIZON_DAYS))
    for row in rockets.get("kandidati", []):
        bars = cache.load_series(cache_conn, row["ticker"])
        if bars is None:
            continue
        price, as_of = bars.closes[-1], min(parse_iso(f"{bars.date(len(bars.days) - 1)}T21:00:00Z"), now)
        q = quote(row["ticker"])
        if q is not None and q.price and q.price_time and q.price_time <= now:
            if q.price / price - 1 >= TOO_LATE_JUMP:
                notes.append(f"{row['ticker']}: od posledního závěru +{(q.price / price - 1) * 100:.0f} % — raketa už "
                             "startuje, nezapsáno (TOO LATE, §2)")
                continue
            price, as_of = q.price, q.price_time
        listing_id = _listing_for(conn, cache_conn, row, now)
        if conn.execute("SELECT 1 FROM predictions WHERE listing_id = ? AND mode = 'LIVE' AND source = 'DISCOVERY'"
                        " AND made_at >= ?", (listing_id, since)).fetchone():
            continue
        company_id = conn.execute("SELECT company_id FROM listings WHERE id = ?", (listing_id,)).fetchone()[0]
        catalyst_id = _trial_catalysts(conn, company_id, row, now)
        pct = lambda v: round(v * 100, 1) if v is not None else None
        hist = (f"V testu mimo vzorek mělo {row['skupina'].replace('top', 'horní ')} % skóre raketu v {pct(row['hist_rakety'])} % "
                f"případů (všechny akcie {pct(row['zakladni_cetnost'])} %), propad ≤ −33 % v {pct(row['hist_propady'])} %.")
        try:
            pid = record_prediction(conn, PredictionInput(
                listing_id=listing_id, horizon="M6_PLUS", price=price, currency=row.get("mena") or "NEOVĚŘENO",
                price_as_of=as_of, price_source="Yahoo Finance chart API",
                category="C", verdict="SPEC_BUY" if edge else "WATCH",
                rationale=(f"Predikce rakety (běh objevování {run_id}): cena do 6 měsíců aspoň +50 %. "
                           f"Skóre v horních {row['percentil'] * 100:.1f} % ze všech akcií, fáze {row['faze']}. "
                           f"Proč: {'; '.join(row['proc']) or '—'}. {hist}"),
                catalyst_id=catalyst_id,
                probability_pct=pct(row["hist_rakety"]), p_rocket_pct=pct(row["p_raketa"]),
                p_drop_pct=pct(row["hist_propady"]), base_rate_pct=pct(row["zakladni_cetnost"]),
                target_move_pct=50.0,
                bull_move_pct=pct(row["hist_q80"]), base_move_pct=pct(row["hist_median"]), bear_move_pct=pct(row["hist_q20"]),
                bull_case="Horní kvintil výnosu za 6 měsíců u podobně hodnocených akcií v testu.",
                base_case="Medián výnosu za 6 měsíců u podobně hodnocených akcií v testu.",
                bear_case="Dolní kvintil — volatilní akcie mohou stejně snadno spadnout.",
                key_risk="; ".join((row.get("proti") or [])[:2] + [f"šance na propad ≤ −33 %: {pct(row['hist_propady'])} %"]),
                scores=Scores(rocket=int(round((1 - row["percentil"]) * 100))),
                benchmark_symbol=config.BENCHMARK_SYMBOL, benchmark_price=bench,
                source="DISCOVERY", discovery_run_id=run_id,
            ), now=now)
            created.append(pid)
        except LedgerRuleError as exc:
            notes.append(f"{row['ticker']}: {exc}")
    if not edge:
        notes.append("Model raket nemá v testu jasnou směrovou výhodu — predikce jsou zapsané jako WATCH (sledovat), "
                     "aby se jejich přesnost měřila v ledgeru.")
    return created, notes
