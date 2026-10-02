import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest

from stockradar import config
from stockradar.catalysts import add_catalyst, set_catalyst_status
from stockradar.companies import record_xtb_check
from stockradar.ledger import (
    LedgerRuleError, PredictionInput, Scores, record_outcome, record_prediction, register_rows,
)
from tests.conftest import NOW


def make_input(listing_id, **overrides):
    base = PredictionInput(
        listing_id=listing_id, horizon="D0_14", price=4.2, currency="USD",
        price_as_of=NOW - timedelta(minutes=30), price_source="test feed",
        category="A", verdict="WATCH", rationale="test", market_cap=180e6, market_cap_currency="USD",
        probability_pct=45, bull_move_pct=150, base_move_pct=10, bear_move_pct=-60,
        scores=Scores(overall_setup=88, rocket=80),
    )
    return replace(base, **overrides)


@pytest.fixture
def xtb_required(monkeypatch):
    """Brána XTB je od 2026-10-02 vypnutá (rozhodnutí uživatele); tyto testy ji zapínají."""
    monkeypatch.setattr(config, "REQUIRE_XTB_FOR_BUY", True)


def xtb_ok(conn, listing_id, days_ago=1):
    return record_xtb_check(conn, listing_id, "ANO", source="xStation search", instruments=["STOCK"],
                            checked_at=NOW - timedelta(days=days_ago))


def test_watch_prediction_recorded_with_copied_state(conn, listing):
    _, listing_id = listing
    pid = record_prediction(conn, make_input(listing_id), now=NOW)
    row = conn.execute("SELECT * FROM predictions WHERE id = ?", (pid,)).fetchone()
    assert row["made_at"] == row["recorded_at"] == "2026-10-02T12:00:00Z"
    assert row["xtb_status"] == "NEOVERENO"
    assert row["price_freshness"] == "FRESH"
    assert row["score_overall_setup"] == 88
    assert row["probability_pct"] == 45 and row["bull_move_pct"] == 150


def test_ledger_is_append_only(conn, listing):
    """§29: XYZ = BUY / 88 zůstává 88, i když se názor později změní."""
    _, listing_id = listing
    pid = record_prediction(conn, make_input(listing_id), now=NOW)
    with pytest.raises(sqlite3.IntegrityError, match="§29"):
        with conn:
            conn.execute("UPDATE predictions SET score_overall_setup = 60 WHERE id = ?", (pid,))
    with pytest.raises(sqlite3.IntegrityError, match="§29"):
        with conn:
            conn.execute("DELETE FROM predictions WHERE id = ?", (pid,))


def test_live_prediction_cannot_be_backdated(conn, listing):
    _, listing_id = listing
    with pytest.raises(LedgerRuleError):
        record_prediction(conn, make_input(listing_id), made_at=NOW - timedelta(days=1), now=NOW)


@pytest.mark.parametrize("overrides", [{"verdict": "SPEC_BUY"}, {"is_main_pick": True}])
def test_buy_without_xtb_check_is_refused(conn, listing, xtb_required, overrides):
    """§5 + poučení XSPRAY."""
    _, listing_id = listing
    with pytest.raises(LedgerRuleError, match="XTB NEOVĚŘENO"):
        record_prediction(conn, make_input(listing_id, **overrides), now=NOW)


def test_buy_not_available_on_xtb_is_refused(conn, listing, xtb_required):
    _, listing_id = listing
    record_xtb_check(conn, listing_id, "NE", source="xStation search", checked_at=NOW - timedelta(days=1))
    with pytest.raises(LedgerRuleError, match="NOT AVAILABLE ON XTB"):
        record_prediction(conn, make_input(listing_id, verdict="SPEC_BUY"), now=NOW)


def test_buy_with_stale_xtb_check_is_refused(conn, listing, xtb_required):
    _, listing_id = listing
    xtb_ok(conn, listing_id, days_ago=45)
    with pytest.raises(LedgerRuleError, match="ověř znovu"):
        record_prediction(conn, make_input(listing_id, verdict="SPEC_BUY"), now=NOW)


def test_buy_with_fresh_xtb_check_is_recorded(conn, listing):
    _, listing_id = listing
    check_id = xtb_ok(conn, listing_id)
    pid = record_prediction(conn, make_input(listing_id, verdict="SPEC_BUY", is_main_pick=True), now=NOW)
    row = conn.execute("SELECT xtb_status, xtb_instruments, xtb_check_id FROM predictions WHERE id = ?",
                       (pid,)).fetchone()
    assert tuple(row) == ("ANO", "STOCK", check_id)


def test_buy_without_xtb_allowed_by_default(conn, listing):
    """Rozhodnutí uživatele 2026-10-02: XTB jen informativně — doporučení se zapíše s XTB = NEOVĚŘENO."""
    assert config.REQUIRE_XTB_FOR_BUY is False
    _, listing_id = listing
    pid = record_prediction(conn, make_input(listing_id, verdict="SPEC_BUY", is_main_pick=True), now=NOW)
    assert conn.execute("SELECT xtb_status FROM predictions WHERE id = ?", (pid,)).fetchone()[0] == "NEOVERENO"


