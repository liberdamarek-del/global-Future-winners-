"""Centrum (v0.10.0): role a spolehlivost, důkazy, ruční výzkum, pohled na firmu, rozpory, deník, registr, paměť výpočtů."""

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest

from stockradar.causal import memo
from stockradar.discovery import cache as dcache
from stockradar.hub import evidence as E
from stockradar.hub import feedback as F
from stockradar.hub import integrate as I
from stockradar.hub import registry as R

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 7)


def test_signal_role_is_single_source_of_truth():
    assert F.signal_role("SIGNAL_6M", {"poradi": 1, "final": "NEVÍM"}) == "SIGNAL_6M:vyber"
    assert F.signal_role("SIGNAL_6M", {"poradi_velke": 3, "final": "RŮST"}) == "SIGNAL_6M:vyber"
    assert F.signal_role("SIGNAL_1M", {"final": "POKLES"}) == "SIGNAL_1M:varovani"          # nejslabší (bez pořadí)
    assert F.signal_role("SIGNAL_1M", {"poradi": 4, "final": "POKLES"}) == "SIGNAL_1M:pokles"
    assert F.signal_role("SIGNAL_14D", {"final": "NEVÍM"}) is None


def test_judge_and_weekly_t():
    assert F.judge(3.0, typ="t", metrika="m")["stav"] == "OVĚŘENO" and F.judge(3.0, typ="t", metrika="m")["vaha"] == 0.75
    assert F.judge(1.5, typ="t", metrika="m")["vaha"] == F.W_UNVERIFIED
    assert F.judge(-2.5, typ="t", metrika="m") | {} == F.judge(-2.5, typ="t", metrika="m")
    assert F.judge(-2.5, typ="t", metrika="m")["stav"] == "CHYBA" and F.judge(-2.5, typ="t", metrika="m")["vaha"] == 0
    assert F.judge(None, typ="t", metrika="m")["stav"] == "NEOVĚŘENO"
    t, n, weeks = F.weekly_t([(w, 0.02 + 0.001 * (w % 3)) for w in range(10) for _ in range(3)])
    assert n == 30 and weeks == 10 and t > 10
    assert F.weekly_t([(1, 0.1), (2, 0.2)])[0] is None                                       # málo týdnů


def _signal_run(conn, model, cards, *, cfg="abc", t_top=0.5, t_bottom=-3.0, t_pokles=-1.0, data="2026-10-02",
                run_at="2026-10-03T10:00:00Z", version="0.10.0"):
    res = {"karty": cards, "zaklad": {"up5": 0.1, "down5": 0.2}, "prah_rust": 0.4, "prah_pokles": -0.25,
           "poradi_vse": ",".join(c["ticker"] for c in cards)}
    conn.execute("INSERT INTO signal_runs (run_at, data_through, model_name, config_hash, result_json, app_version)"
                 " VALUES (?, ?, ?, ?, ?, ?)", (run_at, data, model, cfg, json.dumps(res), version))
    metrics = {"horni_desetina": {"t": t_top, "n_indep": 100, "nad_tydnem": 0.01},
               "dolni_desetina": {"t": t_bottom, "n_indep": 100, "nad_tydnem": -0.1},
               "rozhodnuti": {"POKLES": {"t": t_pokles, "n_indep": 50, "nad_tydnem": -0.05}}}
    conn.execute("INSERT INTO model_evaluations (model_name, config_hash, split, period_start, period_end, n_samples,"
                 " n_independent, metrics_json, evaluated_at, app_version) VALUES (?, ?, 'LOCKED_TEST', '2025-07-18',"
                 " '2026-03-27', 1000, 100, ?, '2026-10-06T08:00:00Z', '0.9.0')", (model, cfg, json.dumps(metrics)))
    conn.commit()


CARDS = [{"ticker": "VLO", "firma": "Valero", "obor": "integrated oil companies", "poradi": None, "poradi_velke": 3,
          "final": "NEVÍM", "p_up": 0.15, "p_down": 0.24, "duvera": 65, "den_ceny": "2026-10-02"},
         {"ticker": "LWLG", "firma": "Lightwave", "obor": "semiconductors", "final": "POKLES", "p_up": 0.1, "p_down": 0.6,
          "duvera": 70, "den_ceny": "2026-10-02"}]


