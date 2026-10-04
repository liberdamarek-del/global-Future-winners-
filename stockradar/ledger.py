"""PREDICTION LEDGER (§28, §29, §30): append-only záznam predikcí a jejich vyhodnocení.

Vynucená pravidla:
  §5   XTB: od 2026-10-02 jen informativně (rozhodnutí uživatele); s config.REQUIRE_XTB_FOR_BUY=True
       platí brána z poučení XSPRAY (spekulativní BUY / MAIN PICK jen s čerstvou kontrolou = ANO)
  §2   spekulativní BUY nesmí stavět na katalyzátoru, který už proběhl nebo právě probíhá (poučení RARE)
  §19  pravděpodobnost a velikost pohybu se ukládají odděleně
  §52  cena se označí FRESH/STALE podle stáří vůči okamžiku predikce
  §59  predikce nesmí použít katalyzátor zveřejněný až po svém vzniku
"""

import sqlite3
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta

from stockradar import __version__
from stockradar.catalysts import date_text, get_catalyst
from stockradar.companies import get_listing, latest_xtb_check, xtb_check_age
from stockradar import config
from stockradar.data_quality import freshness
from stockradar.enums import Category, CatalystStatus, DateStatus, Horizon, OutcomeResult, Verdict
from stockradar.timeutil import parse_date, parse_iso, to_iso, utcnow


class LedgerRuleError(ValueError):
    """Porušení pravidla MASTER PROMPTu — predikce se nezapíše."""


@dataclass(frozen=True)
class Scores:
    """§20: vícerozměrné skóre 0–100. U *_risk platí 100 = nejvyšší riziko. None = nehodnoceno."""
    fundament: int | None = None
    catalyst: int | None = None
    catalyst_timing: int | None = None
    upside: int | None = None
    surprise: int | None = None
    financial_health: int | None = None
    valuation: int | None = None
    technical: int | None = None
    dilution_risk: int | None = None
    execution_risk: int | None = None
    rocket: int | None = None
    overall_setup: int | None = None

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if value is not None and not (isinstance(value, int) and 0 <= value <= 100):
                raise ValueError(f"skóre {f.name} musí být celé číslo 0–100, ne {value!r}")


@dataclass(frozen=True)
class PredictionInput:
    listing_id: int
    horizon: str
    price: float
    currency: str
    price_as_of: datetime
    price_source: str
    category: str
    verdict: str
    rationale: str
    market_cap: float | None = None
    market_cap_currency: str | None = None
    catalyst_id: int | None = None
    is_main_pick: bool = False
    probability_pct: float | None = None
    bull_move_pct: float | None = None
    base_move_pct: float | None = None
    bear_move_pct: float | None = None
    bull_case: str | None = None
    base_case: str | None = None
    bear_case: str | None = None
    key_risk: str | None = None
    scores: Scores = field(default_factory=Scores)
    benchmark_symbol: str | None = None
    benchmark_price: float | None = None
    p_rocket_pct: float | None = None
    model_run_id: int | None = None
    source: str | None = None
    discovery_run_id: int | None = None
    target_move_pct: float | None = None   # cíl predikce rakety (např. +50 = max. cena aspoň +50 % v horizontu)
    p_drop_pct: float | None = None        # šance na propad (zrcadlově, např. −33 %)
    base_rate_pct: float | None = None     # kolik % všech akcií cíl historicky splnilo (srovnání s náhodou)


