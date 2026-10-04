from datetime import timedelta

import pytest

from stockradar.data_quality import freshness, freshness_label
from tests.conftest import NOW


def test_fresh_within_four_hours():
    assert freshness(NOW - timedelta(hours=4), NOW) == "FRESH"


def test_stale_after_four_hours():
    assert freshness(NOW - timedelta(hours=4, minutes=1), NOW) == "STALE"
    assert freshness_label("STALE") == "DATA STALE"


def test_future_timestamp_rejected():
    with pytest.raises(ValueError):
        freshness(NOW + timedelta(minutes=1), NOW)


def test_last_close_stays_fresh_over_weekend():
    from datetime import datetime, timezone
    friday_close = datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc)
    assert freshness(friday_close, datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)) == "FRESH"   # sobota
    assert freshness(friday_close, datetime(2026, 10, 4, 22, 0, tzinfo=timezone.utc)) == "FRESH"  # neděle
    assert freshness(friday_close, datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)) == "STALE"   # pondělí
    tuesday_close = datetime(2026, 10, 6, 20, 0, tzinfo=timezone.utc)
    assert freshness(tuesday_close, datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)) == "STALE"  # středa
