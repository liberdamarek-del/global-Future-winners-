import math

from stockradar import model as m


def test_ranks_handle_ties_and_missing():
    r = m.ranks({"a": 1.0, "b": 2.0, "c": 2.0, "d": None})
    assert r["d"] == 0.5
    assert r["b"] == r["c"] > r["a"]
    assert 0 < r["a"] < 1


def test_composite_is_bounded_and_ordered():
    fr = {f: {"lo": 0.0, "hi": 1.0} for f in m.FACTORS}
    weights = {f: 0.0 for f in m.FACTORS} | {"mom_120": 1.0}
    s = m.composite(fr, weights)
    assert s["hi"] == 100 and s["lo"] == 0


def _series(n, start=10.0, step=0.01, volume=1000.0):
    days = [f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]
    closes = [start * (1 + step) ** i for i in range(n)]
    return m.Series(days, closes, [volume] * n)


def test_price_factors_need_enough_history():
    s = _series(130)
    f = m.price_factors(s, 129, usd_rate=1.0)
    assert math.isclose(f["mom_120"], 1.01 ** 120 - 1, rel_tol=1e-9)
    assert f["ext_50"] > 0 and f["dd_252"] == 0.0
    assert f["small_size"] < 0
    short = m.price_factors(_series(30), 29, usd_rate=1.0)
    assert short["mom_120"] is None and short["ext_50"] is None and short["small_size"] is None


def test_event_factors_respect_publication_dates():
    u = m.Universe(members=[], series={}, catalysts=[
        {"company_id": 1, "status": "UPCOMING", "published_at": "2026-09-10T00:00:00Z", "date_status": "VERIFIED",
         "event_date": "2026-10-10", "window_start": None, "window_end": None}],
        relationships=[{"company_id": 1, "counterparty": "Google", "announced_on": "2026-09-01"},
                       {"company_id": 1, "counterparty": "US DOE", "announced_on": "2020-01-01"}])
    assert m.event_factors(u, 1, "2026-08-25", live=False) == {"bigtech": 0.0, "catalyst_45": 0.0}
    # dohoda už známá, katalyzátor ještě nezveřejněn -> nesmí se použít (look-ahead, §59)
    assert m.event_factors(u, 1, "2026-09-05", live=False) == {"bigtech": 1.0, "catalyst_45": 0.0}
    assert m.event_factors(u, 1, "2026-09-15", live=False) == {"bigtech": 1.0, "catalyst_45": 1.0}
    assert m.event_factors(u, 1, "2027-10-15", live=False)["bigtech"] == 0.5


def _panel(signal: bool, n_dates=60, n_names=20):
    panel = []
    for d in range(n_dates):
        raw = {f: {f"S{i}": float((i * 7 + d) % n_names) for i in range(n_names)} for f in m.FACTORS}
        excess = {f"S{i}": (raw["mom_120"][f"S{i}"] / 100 if signal else ((i * 13 + d * 5) % n_names - 10) / 100)
                  for i in range(n_names)}
        panel.append(m.PanelDate(f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}", raw, dict(excess), excess))
    return panel


def test_learning_moves_weight_toward_evidence():
    w_signal, met = m.learn(_panel(True), as_of="2026-03-31")
    assert met["mom_120"]["ic"] > 0.99
    assert w_signal["mom_120"] > m.FACTORS["mom_120"]["prior"]
    assert 0 < met["mom_120"]["data_weight"] < 1


def test_calibration_and_out_of_sample():
    panel = _panel(True)
    weights, _ = m.learn(panel, as_of="2026-03-31")
    cal = m.calibrate(panel, weights)
    assert sum(b["n"] for b in cal) == 60 * 20
    assert all(0 < b["p_beat"] < 1 for b in cal)
    assert m.bin_for(99.9, cal)["do"] == 101
    assert "poznamka" in m.out_of_sample(panel[:30])
    assert m.out_of_sample(panel)["ic"] is not None
