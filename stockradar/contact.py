"""E-mail uživatele pro zdroje, které ho vyžadují (SEC EDGAR) — s evidencí KAŽDÉHO použití.

Rozhodnutí uživatele 2026-10-03: „smíš používat můj e-mail, ale musím vědět, kolikrát denně a na jakých
stránkách si ho použil“. Proto:
  * e-mail se posílá jen serverům v ALLOWED_HOSTS (SEC EDGAR vyžaduje kontakt v hlavičce User-Agent),
  * každý dotaz s e-mailem se před odesláním zapíše do tabulky email_usage (den, server, účel, počet),
  * e-mail není v gitu: čte se z proměnné STOCKRADAR_CONTACT_EMAIL nebo ze souboru data/kontakt.txt
    (adresář data/ je v .gitignore). Bez e-mailu se SEC krok přeskočí a nic se neodešle.
"""

import gzip
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from pathlib import Path

from stockradar import config
from stockradar.timeutil import to_iso, utcnow

EMAIL_FILE = config.PROJECT_ROOT / "data" / "kontakt.txt"
ALLOWED_HOSTS = ("www.sec.gov", "data.sec.gov")
MAX_PER_SECOND = 5.0  # SEC povoluje 10 dotazů/s — držíme se polovičního tempa


class ContactMissing(RuntimeError):
    """E-mail není nastavený — zdroj, který ho vyžaduje, se přeskočí."""


def email() -> str | None:
    value = os.environ.get("STOCKRADAR_CONTACT_EMAIL")
    if not value:
        path = Path(os.environ.get("STOCKRADAR_CONTACT_FILE", EMAIL_FILE))
        value = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    return value if "@" in value else None


def user_agent() -> str:
    addr = email()
    if addr is None:
        raise ContactMissing("e-mail pro SEC není nastaven (data/kontakt.txt nebo STOCKRADAR_CONTACT_EMAIL)")
    return f"GlobalFutureWinners research {addr}"


class _Usage:
    """Počítadlo použití e-mailu — zapisuje hned do hlavní DB (bezpečné pro více vláken)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.conn: sqlite3.Connection | None = None
        self.path: Path | None = None
        self.next_at = 0.0

    def _conn(self) -> sqlite3.Connection:
        path = config.db_path()
        if self.conn is None or self.path != path:
            from stockradar.db import migrate
            self.conn = sqlite3.connect(path, timeout=60, check_same_thread=False)
            migrate(self.conn)
            self.path = path
        return self.conn

    def record(self, host: str, purpose: str, n: int = 1) -> None:
        now = to_iso(utcnow())
        with self.lock:
            conn = self._conn()
            with conn:
                conn.execute(
                    "INSERT INTO email_usage (day, host, purpose, requests, first_at, last_at) VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(day, host, purpose) DO UPDATE SET requests = requests + excluded.requests,"
                    " last_at = excluded.last_at", (now[:10], host, purpose, n, now, now))

    def throttle(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = self.next_at - now
            self.next_at = max(now, self.next_at) + 1.0 / MAX_PER_SECOND
        if delay > 0:
            time.sleep(delay)

    def reset(self) -> None:
        with self.lock:
            if self.conn is not None:
                self.conn.close()
            self.conn, self.path = None, None


USAGE = _Usage()


def http_get(url: str, purpose: str, *, timeout: int = 60, retries: int = 3) -> bytes:
    """GET s e-mailem v User-Agent. Každý pokus (i neúspěšný) se započítá — e-mail odešel v hlavičce."""
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"e-mail se smí posílat jen na {', '.join(ALLOWED_HOSTS)}, ne na {host}")
    ua = user_agent()
    last: Exception | None = None
    for attempt in range(retries):
        USAGE.throttle()
        USAGE.record(host, purpose)
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip" or data[:2] == b"\x1f\x8b":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 404:
                raise
            time.sleep((10 if exc.code in (403, 429) else 2) * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def usage(conn: sqlite3.Connection, *, days: int = 7) -> list[dict]:
    """Použití e-mailu za posledních `days` dní (nejnovější první)."""
    since = (utcnow().date() - timedelta(days=days - 1)).isoformat()
    return [dict(r) for r in conn.execute(
        "SELECT day, host, purpose, requests, first_at, last_at FROM email_usage WHERE day >= ?"
        " ORDER BY day DESC, host, purpose", (since,))]


def usage_summary(conn: sqlite3.Connection, *, days: int = 7) -> dict:
    rows = usage(conn, days=days)
    by_day: dict[str, dict] = {}
    for r in rows:
        d = by_day.setdefault(r["day"], {"den": r["day"], "celkem": 0, "servery": {}})
        d["celkem"] += r["requests"]
        d["servery"][r["host"]] = d["servery"].get(r["host"], 0) + r["requests"]
    total = conn.execute("SELECT COALESCE(SUM(requests), 0) FROM email_usage").fetchone()[0]
    return {"nastaveno": email() is not None, "povolene_servery": list(ALLOWED_HOSTS), "dny": list(by_day.values()),
            "celkem_od_zacatku": total, "detail": rows}
