"""§56: persistentní stav nezávislý na chatu.

Zdroj pravdy je adresář state/ v gitu (JSONL, jeden soubor na tabulku, deterministicky seřazený).
SQLite v data/ je pracovní kopie, kterou lze kdykoli znovu sestavit příkazem `restore`.
Git historie state/ zároveň dokládá, že se historické predikce nepřepisovaly.
"""

import json
import sqlite3
from pathlib import Path

# Pořadí respektuje cizí klíče. catalyst_types se plní migrací, neexportuje se.
# Cache bezplatných dat (price_bars, sec_*) se neexportuje — dá se kdykoli stáhnout znovu.
TABLES = (
    "companies",
    "listings",
    "chain_nodes",
    "company_chain",
    "relationships",
    "xtb_checks",
    "catalysts",
    "model_versions",
    "model_runs",
    "discovery_runs",
    "smart_money_runs",
    "predictions",
    "prediction_outcomes",
    "status_changes",
    "lessons",
    "snapshots",
    "email_usage",
)


def _dump_table(conn: sqlite3.Connection, table: str) -> str:
    lines = [
        json.dumps(dict(row), ensure_ascii=False, sort_keys=True)
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")
    ]
    return "".join(line + "\n" for line in lines)


def export_state(conn: sqlite3.Connection, state_dir: Path) -> dict[str, int]:
    state_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for table in TABLES:
        content = _dump_table(conn, table)
        (state_dir / f"{table}.jsonl").write_text(content, encoding="utf-8")
        counts[table] = content.count("\n")
    return counts


def unexported_tables(conn: sqlite3.Connection, state_dir: Path) -> list[str]:
    """Tabulky, jejichž obsah v DB se liší od state/ (= neuložená práce)."""
    differing = []
    for table in TABLES:
        path = state_dir / f"{table}.jsonl"
        on_disk = path.read_text(encoding="utf-8") if path.exists() else ""
        if _dump_table(conn, table) != on_disk:
            differing.append(table)
    return differing


def has_state(state_dir: Path) -> bool:
    return any((state_dir / f"{t}.jsonl").exists() for t in TABLES)


def restore_state(conn: sqlite3.Connection, state_dir: Path) -> dict[str, int]:
    """Nahraje state/ do prázdné databáze (po migraci)."""
    for table in TABLES:
        if conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
            raise RuntimeError(f"restore vyžaduje prázdnou databázi, tabulka {table} obsahuje data")
    counts = {}
    conn.execute("BEGIN")
    try:
        # Cizí klíče se kontrolují až při COMMIT (např. superseded_by ukazuje na pozdější řádek).
        conn.execute("PRAGMA defer_foreign_keys = ON")
        for table in TABLES:
            path = state_dir / f"{table}.jsonl"
            if not path.exists():
                counts[table] = 0
                continue
            columns = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
            sql = (f"INSERT INTO {table} ({', '.join(columns)}) "
                   f"VALUES ({', '.join('?' for _ in columns)})")
            n = 0
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                unknown = set(record) - set(columns)
                if unknown:
                    raise RuntimeError(f"{path.name}:{line_no}: neznámé sloupce {sorted(unknown)}")
                conn.execute(sql, [record.get(c) for c in columns])
                n += 1
            counts[table] = n
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return counts
