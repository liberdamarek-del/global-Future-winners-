"""Signální engine na 14 dní: režim, cíle, kalibrace, rozhodnutí NEVÍM, zprávy, registr zamčeného testu (bez sítě)."""

import sqlite3
from datetime import date

import pytest

from stockradar.db import open_db
from stockradar.signals import card as C
from stockradar.signals import model as M
from stockradar.signals import news, panel, regime, store
from stockradar.signals.extra import Extra


def test_regime_rules():
    f = {"spy_ma200": 0.05, "spy_dd": -0.02, "spy_r5": 0.01, "vix": 14.0}
    assert regime.label_from(f) == "BÝČÍ KLIDNÝ"
    assert regime.label_from({**f, "vix": 24.0}) == "BÝČÍ VOLATILNÍ"
    assert regime.label_from({**f, "vix": 35.0}) == "ŠOK VOLATILITY"
    assert regime.label_from({**f, "spy_r5": -0.06}) == "ŠOK VOLATILITY"
    assert regime.label_from({**f, "spy_ma200": -0.04, "spy_dd": -0.15, "vix": 25.0}) == "MEDVĚDÍ"
    assert regime.label_from({**f, "spy_ma200": -0.01, "spy_dd": -0.05}) == "BEZ TRENDU"
    assert regime.earnings_season(date(2026, 4, 25).toordinal())
    assert not regime.earnings_season(date(2026, 3, 10).toordinal())


def test_targets_from_future_prices():
    c = [100.0] * 260 + [101, 102, 103, 104, 112, 106, 105, 104, 106, 106.5] + [107.0] * 130
    lab = panel.fwd_labels(c, 259)
    assert lab["fwd_10"] == pytest.approx(0.065) and lab["up5"] and not lab["down5"]
    assert lab["big"]                      # +12 % během okna = prudký pohyb
    assert lab["fwd_120"] == pytest.approx(0.07)
    assert panel.fwd_labels(c, len(c) - 3)["fwd_10"] is None   # budoucnost ještě není známá


def test_calibration_is_monotone_and_interpolated():
    preds = [i / 100 for i in range(100)] * 3
    ys = [1 if (i % 100) / 100 > 0.5 else 0 for i in range(300)]
    ys[10] = 1                              # šum v nízkém binu
    cal = M.calibrate(preds, ys)
    assert all(a <= b for a, b in zip(cal["rate"], cal["rate"][1:]))
    lo, hi = M.apply_cal(cal, 0.05), M.apply_cal(cal, 0.95)
    assert lo < 0.2 and hi > 0.8
    mid = M.apply_cal(cal, 0.5)
    assert lo <= mid <= hi


def _sm(bands_mean=0.01):
    sm = M.SignalModel([], {}, {}, {})
    sm.bands = {"edges": [0.0], "pasma": [{"pasmo": 1, "nad_oborem": -0.01, "sum": 0.01},
                                          {"pasmo": 2, "nad_oborem": bands_mean, "sum": 0.01}]}
    return sm


def test_decision_relative_to_market_and_confidence():
    base = {"up5": 0.22, "down5": 0.23}
    strong = {"up5": 0.36, "down5": 0.18, "dir": 0.18}
    assert C.decide(strong, 80, base, _sm())[0] == "RŮST"
    assert C.decide(strong, 40, base, _sm())[0] == "NEVÍM"           # nízká důvěra → NO-TRADE
    # celý trh dnes posunutý nahoru (režim) → stejná pravděpodobnost už není výjimečná
    assert C.decide(strong, 80, base, _sm(), ref={"up5": 0.33, "down5": 0.2})[0] == "NEVÍM"
    weak = {"up5": 0.25, "down5": 0.22, "dir": 0.03}
    assert C.decide(weak, 90, base, _sm())[0] == "NEVÍM"
    down = {"up5": 0.15, "down5": 0.40, "dir": -0.25}
    assert C.decide(down, 80, base, _sm())[0] == "POKLES"


def test_independent_cases_and_weekly_t():
    p = panel.SPanel(["r5"])
    for wk in range(10):
        for g in ("a", "a", "b"):
            p.add("X", 700000 + 7 * wk, g, "BÝČÍ KLIDNÝ", {"r5": 0.0}, None)
    rows = list(range(len(p)))
    assert len(rows) == 30 and M.n_independent(p, rows) == 20     # stejný týden a obor = jeden případ
    t = M.weekly_t(p, rows, [0.01 + 0.004 * ((k // 3) % 2) for k in rows])
    assert t is not None and t > 2
    assert M.p_from_t(0.0) == pytest.approx(1.0) and M.p_from_t(3.0) < 0.01


def test_news_rewrites_are_one_story_and_sources_ranked():
    heads = [
        {"datum": "2026-09-20", "titulek": "Acme wins $2 billion Pentagon contract for drones - Reuters", "zdroj": "Reuters"},
        {"datum": "2026-09-20", "titulek": "Acme wins $2 billion Pentagon drone contract - Motley Fool", "zdroj": "The Motley Fool"},
        {"datum": "2026-09-21", "titulek": "Acme wins Pentagon contract for drones worth $2 billion", "zdroj": "Benzinga"},
        {"datum": "2026-10-01", "titulek": "Acme announces CEO transition", "zdroj": "Business Wire"},
    ]
    st = news.stories(heads)
    assert len(st) == 2 and st[0]["kopii"] == 3 and st[0]["kvalita"] == 80
    a = news.assess(heads, date(2026, 10, 3))
    assert a["prepisu"] == 2 and a["novych_7d"] == 1 and a["kvalita"] == 85
    assert news.source_quality("www.sec.gov")[0] == 100 and news.source_quality("reddit")[0] == 15


def test_announcement_day_is_8k_with_largest_volume():
    class B:
        days = list(range(1000, 1200))
        volumes = [100.0] * 200
        closes = [10.0] * 200
    B.volumes[150] = 900.0                 # reakce na výsledky
    ann = Extra._ann_day(1160, [1160], [1130, 1150], B)
    assert ann == 1150


def test_locked_test_registry_is_write_once(tmp_path):
    conn = open_db(tmp_path / "t.db")
    store.record_eval(conn, "SIGNAL_14D", "abc", "LOCKED_TEST", ("2025-07-18", "2026-03-27"), {"vzorku": 5, "nezavislych": 4})
    assert store.locked_result(conn, "SIGNAL_14D", "abc")["vzorku"] == 5
    with pytest.raises(sqlite3.IntegrityError):
        store.record_eval(conn, "SIGNAL_14D", "abc", "LOCKED_TEST", ("2025-07-18", "2026-03-27"), {"vzorku": 9})
    store.record_eval(conn, "SIGNAL_14D", "abc", "VALIDATION", ("2024-07-19", "2025-06-27"), {"vzorku": 1})
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE model_evaluations SET n_samples = 0")
    assert len(store.locked_attempts(conn, "SIGNAL_14D")) == 1


def test_protocol_periods_do_not_overlap():
    days = range(date(2022, 1, 1).toordinal(), date(2026, 10, 1).toordinal())
    seq = [M.split_of(d) for d in days]
    order = [s for i, s in enumerate(seq) if s and (i == 0 or seq[i - 1] != s)]
    assert order == ["TRAIN", "VALIDATION", "LOCKED_TEST", "POST"]
    assert M.split_of(date(2024, 7, 10).toordinal()) is None          # mezera 3 týdny (cíl je 10 obchodních dní)
    assert M.share_for(date(2024, 7, 10).toordinal()) == 0
