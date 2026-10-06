"""Kauzální radar: graf komodit, citlivost bez pohledu do budoucnosti, test řetězců, události, karty, záznam (bez sítě)."""

import math
import random
import sqlite3
from datetime import date

import pytest

from stockradar.causal import chains, events, radar
from stockradar.causal import commodities as CM
from stockradar.causal import store as cstore
from stockradar.causal.exposure import Exposure, Weekly, build_exposure, rolling_beta, shock
from stockradar.db import open_db


def test_graph_links_events_to_commodities():
    assert CM.chain_for("COCOA", "packaged foods")[1] == -1               # dražší kakao škodí výrobcům čokolády
    assert CM.chain_for("BRENT", "oil & gas production")[:2] == (1, 1)
    assert CM.chain_for("BRENT", "biotechnology: biological products") is None
    assert "COCOA" in CM.match_text("Drought hits cocoa harvest in Ivory Coast")
    assert "COCOA" in CM.producers_in("Côte d'Ivoire, Ghana")
    assert "BRENT" in CM.producers_in("Attacks near the Strait of Hormuz")
    assert all(c["id"] in CM.BY_ID and c["symbol"] in CM.BY_SYMBOL for c in CM.COMMODITIES)


def test_rolling_beta_uses_only_the_past():
    rng = random.Random(1)
    x = [rng.gauss(0, 0.02) for _ in range(120)]
    y = [2.0 * a + rng.gauss(0, 0.005) for a in x]
    out = rolling_beta(y, x, window=78, min_n=52)
    assert math.isnan(out[50][0]) and out[60][0] == pytest.approx(2.0, abs=0.15) and out[60][1] > 10
    y2 = y[:100] + [-5 * a for a in x[100:]]                                # budoucí změna nesmí ovlivnit minulost
    assert rolling_beta(y2, x, window=78, min_n=52)[99] == out[99]


def _weekly(n=200, lag_effect=0.0, seed=3):
    """Komodita s občasnými šoky; obor A se hýbe s komoditou hned (a volitelně i se zpožděním), obor B je nezávislý."""
    rng = random.Random(seed)
    comm = [rng.gauss(0, 0.02) for _ in range(n)]
    for k in range(40, n, 23):
        for j in range(4):
            comm[k + j if k + j < n else n - 1] += 0.04
    a, b = [], []
    for w in range(n):
        lagged = sum(comm[w - j] for j in range(5, 9) if w - j >= 0) * lag_effect
        a.append(0.8 * comm[w] + lagged + rng.gauss(0, 0.01))
        b.append(rng.gauss(0, 0.01))
    weeks = [738000 + 7 * i for i in range(n)]
    return Weekly(weeks, {"metal mining": a, "restaurants": b}, {"COPPER": comm}, {"metal mining": 30, "restaurants": 40})


def test_chain_study_finds_planted_delay_and_not_without_it():
    ex = build_exposure(_weekly(lag_effect=0.25))
    per = {"VSE": (0, 10 ** 7)}
    res = chains.study(ex, per, log=lambda m: None)["obdobi"]["VSE"]
    assert res["soku"] > 0 and res["empiricke"]["uz_v_cene_4t"]["prumer"] > 0      # okamžitý dopad
    assert res["empiricke"]["4t"]["prumer"] > 0.02                                    # zpožděný dopad nalezen
    res0 = chains.study(build_exposure(_weekly(lag_effect=0.0)), per, log=lambda m: None)["obdobi"]["VSE"]
    assert abs(res0["empiricke"]["4t"]["prumer"]) < 0.02                              # bez zpoždění nic


def test_shock_zscore_and_wind_from_past_only():
    wk = _weekly()
    ex = build_exposure(wk)
    sh = shock(wk, "COPPER", 43)
    assert sh is not None and sh[0] > 0.1 and sh[1] > 1.5
    w4, gap = chains.wind(ex, "metal mining", wk.weeks[150], 4)
    assert w4 is not None and gap is not None
    feats = chains.CausalFeatures(ex).features("metal mining", wk.weeks[150])
    assert set(feats) == {"wind4", "wind13", "wind13_gap"}


