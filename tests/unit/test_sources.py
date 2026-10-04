"""Nové zdroje v0.4.0: evidence e-mailu, SEC EDGAR, ClinicalTrials.gov, point-in-time fundamenty (bez sítě)."""

import sqlite3
from datetime import date

import pytest

from stockradar import contact
from stockradar.discovery import cache
from stockradar.discovery.fundamentals import Fundamentals
from stockradar.sources import clinicaltrials, sec


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKRADAR_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("STOCKRADAR_CONTACT_FILE", str(tmp_path / "kontakt.txt"))
    monkeypatch.delenv("STOCKRADAR_CONTACT_EMAIL", raising=False)
    contact.USAGE.reset()
    yield tmp_path
    contact.USAGE.reset()


def test_email_missing_means_nothing_is_sent(db_env, monkeypatch):
    assert contact.email() is None
    with pytest.raises(contact.ContactMissing):
        contact.user_agent()
    called = []
    monkeypatch.setattr(contact.urllib.request, "urlopen", lambda *a, **k: called.append(a))
    with pytest.raises(contact.ContactMissing):
        contact.http_get("https://data.sec.gov/x.json", "test")
    assert called == []
    assert sec.refresh(cache.connect(":memory:"))["stav"].startswith("VYPNUTO")


def test_email_only_to_allowed_hosts_and_every_use_is_counted(db_env, monkeypatch):
    (db_env / "kontakt.txt").write_text("someone@example.com\n")
    assert contact.user_agent().endswith("someone@example.com")
    with pytest.raises(ValueError, match="jen na"):
        contact.http_get("https://query1.finance.yahoo.com/x", "test")

    class Resp:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"

    sent = []
    monkeypatch.setattr(contact.urllib.request, "urlopen", lambda req, timeout: sent.append(req) or Resp())
    monkeypatch.setattr(contact, "MAX_PER_SECOND", 1000.0)
    for _ in range(3):
        contact.http_get("https://data.sec.gov/api/x.json", "fundamenty")
    contact.http_get("https://www.sec.gov/files/company_tickers.json", "tickery")
    assert all("someone@example.com" in r.get_header("User-agent") for r in sent)
    conn = sqlite3.connect(db_env / "t.db")
    conn.row_factory = sqlite3.Row
    rows = {(r["host"], r["purpose"]): r["requests"] for r in conn.execute("SELECT * FROM email_usage")}
    assert rows == {("data.sec.gov", "fundamenty"): 3, ("www.sec.gov", "tickery"): 1}
    summ = contact.usage_summary(conn)
    assert summ["celkem_od_zacatku"] == 4 and summ["dny"][0]["servery"] == {"data.sec.gov": 3, "www.sec.gov": 1}
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("UPDATE email_usage SET requests = 0")
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("DELETE FROM email_usage")


def test_sec_parsers():
    assert sec.quarters(date(2025, 11, 1), date(2026, 4, 1)) == [(2025, 4), (2026, 1), (2026, 2)]
    text = ("Description: Master Index\n\nCIK|Company Name|Form Type|Date Filed|Filename\n----\n"
            "123|ACME|8-K|2026-07-01|edgar/data/123/a.txt\n123|ACME|4|2026-07-02|edgar/data/123/b.txt\n"
            "123|ACME|SC 13D|2026-07-03|edgar/data/123/c.txt\n9|BANK|424B2|2026-07-03|edgar/data/9/d.txt\n")
    rows = sec.parse_master(text)
    assert [(r[1], r[2]) for r in rows] == [(123, "8-K"), (123, "SC 13D")]  # Form 4 a 424B2 se neukládají
    assert sec.parse_frame({"data": [{"cik": 5, "end": "2025-06-30", "val": 10}]}) == [(5, "2025-06-30", 10.0)]