def test_reliability_from_locked_test_marks_verified_warning(conn):
    _signal_run(conn, "SIGNAL_6M", CARDS)
    rel = F.reliability(conn)
    assert rel["SIGNAL_6M:varovani"]["stav"] == "OVĚŘENO" and rel["SIGNAL_6M:varovani"]["t"] == 3.0
    assert rel["SIGNAL_6M:vyber"]["stav"] == "NEOVĚŘENO" and rel["SIGNAL_6M:vyber"]["vaha"] == F.W_UNVERIFIED
    assert rel["SIGNAL_14D:vyber"]["typ"] == "chybí"                                   # model bez běhu = neověřeno
    assert set(rel) == set(F.ROLES)


def test_research_is_append_only_and_validated(conn):
    with pytest.raises(ValueError):
        E.add_research(conn, entity_type="firma", entity="vlo", kind="riziko", direction=-1, horizon_days=120,
                       summary="x", source="s", source_url="http://bez-tls", published_on="2026-10-06")
    rid = E.add_research(conn, entity_type="firma", entity="vlo", kind="riziko", direction=-1, horizon_days=120,
                         summary="G7 uvolňuje zásoby", source="StockTitan", source_url="https://stocktitan.net/x",
                         published_on="2026-10-06", now=NOW)
    row = conn.execute("SELECT entity, valid_until FROM research_evidence WHERE id = ?", (rid,)).fetchone()
    assert row["entity"] == "VLO" and row["valid_until"] == "2027-02-03"
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE research_evidence SET direction = 1")
    items, expired = E.from_research(conn, date(2027, 3, 1))
    assert items == [] and expired == 1                                                 # prošlý výzkum se nepočítá


def test_dossier_finds_conflict_lessons_and_checks(conn):
    _signal_run(conn, "SIGNAL_6M", CARDS)
    E.add_research(conn, entity_type="firma", entity="VLO", kind="riziko", direction=-1, horizon_days=120,
                   summary="G7 uvolňuje zásoby nafty", source="StockTitan", source_url="https://stocktitan.net/x",
                   published_on="2026-10-06", now=NOW)
    conn.execute("INSERT INTO lessons (case_key, title, outcome_type, summary, lessons_json, source, recorded_at) VALUES"
                 " ('POUCENI-RAKETY-VOLATILITA', 'Volatilita', 'REFERENCE', 's', '[\"směr nejde\"]', 'test', '2026-10-03T00:00:00Z')")
    res = I.build(conn, None, TODAY)
    by = {d["ticker"]: d for d in res["firmy"]}
    vlo, lw = by["VLO"], by["LWLG"]
    assert vlo["postoj"] == "ROZPOR" and vlo["rozpory"] and vlo["pro"] == 0.1 and vlo["proti"] == 0.1
    assert [l["klic"] for l in vlo["pouceni"]] == ["POUCENI-RAKETY-VOLATILITA"]
    assert any("neověřených rolí" in k for k in vlo["kontrola"]) and any("XTB neověřena" in k for k in vlo["kontrola"])
    assert lw["postoj"] == "RIZIKO" and lw["overeno_proti"] and lw["proti"] == 0.75   # ověřené varování, t 3 → 0,75
    assert res["pocty"]["ROZPOR"] == 1 and any("rozpor" in c["text"] for c in res["kontroly"])


def test_stale_evidence_halves_weight_and_module_verdict_caps_it():
    rel = {"SIGNAL_1M:varovani": {"stav": "OVĚŘENO", "vaha": 0.9, "t": 3.6, "nazev": "1 m varování"},
           "SMART_MONEY:nakup": {"stav": "OVĚŘENO", "vaha": 0.6, "t": 2.7, "nazev": "insideři"}}
    old = E._ev("ABC", modul="SIGNAL_1M", role="SIGNAL_1M:varovani", druh="riziko", smer=-1, horizont=30, text="t",
                zdroj="z", data_do="2026-09-20")
    sm = E._ev("ABC", modul="SMART_MONEY", role="SMART_MONEY:nakup", druh="prilezitost", smer=1, horizont=182, text="t",
               zdroj="z", data_do="2026-10-01", uprava={"strop": 0.1, "stav": "NEOVĚŘENO", "duvod": "verdikt NÍZKÁ"})
    d = I.dossier("ABC", [old, sm], rel, {}, {}, [], TODAY)
    assert d["proti"] == 0.45 and d["pro"] == 0.1 and d["postoj"] == "ROZPOR"
    assert next(x for x in d["dukazy"] if x["modul"] == "SMART_MONEY")["spolehlivost"] == "NEOVĚŘENO"
    assert any("verdikt NÍZKÁ" in k for k in d["kontrola"]) and any("starší než čtvrtina" in k for k in d["kontrola"])


