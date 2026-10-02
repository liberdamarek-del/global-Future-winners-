import sqlite3

import pytest

from stockradar.lessons import seed_master_prompt_cases
from stockradar.universe import (
    CATALYSTS, COMPANIES, RELATIONSHIPS, add_relationship, add_tracked_company, seed_energy_universe,
)
from tests.conftest import NOW


def test_seed_is_idempotent_and_complete(conn):
    seed_master_prompt_cases(conn, now=NOW)
    first = seed_energy_universe(conn, now=NOW)
    assert first["companies"] == len(COMPANIES) + 1  # + Holtec (pre-IPO)
    assert first["relationships"] == len(RELATIONSHIPS) and first["catalysts"] == len(CATALYSTS)
    assert seed_energy_universe(conn, now=NOW) == {"chain_nodes": 0, "companies": 0, "relationships": 0, "catalysts": 0}


def test_every_relationship_and_catalyst_has_a_source(conn):
    seed_energy_universe(conn, now=NOW)
    for r in conn.execute("SELECT * FROM relationships"):
        assert r["source_url"].startswith("https://") and r["source"]
    for k in conn.execute("SELECT * FROM catalysts"):
        assert k["source_url"].startswith("https://")
        assert k["date_status"] != "VERIFIED" or k["event_date"]


def test_research_helpers(conn):
    seed_energy_universe(conn, now=NOW)
    cid = add_tracked_company(conn, "Example Grid", yahoo_symbol="EXG.DE", exchange="XETRA", currency="EUR",
                              nodes=["GRID"], now=NOW)
    assert conn.execute("SELECT yahoo_symbol, ticker FROM listings WHERE company_id = ?", (cid,)).fetchone()[:] == \
        ("EXG.DE", "EXG")
    rid = add_relationship(conn, party="Example Grid", counterparty="Google", rel_type="SUPPLY", binding="FRAMEWORK",
                           description="test", announced_on="2026-10-01", source="test",
                           source_url="https://example.com", company_id=cid, now=NOW)
    with pytest.raises(sqlite3.IntegrityError, match="§24"):
        with conn:
            conn.execute("UPDATE relationships SET binding = 'FIRM' WHERE id = ?", (rid,))
    with pytest.raises(sqlite3.IntegrityError):
        add_relationship(conn, party="x", counterparty="Google", rel_type="PPA", binding="FIRM", description="x",
                         announced_on="2026-10-01", source="x", source_url="http://insecure", now=NOW)
