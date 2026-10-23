"""v0.17.0 (zadání uživatele 2026-10-23): propady a jednodenní skoky v deníku, podání u SEC, co následovalo,
historická studie a denní přehled trhu a sektorů. Bez sítě."""

import json
import sqlite3
from datetime import date, timedelta

import pytest

from stockradar.discovery import cache as dcache
from stockradar.discovery import diary as D
from stockradar.discovery import market_day as MD
from stockradar.discovery import moves as M
from stockradar.signals.regime import Series

QUIET = lambda m: None  # noqa: E731


def bdays(start: date, n: int) -> list[int]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.toordinal())
        d += timedelta(days=1)
    return out


def store(cconn, symbol, days, closes, vol=200_000.0):
    dcache.store_series(cconn, symbol, "USD", [(date.fromordinal(d).isoformat(), c, vol) for d, c in zip(days, closes)],
                        source="test", fetched_at="2026-10-23T00:00:00Z")


def test_one_day_jump_and_drop_windows():
    days = list(range(30))
    vols = [200_000.0] * 29 + [2_000_000.0]
    up = D.detect(days, [10.0] * 29 + [13.0], vols)
    assert up["okna"] == ["1d", "5d"] and up["start"] == days[-6] and up["smer"] == 1 and up["rel_objem"] == pytest.approx(10)
    down = D.detect(days, [10.0] * 29 + [7.5], vols, -1)
    assert down["okna"] == ["1d", "5d"] and down["moves"]["1d"] == pytest.approx(-0.25) and down["smer"] == -1
    assert D.detect(days, [10.0] * 29 + [7.5], vols) is None                         # propad není raketa
    assert D.detect(days, [0.9] * 29 + [0.6], [5_000_000.0] * 30, -1) is None        # propad z ceny pod 1 USD
    assert D.detect(days, [10.0] * 29 + [8.5], vols, -1) is None                     # −15 % je pod prahem
    assert D.strength(up) == pytest.approx(D.strength({"okna": ["1d"], "moves": {"1d": 1 / 1.3 - 1}}))


def _found(sym, direction, end, move=0.4):
    key = "1d" if direction > 0 else "5d"
    return {"symbol": sym, "nazev": sym, "mcap": 5e8, "smer": direction, "okna": [key],
            "moves": {"1d": move if direction > 0 else -0.1, "5d": move * direction, "10d": None, "21d": None},
            "start": (end - timedelta(days=7)).toordinal(), "end": end.toordinal(), "cena": 5.0, "obrat": 2e6, "rel_objem": 6.0}


def test_rocket_then_drop_are_two_episodes(conn):
    end = date(2026, 10, 12)
    assert len(D.record_new(conn, [_found("ABC", 1, end)], today=end, log=QUIET)) == 1
    new = D.record_new(conn, [_found("ABC", -1, end + timedelta(days=3)), _found("ABC", 1, end + timedelta(days=3))],
                       today=end, log=QUIET)
    assert [r["smer"] for r in new] == [-1]                                           # raketa už je, propad je nový příběh
    row = conn.execute("SELECT direction, move_1d, rel_volume FROM rocket_events WHERE direction = -1").fetchone()
    assert tuple(row) == (-1, -0.1, 6.0)


def test_sec_cause_reads_form_type_not_content():
    earn = {"form": "8-K", "items": "2.02,9.01", "datum": "2026-10-20", "url": "https://www.sec.gov/a"}
    offer = {"form": "424B5", "items": "", "datum": "2026-10-21", "url": "https://www.sec.gov/b"}
    other = {"form": "8-K", "items": "8.01", "datum": "2026-10-21", "url": "https://www.sec.gov/c"}
    assert M.describe(earn) == "8-K: výsledky hospodaření" and M.describe(offer) == "prospekt emise"
    assert M.sec_cause([earn, offer], 1)["kod"] == "EARNINGS"                         # raketa: výsledky před emisí
    assert M.sec_cause([earn, offer], -1)["kod"] == "FINANCING"                       # propad: emise je typický spouštěč
    assert M.sec_cause([other], 1) is None                                            # „jiná událost“ nic neříká
    assert M.sec_cause([{"form": "8-K", "items": "3.01", "datum": "x", "url": "u"}], -1)["kod"] == "DELISTING"


