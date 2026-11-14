"""Raketový deník (2026-10-13): snímek po závěru, kontrola splitu, okna 5 / 10 / 21 dní, epizody, ověřená příčina."""

import sqlite3
from datetime import date, datetime, timezone

import pytest

from stockradar.discovery import diary as D


def test_session_day_only_after_new_york_close():
    assert D.session_day(datetime(2026, 10, 13, 12, 13, tzinfo=timezone.utc)) == date(2026, 10, 12)   # úterý ráno → pondělí
    assert D.session_day(datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)) is None                  # trh obchoduje
    assert D.session_day(datetime(2026, 10, 13, 20, 47, tzinfo=timezone.utc)) == date(2026, 10, 13)   # po závěru
    assert D.session_day(datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)) == date(2026, 10, 9)      # pondělí ráno → pátek


def test_parse_snapshot_and_previous_close():
    rows = [{"symbol": "BRK/B", "lastsale": "$480.10", "netchange": "-2.10", "volume": "3,000,000", "marketCap": "1.0E12", "name": "B"},
            {"symbol": "ZZZ", "lastsale": "NA", "netchange": "", "volume": "", "marketCap": "", "name": "Z"}]
    assert D.parse_snapshot(rows) == [("BRK-B", 480.10, pytest.approx(482.20), 3_000_000.0, 1e12, "B")]


def test_merge_series_rejects_split_and_stale_data():
    days, closes, vols = [100, 101, 102], [10.0, 10.0, 10.0], [1, 1, 1]
    ok = D.merge_series(days, closes, vols, [(105, 12.0, 10.1, 5)])
    assert ok[0][-1] == 105 and ok[1][-1] == 12.0 and ok[3] is None
    split = D.merge_series(days, closes, vols, [(105, 100.0, 95.0, 5)])                       # 1:10 reverse split
    assert "split" in split[3]
    assert "mezera" in D.merge_series(days, closes, vols, [(120, 12.0, 11.0, 5)])[3]
    assert "split" in D.merge_series(days, closes, vols, [(102, 0.2, 0.21, 5)])[3]          # týž den: Yahoo 10, Nasdaq 0,2
    assert D.merge_series(days, closes, vols, [(102, 10.01, 9.9, 5)])[3] is None


def test_detect_windows_and_liquidity():
    days = list(range(30))
    closes = [10.0] * 25 + [10.5, 11.0, 12.0, 13.0, 13.5]                                     # +35 % za 5 dní
    vols = [200_000.0] * 30
    hit = D.detect(days, closes, vols)
    assert hit["okna"] == ["5d"] and hit["moves"]["5d"] == pytest.approx(0.35) and hit["start"] == days[-6]
    assert D.detect(days, closes, [1_000.0] * 30) is None                                       # nelikvidní
    assert D.detect(days, [0.5] * 25 + [0.6, 0.7, 0.8, 0.9, 0.95], vols) is None               # cena pod 1 USD


def test_episode_is_recorded_once_and_cause_needs_primary_source(conn):
    found = [{"symbol": "ABC", "nazev": "Abc", "mcap": 5e8, "okna": ["5d"], "moves": {"5d": 0.4, "10d": 0.4, "21d": 0.4},
              "start": date(2026, 10, 5).toordinal(), "end": date(2026, 10, 12).toordinal(), "cena": 5.0, "obrat": 2e6}]
    auto = lambda name, t0, end, symbol: {"stav": "AUTO", "kod": "FDA", "hlavni_pricina": "regulatorní schválení", "titulky": []}
    new = D.record_new(conn, found, today=date(2026, 10, 13), auto=auto, log=lambda m: None)
    assert len(new) == 1 and new[0]["auto"]["kod"] == "FDA"
    again = dict(found[0], end=date(2026, 10, 14).toordinal())                                   # stejná epizoda o 2 dny později
    assert D.record_new(conn, [again], today=date(2026, 10, 15), log=lambda m: None) == []
    eid = new[0]["id"]
    with pytest.raises(ValueError):
        D.record_cause(conn, eid, code="NEZNAMY", status="OVĚŘENO", summary="x", source="y", source_url="https://a", published_on="2026-10-12")
    with pytest.raises(sqlite3.IntegrityError):
        D.record_cause(conn, eid, code="FDA", status="OVĚŘENO", summary="x", source="y", source_url="http://a", published_on="2026-10-12")
    D.record_cause(conn, eid, code="FDA", status="OVĚŘENO", summary="FAKT: FDA schválila lék", source="FDA",
                   source_url="https://www.fda.gov/x", published_on="2026-10-12", scheduled=True, pre_signals="PDUFA datum známé")
    r = D.recent(conn, today=date(2026, 10, 13))
    assert r[0]["pricina"]["cause_code"] == "FDA" and r[0]["pricina"]["scheduled"] == 1
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("UPDATE rocket_events SET price = 1")


