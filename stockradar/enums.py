"""Slovníky hodnot z MASTER PROMPTu. Kódy jsou ASCII (DB), popisky pro zobrazení."""

from enum import StrEnum


class Category(StrEnum):  # §21
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    NEOVERENO = "NEOVERENO"


class Verdict(StrEnum):  # §37
    SPEC_BUY = "SPEC_BUY"
    WATCH = "WATCH"
    HOLD = "HOLD"
    NEKUPOVAT = "NEKUPOVAT"
    TOO_LATE = "TOO_LATE"
    AVOID = "AVOID"


class RadarStatus(StrEnum):  # §33
    ACTIVE = "ACTIVE"
    WATCH = "WATCH"
    WAIT = "WAIT"
    TOO_LATE = "TOO_LATE"
    REJECT = "REJECT"
    REFERENCE = "REFERENCE"  # učební / referenční případ, ne nákupní kandidát
    REMOVED = "REMOVED"
    NEOVERENO = "NEOVERENO"


class XtbStatus(StrEnum):  # §5
    ANO = "ANO"
    NE = "NE"
    NEOVERENO = "NEOVERENO"


class XtbInstrument(StrEnum):  # §5: skutečná akcie vs CFD vs jiný instrument
    STOCK = "STOCK"
    CFD = "CFD"
    ETF = "ETF"
    OTHER = "OTHER"


class DateStatus(StrEnum):  # §10
    VERIFIED = "VERIFIED"
    ESTIMATED = "ESTIMATED"
    UNCERTAIN = "UNCERTAIN"
    NEOVERENO = "NEOVERENO"


class CatalystStatus(StrEnum):
    UPCOMING = "UPCOMING"
    IN_PROGRESS = "IN_PROGRESS"
    OCCURRED = "OCCURRED"
    DELAYED = "DELAYED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class Horizon(StrEnum):  # §1
    D0_14 = "D0_14"
    D15_45 = "D15_45"
    M6_PLUS = "M6_PLUS"


class OutcomeResult(StrEnum):
    HIT = "HIT"
    PARTIAL = "PARTIAL"
    MISS = "MISS"
    INVALIDATED = "INVALIDATED"
    NEOVERENO = "NEOVERENO"


LABELS = {
    "NEOVERENO": "NEOVĚŘENO",
    "SPEC_BUY": "spekulativní BUY",
    "TOO_LATE": "TOO LATE",
    "D0_14": "0–14 dní",
    "D15_45": "15–45 dní",
    "M6_PLUS": "6M–10+ let",
}


def label(value: str | None) -> str:
    """Popisek pro zobrazení; chybějící hodnota se zobrazí jako NEOVĚŘENO."""
    if value is None:
        return "NEOVĚŘENO"
    return LABELS.get(value, value)