def _payload(rows):
    keys = ("accessionNumber", "filingDate", "acceptanceDateTime", "form", "items", "primaryDocument", "primaryDocDescription")
    return {"filings": {"recent": {k: [r.get(k) for r in rows] for k in keys}}}


def test_attach_sec_one_request_per_move(conn):
    cconn = dcache.connect(":memory:")
    cconn.execute("INSERT INTO sec_tickers VALUES ('ABC', 123, 'Abc', 'x')")
    end = date(2026, 10, 12)
    D.record_new(conn, [_found("ABC", 1, end), _found("ZZZ", 1, end)], today=end, log=QUIET)
    calls = []

    def fetch(cik):
        calls.append(cik)
        return _payload([
            {"accessionNumber": "0001-26-1", "filingDate": "2026-10-09", "form": "8-K", "items": "2.02,9.01", "primaryDocument": "a.htm"},
            {"accessionNumber": "0001-26-2", "filingDate": "2026-09-01", "form": "10-Q", "primaryDocument": "q.htm"},   # mimo okno
            {"accessionNumber": "0001-26-3", "filingDate": "2026-10-10", "form": "4", "primaryDocument": "f.xml"}])     # Form 4 ne

    res = M.attach_sec(conn, cconn, fetch=fetch, log=QUIET)
    assert res["dotazu"] == 1 and res["zapsano"] == 1 and res["bez_cik"] == 1 and calls == [123]
    filings = json.loads(conn.execute("SELECT filings_json FROM move_sec WHERE status = 'OK'").fetchone()[0])
    assert [f["form"] for f in filings] == ["8-K"] and filings[0]["url"] == "https://www.sec.gov/Archives/edgar/data/123/0001261/a.htm"
    assert M.attach_sec(conn, cconn, fetch=fetch, log=QUIET)["cekalo"] == 0 and calls == [123]    # podruhé nic
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("UPDATE move_sec SET status = 'BEZ_CIK'")


def test_attach_sec_error_retries_next_run(conn):
    cconn = dcache.connect(":memory:")
    cconn.execute("INSERT INTO sec_tickers VALUES ('ABC', 123, 'Abc', 'x')")
    D.record_new(conn, [_found("ABC", 1, date(2026, 10, 12))], today=date(2026, 10, 12), log=QUIET)
    res = M.attach_sec(conn, cconn, fetch=lambda cik: (_ for _ in ()).throw(RuntimeError("503")), log=QUIET)
    assert res["chyb"] == 1 and conn.execute("SELECT COUNT(*) FROM move_sec").fetchone()[0] == 0


def test_outcomes_after_5_20_60_days_vs_spy(conn):
    cconn = dcache.connect(":memory:")
    days = bdays(date(2026, 1, 5), 140)
    closes = [10.0] * 60 + [14.0] + [14.0 * (1 - 0.002 * k) for k in range(1, 80)]
    store(cconn, "ABC", days, closes)
    end = date.fromordinal(days[60])
    D.record_new(conn, [dict(_found("ABC", 1, end), cena=14.0)], today=end, log=QUIET)
    spy = Series(days, [100.0 + 0.1 * i for i in range(len(days))])
    res = M.record_outcomes(conn, cconn, today=date.fromordinal(days[-1]) + timedelta(days=1), spy=spy)
    assert res["zapsano"] == 3
    rows = {r["horizon"]: r for r in conn.execute("SELECT * FROM move_outcomes")}
    assert rows[5]["return_pct"] == pytest.approx(-1.0, abs=0.01) and rows[60]["day"] == date.fromordinal(days[120]).isoformat()
    assert rows[20]["spy_return_pct"] == pytest.approx((spy.values[80] / spy.values[60] - 1) * 100, abs=1e-3)
    assert M.record_outcomes(conn, cconn, today=date.fromordinal(days[-1]), spy=spy)["cekalo"] == 0


def test_outcome_waits_for_spy_then_records_without_it(conn):
    cconn = dcache.connect(":memory:")
    days = bdays(date(2026, 1, 5), 70)
    store(cconn, "ABC", days, [10.0] * 60 + [14.0] * 10)
    end = date.fromordinal(days[60])
    D.record_new(conn, [_found("ABC", 1, end)], today=end, log=QUIET)
    nospy = Series([], [])
    soon = date.fromordinal(days[65]) + timedelta(days=2)
    assert M.record_outcomes(conn, cconn, today=soon, spy=nospy)["zapsano"] == 0          # SPY ještě není → čekat
    later = date.fromordinal(days[65]) + timedelta(days=12)
    assert M.record_outcomes(conn, cconn, today=later, spy=nospy)["zapsano"] == 1          # pak bez srovnání s trhem
    assert conn.execute("SELECT spy_return_pct FROM move_outcomes").fetchone()[0] is None