def test_xtb_db_trigger_removed_by_migration_0002(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert "predictions_xtb_gate" not in names
    assert {"predictions_no_update", "predictions_no_delete"} <= names


@pytest.mark.parametrize("status", ["OCCURRED", "IN_PROGRESS", "CANCELLED"])
def test_buy_on_finished_or_running_catalyst_is_refused(conn, listing, status):
    """§2 + poučení RARE: hledáme firmu PŘED katalyzátorem."""
    company_id, listing_id = listing
    xtb_ok(conn, listing_id)
    cid = add_catalyst(conn, company_id, "FDA_DECISION", "PDUFA", date_status="VERIFIED",
                       event_date="2026-10-10", source="FDA", now=NOW - timedelta(days=10))
    set_catalyst_status(conn, cid, status)
    with pytest.raises(LedgerRuleError, match="PŘED"):
        record_prediction(conn, make_input(listing_id, verdict="SPEC_BUY", catalyst_id=cid), now=NOW)


def test_buy_on_past_catalyst_date_is_refused(conn, listing):
    company_id, listing_id = listing
    xtb_ok(conn, listing_id)
    cid = add_catalyst(conn, company_id, "FDA_DECISION", "PDUFA", date_status="VERIFIED",
                       event_date="2026-09-30", source="FDA", now=NOW - timedelta(days=10))
    with pytest.raises(LedgerRuleError, match="uplynulo"):
        record_prediction(conn, make_input(listing_id, verdict="SPEC_BUY", catalyst_id=cid), now=NOW)


def test_catalyst_snapshot_copied_into_prediction(conn, listing):
    company_id, listing_id = listing
    cid = add_catalyst(conn, company_id, "CLINICAL_DATA", "Phase 3 topline", date_status="ESTIMATED",
                       window=("2026-10-01", "2026-12-31"), now=NOW - timedelta(days=1))
    pid = record_prediction(conn, make_input(listing_id, catalyst_id=cid), now=NOW)
    row = conn.execute("SELECT catalyst_text, catalyst_date_text, catalyst_date_status FROM predictions"
                       " WHERE id = ?", (pid,)).fetchone()
    assert tuple(row) == ("Phase 3 topline", "2026-10-01..2026-12-31 (ESTIMATED)", "ESTIMATED")


def test_backtest_cannot_use_information_from_the_future(conn, listing):
    """§59: informace zveřejněná 10. září nesmí být použita pro predikci z 5. září."""
    company_id, listing_id = listing
    cid = add_catalyst(conn, company_id, "CONTRACT", "kontrakt", date_status="NEOVERENO",
                       published_at=NOW.replace(month=9, day=10), now=NOW)
    made_at = NOW.replace(month=9, day=5)
    with pytest.raises(LedgerRuleError, match="look-ahead"):
        record_prediction(conn, make_input(listing_id, catalyst_id=cid, price_as_of=made_at),
                          mode="BACKTEST", made_at=made_at, now=NOW)


def test_backtest_uses_xtb_state_known_at_that_time(conn, listing, xtb_required):
    _, listing_id = listing
    xtb_ok(conn, listing_id, days_ago=1)  # ověřeno až 1. 10.
    made_at = NOW - timedelta(days=20)
    with pytest.raises(LedgerRuleError, match="XTB NEOVĚŘENO"):
        record_prediction(conn, make_input(listing_id, verdict="SPEC_BUY", price_as_of=made_at),
                          mode="BACKTEST", made_at=made_at, now=NOW)


def test_stale_price_is_flagged(conn, listing):
    _, listing_id = listing
    pid = record_prediction(conn, make_input(listing_id, price_as_of=NOW - timedelta(hours=5)), now=NOW)
    assert conn.execute("SELECT price_freshness FROM predictions WHERE id = ?", (pid,)).fetchone()[0] == "STALE"


def test_future_price_is_refused(conn, listing):
    _, listing_id = listing
    with pytest.raises(LedgerRuleError):
        record_prediction(conn, make_input(listing_id, price_as_of=NOW + timedelta(minutes=1)), now=NOW)


def test_scores_validated():
    with pytest.raises(ValueError):
        Scores(rocket=101)
    with pytest.raises(ValueError):
        Scores(rocket=50.5)


def test_outcome_cannot_be_recorded_early(conn, listing):
    _, listing_id = listing
    pid = record_prediction(conn, make_input(listing_id), now=NOW)
    with pytest.raises(LedgerRuleError, match="předčasné"):
        record_outcome(conn, pid, horizon_days=7, price=5, price_source="feed",
                       observed_at=NOW + timedelta(days=6), result="HIT", now=NOW + timedelta(days=6))


def test_outcomes_build_register_and_are_immutable(conn, listing):
    _, listing_id = listing
    pid = record_prediction(conn, make_input(listing_id), now=NOW)
    later = NOW + timedelta(days=31)
    record_outcome(conn, pid, horizon_days=7, price=5.04, price_source="feed", observed_at=NOW + timedelta(days=7),
                   result="PARTIAL", max_price=5.5, min_price=4.0, now=later)
    oid = record_outcome(conn, pid, horizon_days=30, price=2.1, price_source="feed", observed_at=later,
                         result="MISS", max_price=6.0, min_price=2.0, deviation="-50 % vs base +10 %",
                         reason="CRL", lesson="kontrolovat CMC", now=later)
    assert conn.execute("SELECT return_pct FROM prediction_outcomes WHERE id = ?", (oid,)).fetchone()[0] == -50.0
    [row] = register_rows(conn)
    assert (row["price_7d"], row["price_14d"], row["price_30d"]) == (5.04, None, 2.1)
    assert (row["period_max"], row["period_min"], row["result"]) == (6.0, 2.0, "MISS")
    with pytest.raises(sqlite3.IntegrityError, match="§30"):
        with conn:
            conn.execute("UPDATE prediction_outcomes SET result = 'HIT'")
