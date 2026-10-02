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