def test_snapshot_skips_holiday_with_unchanged_prices():
    c = sqlite3.connect(":memory:")
    rows = [{"symbol": f"S{i}", "lastsale": f"${10 + i}", "netchange": "0.5", "volume": "1000", "marketCap": "1", "name": "x"}
            for i in range(50)]
    first = D.take_snapshot(c, now=datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc), fetch=lambda: rows, log=lambda m: None)
    assert first["stav"] == "OK" and first["den"] == "2026-10-12"
    same = D.take_snapshot(c, now=datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc), fetch=lambda: rows, log=lambda m: None)
    assert same["stav"] == "PŘESKOČENO"                                                            # svátek: stejné ceny
    assert D.take_snapshot(c, now=datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc), fetch=lambda: rows)["stav"] == "PŘESKOČENO"


def test_snapshot_source_refusal_is_recorded_not_raised():
    """10. 11. 2026: screener vrátil HTTP 403 a `rakety` spadl celý. Výpadek zdroje se zapíše a deník běží dál."""
    import urllib.error
    c = sqlite3.connect(":memory:")
    when = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)

    def refused():
        raise urllib.error.HTTPError("https://api.nasdaq.com/x", 403, "Forbidden", None, None)

    res = D.take_snapshot(c, now=when, fetch=refused, log=lambda m: None)
    assert res["stav"] == "BLOKOVÁNO" and "403" in res["duvod"]
    res = D.take_snapshot(c, now=when, fetch=lambda: (_ for _ in ()).throw(urllib.error.URLError("timeout")), log=lambda m: None)
    assert res["stav"] == "CHYBA" and "URLError" in res["duvod"]
    assert c.execute("SELECT COUNT(*) FROM nasdaq_snap").fetchone()[0] == 0


def test_hub_shows_rockets_as_context_but_not_data_errors(conn):
    from stockradar.hub import evidence as E
    found = [{"symbol": s, "nazev": s, "mcap": 1e8, "okna": ["5d"], "moves": {"5d": 0.5, "10d": 0.5, "21d": 0.5},
              "start": date(2026, 10, 5).toordinal(), "end": date(2026, 10, 12).toordinal(), "cena": 5.0, "obrat": 2e6}
             for s in ("REAL", "FAKE")]
    new = D.record_new(conn, found, today=date(2026, 10, 13), log=lambda m: None)
    fake = next(r["id"] for r in new if r["symbol"] == "FAKE")
    D.record_cause(conn, fake, code="CHYBA_DAT", status="OVĚŘENO", summary="zpětný split", source="PR",
                   source_url="https://x.example", published_on="2026-09-30")
    ev = E.from_rocket_diary(conn, date(2026, 10, 13))
    assert [e["entita"] for e in ev] == ["REAL"] and ev[0]["druh"] == "kontext" and ev[0]["smer"] == 0


