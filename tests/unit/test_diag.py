"""Diagnostika: každá kontrola musí umět OK i problém (VAROVÁNÍ / CHYBA) a nejhorší úroveň určuje návratový kód."""

import json
from datetime import timedelta

import pytest

from stockradar import config, diag
from stockradar.catalysts import add_catalyst
from stockradar.discovery import cache as dcache
from stockradar.ledger import PredictionInput, Scores, record_prediction
from stockradar.lessons import seed_master_prompt_cases
from stockradar.site import DOC_LIMIT
from stockradar.state_io import export_state
from tests.conftest import NOW


def by_name(checks: list[dict]) -> dict:
    return {c["kontrola"]: c for c in checks}


def run(conn, tmp_path, now=NOW, cache=None):
    web = tmp_path / "web"
    web.mkdir(exist_ok=True)
    return diag.run_checks(conn, state_dir=tmp_path / "state", web_dir=web, cache_conn=cache, now=now)


@pytest.fixture(autouse=True)
def no_email(monkeypatch, tmp_path):
    monkeypatch.delenv("STOCKRADAR_CONTACT_EMAIL", raising=False)
    monkeypatch.setenv("STOCKRADAR_CONTACT_FILE", str(tmp_path / "kontakt.txt"))


def test_fresh_db_reports_missing_runs_as_errors(conn, tmp_path):
    checks = run(conn, tmp_path)
    c = by_name(checks)
    assert c["Schéma databáze"]["uroven"] == "OK"
    assert c["Ceny S&P 500 (SPY)"]["uroven"] == "CHYBA" and c["Ceny S&P 500 (SPY)"]["detail"] == "chybí"
    assert c["Denní běh (update)"]["uroven"] == "CHYBA"
    assert c["Týdenní objevování (discover)"]["uroven"] == "VAROVÁNÍ"
    assert c["Vyhodnocení predikcí"]["uroven"] == "OK" and c["Katalyzátory po termínu"]["uroven"] == "OK"
    assert c["Použití e-mailu (7 dní)"]["detail"] == "za 7 dní nepoužit"
    assert "SEC EDGAR" not in c                       # bez cache se kontroly objevování přeskočí
    assert diag.worst(checks) == "CHYBA"
    assert all(ch["uroven"] in diag.LEVELS for ch in checks)


def test_unexported_state_is_a_warning_until_export(conn, tmp_path):
    seed_master_prompt_cases(conn)
    assert by_name(run(conn, tmp_path))["Uložení do state/"]["uroven"] == "VAROVÁNÍ"
    export_state(conn, tmp_path / "state")
    assert by_name(run(conn, tmp_path))["Uložení do state/"]["uroven"] == "OK"


@pytest.mark.parametrize("last_day, level", [("2026-10-01", "OK"), ("2026-09-25", "VAROVÁNÍ")])
def test_spy_freshness(conn, tmp_path, last_day, level):
    conn.execute("INSERT INTO price_bars VALUES (?, ?, 1, 1, 't', ?)", (config.BENCHMARK_SYMBOL, last_day, "x"))
    assert by_name(run(conn, tmp_path))["Ceny S&P 500 (SPY)"]["uroven"] == level


def _model_run(conn, run_at):
    conn.execute("INSERT OR IGNORE INTO model_versions (id, created_at, weights_json, metrics_json, calibration_json,"
                 " training_window, n_samples, reason) VALUES (1, ?, '{}', '{}', '{}', 't', 0, 't')", (run_at,))
    conn.execute("INSERT INTO model_runs (run_at, data_date, model_version_id, scores_json, steps_json, warnings_json)"
                 " VALUES (?, '2026-10-01', 1, '{}', '[]', '[]')", (run_at,))


