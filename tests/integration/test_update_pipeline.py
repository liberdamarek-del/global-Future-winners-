"""Integrace: UPDATE nad syntetickými daty (bez sítě) — predikce, vyhodnocení po 30 dnech, učení, web."""

import json
import random
from datetime import date, datetime, timedelta, timezone

import pytest

from stockradar import update
from stockradar.db import open_db
from stockradar.sources.yahoo import Quote
from stockradar.update import run_update


def business_days(end: date, n: int) -> list[str]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out[::-1]


def make_fetch(end: date):
    def fetch(symbol: str, range_: str) -> Quote:
        rng = random.Random(symbol)
        days = business_days(end, 800)
        price, bars = 10.0 + rng.random() * 50, []
        drift = (rng.random() - 0.4) / 500
        for day in days:
            price *= 1 + drift + rng.gauss(0, 0.02)
            bars.append((day, round(max(price, 0.5), 4), 1e5 + rng.random() * 1e6))
        fx = symbol.endswith("=X")
        return Quote(symbol, None if fx else "USD", "TEST", symbol, bars[-1][1],
                     datetime.fromisoformat(days[-1]).replace(hour=20, tzinfo=timezone.utc), bars)
    return fetch


@pytest.fixture
def conn():
    c = open_db(":memory:")
    yield c
    c.close()


def test_update_creates_predictions_then_evaluates_them(conn, tmp_path, monkeypatch):
    # Náhodná data nemají signál — prahy snížíme, aby vznikly predikce k vyhodnocení.
    monkeypatch.setattr(update, "MIN_SCORE", 0.0)
    monkeypatch.setattr(update, "MIN_P_BEAT", 0.0)
    t0 = datetime(2026, 10, 2, 21, 30, tzinfo=timezone.utc)
    r1 = run_update(conn, state_dir=tmp_path / "state", web_dir=tmp_path / "web", now=t0, fetch=make_fetch(t0.date()))
    assert r1["run_id"] == 1 and r1["version_changed"]
    assert r1["steps"]["Ceny (Yahoo)"].startswith("DONE")
    assert conn.execute("SELECT COUNT(*) FROM chain_nodes").fetchone()[0] == 11
    n_pred = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    assert n_pred == len(r1["created"]) == 5

    # Druhý běh týž den: žádné duplicitní predikce stejné firmy do 30 dní.
    r2 = run_update(conn, state_dir=tmp_path / "state", web_dir=tmp_path / "web", now=t0 + timedelta(hours=1),
                    fetch=make_fetch(t0.date()))
    assert r2["created"] == []

    docs = {n: json.loads((tmp_path / "web" / f"stav_{n}.json").read_text()) for n in ("aktualni", "predikce", "retezec")}
    assert docs["aktualni"]["kroky"]["Data pro web"] == "DONE"
    assert len(docs["aktualni"]["vsechny"]) == 46
    assert len(docs["retezec"]["dohody"]) == 22
    assert len(docs["predikce"]["predikce"]) == n_pred

    t1 = t0 + timedelta(days=31)
    r3 = run_update(conn, state_dir=tmp_path / "state", web_dir=tmp_path / "web", now=t1,
                    fetch=make_fetch(t1.date()))
    outcomes = conn.execute("SELECT * FROM prediction_outcomes").fetchall()
    assert {o["horizon_days"] for o in outcomes} == {7, 14, 30}
    assert len(outcomes) == 3 * n_pred == len(r3["evaluated"])
    for o in outcomes:
        assert o["excess_return_pct"] == pytest.approx(o["return_pct"] - o["benchmark_return_pct"], abs=1e-3)
        assert o["result"] == ("HIT" if o["excess_return_pct"] > 0 else "MISS")
    acc = json.loads((tmp_path / "web" / "stav_aktualni.json").read_text())["presnost"]
    assert acc[2]["dni"] == 30 and acc[2]["vyhodnoceno"] == n_pred
    # Po 30 dnech může model predikovat stejné firmy znovu.
    assert len(r3["created"]) > 0


def test_update_survives_partial_price_failures(conn, tmp_path):
    t0 = datetime(2026, 10, 2, 21, 30, tzinfo=timezone.utc)
    good = make_fetch(t0.date())

    def flaky(symbol, range_):
        if symbol in ("GFUZ", "RR.L"):
            raise RuntimeError("HTTP 429")
        return good(symbol, range_)

    r = run_update(conn, state_dir=tmp_path / "state", web_dir=None, now=t0, fetch=flaky)
    assert r["steps"]["Ceny (Yahoo)"].startswith("DONE")
    assert any("GFUZ" in w for w in r["warnings"])
    assert r["run_id"] is not None
