"""Diagnostika (python -m stockradar diag): je všechno čerstvé, vyhodnocené a uložené?

Úrovně: OK · INFO · VAROVÁNÍ (něco zastaralo, ale běh funguje) · CHYBA (výsledky nejsou spolehlivé nebo se ztrácejí).
Denní rutina ji spouští po `update`; každou CHYBU je potřeba opravit v kódu nebo v datech, ne jen přejít.
"""

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from stockradar import config
from stockradar.contact import email, usage_summary
from stockradar.db import available_migrations, schema_version
from stockradar.state_io import unexported_tables
from stockradar.timeutil import parse_iso, utcnow
from stockradar.update import EVAL_DAYS

LEVELS = ("OK", "INFO", "VAROVÁNÍ", "CHYBA")


def _age_days(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    t = parse_iso(iso) if "T" in iso else datetime.fromisoformat(iso).replace(tzinfo=now.tzinfo)
    return (now - t).total_seconds() / 86400


def run_checks(conn: sqlite3.Connection, *, state_dir: Path, web_dir: Path, cache_conn=None,
               now: datetime | None = None) -> list[dict]:
    now = now or utcnow()
    out: list[dict] = []

    def add(level, check, detail):
        out.append({"uroven": level, "kontrola": check, "detail": detail})

    # 1) schéma a uložení stavu
    want = len(available_migrations())
    have = schema_version(conn)
    add("OK" if have == want else "CHYBA", "Schéma databáze", f"verze {have}, migrací {want}")
    pending = unexported_tables(conn, state_dir)
    add("OK" if not pending else "VAROVÁNÍ", "Uložení do state/",
        "vše exportováno" if not pending else f"neexportované tabulky: {', '.join(pending)} → python -m stockradar export")

    # 2) čerstvost cen a běhů
    spy = conn.execute("SELECT MAX(date) FROM price_bars WHERE symbol = ?", (config.BENCHMARK_SYMBOL,)).fetchone()[0]
    age = (now.date() - date.fromisoformat(spy)).days if spy else None
    add("CHYBA" if age is None else "VAROVÁNÍ" if age > 4 else "OK", "Ceny S&P 500 (SPY)",
        "chybí" if age is None else f"poslední den {spy} ({age} dní)")
    last_run = conn.execute("SELECT MAX(run_at) FROM model_runs").fetchone()[0]
    a = _age_days(last_run, now)
    add("CHYBA" if a is None else "VAROVÁNÍ" if a > 3.5 else "OK", "Denní běh (update)",
        "nikdy" if a is None else f"poslední {last_run} ({a:.1f} dne)")
    last_disc = conn.execute("SELECT MAX(run_at) FROM discovery_runs").fetchone()[0]
    a = _age_days(last_disc, now)
    add("VAROVÁNÍ" if a is None or a > 8 else "OK", "Týdenní objevování (discover)",
        "nikdy" if a is None else f"poslední {last_disc} ({a:.1f} dne)")

    # 3) ledger: zpožděná vyhodnocení a predikce bez cen
    overdue, no_prices = [], []
    for p in conn.execute("SELECT p.id, p.made_at, l.yahoo_symbol FROM predictions p JOIN listings l ON l.id = p.listing_id"
                          " WHERE p.mode = 'LIVE'"):
        have_h = {r[0] for r in conn.execute("SELECT horizon_days FROM prediction_outcomes WHERE prediction_id = ?", (p[0],))}
        made = parse_iso(p[1])
        late = [n for n in EVAL_DAYS if n not in have_h and made + timedelta(days=n + 5) < now]
        if late:
            overdue.append(f"#{p[0]} {p[2]} (+{', +'.join(map(str, late))} d)")
        if p[2] and not conn.execute("SELECT 1 FROM price_bars WHERE symbol = ? LIMIT 1", (p[2],)).fetchone():
            no_prices.append(f"#{p[0]} {p[2]}")
    add("CHYBA" if overdue else "OK", "Vyhodnocení predikcí",
        "vše včas" if not overdue else "zpožděná: " + "; ".join(overdue[:10]))
    add("CHYBA" if no_prices else "OK", "Ceny pro predikce", "všechny mají ceny" if not no_prices else
        "chybí ceny: " + ", ".join(no_prices[:10]))

    # 4) katalyzátory, jejichž okno už skončilo, ale nejsou označené
    stale = conn.execute(
        "SELECT c.id, co.name, COALESCE(c.event_date, c.window_end) AS end_day FROM catalysts c"
        " JOIN companies co ON co.id = c.company_id WHERE c.status IN ('UPCOMING','DELAYED')"
        " AND COALESCE(c.event_date, c.window_end) < ?", ((now.date() - timedelta(days=7)).isoformat(),)).fetchall()
    add("VAROVÁNÍ" if stale else "OK", "Katalyzátory po termínu",
        "žádné" if not stale else "ověř a označ (set_catalyst_status): " +
        "; ".join(f"#{r[0]} {r[1]} ({r[2]})" for r in stale[:8]))

    # 5) data z cache objevování: SEC, ClinicalTrials, ceny tisíců firem
    if cache_conn is not None:
        n_series, fresh = cache_conn.execute(
            "SELECT COUNT(*), SUM(fetched_at >= ?) FROM series WHERE error IS NULL AND n > 0",
            ((now - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ"),)).fetchone()
        add("OK" if n_series and (fresh or 0) / n_series > 0.8 else "VAROVÁNÍ", "Ceny globálního vesmíru",
            f"{n_series or 0} řad, čerstvých do 8 dní {fresh or 0}")
        sec_last = cache_conn.execute("SELECT MAX(fetched_at) FROM sec_index_done").fetchone()[0]
        a = _age_days(sec_last, now)
        add("INFO" if email() is None else "VAROVÁNÍ" if a is None or a > 8 else "OK", "SEC EDGAR",
            "e-mail není nastaven — SEC vypnutý" if email() is None else
            f"poslední stažení {sec_last}, faktů {cache_conn.execute('SELECT COUNT(*) FROM sec_facts').fetchone()[0]}")
        ct = cache_conn.execute("SELECT COUNT(*), MAX(fetched_at) FROM ct_studies").fetchone()
        a = _age_days(ct[1], now)
        add("VAROVÁNÍ" if a is None or a > 8 else "OK", "ClinicalTrials.gov", f"{ct[0]} studií, staženo {ct[1]}")

    # 6) web: velikost dokumentů vůči limitu serveru
    from stockradar.site import DOC_LIMIT
    for f in sorted(web_dir.glob("stav_*.json")):
        size = f.stat().st_size
        add("CHYBA" if size > DOC_LIMIT else "VAROVÁNÍ" if size > 0.85 * DOC_LIMIT else "OK", f"Web {f.name}",
            f"{size // 1024} kB z limitu {DOC_LIMIT // 1024} kB")

    # 7) centrum a registr modulů (v0.10.0): propojený pohled musí být novější než výstupy modulů; selhané běhy z deníku
    from stockradar.hub import feedback, registry
    hub_last = conn.execute("SELECT MAX(run_at) FROM hub_runs").fetchone()[0]
    newest = max((conn.execute(f"SELECT MAX(run_at) FROM {t}").fetchone()[0] or "", t) for t in
                 ("model_runs", "discovery_runs", "smart_money_runs", "signal_runs", "causal_runs"))
    add("VAROVÁNÍ" if not hub_last or hub_last < newest[0] else "OK", "Centrum důkazů (propojený pohled)",
        "zatím neběželo → python -m stockradar hub" if not hub_last else
        f"starší než výstup {newest[1]} ({newest[0]}) → python -m stockradar hub" if hub_last < newest[0] else f"poslední běh {hub_last}")
    mods = registry.modules_status(conn, cache_conn, feedback.reliability(conn), now)
    failed = [m for m in mods if m["stav"] == "CHYBA" and m["duvod"].startswith("poslední běh")]
    other = [m for m in mods if m["stav"] == "CHYBA" and m not in failed]
    add("CHYBA" if failed else "VAROVÁNÍ" if other else "OK", "Stav modulů (registr)",
        "; ".join(f"{m['nazev']}: {m['duvod']}" for m in failed + other) or
        ", ".join(f"{k} {sum(1 for m in mods if m['stav'] == k)}" for k in registry.SUMMARY_KEYS if any(m["stav"] == k for m in mods)))

    # 8) použití e-mailu (pro uživatele)
    summ = usage_summary(conn, days=7)
    days = ", ".join(f"{d['den']}: {d['celkem']}× ({', '.join(f'{h} {n}×' for h, n in d['servery'].items())})"
                     for d in summ["dny"]) or "za 7 dní nepoužit"
    add("INFO", "Použití e-mailu (7 dní)", days)
    return out


def worst(checks: list[dict]) -> str:
    return max((c["uroven"] for c in checks), key=LEVELS.index, default="OK")


def to_json(checks: list[dict]) -> str:
    return json.dumps(checks, ensure_ascii=False, indent=1)
