import json
import sqlite3

import pytest

from stockradar.lessons import MASTER_PROMPT_CASES, seed_master_prompt_cases
from tests.conftest import NOW


def test_seed_creates_all_section_31_cases_once(conn):
    created = seed_master_prompt_cases(conn, now=NOW)
    assert created == ["CAPR", "NEBIUS", "UNITREE", "MODERNA", "XSPRAY", "RARE", "BEAM", "TLX", "SLS"]
    assert seed_master_prompt_cases(conn, now=NOW) == []
    assert conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0] == len(MASTER_PROMPT_CASES)


def test_seed_does_not_fabricate_history(conn):
    """§71: bez doložených cen a dat se nezakládají žádné predikce, katalyzátory ani XTB stavy."""
    seed_master_prompt_cases(conn, now=NOW)
    for table in ("predictions", "prediction_outcomes", "catalysts", "xtb_checks"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    assert conn.execute("SELECT COUNT(*) FROM companies WHERE category IS NOT NULL OR verdict IS NOT NULL"
                        ).fetchone()[0] == 0


def test_seed_statuses_match_master_prompt(conn):
    seed_master_prompt_cases(conn, now=NOW)
    rows = dict(conn.execute("SELECT l.case_key, c.radar_status FROM lessons l JOIN companies c"
                             " ON c.id = l.company_id").fetchall())
    assert rows["CAPR"] == "REFERENCE"
    assert {rows["BEAM"], rows["TLX"], rows["SLS"]} == {"WATCH"}
    assert rows["XSPRAY"] == "NEOVERENO"
    beam = conn.execute("SELECT lessons_json FROM lessons WHERE case_key = 'BEAM'").fetchone()[0]
    assert "Sledovat BEAM-302." in json.loads(beam)


def test_lessons_are_immutable(conn):
    seed_master_prompt_cases(conn, now=NOW)
    with pytest.raises(sqlite3.IntegrityError, match="§30"):
        with conn:
            conn.execute("UPDATE lessons SET outcome_type = 'HIT' WHERE case_key = 'MODERNA'")
