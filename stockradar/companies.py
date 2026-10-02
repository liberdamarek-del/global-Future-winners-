"""Firmy, listingy, kontroly XTB a změny verdiktu (§5, §33, §34, §60)."""

import sqlite3
from datetime import datetime

from stockradar.enums import Category, RadarStatus, Verdict, XtbInstrument, XtbStatus, label
from stockradar.timeutil import parse_iso, to_iso, utcnow

STATUS_FIELDS = {"category": Category, "verdict": Verdict, "radar_status": RadarStatus}


class NotFoundError(LookupError):
    pass


def add_company(
    conn: sqlite3.Connection,
    name: str,
    *,
    country: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    listing_status: str = "ACTIVE",
    notes: str | None = None,
    now: datetime | None = None,
) -> int:
    ts = to_iso(now or utcnow())
    with conn:
        cur = conn.execute(
            "INSERT INTO companies (name, country, sector, industry, listing_status, notes, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, country, sector, industry, listing_status, notes, ts, ts),
        )
    return cur.lastrowid


def get_company(conn: sqlite3.Connection, company_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"firma id={company_id} neexistuje")
    return row


def find_company(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM companies WHERE name = ?", (name,)).fetchone()


def add_listing(
    conn: sqlite3.Connection,
    company_id: int,
    ticker: str,
    exchange: str,
    *,
    currency: str | None = None,
    security_type: str = "COMMON",
    is_primary: bool = False,
    valid_from: str | None = None,
    now: datetime | None = None,
) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO listings (company_id, ticker, exchange, currency, security_type, is_primary,"
            " valid_from, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (company_id, ticker.upper(), exchange, currency, security_type, int(is_primary),
             valid_from, to_iso(now or utcnow())),
        )
    return cur.lastrowid


def get_listing(conn: sqlite3.Connection, listing_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"listing id={listing_id} neexistuje")
    return row


def find_listing(conn: sqlite3.Connection, ticker: str, exchange: str | None = None) -> sqlite3.Row:
    """Najde aktuálně platný listing. Při nejednoznačnosti vyžaduje burzu — žádné hádání."""
    sql = "SELECT * FROM listings WHERE ticker = ? AND valid_to IS NULL"
    params: list = [ticker.upper()]
    if exchange is not None:
        sql += " AND exchange = ?"
        params.append(exchange)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        raise NotFoundError(f"listing {ticker} ({exchange or 'libovolná burza'}) neexistuje")
    if len(rows) > 1:
        exchanges = ", ".join(r["exchange"] for r in rows)
        raise LookupError(f"ticker {ticker} je na více burzách ({exchanges}) — uveď burzu")
    return rows[0]


def record_xtb_check(
    conn: sqlite3.Connection,
    listing_id: int,
    status: str,
    *,
    source: str,
    instruments: tuple[str, ...] | list[str] = (),
    xtb_symbol: str | None = None,
    note: str | None = None,
    checked_at: datetime | None = None,
) -> int:
    """Zapíše výsledek kontroly dostupnosti na XTB. `source` = kde/jak bylo ověřeno."""
    XtbStatus(status)
    normalized = sorted({XtbInstrument(i).value for i in instruments})
    if status == XtbStatus.ANO and not normalized:
        raise ValueError("XTB = ANO vyžaduje typ instrumentu (STOCK / CFD / ETF / OTHER)")
    if status != XtbStatus.ANO and normalized:
        raise ValueError("instrumenty se uvádějí jen u XTB = ANO")
    with conn:
        cur = conn.execute(
            "INSERT INTO xtb_checks (listing_id, status, instruments, xtb_symbol, source, note, checked_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (listing_id, status, ",".join(normalized) or None, xtb_symbol, source, note,
             to_iso(checked_at or utcnow())),
        )
    return cur.lastrowid


def latest_xtb_check(
    conn: sqlite3.Connection, listing_id: int, *, as_of: datetime | None = None
) -> sqlite3.Row | None:
    """Poslední kontrola XTB známá k okamžiku `as_of` (bez look-ahead)."""
    as_of_iso = to_iso(as_of or utcnow())
    return conn.execute(
        "SELECT * FROM xtb_checks WHERE listing_id = ? AND checked_at <= ?"
        " ORDER BY checked_at DESC, id DESC LIMIT 1",
        (listing_id, as_of_iso),
    ).fetchone()


def xtb_check_age(check: sqlite3.Row, as_of: datetime):
    return as_of - parse_iso(check["checked_at"])


def change_status(
    conn: sqlite3.Connection,
    company_id: int,
    field: str,
    new_value: str,
    *,
    reason: str,
    source: str | None = None,
    now: datetime | None = None,
) -> str:
    """§34: změní kategorii / verdikt / radar status a trvale zapíše důvod.

    Vrací text pro uživatele: 'MĚNÍM VERDIKT. …' nebo 'Verdikt zůstává beze změny.'
    """
    if field not in STATUS_FIELDS:
        raise ValueError(f"neznámé pole {field!r}, povoleno: {', '.join(STATUS_FIELDS)}")
    STATUS_FIELDS[field](new_value)
    if not reason or not reason.strip():
        raise ValueError("§34: změna verdiktu musí mít důvod")
    company = get_company(conn, company_id)
    old_value = company[field]
    if old_value == new_value:
        return "Verdikt zůstává beze změny."
    ts = to_iso(now or utcnow())
    with conn:
        conn.execute(f"UPDATE companies SET {field} = ?, updated_at = ? WHERE id = ?",
                     (new_value, ts, company_id))
        conn.execute(
            "INSERT INTO status_changes (company_id, field, old_value, new_value, reason, source, changed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (company_id, field, old_value, new_value, reason.strip(), source, ts),
        )
    return (f"MĚNÍM VERDIKT. [{company['name']} / {field}] "
            f"Původně: {label(old_value)} | Nově: {label(new_value)} | Důvod: {reason.strip()}")
