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


def test_14d_config_is_frozen_after_locked_test():
    # zamčený test SIGNAL_14D proběhl s touto konfigurací (2026-10-05); jakákoli změna = nový pokus → vědomě a v CHANGELOG
    assert M.config_hash(list(panel.MODEL_FEATURES)) == "a1b0f2e61e6c56cc"
    assert M.config_hash(list(panel.MODEL_FEATURES), "SIGNAL_1M") != "a1b0f2e61e6c56cc"


def test_one_month_view_and_purged_splits():
    c = [100.0] * 260 + [100 + 1.05 * i for i in range(1, 21)] + [121.0] * 130
    lab = panel.fwd_labels(c, 259)
    assert lab["up10_20"] and not lab["down10_20"] and lab["big20_20"]          # +21 % za 20 dní
    p = panel.SPanel(["r5"])
    p.add("X", 738000, "a", "BÝČÍ KLIDNÝ", {"r5": 0.0}, {**lab, "ex_sec_20": 0.03, "beat_sec_20": True})
    v = M.view(p, "SIGNAL_1M")
    assert v.y["up5"][0] == 1 and v.main_h == 20 and v.ex_sec[0] == pytest.approx(0.03) and len(v) == 1
    assert M.view(p, "SIGNAL_14D") is p
    # 1 měsíc: delší mezera před dalším obdobím, aby se cíle (20 obchodních dní) nepřekrývaly
    assert M.split_of(date(2024, 6, 28).toordinal()) == "TRAIN"
    assert M.split_of(date(2024, 6, 28).toordinal(), 33) is None
    assert M.split_of(date(2024, 6, 10).toordinal(), 33) == "TRAIN"
    assert M.split_of(date(2026, 3, 27).toordinal(), 33) is None
    assert M.split_of(date(2025, 8, 1).toordinal(), 33) == "LOCKED_TEST"


def test_ranking_rule_from_validation():
    from stockradar.signals import run
    mk = lambda t, up, dn, raw: {"t": t, "pred": {"up5": up, "down5": dn, "dir": up - dn, "raw": {"up5": raw}}}
    live = [mk("VOLATILE", 0.318, 0.31, 0.60), mk("CALM", 0.318, 0.20, 0.40), mk("DOWN", 0.30, 0.35, 0.90),
            mk("LOWER", 0.29, 0.10, 0.35)]
    order = [x["t"] for x in sorted(live, key=run.rank_key, reverse=True)]
    # stejná šance na růst → přednost menšímu riziku poklesu; víc poklesu než růstu → na konec
    assert order == ["CALM", "VOLATILE", "LOWER", "DOWN"]


def test_six_month_model_labels_splits_and_frozen_neighbours():
    c = [100.0] * 260 + [100 + 0.4 * i for i in range(1, 127)] + [150.0] * 10
    lab = panel.fwd_labels(c, 259)
    assert lab["up40_126"] and not lab["down25_126"] and lab["big50_126"]           # +50 % za půl roku
    # mezera ~půl roku mezi obdobími, bez POST (výsledky po testu ještě nejsou známé)
    assert M.split_of(date(2024, 1, 10).toordinal(), 185, False) == "TRAIN"
    assert M.split_of(date(2024, 3, 1).toordinal(), 185, False) is None
    assert M.split_of(date(2025, 3, 1).toordinal(), 185, False) is None
    assert M.split_of(date(2026, 3, 20).toordinal(), 185, False) == "LOCKED_TEST"
    assert M.split_of(date(2026, 6, 1).toordinal(), 185, False) is None
    assert set(panel.BASE_FEATURES) <= set(M.features_of("SIGNAL_6M"))
    assert not set(panel.CAUSAL_FEATURES) & set(M.features_of("SIGNAL_1M"))
    # model na 1 měsíc má stále stejný otisk (jeho zamčený test už proběhl)
    assert M.config_hash(list(panel.MODEL_FEATURES), "SIGNAL_1M") == "bbe4e6a6613a4812"


def test_base_pattern_features():
    c = [100.0] * 60 + [80.0 if i % 25 == 0 else 86.0 for i in range(140)]     # 3 měsíce do strany, support 80 USD
    f = panel.base_features(c, len(c) - 1)
    assert f["support_tests"] >= 5 and f["range63"] < 0.1 and f["dist_low126"] == pytest.approx(0.075)
