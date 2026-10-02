import sqlite3

import pytest

from stockradar.db import available_migrations, migrate, open_db, schema_version


def test_migrations_apply_and_are_idempotent():
    conn = open_db(":memory:")
    assert schema_version(conn) == len(available_migrations())
    assert migrate(conn) == []


def test_foreign_keys_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("INSERT INTO listings (company_id, ticker, exchange, created_at)"
                         " VALUES (999, 'X', 'NASDAQ', '2026-10-02T00:00:00Z')")


def test_companies_cannot_be_deleted(conn, listing):
    company_id, _ = listing
    with pytest.raises(sqlite3.IntegrityError, match="§60"):
        with conn:
            conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))
