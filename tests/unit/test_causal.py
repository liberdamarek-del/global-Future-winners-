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
    heads += [{"datum": "2026-09-02", "titulek": "Cocoa prices steady", "zdroj": "Reuters"}]
    fetch = lambda q, a, b: [h for h in heads if a <= date.fromisoformat(h["datum"]) < b]
    p = events.news_pulse("COCOA", date(2026, 10, 6), fetch=fetch, pause=0)
    assert p["pribehu_7d"] >= 1 and p["pribehu_pred_mesicem"] == 1 and p["pozornost"] >= 1


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
    assert mm["smer"] == 1 and mm["dukaz"] == "EMPIRICKY_I_LOGIKA" and mm["v_cene"] is not None
    assert card["scenare"]["pripadu"] >= 4 and {"BASE", "POZITIVNI", "NEGATIVNI"} <= set(card["scenare"])
    assert res["prilezitosti"] and res["prilezitosti"][0]["firmy"][0]["ticker"] == "FCX"


def test_radar_lists_only_firms_with_own_sensitivity_to_the_commodity():
    """Obor podle Nasdaq bývá široký: největší firma oboru (loděnice, výletní lodě) nesmí vypadat jako sázka na
    komoditu, když se s ní sama nehýbe (DRYBULK → GD, RCL, VIK; 2026-10-14)."""
    from array import array
    wk = _weekly(n=200)
    for j in range(4):
        wk.comm["COPPER"][-1 - j] += 0.05
        wk.ind["metal mining"][-1 - j] += 0.02
    rng = random.Random(7)
    wk.stocks = {"FCX": array("d", [0.9 * c + rng.gauss(0, 0.01) for c in wk.comm["COPPER"]]),     # těžař mědi
                 "BIG": array("d", [rng.gauss(0, 0.01) for _ in wk.comm["COPPER"]]),               # s mědí nesouvisí
                 "INV": array("d", [-0.9 * c + rng.gauss(0, 0.01) for c in wk.comm["COPPER"]])}    # opačný směr než obor
    secs = [{"symbol": "BIG", "name": "Big Shipyard", "industry": "metal mining", "market_cap_usd": 9e10},
            {"symbol": "INV", "name": "Inverse", "industry": "metal mining", "market_cap_usd": 8e10},
            {"symbol": "FCX", "name": "Freeport", "industry": "metal mining", "market_cap_usd": 6e10},
            {"symbol": "NODATA", "name": "No data", "industry": "metal mining", "market_cap_usd": 7e10}]
    res = radar.build(build_exposure(wk), {}, date(2026, 10, 2), gdacs_links={}, pulses={}, securities=secs)
    opp = next(o for o in res["prilezitosti"] if o["obor"] == "metal mining")
    assert [f["ticker"] for f in opp["firmy"]] == ["FCX"] and opp["firmy"][0]["t"] >= 2
    assert "vlastní citlivost" in opp["firmy_pravidlo"]
    assert radar.firms(secs, "metal mining", sens=lambda s: None, sign=1) == []                 # nikdo neprošel → prázdné


def test_news_confirm_supply_scenario_only_at_major_producers():
    """Nálet na zlatý důl v Súdánu (není mezi hlavními výrobci) nesmí spustit scénář „zlato ↑“ (2026-10-15)."""
    heads = [{"datum": "2026-10-12", "titulek": f"Airstrike kills workers at Sudan gold mine {i}", "zdroj": "X"} for i in range(5)]
    fetch = lambda q, a, b: [h for h in heads if a <= date.fromisoformat(h["datum"]) < b]
    assert events.news_pulse("GOLD", date(2026, 10, 15), fetch=fetch, pause=0)["u_vyrobcu_7d"] == 0
    heads.append({"datum": "2026-10-13", "titulek": "Strike halts gold mines in Ghana", "zdroj": "Y"})
    assert events.news_pulse("GOLD", date(2026, 10, 15), fetch=fetch, pause=0)["u_vyrobcu_7d"] == 1
    wk = _weekly(n=200)                                                                 # poslední 4 týdny bez cenového šoku
    ex = build_exposure(wk)
    secs = [{"symbol": "FCX", "name": "Freeport", "industry": "metal mining", "market_cap_usd": 6e10}]
    run = lambda n_prod: radar.build(ex, {}, date(2026, 10, 2), gdacs_links={}, securities=secs, pulse_history={"COPPER": [1, 1, 1]},
                                     pulses={"COPPER": {"pribehu_7d": 6, "u_vyrobcu_7d": n_prod, "titulky": []}})
    quiet = run(0)
    assert quiet["karty"][0]["stav"].startswith("SLEDOVAT") and quiet["prilezitosti"] == []
    assert "zprávy mimo hlavní výrobce" in quiet["karty"][0]["spoustec"]
    loud = run(2)
    assert loud["karty"][0]["stav"] == "PŘÍLEŽITOST" and "zprávy" in loud["karty"][0]["spoustec"]