def test_clinicaltrials_parse_and_sponsor_matching():
    s = clinicaltrials.parse_study({"protocolSection": {
        "identificationModule": {"nctId": "NCT1", "briefTitle": "Drug X"},
        "statusModule": {"overallStatus": "ACTIVE_NOT_RECRUITING",
                         "primaryCompletionDateStruct": {"date": "2026-12", "type": "ESTIMATED"}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Capricor Inc."}},
        "designModule": {"phases": ["PHASE3"], "enrollmentInfo": {"count": 120}}}})
    assert s["pcd"] == "2026-12" and s["pcd_type"] == "ESTIMATED" and s["phase"] == "PHASE3"
    assert clinicaltrials.norm_name("Beam Therapeutics Inc.") == "beam therapeutics"
    c = cache.connect(":memory:")
    c.executemany("INSERT INTO securities (symbol, name, source, fetched_at) VALUES (?, ?, 't', 't')",
                  [("CAPR", "Capricor Therapeutics, Inc. Common Stock"), ("BEAM", "Beam Therapeutics Inc. Common Stock")])
    c.executemany("INSERT INTO ct_studies (nct, sponsor, fetched_at) VALUES (?, ?, 't')",
                  [("NCT1", "Capricor Inc."), ("NCT2", "Beam Therapeutics Inc."), ("NCT3", "Unknown Pharma Co")])
    clinicaltrials.build_sponsor_map(c)
    m = {r["sponsor"]: r["symbol"] for r in c.execute("SELECT * FROM ct_sponsor_map")}
    assert m == {"Capricor Inc.": "CAPR", "Beam Therapeutics Inc.": "BEAM", "Unknown Pharma Co": None}


def test_fundamentals_are_point_in_time():
    c = cache.connect(":memory:")
    c.execute("INSERT INTO sec_tickers VALUES ('ACME', 1, 'Acme', 't')")
    # 10-Q za Q2/2025 podané 2025-08-10 → tržby Q2 se smí použít až od 10. 8.
    c.executemany("INSERT INTO sec_filings (path, cik, form, filed) VALUES (?, 1, ?, ?)",
                  [("a", "10-Q", "2024-08-09"), ("b", "10-Q", "2025-08-10"), ("c", "S-3", "2025-08-20"),
                   ("d", "8-K", "2025-08-25")])
    c.executemany("INSERT INTO sec_facts (cik, concept, period, end_day, val, source) VALUES (1, ?, ?, ?, ?, 't')",
                  [("revenue", "CY2024Q2", "2024-06-30", 100.0), ("revenue", "CY2025Q2", "2025-06-30", 250.0),
                   ("shares", "CY2024Q2", "2024-06-30", 1e6), ("shares", "CY2025Q2", "2025-06-30", 1.5e6)])
    f = Fundamentals(c, ["ACME", "OTHER"])
    before = f.features("ACME", date(2025, 8, 9).toordinal(), 10.0)
    after = f.features("ACME", date(2025, 8, 30).toordinal(), 10.0)
    assert before["rev_yoy"] is None and after["rev_yoy"] == pytest.approx(1.5)
    assert after["dilution"] == pytest.approx(0.5) and after["log_mcap"] is not None
    assert after["offer_90"] == 1 and after["n8k_30"] == 1
    assert f.features("OTHER", date(2025, 8, 30).toordinal(), 10.0)["has_fund"] == 0.0


def test_download_error_keeps_existing_history():
    c = cache.connect(":memory:")
    cache.store_series(c, "AAA", "USD", [("2026-01-02", 10.0, 100.0), ("2026-01-05", 11.0, 100.0)],
                       source="t", fetched_at="2026-01-05T00:00:00Z")
    cache.store_error(c, "AAA", "HTTP Error 429", fetched_at="2026-01-12T00:00:00Z")
    assert len(cache.load_series(c, "AAA").closes) == 2
    cache.store_error(c, "BBB", "HTTP Error 404", fetched_at="2026-01-12T00:00:00Z")
    assert cache.load_series(c, "BBB") is None


def test_sec_frames_do_not_refetch_old_empty_quarters(monkeypatch):
    import urllib.error
    c = cache.connect(":memory:")
    calls = []

    def fake_get(url, purpose, **kw):
        calls.append(url)
        if "SalesRevenueNet" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return b'{"data": []}'

    monkeypatch.setattr(sec.contact, "http_get", fake_get)
    sec.fetch_frames(c, start=date(2024, 1, 1), end=date(2025, 12, 31), refresh_recent=2)
    first = len(calls)
    calls.clear()
    sec.fetch_frames(c, start=date(2024, 1, 1), end=date(2025, 12, 31), refresh_recent=2)
    # druhý běh: jen 2 poslední kvartály × 6 tagů, staré prázdné kvartály se už nestahují
    assert first == 6 * 8 and len(calls) == 6 * 2
