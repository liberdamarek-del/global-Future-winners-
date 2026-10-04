"""§52: kvalita dat — stará data se nesmí vydávat za live."""

from datetime import datetime, timedelta

from stockradar.config import PRICE_MAX_AGE

MAX_CLOSE_AGE = timedelta(days=3, hours=12)  # pátek večer → pondělí ráno


def freshness(as_of: datetime, now: datetime, max_age: timedelta = PRICE_MAX_AGE) -> str:
    """'FRESH' nebo 'STALE' (zobrazuje se jako DATA STALE).

    FRESH = cena mladší než `max_age`, NEBO je to závěrečná cena z dřívějšího dne a od ní neproběhla další
    obchodní seance (mezi dnem ceny a dneškem včetně není žádný pracovní den: pátek → sobota/neděle).
    Stejný den platí jen limit `max_age` (nevíme, jestli burza už zavřela). Svátky se nezohledňují
    (konzervativně: svátek se počítá jako obchodní den → STALE).
    """
    if as_of > now:
        raise ValueError("časová značka dat je v budoucnosti")
    if now - as_of <= max_age:
        return "FRESH"
    if now - as_of > MAX_CLOSE_AGE or now.date() == as_of.date():
        return "STALE"
    d, sessions = as_of.date() + timedelta(days=1), 0
    while d < now.date():
        sessions += d.weekday() < 5
        d += timedelta(days=1)
    if now.weekday() < 5:
        sessions += 1  # dnešní seance už mohla začít
    return "FRESH" if sessions == 0 else "STALE"


def freshness_label(value: str) -> str:
    return "DATA STALE" if value == "STALE" else value
