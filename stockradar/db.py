"""SQLite připojení a verzované migrace (PRAGMA user_version)."""

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def available_migrations() -> list[tuple[int, Path]]:
    """Soubory NNNN_popis.sql seřazené podle čísla verze."""
    found = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(path.name.split("_", 1)[0])
        found.append((version, path))
    versions = [v for v, _ in found]
    if versions != list(range(1, len(versions) + 1)):
        raise RuntimeError(f"migrace musí být číslované souvisle od 1, nalezeno {versions}")
    return found


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Aplikuje chybějící migrace, každou v jedné transakci. Vrací aplikované verze."""
    applied = []
    current = schema_version(conn)
    for version, path in available_migrations():
        if version <= current:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
        except sqlite3.Error:
            if conn.in_transaction:
                conn.rollback()
            raise
        applied.append(version)
    return applied


def open_db(path: str | Path) -> sqlite3.Connection:
    conn = connect(path)
    migrate(conn)
    return conn