def test_live_stats_and_cause_agreement(conn):
    end = date(2026, 9, 1)
    new = D.record_new(conn, [dict(_found(s, 1, end), symbol=s) for s in ("A1", "A2", "A3")], today=end, log=QUIET)
    for i, r in enumerate(new):
        with conn:
            conn.execute("INSERT INTO move_outcomes (event_id, horizon, base_day, base_price, day, price, return_pct,"
                         " spy_return_pct, recorded_at) VALUES (?, 20, '2026-09-01', 5, '2026-09-29', 5, ?, 1.0, 'x')",
                         (r["id"], [-10.0, 5.0, -2.0][i]))
    D.record_cause(conn, new[0]["id"], code="EARNINGS", status="OVĚŘENO", summary="FAKT: výsledky", source="8-K",
                   source_url="https://www.sec.gov/x", published_on="2026-08-31")
    with conn:
        conn.execute("INSERT INTO move_sec (event_id, cik, status, filings_json, checked_at) VALUES (?, 1, 'OK', ?, 'x')",
                     (new[0]["id"], json.dumps([{"form": "8-K", "items": "2.02", "datum": "2026-08-31", "url": "https://u"}])))
    st = M.live_stats(conn)["rakety"]
    allg = st["skupiny"][0]
    assert allg["skupina"] == "všechny" and allg["20d"]["n"] == 3 and allg["20d"]["median"] == -2.0
    assert allg["20d"]["pokracovalo"] == pytest.approx(1 / 3, abs=1e-3) and allg["20d"]["maly_vzorek"]
    assert any(g["skupina"] == "výsledky / výhled" for g in st["skupiny"])
    ag = M.cause_agreement(conn)
    assert ag["SEC"] == {"shoda": 1, "z": 1, "podil": 1.0}


def test_history_study_uses_the_same_rules(conn):
    cconn = dcache.connect(":memory:")
    days = bdays(date(2024, 1, 1), 300)
    jump = [10.0] * 150 + [13.5] + [13.5 * (1 + 0.001 * k) for k in range(1, 150)]       # +35 % za den, pak mírně nahoru
    store(cconn, "JMP", days, jump)
    store(cconn, "FLT", days, [20.0] * 300)
    store(cconn, "GLT", days, [10.0] * 150 + [1.0, 9.8] + [10.0] * 148)                 # chyba dat: pád a návrat
    cconn.execute("INSERT INTO sec_tickers VALUES ('JMP', 7, 'Jump', 'x')")
    cconn.execute("INSERT INTO sec_filings VALUES ('edgar/data/7/a.txt', 7, '10-Q', ?)", (date.fromordinal(days[150]).isoformat(),))
    spy = Series(days, [100.0] * 300)
    events = M.scan_history(cconn, spy, log=QUIET)
    assert [(e["smer"], e["jednodenni"]) for e in events] == [(1, True)]
    assert events[0]["druhy"] == {"s výsledky (10-Q/10-K)"} and events[0]["vynos"][20][0] == pytest.approx(2.0, abs=0.01)
    s = M.summarize_history(events)["skupiny"]["rakety"]
    groups = {g["skupina"]: g for g in s["tabulka"]}
    assert groups["jednodenní skok"]["pohybu"] == 1 and groups["všechny"]["maly_vzorek"]
    assert groups["s výsledky (10-Q/10-K)"]["20d"]["pokracovalo"] == 1.0


def test_history_study_is_weekly(conn, monkeypatch):
    cconn = dcache.connect(":memory:")
    days = bdays(date(2024, 1, 1), 100)
    store(cconn, "JMP", days, [10.0] * 50 + [13.5] * 50)
    assert M.history_study(conn, cconn, log=QUIET)["pohybu"] == 1
    assert M.history_study(conn, cconn, log=QUIET) is None                             # tentýž týden se nepočítá znovu
    assert M.history_study(conn, cconn, force=True, log=QUIET) is not None
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("DELETE FROM move_studies")


