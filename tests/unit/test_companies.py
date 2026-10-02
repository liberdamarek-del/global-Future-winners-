import sqlite3
from datetime import timedelta

import pytest

from stockradar.companies import (
    add_listing, change_status, find_listing, latest_xtb_check, record_xtb_check,
)
from tests.conftest import NOW


def test_change_status_logs_reason(conn, listing):
    company_id, _ = listing
    msg = change_status(conn, company_id, "category", "A", reason="silný setup", now=NOW)
    assert msg.startswith("MĚNÍM VERDIKT.")
    msg = change_status(conn, company_id, "category", "C", reason="FDA CRL", now=NOW)
    assert "Původně: A" in msg and "Nově: C" in msg and "Důvod: FDA CRL" in msg
    rows = conn.execute("SELECT old_value, new_value, reason FROM status_changes ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [(None, "A", "silný setup"), ("A", "C", "FDA CRL")]


def test_unchanged_status_is_reported_and_not_logged(conn, listing):
    company_id, _ = listing
    change_status(conn, company_id, "verdict", "WATCH", reason="první hodnocení", now=NOW)
    assert change_status(conn, company_id, "verdict", "WATCH", reason="znovu", now=NOW) == \
        "Verdikt zůstává beze změny."
    assert conn.execute("SELECT COUNT(*) FROM status_changes").fetchone()[0] == 1


@pytest.mark.parametrize("field,value,reason", [
    ("category", "A", "  "),
    ("category", "Z", "důvod"),
    ("price", "1", "důvod"),
])
def test_change_status_validation(conn, listing, field, value, reason):
    company_id, _ = listing
    with pytest.raises(ValueError):
        change_status(conn, company_id, field, value, reason=reason)


def test_status_history_is_immutable(conn, listing):
    company_id, _ = listing
    change_status(conn, company_id, "category", "B", reason="x", now=NOW)
    with pytest.raises(sqlite3.IntegrityError, match="§34"):
        with conn:
            conn.execute("UPDATE status_changes SET new_value = 'A+'")


def test_xtb_requires_instrument_when_available(conn, listing):
    _, listing_id = listing
    with pytest.raises(ValueError):
        record_xtb_check(conn, listing_id, "ANO", source="xStation")
    with pytest.raises(ValueError):
        record_xtb_check(conn, listing_id, "NE", source="xStation", instruments=["CFD"])
    with pytest.raises(ValueError):
        record_xtb_check(conn, listing_id, "ANO", source="xStation", instruments=["FUTURES"])


def test_latest_xtb_check_respects_time(conn, listing):
    _, listing_id = listing
    record_xtb_check(conn, listing_id, "NE", source="xStation", checked_at=NOW - timedelta(days=5))
    record_xtb_check(conn, listing_id, "ANO", source="xStation", instruments=["STOCK", "CFD"],
                     checked_at=NOW - timedelta(days=1))
    assert latest_xtb_check(conn, listing_id, as_of=NOW)["status"] == "ANO"
    assert latest_xtb_check(conn, listing_id, as_of=NOW)["instruments"] == "CFD,STOCK"
    assert latest_xtb_check(conn, listing_id, as_of=NOW - timedelta(days=3))["status"] == "NE"
    assert latest_xtb_check(conn, listing_id, as_of=NOW - timedelta(days=10)) is None


def test_find_listing_refuses_to_guess(conn, listing):
    company_id, _ = listing
    add_listing(conn, company_id, "TBIO", "ASX", now=NOW)
    with pytest.raises(LookupError, match="uveď burzu"):
        find_listing(conn, "TBIO")
    assert find_listing(conn, "tbio", "ASX")["exchange"] == "ASX"
