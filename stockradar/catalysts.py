"""Katalyzátory (§10): přesné datum jen když je ověřené, jinak okno — odhad se nesmí tvářit jako fakt."""

import sqlite3
from datetime import date, datetime, timedelta

from stockradar.enums import CatalystStatus, DateStatus
from stockradar.timeutil import parse_date, to_iso, utcnow

OPEN_STATUSES = (CatalystStatus.UPCOMING, CatalystStatus.DELAYED)


def add_catalyst(
    conn: sqlite3.Connection,
    company_id: int,
    type_code: str,
    description: str,
    *,
    date_status: str,
    event_date: str | None = None,
    window: tuple[str, str] | None = None,
    source: str | None = None,
    source_url: str | None = None,
    published_at: datetime | None = None,
    status: str = "UPCOMING",
    now: datetime | None = None,
) -> int:
    """Zapíše katalyzátor.

    date_status=VERIFIED  -> event_date 'YYYY-MM-DD' + source (povinné)
    ESTIMATED/UNCERTAIN   -> window=('YYYY-MM-DD', 'YYYY-MM-DD'), např. měsíc nebo kvartál
    NEOVERENO             -> bez data
    published_at = kdy byla informace veřejná; neznámo -> okamžik zápisu (konzervativní, §59).
    """
    DateStatus(date_status)
    CatalystStatus(status)
    if status == CatalystStatus.SUPERSEDED:
        raise ValueError("nový katalyzátor nemůže být SUPERSEDED — použij supersede_catalyst()")
    if date_status == DateStatus.VERIFIED:
        if event_date is None or window is not None:
            raise ValueError("VERIFIED vyžaduje přesné event_date a žádné okno")
        if not source or not source.strip():
            raise ValueError("VERIFIED datum vyžaduje zdroj (§10, §45)")
        parse_date(event_date)
    elif date_status in (DateStatus.ESTIMATED, DateStatus.UNCERTAIN):
        if event_date is not None:
            raise ValueError("§10: odhad nesmí mít přesné datum — použij okno (window)")
        if window is None:
            raise ValueError(f"{date_status} vyžaduje okno window=(od, do)")
        start, end = parse_date(window[0]), parse_date(window[1])
        if start > end:
            raise ValueError("začátek okna je po jeho konci")
    else:
        if event_date is not None or window is not None:
            raise ValueError("NEOVERENO katalyzátor nemá datum ani okno")

    now_iso = to_iso(now or utcnow())
    published_iso = to_iso(published_at) if published_at else now_iso
    if published_iso > now_iso:
        raise ValueError("published_at nemůže být v budoucnosti")
    window_start, window_end = window if window else (None, None)
    with conn:
        cur = conn.execute(
            "INSERT INTO catalysts (company_id, type_code, description, date_status, event_date,"
            " window_start, window_end, status, source, source_url, published_at, recorded_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company_id, type_code, description, date_status, event_date, window_start, window_end,
             status, source, source_url, published_iso, now_iso),
        )
    return cur.lastrowid


def get_catalyst(conn: sqlite3.Connection, catalyst_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM catalysts WHERE id = ?", (catalyst_id,)).fetchone()
    if row is None:
        raise LookupError(f"katalyzátor id={catalyst_id} neexistuje")
    return row


def set_catalyst_status(conn: sqlite3.Connection, catalyst_id: int, status: str) -> None:
    CatalystStatus(status)
    if status == CatalystStatus.SUPERSEDED:
        raise ValueError("pro SUPERSEDED použij supersede_catalyst()")
    with conn:
        cur = conn.execute("UPDATE catalysts SET status = ? WHERE id = ?", (status, catalyst_id))
    if cur.rowcount == 0:
        raise LookupError(f"katalyzátor id={catalyst_id} neexistuje")


def supersede_catalyst(conn: sqlite3.Connection, old_id: int, new_id: int) -> None:
    """Posun termínu / upřesnění: starý záznam zůstává v historii, ukazuje na nový."""
    old, new = get_catalyst(conn, old_id), get_catalyst(conn, new_id)
    if old["company_id"] != new["company_id"]:
        raise ValueError("nahrazující katalyzátor musí patřit stejné firmě")
    with conn:
        conn.execute("UPDATE catalysts SET status = 'SUPERSEDED', superseded_by = ? WHERE id = ?",
                     (new_id, old_id))


def date_text(row: sqlite3.Row) -> str:
    """Datum katalyzátoru pro zobrazení vždy včetně míry jistoty."""
    status = row["date_status"]
    if status == DateStatus.VERIFIED:
        return f"{row['event_date']} (VERIFIED)"
    if status in (DateStatus.ESTIMATED, DateStatus.UNCERTAIN):
        return f"{row['window_start']}..{row['window_end']} ({status})"
    return "NEOVĚŘENO"


def upcoming_catalysts(
    conn: sqlite3.Connection, *, today: date, within_days: int
) -> list[sqlite3.Row]:
    """Otevřené katalyzátory, které mohou nastat v [today, today+within_days].

    Patří sem i odhady, jejichž okno se s intervalem překrývá — v datech zůstávají označené jako odhad.
    """
    start = today.isoformat()
    end = (today + timedelta(days=within_days)).isoformat()
    return conn.execute(
        "SELECT c.*, co.name AS company_name FROM catalysts c JOIN companies co ON co.id = c.company_id"
        " WHERE c.status IN ('UPCOMING','DELAYED') AND ("
        "   (c.date_status = 'VERIFIED' AND c.event_date BETWEEN ? AND ?)"
        "   OR (c.date_status IN ('ESTIMATED','UNCERTAIN') AND c.window_start <= ? AND c.window_end >= ?))"
        " ORDER BY COALESCE(c.event_date, c.window_start), c.id",
        (start, end, end, start),
    ).fetchall()