def _snap_day(cconn, day):
    cconn.executescript(D.SNAP_SCHEMA)
    rows = []
    for i in range(120):
        ind = "Semiconductors" if i < 20 else "Banks" if i < 60 else "Software"
        sector = "Technology" if ind != "Banks" else "Finance"
        prev = 50.0
        r = -0.06 if ind == "Semiconductors" else 0.002 if ind == "Banks" else 0.004
        if i == 0:
            r = -0.15                                                                     # největší firma oboru padá nejvíc
        cap = (5e11 if i == 0 else 2e10) * (1 + r)
        rows.append((day, f"S{i}", prev * (1 + r), prev, 1e6, cap, f"Firma {i} Inc", "x"))
        cconn.execute("INSERT OR REPLACE INTO securities (symbol, name, sector, industry, market_cap_usd, source, fetched_at)"
                      " VALUES (?, ?, ?, ?, ?, 'test', 'x')", (f"S{i}", f"Firma {i} Inc", sector, ind, cap))
    cconn.executemany("INSERT INTO nasdaq_snap VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)


def test_market_day_explains_sector_move(conn):
    cconn = dcache.connect(":memory:")
    _snap_day(cconn, "2026-10-22")
    heads = lambda q, a, b: [{"datum": "2026-10-22", "titulek": "Why Firma 0 stock plunged after earnings miss", "zdroj": "X"}]
    res = MD.build(conn, cconn, "2026-10-22", fetch=heads, pause=0)
    semis = res["obory"][0]
    assert semis["nazev"] == "Semiconductors" and semis["zmena"] < -0.08 and semis["rostlo"] == 0.0
    assert semis["tahouni"][0]["ticker"] == "S0" and semis["podil_tri"] > 0.6
    assert any("hlavně 3 firmy" in s for s in semis["vysvetleni"]) and semis["titulky"]["pricny"][0]["kod"] == "EARNINGS"
    assert res["sektory"][0]["nazev"] == "Finance" and res["sektory"][-1]["nazev"] == "Technology"
    assert MD.record(conn, res) and not MD.record(conn, res)
    assert MD.run(conn, cconn, fetch=None, log=QUIET)["stav"] == "UŽ JE"


def test_web_doc_and_old_state_restore(conn, tmp_path):
    from stockradar.db import open_db
    from stockradar.site import build_pohyby_doc
    from stockradar.state_io import export_state, restore_state
    today = date.today()
    D.record_new(conn, [_found("UP1", 1, today), _found("DN1", -1, today)], today=today, log=QUIET)
    doc = build_pohyby_doc(conn)
    assert [r["ticker"] for r in doc["rakety"]] == ["UP1"] and doc["propady"][0]["smer"] == -1
    assert doc["pocty"] == {"rakety": 1, "propady": 1, "za_dni": 30, "rakety_za_obdobi": 1, "propady_za_obdobi": 1}
    # export ze starší verze (bez sloupců direction / move_1d / rel_volume) se obnoví s výchozí hodnotou
    export_state(conn, tmp_path)
    lines = [json.loads(x) for x in (tmp_path / "rocket_events.jsonl").read_text(encoding="utf-8").splitlines()]
    old = [{k: v for k, v in r.items() if k not in ("direction", "move_1d", "rel_volume")} for r in lines if r["symbol"] == "UP1"]
    (tmp_path / "rocket_events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in old), encoding="utf-8")
    fresh = open_db(":memory:")
    restore_state(fresh, tmp_path)
    assert fresh.execute("SELECT direction FROM rocket_events").fetchall()[0][0] == 1


def test_monthly_window_does_not_record_the_same_jump_twice(conn):
    """21 obchodních dní je ~30 kalendářních: skok musí zůstat jednou epizodou i po 22 dnech (dřív se zapsal podruhé)."""
    cconn = dcache.connect(":memory:")
    days = bdays(date(2024, 1, 1), 200)
    store(cconn, "ONE", days, [10.0] * 100 + [16.0] * 100)                              # +60 % za den, pak rovně
    store(cconn, "TWO", days, [10.0] * 100 + [16.0] * 30 + [21.0] * 70)                 # po měsíci nový skok +31 %
    events = M.scan_history(cconn, Series(days, [100.0] * 200), log=QUIET)
    assert sorted((e["smer"], date.fromordinal(e["den"]) == date.fromordinal(days[100])) for e in events) == \
        [(1, False), (1, True), (1, True)]
    first = D.detect(days[:101], [10.0] * 100 + [16.0], [200_000.0] * 101)
    later = D.detect(days[:118], [10.0] * 100 + [16.0] * 18, [200_000.0] * 118)          # 17 obchodních dní ≈ 23 kalendářních
    assert later is not None and later["end"] - first["end"] > D.EPISODE_DAYS
    assert D.same_story(later, first["end"]) and not D.same_story(first, None)


def test_snapshot_is_stored_under_the_day_its_prices_are_from():
    """Screener vydá závěr dne D až ráno D+1: večerní běh 22. 10. dostal ceny z 21. 10. (S&P +0,6 %, ne −1,2 %)."""
    from datetime import datetime, timezone
    c = sqlite3.connect(":memory:")
    rows = [{"symbol": f"S{i}", "lastsale": f"${10 + i}", "netchange": "0.5", "volume": "1000", "marketCap": "1", "name": "x"}
            for i in range(10)]
    ref = {f"S{i}": {"2026-10-21": 10.0 + i, "2026-10-22": 9.0 + i} for i in range(10)}
    evening = datetime(2026, 10, 22, 20, 47, tzinfo=timezone.utc)                    # 16:47 v New Yorku
    res = D.take_snapshot(c, now=evening, fetch=lambda: rows, reference=ref, log=QUIET)
    assert res == {"stav": "OK", "den": "2026-10-21", "akcii": 10}
    assert D.take_snapshot(c, now=evening, fetch=lambda: rows, reference=ref, log=QUIET)["stav"] == "UŽ JE"
    bad = {f"S{i}": {"2026-10-22": 50.0} for i in range(10)}
    assert D.take_snapshot(sqlite3.connect(":memory:"), now=evening, fetch=lambda: rows, reference=bad,
                           log=QUIET)["stav"] == "NEOVĚŘENO"
    # oprava staršího snímku se špatným dnem: přejmenovat, nebo smazat, když skutečný den už je
    c.execute("UPDATE nasdaq_snap SET day = '2026-10-22'")
    assert D.repair_snapshots(c, ref, log=QUIET) == ["2026-10-22: ceny jsou z 2026-10-21 → přejmenováno"]
    assert [r[0] for r in c.execute("SELECT DISTINCT day FROM nasdaq_snap")] == ["2026-10-21"]


def test_reverse_split_with_low_volume_is_not_a_rocket():
    days = list(range(40))
    closes = [0.25] * 35 + [2.1, 1.9, 1.6, 1.4, 1.23]                                   # split 1:10 a pak pokles
    vols = [8_000_000.0] * 35 + [600_000.0] * 5                                          # objem v kusech klesl
    assert D.detect(days, closes, vols) is not None and D.unadjusted_split(closes, vols, 39)
    assert not D.unadjusted_split(closes, [8_000_000.0] * 35 + [90_000_000.0] * 5, 39)   # skutečná raketa: objem vysoko
    frgt = [8_000_000.0] * 35 + [9_000_000.0, 700_000.0, 500_000.0, 400_000.0, 600_000.0]    # v den splitu objem vysoký
    assert D.unadjusted_split(closes, frgt, 39) and not D.unadjusted_split(closes, frgt, 35)  # v den splitu ještě nepoznat
    assert D.unadjusted_split(closes, frgt, 35, until=39)                                  # historie: 5 dní dopředu


def test_market_day_refuses_snapshot_that_disagrees_with_sp500(conn):
    cconn = dcache.connect(":memory:")
    _snap_day(cconn, "2026-10-22")                                                       # trh v datech asi −3 %
    with conn:
        conn.executemany("INSERT INTO price_bars (symbol, date, close, volume, source, fetched_at) VALUES ('SPY', ?, ?, 1, 't', 'x')",
                         [("2026-10-21", 7757.17), ("2026-10-22", 7757.17 * 1.006)])
    res = MD.build(conn, cconn, "2026-10-22", fetch=None)
    assert res["stav"] == "NEOVĚŘENO" and "S&P 500" in res["duvod"] and not MD.record(conn, res)