@pytest.mark.parametrize("age_days, level", [(1, "OK"), (5, "VAROVÁNÍ")])
def test_daily_run_age(conn, tmp_path, age_days, level):
    _model_run(conn, (NOW - timedelta(days=age_days)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert by_name(run(conn, tmp_path))["Denní běh (update)"]["uroven"] == level


def _prediction(conn, listing_id, made_at):
    p = PredictionInput(listing_id=listing_id, horizon="D0_14", price=4.2, currency="USD",
                        price_as_of=made_at - timedelta(minutes=30), price_source="test", category="A",
                        verdict="WATCH", rationale="test", scores=Scores(overall_setup=50))
    return record_prediction(conn, p, now=made_at)


def test_overdue_evaluations_and_missing_prices_are_errors(conn, listing, tmp_path):
    _, listing_id = listing
    conn.execute("UPDATE listings SET yahoo_symbol = 'TBIO' WHERE id = ?", (listing_id,))
    pid = _prediction(conn, listing_id, NOW - timedelta(days=20))
    c = by_name(run(conn, tmp_path))
    assert c["Vyhodnocení predikcí"]["uroven"] == "CHYBA" and f"#{pid} TBIO (+7, +14 d)" in c["Vyhodnocení predikcí"]["detail"]
    assert c["Ceny pro predikce"]["uroven"] == "CHYBA" and "TBIO" in c["Ceny pro predikce"]["detail"]

    conn.execute("INSERT INTO price_bars VALUES ('TBIO', '2026-10-01', 4.0, 1, 't', 'x')")
    assert by_name(run(conn, tmp_path))["Ceny pro predikce"]["uroven"] == "OK"
    # predikce mladší než horizont + 5 dní rezervy ještě není zpožděná
    assert by_name(run(conn, tmp_path, now=NOW - timedelta(days=8)))["Vyhodnocení predikcí"]["uroven"] == "OK"


def test_catalyst_after_window_is_warning(conn, listing, tmp_path):
    company_id, _ = listing
    add_catalyst(conn, company_id, "FDA_DECISION", "PDUFA", date_status="VERIFIED", event_date="2026-09-01",
                 source="test", source_url="https://example.com", published_at=NOW - timedelta(days=60))
    c = by_name(run(conn, tmp_path))["Katalyzátory po termínu"]
    assert c["uroven"] == "VAROVÁNÍ" and "Test Bio (2026-09-01)" in c["detail"]


def test_cache_checks_and_sec_without_email(conn, tmp_path):
    cache = dcache.connect(":memory:")
    fresh = (NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cache.execute("INSERT INTO series (symbol, n, fetched_at) VALUES ('AAA', 10, ?)", (fresh,))
    cache.execute("INSERT INTO ct_studies (nct, sponsor, fetched_at) VALUES ('NCT1', 'X', ?)", (fresh,))
    c = by_name(run(conn, tmp_path, cache=cache))
    assert c["Ceny globálního vesmíru"]["uroven"] == "OK"
    assert c["SEC EDGAR"]["uroven"] == "INFO" and "SEC vypnutý" in c["SEC EDGAR"]["detail"]
    assert c["ClinicalTrials.gov"]["uroven"] == "OK"

    old = (NOW - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cache.execute("INSERT INTO series (symbol, n, fetched_at) VALUES ('BBB', 10, ?)", (old,))
    assert by_name(run(conn, tmp_path, cache=cache))["Ceny globálního vesmíru"]["uroven"] == "VAROVÁNÍ"


def test_sec_with_email_requires_recent_download(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKRADAR_CONTACT_EMAIL", "test@example.com")
    cache = dcache.connect(":memory:")
    assert by_name(run(conn, tmp_path, cache=cache))["SEC EDGAR"]["uroven"] == "VAROVÁNÍ"
    cache.execute("INSERT INTO sec_index_done VALUES ('2026Q3', 1, ?)", ((NOW - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),))
    assert by_name(run(conn, tmp_path, cache=cache))["SEC EDGAR"]["uroven"] == "OK"


@pytest.mark.parametrize("size, level", [(1000, "OK"), (int(0.9 * DOC_LIMIT), "VAROVÁNÍ"), (DOC_LIMIT + 1, "CHYBA")])
def test_web_document_size_against_server_limit(conn, tmp_path, size, level):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "stav_test.json").write_bytes(b"x" * size)
    assert by_name(run(conn, tmp_path))["Web stav_test.json"]["uroven"] == level


def test_hub_older_than_module_output_is_warning(conn, tmp_path):
    assert "zatím neběželo" in by_name(run(conn, tmp_path))["Centrum důkazů (propojený pohled)"]["detail"]
    _model_run(conn, "2026-10-02T10:00:00Z")
    conn.execute("INSERT INTO hub_runs (run_at, summary_json, app_version) VALUES ('2026-10-01T10:00:00Z', '{}', 't')")
    c = by_name(run(conn, tmp_path))["Centrum důkazů (propojený pohled)"]
    assert c["uroven"] == "VAROVÁNÍ" and "model_runs" in c["detail"]
    conn.execute("INSERT INTO hub_runs (run_at, summary_json, app_version) VALUES ('2026-10-02T11:00:00Z', '{}', 't')")
    assert by_name(run(conn, tmp_path))["Centrum důkazů (propojený pohled)"]["uroven"] == "OK"


def test_worst_and_json():
    checks = [{"uroven": "OK", "kontrola": "a", "detail": ""}, {"uroven": "VAROVÁNÍ", "kontrola": "b", "detail": "č"}]
    assert diag.worst(checks) == "VAROVÁNÍ"
    assert diag.worst([]) == "OK"
    assert json.loads(diag.to_json(checks)) == checks and "č" in diag.to_json(checks)


def test_age_days_accepts_timestamp_and_date():
    assert diag._age_days(None, NOW) is None
    assert diag._age_days("2026-10-01T12:00:00Z", NOW) == pytest.approx(1.0)
    assert diag._age_days("2026-10-01", NOW) == pytest.approx(1.5)
