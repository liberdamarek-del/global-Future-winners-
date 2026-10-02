from datetime import datetime, timezone

import pytest

from stockradar.companies import add_company, add_listing
from stockradar.db import open_db

NOW = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    c = open_db(":memory:")
    yield c
    c.close()


@pytest.fixture
def listing(conn):
    """Testovací firma s jedním listingem. Vrací (company_id, listing_id)."""
    company_id = add_company(conn, "Test Bio", country="US", sector="Healthcare", now=NOW)
    listing_id = add_listing(conn, company_id, "TBIO", "NASDAQ", currency="USD", is_primary=True, now=NOW)
    return company_id, listing_id