def record_prediction(
    conn: sqlite3.Connection,
    p: PredictionInput,
    *,
    mode: str = "LIVE",
    made_at: datetime | None = None,
    now: datetime | None = None,
) -> int:
    """Zapíše predikci. LIVE = okamžik zápisu (nelze zpětně datovat); BACKTEST = made_at v minulosti."""
    Horizon(p.horizon)
    Category(p.category)
    Verdict(p.verdict)
    now = now or utcnow()
    if mode == "LIVE":
        if made_at is not None:
            raise LedgerRuleError("§29: živou predikci nelze zpětně datovat — made_at je okamžik zápisu")
        made_at = now
    elif mode == "BACKTEST":
        if made_at is None or made_at > now:
            raise LedgerRuleError("BACKTEST vyžaduje made_at v minulosti")
    else:
        raise ValueError(f"neznámý režim {mode!r}")

    if p.price_as_of > made_at:
        raise LedgerRuleError("§59: cena z budoucnosti vůči okamžiku predikce")
    for name in ("probability_pct", "p_rocket_pct", "p_drop_pct", "base_rate_pct"):
        value = getattr(p, name)
        if value is not None and not 0 <= value <= 100:
            raise ValueError(f"{name} musí být 0–100")
    if p.target_move_pct is not None and p.target_move_pct <= 0:
        raise ValueError("target_move_pct musí být kladný (cíl růstu v %)")

    listing = get_listing(conn, p.listing_id)
    is_buy = p.verdict == Verdict.SPEC_BUY or p.is_main_pick

    # §5 — stav XTB se zapisuje vždy; jako brána jen když ji uživatel vyžaduje.
    xtb = latest_xtb_check(conn, p.listing_id, as_of=made_at)
    if is_buy and config.REQUIRE_XTB_FOR_BUY:
        if xtb is None:
            raise LedgerRuleError(f"§5: {listing['ticker']} — XTB NEOVĚŘENO, nelze vydat doporučení")
        if xtb["status"] != "ANO":
            raise LedgerRuleError(f"§5: {listing['ticker']} — STATUS = NOT AVAILABLE ON XTB "
                                  f"(poslední kontrola: {xtb['status']}), hledej alternativu")
        if xtb_check_age(xtb, made_at) > config.XTB_CHECK_MAX_AGE:
            raise LedgerRuleError(f"§5: kontrola XTB z {xtb['checked_at']} je starší než "
                                  f"{config.XTB_CHECK_MAX_AGE.days} dní — ověř znovu")

    catalyst = None
    if p.catalyst_id is not None:
        catalyst = get_catalyst(conn, p.catalyst_id)
        if catalyst["company_id"] != listing["company_id"]:
            raise LedgerRuleError("katalyzátor patří jiné firmě než listing")
        if catalyst["published_at"] > to_iso(made_at):
            raise LedgerRuleError("§59: katalyzátor byl zveřejněn až po okamžiku predikce (look-ahead bias)")
        if is_buy:
            if catalyst["status"] not in (CatalystStatus.UPCOMING, CatalystStatus.DELAYED):
                raise LedgerRuleError(f"§2: katalyzátor má stav {catalyst['status']} — hledáme firmu PŘED "
                                      "katalyzátorem, ne po něm (poučení RARE)")
            if (catalyst["date_status"] == DateStatus.VERIFIED
                    and parse_date(catalyst["event_date"]) < made_at.date()):
                raise LedgerRuleError("§2: datum katalyzátoru už uplynulo")

    s = asdict(p.scores)
    made_iso = to_iso(made_at)
    with conn:
        cur = conn.execute(
            """INSERT INTO predictions (
                mode, made_at, recorded_at, company_id, listing_id, horizon,
                price, currency, price_as_of, price_source, price_freshness, market_cap, market_cap_currency,
                catalyst_id, catalyst_text, catalyst_date_text, catalyst_date_status,
                category, verdict, is_main_pick, xtb_check_id, xtb_status, xtb_instruments,
                probability_pct, bull_move_pct, base_move_pct, bear_move_pct,
                bull_case, base_case, bear_case, key_risk, rationale,
                score_fundament, score_catalyst, score_catalyst_timing, score_upside, score_surprise,
                score_financial_health, score_valuation, score_technical, score_dilution_risk,
                score_execution_risk, score_rocket, score_overall_setup, model_version,
                benchmark_symbol, benchmark_price, p_rocket_pct, model_run_id, source, discovery_run_id,
                target_move_pct, p_drop_pct, base_rate_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mode, made_iso, made_iso if mode == "LIVE" else to_iso(now),
                listing["company_id"], p.listing_id, p.horizon,
                p.price, p.currency, to_iso(p.price_as_of), p.price_source,
                freshness(p.price_as_of, made_at), p.market_cap, p.market_cap_currency,
                p.catalyst_id,
                catalyst["description"] if catalyst else None,
                date_text(catalyst) if catalyst else None,
                catalyst["date_status"] if catalyst else None,
                p.category, p.verdict, int(p.is_main_pick),
                xtb["id"] if xtb else None,
                xtb["status"] if xtb else "NEOVERENO",
                xtb["instruments"] if xtb else None,
                p.probability_pct, p.bull_move_pct, p.base_move_pct, p.bear_move_pct,
                p.bull_case, p.base_case, p.bear_case, p.key_risk, p.rationale,
                s["fundament"], s["catalyst"], s["catalyst_timing"], s["upside"], s["surprise"],
                s["financial_health"], s["valuation"], s["technical"], s["dilution_risk"],
                s["execution_risk"], s["rocket"], s["overall_setup"], __version__,
                p.benchmark_symbol, p.benchmark_price, p.p_rocket_pct, p.model_run_id, p.source, p.discovery_run_id,
                p.target_move_pct, p.p_drop_pct, p.base_rate_pct,
            ),
        )
    return cur.lastrowid


def record_outcome(
    conn: sqlite3.Connection,
    prediction_id: int,
    *,
    horizon_days: int,
    price: float,
    price_source: str,
    observed_at: datetime,
    result: str,
    max_price: float | None = None,
    min_price: float | None = None,
    deviation: str | None = None,
    reason: str | None = None,
    lesson: str | None = None,
    benchmark_price: float | None = None,
    now: datetime | None = None,
) -> int:
    """§28/§30: vyhodnocení predikce po N dnech (typicky 7 / 14 / 30). Původní predikce se nemění.

    benchmark_price = cena benchmarku (S&P 500) ve stejný okamžik -> výnos benchmarku a nadvýnos.
    """
    OutcomeResult(result)
    pred = conn.execute("SELECT * FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
    if pred is None:
        raise LookupError(f"predikce id={prediction_id} neexistuje")
    now = now or utcnow()
    if observed_at > now:
        raise LedgerRuleError("pozorování z budoucnosti")
    due = parse_iso(pred["made_at"]) + timedelta(days=horizon_days)
    if observed_at < due:
        raise LedgerRuleError(f"předčasné vyhodnocení: +{horizon_days}d nastane až {to_iso(due)}")
    for bound in (max_price, min_price):
        if bound is not None and bound <= 0:
            raise ValueError("max/min cena musí být kladná")
    if max_price is not None and price > max_price:
        raise ValueError("cena je nad maximem období")
    if min_price is not None and price < min_price:
        raise ValueError("cena je pod minimem období")
    return_pct = round((price / pred["price"] - 1) * 100, 4)
    bench_pct = excess_pct = None
    if benchmark_price is not None:
        if not pred["benchmark_price"]:
            raise ValueError("predikce nemá cenu benchmarku — nadvýnos nelze spočítat")
        bench_pct = round((benchmark_price / pred["benchmark_price"] - 1) * 100, 4)
        excess_pct = round(return_pct - bench_pct, 4)
    with conn:
        cur = conn.execute(
            "INSERT INTO prediction_outcomes (prediction_id, horizon_days, observed_at, price, price_source,"
            " max_price, min_price, return_pct, result, deviation, reason, lesson, recorded_at,"
            " benchmark_return_pct, excess_return_pct)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (prediction_id, horizon_days, to_iso(observed_at), price, price_source, max_price, min_price,
             return_pct, result, deviation, reason, lesson, to_iso(now), bench_pct, excess_pct),
        )
    return cur.lastrowid


def register_rows(conn: sqlite3.Connection) -> list[dict]:
    """§28: řádky historického registru — predikce + výsledky +7d / +14d / +30d."""
    preds = conn.execute(
        "SELECT p.*, l.ticker, l.exchange FROM predictions p JOIN listings l ON l.id = p.listing_id"
        " ORDER BY p.made_at, p.id"
    ).fetchall()
    rows = []
    for p in preds:
        outcomes = {o["horizon_days"]: o for o in conn.execute(
            "SELECT * FROM prediction_outcomes WHERE prediction_id = ?", (p["id"],))}
        maxes = [o["max_price"] for o in outcomes.values() if o["max_price"] is not None]
        mins = [o["min_price"] for o in outcomes.values() if o["min_price"] is not None]
        last = outcomes[max(outcomes)] if outcomes else None
        rows.append({
            **dict(p),
            "price_7d": outcomes[7]["price"] if 7 in outcomes else None,
            "price_14d": outcomes[14]["price"] if 14 in outcomes else None,
            "price_30d": outcomes[30]["price"] if 30 in outcomes else None,
            "period_max": max(maxes) if maxes else None,
            "period_min": min(mins) if mins else None,
            "result": last["result"] if last else None,
        })
    return rows