def test_causal_records_are_append_only_and_evaluated(tmp_path):
    conn = open_db(tmp_path / "t.db")
    wk = _weekly(n=200)
    res = {"den": date.fromordinal(wk.weeks[150]).isoformat(), "prilezitosti": [
        {"komodita": "COPPER", "obor": "metal mining", "rad": 1, "smer": 1, "horizont_dni": 28, "ocekavany_pohyb": 0.03,
         "v_cene": 0.2, "dukaz": "EMPIRICKY_I_LOGIKA", "skore": 50.0},
        {"komodita": "COPPER", "obor": "publishing", "rad": 1, "smer": 1, "horizont_dni": 28, "dukaz": "EMPIRICKY", "skore": 40.0},
        {"komodita": "COPPER", "obor": "restaurants", "rad": 3, "smer": -1, "horizont_dni": 90, "dukaz": "LOGIKA_NEOVERENO",
         "skore": 5.0}]}
    run_id = cstore.save_run(conn, res)
    assert len(cstore.save_forecasts(conn, run_id, res)) == 1                         # jen data I logika
    assert cstore.save_forecasts(conn, run_id, res) == []                              # stejný den znovu nezapíše
    done = cstore.evaluate(conn, wk)
    assert len(done) == 1 and cstore.scorecard(conn)["vyhodnoceno"] == 1
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE causal_forecasts SET direction = -1")
    assert len(cstore.config_hash()) == 16


def test_daily_shock_sees_moves_after_last_stock_day():
    """Týdenní mřížka končí posledním dnem cen akcií; skok komodity v dalších dnech musí radar vidět z denních cen."""
    from stockradar.causal.exposure import daily_shock
    from stockradar.discovery.cache import Bars
    rng = random.Random(5)
    start = date(2025, 1, 1).toordinal()
    days = list(range(start, start + 600))
    closes, p = [], 100.0
    for i in range(600):
        p *= 1 + rng.gauss(0, 0.01) + (0.03 if i >= 592 else 0.0)          # posledních 8 dní prudký růst
        closes.append(p)
    bars = Bars("HG=F", "USD", days, closes, [1.0] * 600)
    before = daily_shock(bars, days[589])                                 # „poslední den cen akcií“
    after = daily_shock(bars, days[-1])                                   # den běhu radaru
    assert after is not None and after[1] > 2.5 and after[2] == days[-1]
    assert before is None or abs(before[1]) < 2.0
    assert daily_shock(bars, days[-1] + 30) is None                        # stará data (> 5 dní) se nepoužijí


def test_verified_producer_shares_have_primary_source():
    for cid, v in CM.VERIFIED_PRODUCERS.items():
        assert cid in CM.BY_ID and v["url"].startswith("https://") and 0 < sum(v["podily"].values()) <= 1
        assert all(z in CM.BY_ID[cid]["vyrobci"] or share < 0.03 for z, share in v["podily"].items())   # ≥ 3 % je v seznamu
    assert CM.producers_status("ALUMINIUM")["stav"].startswith("OVĚŘENO") and CM.producers_status("COCOA")["stav"] == CM.NEOVERENO
    assert "IRONORE" in CM.producers_in("Floods hit iron ore mines in Iran")


def test_news_pulse_ignores_headlines_where_commodity_word_is_a_name():
    """Loď „HMM Platinum“ a kůň „Platinum Attack“ nejsou zprávy o platině (2026-10-20); název zdroje se nečte."""
    off = ["HMM Platinum firefighting winds down, all 24 crew safe - WorldCargo News",
           "Fire Aboard Brazil-Bound Ship Forces Diversion to South Africa - DatamarNews",
           "Planets align for Platinum Attack - Opie gets the reins and the forecast is good - Lincoln Farms",
           "Platinum Attack Wins G3 Sweynesse - Breednet", "Platinum jubilee fire drill at school - Mining Weekly"]
    for t in off:
        assert not events.relevant("PLATINUM", t, t.rsplit(" - ", 1)[1])
    assert events.relevant("PLATINUM", "Strike halts Sibanye platinum mines in South Africa - Reuters", "Reuters")
    assert events.relevant("USD", "Dollar index slides after Fed comments - CNBC", "CNBC")      # makro: kontext netřeba
    heads = [{"datum": f"2026-10-{15 + i}", "titulek": t, "zdroj": t.rsplit(" - ", 1)[1]} for i, t in enumerate(off)]
    fetch = lambda q, a, b: [h for h in heads if a <= date.fromisoformat(h["datum"]) < b]
    p = events.news_pulse("PLATINUM", date(2026, 10, 20), fetch=fetch, pause=0)
    assert p["pribehu_7d"] == 0 and p["u_vyrobcu_7d"] == 0 and p["mimo_tema_7d"] >= 4
    assert events.relevant("COPPER", "BHP Escondida Workers Approve Deal, Averting Copper Strike - Bloomberg.com")
    assert events.relevant("DRYBULK", "Drone attack sinks ship off Bulgaria's Black Sea coast, PM says - Al Jazeera")
    assert not events.relevant("CORN", "2 stabbed inside massive California corn maze - New York Post")