def test_partly_adjusted_split_is_a_data_error_not_a_rocket():
    vwav = [11.52, 9.16, 9.7, 9.34, 9.06, 0.53, 0.38, 7.32, 5.26, 6.2, 6.21, 5.72, 5.79, 4.87, 4.57, 4.16, 4.42]
    assert D.glitch(vwav)
    assert not D.glitch([10.0, 9.0, 1.5, 1.4, 1.6, 1.7, 1.5])                                   # skutečný pád bez návratu
    assert not D.glitch([1.0, 1.1, 1.3, 2.0, 3.1, 4.5, 4.0])                                    # skutečná raketa


def test_one_day_dip_in_the_window_anchor_is_not_a_rocket():
    """STFS 2026-10-21: 21denní okno začínalo jednodenním propadem 3,62 → 2,90 → 3,66 USD; „+51 %“ bylo jen z kotvy."""
    days = list(range(30))
    vols = [2_000_000.0] * 30
    closes = [3.6] * 7 + [3.62, 2.90, 3.66] + [3.7] * 15 + [3.9, 4.0, 4.1, 4.2, 4.37]
    assert D.detect(days, closes, vols) is None                                                 # proti 3,62 jen +21 %
    assert D.anchor(closes, 29, 21) == pytest.approx(3.62)
    real = [3.6] * 8 + [3.6, 3.6] + [3.7] * 15 + [4.2, 4.6, 5.0, 5.3, 5.6]                      # skutečná raketa +56 %
    assert "21d" in D.detect(days, real, vols)["okna"]
    jump = [5.0] * 29 + [6.5]                                                                    # skok za den dál proti včerejšku
    assert "1d" in D.detect(days, jump, vols)["okna"] and D.anchor(jump, 29, 1) == 5.0


def test_merge_series_rejects_new_security_under_same_ticker():
    """SUPN 2026-11-03: po fúzi s Indivior nese ticker SUPN nová firma (výměna 1,5401 nové akcie za starou); snímek
    nemá předchozí závěr, takže kontrola splitu mlčí a v datech vznikl falešný propad −33 %."""
    days, closes, vols = [100, 101, 102], [41.8, 41.9, 41.92], [1, 1, 1]
    snaps = [(102, 41.92, 41.84, 5, "Supernus Pharmaceuticals Inc. Common Stock"),
             (106, 28.15, None, 9, "Supernus Inc. Common Stock")]
    problem = D.merge_series(days, closes, vols, snaps)[3]
    assert problem and "jiný cenný papír" in problem
    # jen jiný zápis názvu (tečka, „Class A“) při běžném pohybu není problém
    same = [(102, 41.92, 41.84, 5, "Supernus Pharmaceuticals Inc. Common Stock"),
            (106, 43.0, 41.92, 9, "Supernus Pharmaceuticals Inc Common Stock")]
    assert D.merge_series(days, closes, vols, same)[3] is None
    # přejmenování bez skoku ceny řadu nezahodí (stejný cenný papír)
    renamed = [(102, 41.92, 41.84, 5, "Old Name Corp Common Stock"), (106, 42.5, None, 9, "New Name Inc. Common Stock")]
    assert D.merge_series(days, closes, vols, renamed)[3] is None
    # starší snímky bez názvu (4 pole) fungují jako dřív
    assert D.merge_series(days, closes, vols, [(106, 43.0, 41.92, 9)])[3] is None


