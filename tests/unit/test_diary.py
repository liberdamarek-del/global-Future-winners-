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
