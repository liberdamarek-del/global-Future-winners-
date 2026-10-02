import sqlite3
from datetime import timedelta

import pytest

from stockradar.catalysts import (
    add_catalyst, date_text, set_catalyst_status, supersede_catalyst, upcoming_catalysts,
)
from tests.conftest import NOW


def test_verified_requires_exact_date_and_source(conn, listing):
    company_id, _ = listing
    with pytest.raises(ValueError, match="zdroj"):
        add_catalyst(conn, company_id, "FDA_DECISION", "PDUFA", date_status="VERIFIED",
                     event_date="2026-10-10", now=NOW)
    cid = add_catalyst(conn, company_id, "FDA_DECISION", "PDUFA", date_status="VERIFIED",
                       event_date="2026-10-10", source="FDA / 8-K", now=NOW)
    assert date_text(conn.execute("SELECT * FROM catalysts WHERE id = ?", (cid,)).fetchone()) == \
        "2026-10-10 (VERIFIED)"


def test_estimate_cannot_pretend_to_be_fact(conn, listing):
    company_id, _ = listing
    with pytest.raises(ValueError, match="odhad"):
        add_catalyst(conn, company_id, "CLINICAL_DATA", "Phase 3 topline", date_status="ESTIMATED",
                     event_date="2026-11-15", now=NOW)
    # Ani ruční SQL to neobejde.
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO catalysts (company_id, type_code, description, date_status, event_date,"
                " published_at, recorded_at) VALUES (?, 'CLINICAL_DATA', 'x', 'ESTIMATED', '2026-11-15', ?, ?)",
                (company_id, "2026-10-02T00:00:00Z", "2026-10-02T00:00:00Z"))


def test_estimated_requires_ordered_window(conn, listing):
    company_id, _ = listing
    with pytest.raises(ValueError):
        add_catalyst(conn, company_id, "EARNINGS", "Q3", date_status="ESTIMATED", now=NOW)
    with pytest.raises(ValueError):
        add_catalyst(conn, company_id, "EARNINGS", "Q3", date_status="ESTIMATED",
                     window=("2026-11-30", "2026-11-01"), now=NOW)


def test_unverified_has_no_date(conn, listing):
    company_id, _ = listing
    with pytest.raises(ValueError):
        add_catalyst(conn, company_id, "OTHER", "x", date_status="NEOVERENO", window=("2026-11-01", "2026-11-30"))


def test_published_at_cannot_be_future(conn, listing):
    company_id, _ = listing
    with pytest.raises(ValueError):
        add_catalyst(conn, company_id, "OTHER", "x", date_status="NEOVERENO",
                     published_at=NOW + timedelta(days=1), now=NOW)


def test_content_is_immutable_but_status_can_change(conn, listing):
    company_id, _ = listing
    cid = add_catalyst(conn, company_id, "FDA_DECISION", "PDUFA", date_status="VERIFIED",
                       event_date="2026-10-10", source="FDA", now=NOW)
    with pytest.raises(sqlite3.IntegrityError, match="§10"):
        with conn:
            conn.execute("UPDATE catalysts SET event_date = '2026-12-10' WHERE id = ?", (cid,))
    set_catalyst_status(conn, cid, "OCCURRED")
    assert conn.execute("SELECT status FROM catalysts WHERE id = ?", (cid,)).fetchone()[0] == "OCCURRED"


def test_supersede_keeps_history(conn, listing):
    company_id, _ = listing
    old = add_catalyst(conn, company_id, "FDA_DECISION", "PDUFA", date_status="VERIFIED",
                       event_date="2026-10-10", source="FDA", now=NOW)
    new = add_catalyst(conn, company_id, "FDA_DECISION", "PDUFA prodloužena", date_status="VERIFIED",
                       event_date="2027-01-10", source="8-K", now=NOW)
    supersede_catalyst(conn, old, new)
    row = conn.execute("SELECT status, superseded_by, event_date FROM catalysts WHERE id = ?", (old,)).fetchone()
    assert tuple(row) == ("SUPERSEDED", new, "2026-10-10")


def test_upcoming_window_includes_estimates_marked_as_such(conn, listing):
    company_id, _ = listing
    add_catalyst(conn, company_id, "FDA_DECISION", "in range", date_status="VERIFIED",
                 event_date="2026-10-10", source="FDA", now=NOW)
    add_catalyst(conn, company_id, "FDA_DECISION", "too far", date_status="VERIFIED",
                 event_date="2026-12-10", source="FDA", now=NOW)
    add_catalyst(conn, company_id, "EARNINGS", "Q3 window", date_status="ESTIMATED",
                 window=("2026-10-01", "2026-10-31"), now=NOW)
    add_catalyst(conn, company_id, "OTHER", "no date", date_status="NEOVERENO", now=NOW)
    done = add_catalyst(conn, company_id, "FDA_DECISION", "done", date_status="VERIFIED",
                        event_date="2026-10-05", source="FDA", now=NOW)
    set_catalyst_status(conn, done, "OCCURRED")
    rows = upcoming_catalysts(conn, today=NOW.date(), within_days=14)
    assert [(r["description"], r["date_status"]) for r in rows] == [
        ("Q3 window", "ESTIMATED"), ("in range", "VERIFIED")]