def test_refresh_records_once_per_input_change(conn):
    _signal_run(conn, "SIGNAL_6M", CARDS)
    a = I.refresh(conn, None, today=TODAY)
    b = I.refresh(conn, None, today=TODAY)
    assert a["beh"]["stav"] == "OK" and b["beh"]["stav"] == "PŘESKOČENO"
    assert conn.execute("SELECT COUNT(*) FROM hub_runs").fetchone()[0] == 1
    E.add_research(conn, entity_type="firma", entity="LWLG", kind="kontext", direction=0, horizon_days=30, summary="x",
                   source="s", source_url="https://example.com", published_on="2026-10-06", now=NOW)
    c = I.refresh(conn, None, today=TODAY)
    assert c["beh"]["stav"] == "OK" and conn.execute("SELECT COUNT(*) FROM hub_runs").fetchone()[0] == 2
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM hub_runs")
    assert "moduly" in c["system"] and c["system"]["zdroje"][-1]["stav"] == "BLOKOVÁNO"   # GDELT


def test_journal_and_module_states(conn):
    R.record_run(conn, "causal", {"no_news": True}, NOW - timedelta(minutes=2), "CHYBA", {}, "HTTPError: 503", finished=NOW)
    mods = {m["id"]: m for m in R.modules_status(conn, None, F.reliability(conn), NOW)}
    assert mods["kauzalni"]["stav"] == "CHYBA" and "503" in mods["kauzalni"]["duvod"]
    assert mods["energie"]["stav"] == "ROZPRACOVÁNO"                                    # zatím neběžel
    assert mods["zpetna_vazba"]["stav"] == "ROZPRACOVÁNO"
    conn.execute("INSERT INTO discovery_runs (run_at, data_through, stats_json, result_json, models_json, app_version)"
                 " VALUES ('2026-09-20T20:00:00Z', '2026-09-18', '{}', '{}', '{}', '0.9.0')")
    mods = {m["id"]: m for m in R.modules_status(conn, None, F.reliability(conn), NOW)}
    assert mods["objevovani"]["stav"] == "CHYBA" and "zastaralé" in mods["objevovani"]["duvod"]   # týdenní, 17 dní
    j = R.journal(conn)
    assert j[0]["prikaz"] == "causal" and j[0]["trvani_s"] == 120
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE system_runs SET status = 'OK'")


def _cache_with_prices(path, end="2026-10-02", comm_extra=None):
    cc = dcache.connect(path)
    cc.execute("INSERT INTO securities (symbol, name, country, exchange, sector, industry, market_cap_usd, source, fetched_at)"
               " VALUES ('AAA', 'Aaa', 'US', 'NASDAQ', 'Tech', 'software', 1e9, 'test', '2026-10-03T00:00:00Z')")
    days = [(date.fromisoformat(end) - timedelta(days=i)).isoformat() for i in range(300)][::-1]
    dcache.store_series(cc, "AAA", "USD", [(d, 10.0, 1000.0) for d in days], source="t", fetched_at="2026-10-03T00:00:00Z")
    cdays = days + (comm_extra or [])
    dcache.store_series(cc, "HG=F", "USD", [(d, 4.0, 1.0) for d in cdays], source="t", fetched_at="2026-10-06T00:00:00Z")
    return cc


def test_memo_fingerprint_ignores_commodity_days_after_stock_data(tmp_path):
    a = memo.fingerprint(_cache_with_prices(tmp_path / "a.db"))
    b = memo.fingerprint(_cache_with_prices(tmp_path / "b.db", comm_extra=["2026-10-05", "2026-10-06"]))
    c = memo.fingerprint(_cache_with_prices(tmp_path / "c.db", end="2026-10-09"))
    assert a == b and a[1] == "2026-10-02"                    # denní ceny komodit po posledním dni akcií nic nemění
    assert c[0] != a[0]                                        # nové ceny akcií → přepočet


def test_signals_guard_skips_only_unchanged_data(conn, tmp_path):
    from stockradar import __version__
    cc = _cache_with_prices(tmp_path / "c.db")
    models = ("SIGNAL_6M",)
    assert R.signals_unchanged(conn, cc, models) is None                               # zatím žádný běh
    _signal_run(conn, "SIGNAL_6M", CARDS, version=__version__)
    assert "nezměnily" in R.signals_unchanged(conn, cc, models)
    conn.execute("INSERT INTO smart_money_runs (run_at, data_through, result_json, app_version)"
                 " VALUES ('2026-10-04T08:00:00Z', '2026-10-02', '{}', 'x')")
    assert R.signals_unchanged(conn, cc, models) is None                               # nový vstup → počítat
