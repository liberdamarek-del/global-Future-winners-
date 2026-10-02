"""Integrace: zápis dat -> export state/ -> obnova do nové DB -> identický export."""

from datetime import timedelta

import pytest

from stockradar.catalysts import add_catalyst, supersede_catalyst
from stockradar.companies import change_status, record_xtb_check
from stockradar.db import open_db
from stockradar.ledger import PredictionInput, Scores, record_outcome, record_prediction
from stockradar.lessons import seed_master_prompt_cases
from stockradar.snapshots import create_snapshot
from stockradar.state_io import TABLES, export_state, restore_state, unexported_tables
from tests.conftest import NOW


def populate(conn, listing):
    company_id, listing_id = listing
    seed_master_prompt_cases(conn, now=NOW)
    record_xtb_check(conn, listing_id, "ANO", source="xStation", instruments=["STOCK", "CFD"],
                     checked_at=NOW - timedelta(days=1))
    old = add_catalyst(conn, company_id, "FDA_DECISION", "PDUFA", date_status="VERIFIED",
                       event_date="2026-10-10", source="FDA", now=NOW - timedelta(days=2))
    new = add_catalyst(conn, company_id, "FDA_DECISION", "PDUFA (posun)", date_status="VERIFIED",
                       event_date="2026-10-12", source="8-K", now=NOW - timedelta(days=1))
    supersede_catalyst(conn, old, new)
    change_status(conn, company_id, "category", "A", reason="test", now=NOW)
    pid = record_prediction(conn, PredictionInput(
        listing_id=listing_id, horizon="D0_14", price=3.3, currency="USD", price_as_of=NOW,
        price_source="feed", category="A", verdict="SPEC_BUY", is_main_pick=True, rationale="test",
        catalyst_id=new, probability_pct=55.5, bull_move_pct=120.25, bear_move_pct=-45,
        scores=Scores(overall_setup=81, rocket=77)), now=NOW)
    record_outcome(conn, pid, horizon_days=7, price=4.1, price_source="feed",
                   observed_at=NOW + timedelta(days=7), result="HIT", now=NOW + timedelta(days=8))
    create_snapshot(conn, label="test", now=NOW)


def test_export_restore_roundtrip(conn, listing, tmp_path):
    populate(conn, listing)
    first = export_state(conn, tmp_path)
    assert first["predictions"] == 1 and first["lessons"] == 9 and first["catalysts"] == 2
    before = {t: (tmp_path / f"{t}.jsonl").read_text(encoding="utf-8") for t in TABLES}

    restored = open_db(":memory:")
    assert restore_state(restored, tmp_path) == first
    assert unexported_tables(restored, tmp_path) == []
    export_state(restored, tmp_path)
    after = {t: (tmp_path / f"{t}.jsonl").read_text(encoding="utf-8") for t in TABLES}
    assert after == before


def test_unexported_changes_detected(conn, listing, tmp_path):
    company_id, _ = listing
    export_state(conn, tmp_path)
    assert unexported_tables(conn, tmp_path) == []
    change_status(conn, company_id, "verdict", "WATCH", reason="test", now=NOW)
    assert unexported_tables(conn, tmp_path) == ["companies", "status_changes"]


def test_restore_refuses_non_empty_db(conn, listing, tmp_path):
    export_state(conn, tmp_path)
    with pytest.raises(RuntimeError, match="prázdnou"):
        restore_state(conn, tmp_path)


def test_restore_rejects_unknown_columns(listing, conn, tmp_path):
    export_state(conn, tmp_path)
    path = tmp_path / "companies.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace('"country"', '"země"'), encoding="utf-8")
    with pytest.raises(RuntimeError, match="neznámé sloupce"):
        restore_state(open_db(":memory:"), tmp_path)