def test_events_gdacs_and_news_pulse():
    payload = b'{"features": [{"properties": {"eventtype": "DR", "name": "Drought in Ghana", "alertlevel": "Orange",' \
              b' "country": "Ghana, Ivory Coast", "fromdate": "2026-09-01T00:00:00", "todate": "2026-10-01T00:00:00",' \
              b' "severitydata": {"severitytext": "Medium"}, "url": {"report": "https://www.gdacs.org/r"}}}]}'
    ev = events.gdacs(date(2026, 10, 6), get=lambda url: payload)
    links = events.link_gdacs(ev)
    assert "COCOA" in links and links["COCOA"][0]["vazba"].endswith("(NEOVĚŘENO)")
    assert "GOLD" not in links                                                         # sucho zlato neovlivní
    heads = [{"datum": "2026-10-04", "titulek": f"Cocoa farmers hit by drought story {i}", "zdroj": "Reuters"} for i in range(4)]
    heads += [{"datum": "2026-09-10", "titulek": "Cocoa prices steady", "zdroj": "Reuters"}]
    p = events.news_pulse("COCOA", date(2026, 10, 6), fetch=lambda q, a, b: heads, pause=0)
    assert p["pribehu_7d"] >= 1 and p["pozornost"] >= 1


def test_radar_card_has_chain_priced_ratio_and_scenarios():
    wk = _weekly(n=200)
    for j in range(4):                                                                 # čerstvý šok v posledních týdnech
        wk.comm["COPPER"][-1 - j] += 0.05
        wk.ind["metal mining"][-1 - j] += 0.02
    ex = build_exposure(wk)
    secs = [{"symbol": "FCX", "name": "Freeport", "industry": "metal mining", "market_cap_usd": 6e10}]
    res = radar.build(ex, {}, date(2026, 10, 2), gdacs_links={}, pulses={}, securities=secs)
    card = res["karty"][0]
    assert card["komodita"] == "COPPER" and "cenový šok" in card["spoustec"]
    mm = next(x for x in card["retez"] if x["obor"] == "metal mining")
    assert mm["smer"] == 1 and mm["dukaz"] in ("EMPIRICKY", "EMPIRICKY_I_LOGIKA") and mm["v_cene"] is not None
    assert card["scenare"]["pripadu"] >= 4 and {"BASE", "POZITIVNI", "NEGATIVNI"} <= set(card["scenare"])
    assert res["prilezitosti"] and res["prilezitosti"][0]["firmy"][0]["ticker"] == "FCX"


def test_causal_records_are_append_only_and_evaluated(tmp_path):
    conn = open_db(tmp_path / "t.db")
    wk = _weekly(n=200)
    res = {"den": date.fromordinal(wk.weeks[150]).isoformat(), "prilezitosti": [
        {"komodita": "COPPER", "obor": "metal mining", "rad": 1, "smer": 1, "horizont_dni": 28, "ocekavany_pohyb": 0.03,
         "v_cene": 0.2, "dukaz": "EMPIRICKY", "skore": 50.0},
        {"komodita": "COPPER", "obor": "restaurants", "rad": 3, "smer": -1, "horizont_dni": 90, "dukaz": "LOGIKA_NEOVERENO",
         "skore": 5.0}]}
    run_id = cstore.save_run(conn, res)
    assert len(cstore.save_forecasts(conn, run_id, res)) == 1                         # jen s empirickou oporou
    assert cstore.save_forecasts(conn, run_id, res) == []                              # stejný den znovu nezapíše
    done = cstore.evaluate(conn, wk)
    assert len(done) == 1 and cstore.scorecard(conn)["vyhodnoceno"] == 1
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE causal_forecasts SET direction = -1")
    assert len(cstore.config_hash()) == 16
