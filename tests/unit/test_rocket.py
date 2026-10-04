"""Model raket na 6 měsíců: cíl (label), logistická regrese a vyhodnocení predikcí raket v ledgeru."""

import math
import random
from array import array
from datetime import datetime, timedelta, timezone

import pytest

from stockradar import model as m
from stockradar.companies import add_company, add_listing
from stockradar.db import open_db
from stockradar.discovery import rocket
from stockradar.ledger import PredictionInput, record_prediction
from stockradar.update import evaluate_predictions

NOW = datetime(2026, 1, 5, 21, 30, tzinfo=timezone.utc)


def test_label_needs_two_closes_over_target():
    flat = [10.0] * (rocket.HORIZON + 5)
    spike = list(flat)
    spike[5] = 20.0  # jeden chybný tick nad +50 % → není raketa
    assert rocket._label(array("d", spike), 0)[0] == 0
    real = list(flat)
    real[5] = real[6] = 16.0
    assert rocket._label(array("d", real), 0)[:2] == (1, 0)
    down = [10.0, 6.0, 6.0] + [6.0] * rocket.HORIZON
    assert rocket._label(array("d", down), 0)[1] == 1
    assert rocket._label(array("d", flat), 10) is None  # výsledek ještě není známý


def test_logistic_learns_simple_signal():
    rng = random.Random(1)
    x = [rng.gauss(0, 1) for _ in range(3000)]
    y = [1 if rng.random() < 1 / (1 + math.exp(-(2 * v - 1))) else 0 for v in x]
    b0, w = rocket.fit_logistic([x], y, l2=0.1, sweeps=10)
    assert w[0] == pytest.approx(2.0, abs=0.3) and b0 == pytest.approx(-1.0, abs=0.3)


@pytest.fixture
def conn():
    c = open_db(":memory:")
    yield c
    c.close()


def _bars(conn, symbol, closes, start):
    d = start
    for c in closes:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        conn.execute("INSERT INTO price_bars (symbol, date, close, volume, source, fetched_at) VALUES (?, ?, ?, 1, 't', 't')",
                     (symbol, d.date().isoformat(), c))
        d += timedelta(days=1)
    conn.commit()


def _rocket_prediction(conn, symbol):
    cid = add_company(conn, f"Firma {symbol}", now=NOW)
    lid = add_listing(conn, cid, symbol, "US", currency="USD", now=NOW)
    conn.execute("UPDATE listings SET yahoo_symbol = ? WHERE id = ?", (symbol, lid))
    return record_prediction(conn, PredictionInput(
        listing_id=lid, horizon="M6_PLUS", price=10.0, currency="USD", price_as_of=NOW - timedelta(hours=1),
        price_source="t", category="C", verdict="WATCH", rationale="test rakety", probability_pct=25.0,
        target_move_pct=50.0, p_drop_pct=17.0, base_rate_pct=16.0, benchmark_symbol="SPY", benchmark_price=100.0,
        source="DISCOVERY"), now=NOW)


def test_rocket_predictions_are_evaluated_against_target(conn):
    start = NOW + timedelta(days=1)
    _bars(conn, "SPY", [100.0] * 300, start)
    _bars(conn, "HIT1", [10.0] * 20 + [15.5] * 280, start)          # +55 % ve 4. týdnu
    _bars(conn, "SLOW", [11.0] * 300, start)                         # nikdy +50 %
    hit, slow = _rocket_prediction(conn, "HIT1"), _rocket_prediction(conn, "SLOW")
    u = m.Universe([], {"SPY": m.load_series(conn, "SPY")}, [], [])  # predikce jsou mimo energetický vesmír
    done = evaluate_predictions(conn, u, NOW + timedelta(days=100))
    res = {(d["prediction_id"], d["days"]): d["result"] for d in done}
    assert res[(hit, 7)] == "NEOVERENO" and res[(hit, 30)] == "HIT" and res[(hit, 90)] == "HIT"
    assert res[(slow, 90)] == "NEOVERENO"  # 6 měsíců ještě neuplynulo
    done = evaluate_predictions(conn, u, NOW + timedelta(days=200))
    res = {(d["prediction_id"], d["days"]): d["result"] for d in done}
    assert res[(slow, 180)] == "MISS" and res[(hit, 180)] == "HIT"