def test_snapshot_lag_counts_trading_days_without_valid_snapshot(conn):
    """5.–6. 11. 2026: API screeneru vracelo zamrzlé ceny z 5. 11., snímky se správně neukládaly — nově to hlásí
    přehled zdrojů i diag (počet obchodních dní podle SPY bez platného snímku)."""
    cache = sqlite3.connect(":memory:")
    assert D.snapshot_lag(conn, cache)["stav"] == "ROZPRACOVÁNO"            # bez cen SPY nelze posoudit
    for d in ("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"):
        conn.execute("INSERT INTO price_bars (symbol, date, close, volume, source, fetched_at) VALUES ('SPY', ?, 600, 1, 'test', ?)",
                     (d, d + "T22:00:00Z"))
    cache.execute("INSERT INTO nasdaq_snap (day, symbol, close, prev_close, volume, mcap, name, fetched_at)"
                  " VALUES ('2026-11-04', 'AAA', 10, 9.9, 1, 1, 'A', '2026-11-05T13:20:00Z')")
    lag = D.snapshot_lag(conn, cache)
    assert (lag["posledni"], lag["obchodni_den"], lag["chybi"], lag["stav"]) == ("2026-11-04", "2026-11-06", 2, "VAROVÁNÍ")
    cache.execute("INSERT INTO nasdaq_snap (day, symbol, close, prev_close, volume, mcap, name, fetched_at)"
                  " VALUES ('2026-11-05', 'AAA', 10, 9.9, 1, 1, 'A', '2026-11-06T13:20:00Z')")
    assert D.snapshot_lag(conn, cache)["stav"] == "OK"                      # jeden den = ranní snímek ještě nepřišel
    cache.execute("DELETE FROM nasdaq_snap")
    cache.execute("INSERT INTO nasdaq_snap (day, symbol, close, prev_close, volume, mcap, name, fetched_at)"
                  " VALUES ('2026-10-30', 'AAA', 10, 9.9, 1, 1, 'A', '2026-11-01T13:20:00Z')")
    assert D.snapshot_lag(conn, cache)["stav"] == "CHYBA"                   # 5 obchodních dní bez snímku


# ------------------------------------------------------------------ N-25 (v0.17.17): záloha snímku z Yahoo spark

def test_parse_spark_reads_closes_per_symbol():
    from stockradar.sources import yahoo
    resp = lambda sym, closes: {"symbol": sym, "response": [{"meta": {"exchangeTimezoneName": "America/New_York",
                                "gmtoffset": -18000}, "timestamp": [1793975400, 1794234600, 1794321000],   # 6., 9., 10. 11.
                                "indicators": {"quote": [{"close": closes}]}}]}
    out = yahoo.parse_spark({"spark": {"result": [resp("AAA", [10.0, None, 12.0]), resp("BBB", [5.0, 5.5, 6.0])]}})
    assert out["AAA"] == [("2026-11-06", 10.0), ("2026-11-10", 12.0)]
    assert [d for d, _ in out["BBB"]] == ["2026-11-06", "2026-11-09", "2026-11-10"]


def _snap_db(day="2026-11-06", n=30):
    c = sqlite3.connect(":memory:")
    c.executescript(D.SNAP_SCHEMA)
    c.executemany("INSERT INTO nasdaq_snap VALUES (?, ?, ?, ?, ?, ?, ?, 'x')",
                  [(day, f"S{i}", 10.0 + i, 10.0 + i, 1e6, 1e8, f"Firma {i}") for i in range(n)])
    return c


def test_fallback_snapshot_fills_missing_days_only_when_it_matches_reference():
    c = _snap_db()
    when = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)                     # před otevřením v New Yorku
    spark = {f"S{i}": [("2026-11-06", 10.0 + i), ("2026-11-09", 11.0 + i), ("2026-11-10", 12.0 + i)] for i in range(30)}
    ref = {f"S{i}": {"2026-11-09": 11.0 + i, "2026-11-10": 12.0 + i} for i in range(5)}
    calls = []
    fetch = lambda syms: (calls.append(len(syms)), {s: spark[s] for s in syms})[1]
    assert D.fallback_snapshot(c, {k: {"2026-11-09": v["2026-11-09"]} for k, v in ref.items()}, now=when, fetch=fetch,
                               pause=0, log=lambda m: None)["stav"] == "NEPOTŘEBA"   # 1 chybějící den < 2
    res = D.fallback_snapshot(c, ref, now=when, fetch=fetch, pause=0, log=lambda m: None)
    assert res["stav"] == "OK" and [x["den"] for x in res["dny"]] == ["2026-11-09", "2026-11-10"] and calls == [20, 10]
    row = c.execute("SELECT close, prev_close, volume, name FROM nasdaq_snap WHERE day = '2026-11-10' AND symbol = 'S3'").fetchone()
    assert row == (15.0, 14.0, None, "Firma 3")                                   # objem NULL = záložní snímek
    c2 = _snap_db()
    bad = {k: {"2026-11-09": v["2026-11-09"] * 1.05, "2026-11-10": v["2026-11-10"]} for k, v in ref.items()}
    res = D.fallback_snapshot(c2, bad, now=when, fetch=fetch, pause=0, log=lambda m: None)
    assert [x["den"] for x in res["dny"]] == ["2026-11-10"]                       # 9. 11. nesedí → neuložen
    assert D.fallback_snapshot(c2, ref, now=datetime(2026, 11, 11, 16, 0, tzinfo=timezone.utc), fetch=fetch,
                               pause=0)["stav"] == "PŘESKOČENO"                    # během obchodování ne


