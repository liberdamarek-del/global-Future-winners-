"""§52: kvalita dat — stará data se nesmí vydávat za live."""

from datetime import datetime, timedelta

from stockradar.config import PRICE_MAX_AGE


def freshness(as_of: datetime, now: datetime, max_age: timedelta = PRICE_MAX_AGE) -> str:
    """'FRESH' nebo 'STALE' (zobrazuje se jako DATA STALE)."""
    if as_of > now:
        raise ValueError("časová značka dat je v budoucnosti")
    return "FRESH" if now - as_of <= max_age else "STALE"


def freshness_label(value: str) -> str:
    return "DATA STALE" if value == "STALE" else value
