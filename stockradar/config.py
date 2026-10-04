"""Cesty a limity. Cesty lze přepsat proměnnými prostředí (testy, jiné prostředí)."""

import os
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Pracovní SQLite databáze — není v gitu, vždy se dá znovu sestavit ze state/.
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "stockradar.db"
# Zdroj pravdy v gitu: textový export všech tabulek (§56 — chat není databáze).
DEFAULT_STATE_DIR = PROJECT_ROOT / "state"
# Data pro webový přehled (generují se při každém update, nejsou v gitu).
DEFAULT_WEB_DIR = PROJECT_ROOT / "data" / "web"

# §52: cena starší než tento limit = DATA STALE.
PRICE_MAX_AGE = timedelta(hours=4)
# §5: kontrola XTB starší než tento limit se pro doporučení nepovažuje za platnou.
XTB_CHECK_MAX_AGE = timedelta(days=30)
# Rozhodnutí uživatele 2026-10-02: XTB není povinná podmínka (stav se jen informativně zapisuje).
REQUIRE_XTB_FOR_BUY = False

# Benchmark pro vyhodnocení predikcí (Yahoo symbol).
BENCHMARK_SYMBOL = "SPY"

# E-mail pro SEC EDGAR a evidence jeho použití: viz stockradar/contact.py (e-mail není v gitu).


def db_path() -> Path:
    return Path(os.environ.get("STOCKRADAR_DB", DEFAULT_DB_PATH))


def state_dir() -> Path:
    return Path(os.environ.get("STOCKRADAR_STATE_DIR", DEFAULT_STATE_DIR))


def web_dir() -> Path:
    return Path(os.environ.get("STOCKRADAR_WEB_DIR", DEFAULT_WEB_DIR))
