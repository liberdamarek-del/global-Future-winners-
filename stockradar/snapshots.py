"""§53: každý update vytvoří historický snapshot stavu radaru."""

import json
import sqlite3
from datetime import datetime

from stockradar import __version__
from stockradar.catalysts import date_text
from stockradar.companies import latest_xtb_check
from stockradar.timeutil import to_iso, utcnow


def radar_state(conn: sqlite3.Connection, *, as_of: datetime) -> dict:
    companies = []
    for c in conn.execute("SELECT * FROM companies ORDER BY id"):
        listings = []
        for l in conn.execute("SELECT * FROM listings WHERE company_id = ? ORDER BY id", (c["id"],)):
            xtb = latest_xtb_check(conn, l["id"], as_of=as_of)
            listings.append({
                "ticker": l["ticker"], "exchange": l["exchange"], "valid_to": l["valid_to"],
                "xtb": xtb["status"] if xtb else "NEOVERENO",
                "xtb_instruments": xtb["instruments"] if xtb else None,
                "xtb_checked_at": xtb["checked_at"] if xtb else None,
            })
        catalysts = [
            {"id": k["id"], "type": k["type_code"], "description": k["description"],
             "date": date_text(k), "status": k["status"]}
            for k in conn.execute(
                "SELECT * FROM catalysts WHERE company_id = ? AND status IN ('UPCOMING','IN_PROGRESS','DELAYED')"
                " ORDER BY id", (c["id"],))
        ]
        companies.append({
            "id": c["id"], "name": c["name"], "country": c["country"], "sector": c["sector"],
            "listing_status": c["listing_status"], "radar_status": c["radar_status"],
            "category": c["category"], "verdict": c["verdict"],
            "listings": listings, "open_catalysts": catalysts,
        })
    return {
        "as_of": to_iso(as_of),
        "companies": companies,
        "predictions_total": conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0],
        "outcomes_total": conn.execute("SELECT COUNT(*) FROM prediction_outcomes").fetchone()[0],
    }


def create_snapshot(conn: sqlite3.Connection, *, label: str | None = None, now: datetime | None = None) -> int:
    now = now or utcnow()
    payload = json.dumps(radar_state(conn, as_of=now), ensure_ascii=False, sort_keys=True)
    with conn:
        cur = conn.execute(
            "INSERT INTO snapshots (taken_at, label, app_version, payload_json) VALUES (?, ?, ?, ?)",
            (to_iso(now), label, __version__, payload),
        )
    return cur.lastrowid