def test_with_fallback_uses_one_missing_day_when_screener_refuses():
    c = _snap_db(day="2026-11-09")
    when = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
    ref = {f"S{i}": {"2026-11-10": 12.0 + i} for i in range(5)}
    spark = lambda syms: {s: [("2026-11-09", 10.0), ("2026-11-10", 12.0 + int(s[1:]))] for s in syms}
    assert D.with_fallback(c, {"stav": "OK"}, ref, now=when, spark=spark) == {"stav": "OK"}
    stale = D.with_fallback(c, {"stav": "NEOVĚŘENO"}, ref, now=when, spark=spark, log=lambda m: None)
    assert stale["zaloha"]["stav"] == "NEPOTŘEBA"                                 # zastaralé ceny: až od 2 dní
    res = D.with_fallback(c, {"stav": "BLOKOVÁNO"}, ref, now=when, spark=spark, log=lambda m: None)
    assert res["stav"] == "BLOKOVÁNO" and res["zaloha"]["stav"] == "OK"           # odmítnutí: už od 1 dne


def test_merge_series_without_volume_skips_split_check_conservatively():
    days, closes, vols = list(range(1, 41)), [10.0] * 40, [1000.0] * 40
    d, c, v, problem = D.merge_series(days, closes, vols, [(41, 11.0, 10.0, None, "x")])
    assert problem is None and v[-1] == 1000.0                                    # neutrální objem, ne 0
    *_, problem = D.merge_series(days, closes, vols, [(41, 30.0, 10.0, None, "x")])
    assert problem and "bez údaje o objemu" in problem                            # skok 3× bez objemu = možný split


# ------------------------------------------------------------------ N-28 (v0.17.20): nácvik záložní cesty

def test_drill_fallback_checks_format_and_match_without_saving():
    ref = {f"S{c}": {"2026-11-12": 10.0, "2026-11-13": 11.0} for c in "ABCDEFG"}
    ok = D.drill_fallback(ref, fetch=lambda syms: {s: [("2026-11-12", 10.0), ("2026-11-13", 11.0)] for s in syms})
    assert ok["stav"] == "OK" and ok["shoda"] == "7/7"
    bad = D.drill_fallback(ref, fetch=lambda syms: {s: [("2026-11-13", 13.0)] for s in syms})
    assert bad["stav"] == "CHYBA"                                                 # ceny nesedí
    changed = D.drill_fallback(ref, fetch=lambda syms: {})
    assert changed["stav"] == "CHYBA" and "0 z 7" in changed["duvod"]             # změněný formát odpovědi
    import urllib.error
    def refused(syms):
        raise urllib.error.HTTPError("https://query1.finance.yahoo.com/x", 429, "Too Many", None, None)
    assert D.drill_fallback(ref, fetch=refused)["stav"] == "CHYBA"
    assert D.drill_fallback({}, fetch=refused)["stav"] == "PŘESKOČENO"


def test_fallback_days_counts_days_without_volume():
    c = _snap_db(day="2026-11-06")                                                # screener: objem vyplněn
    c.executemany("INSERT INTO nasdaq_snap VALUES (?, ?, 1, 1, NULL, NULL, NULL, 'x')",
                  [(d, f"S{i}") for d in ("2026-11-09", "2026-11-10") for i in range(3)])
    assert D.fallback_days(c, today=date(2026, 11, 14)) == 2
