"""Příkazová řádka: python -m stockradar <příkaz>.

Každý příkaz, který mění data, na konci automaticky exportuje state/ (zdroj pravdy v gitu).
"""

import argparse
import json
import sys
from datetime import timedelta

from stockradar import __version__
from stockradar.catalysts import date_text, upcoming_catalysts
from stockradar.companies import latest_xtb_check
from stockradar.config import XTB_CHECK_MAX_AGE, db_path, state_dir
from stockradar.data_quality import freshness_label
from stockradar.db import open_db, schema_version
from stockradar.enums import label
from stockradar.ledger import register_rows
from stockradar.lessons import seed_master_prompt_cases
from stockradar.snapshots import create_snapshot
from stockradar.state_io import TABLES, export_state, has_state, restore_state, unexported_tables
from stockradar.timeutil import parse_iso, to_iso, utcnow


def _table(headers: list[str], rows: list[list]) -> str:
    cells = [[("" if v is None else str(v)) for v in row] for row in rows]
    widths = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(headers)]
    fmt = " | ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*headers), "-+-".join("-" * w for w in widths)]
    lines += [fmt.format(*r) for r in cells]
    return "\n".join(lines)


def _fmt_num(value) -> str | None:
    if value is None:
        return None
    if abs(value) >= 1e9:
        return f"{value / 1e9:.2f}B"
    if abs(value) >= 1e6:
        return f"{value / 1e6:.1f}M"
    return f"{value:g}"


def _open(create: bool = True):
    path = db_path()
    is_new = not path.exists()
    if is_new and not create:
        raise SystemExit(f"databáze {path} neexistuje — spusť nejdřív: python -m stockradar init")
    conn = open_db(path)
    if is_new and has_state(state_dir()):
        restore_state(conn, state_dir())
    return conn


def cmd_init(args) -> int:
    path = db_path()
    existed = path.exists()
    conn = _open()
    if existed:
        print(f"Databáze už existuje: {path} (schema v{schema_version(conn)})")
    elif has_state(state_dir()):
        print(f"Databáze vytvořena a obnovena ze {state_dir()}: {path}")
    else:
        print(f"Nová prázdná databáze: {path} (schema v{schema_version(conn)})")
        print("Historický stav nenalezen — state/ neexistuje (§71).")
    return 0


def cmd_restore(args) -> int:
    path = db_path()
    if not has_state(state_dir()):
        raise SystemExit(f"{state_dir()} neobsahuje žádný stav — není z čeho obnovit")
    if path.exists():
        path.unlink()
    conn = open_db(path)
    counts = restore_state(conn, state_dir())
    print(f"Obnoveno ze {state_dir()} do {path}:")
    for table, n in counts.items():
        print(f"  {table:<20} {n}")
    return 0


def cmd_export(args) -> int:
    conn = _open(create=False)
    counts = export_state(conn, state_dir())
    print(f"Exportováno do {state_dir()}: " + ", ".join(f"{t}={n}" for t, n in counts.items()))
    print("Nezapomeň commitnout state/ (zdroj pravdy projektu).")
    return 0


def cmd_seed_lessons(args) -> int:
    conn = _open()
    created = seed_master_prompt_cases(conn)
    print("Založeny případy §31: " + (", ".join(created) if created else "žádné nové (už existují)"))
    export_state(conn, state_dir())
    return 0


def cmd_snapshot(args) -> int:
    conn = _open(create=False)
    snapshot_id = create_snapshot(conn, label=args.label)
    export_state(conn, state_dir())
    print(f"Snapshot #{snapshot_id} vytvořen a exportován.")
    return 0


def cmd_status(args) -> int:
    conn = _open(create=False)
    now = utcnow()
    print(f"GLOBAL FUTURE WINNERS / STOCK RADAR  v{__version__}  (schema v{schema_version(conn)})")
    print(f"Čas: {to_iso(now)}  DB: {db_path()}")
    print()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    print("Záznamy: " + ", ".join(f"{t}={n}" for t, n in counts.items()))
    pending = unexported_tables(conn, state_dir())
    if pending:
        print(f"POZOR: neexportované změny v {', '.join(pending)} — spusť `python -m stockradar export`")
    print()

    rows = []
    for c in conn.execute("SELECT * FROM companies ORDER BY radar_status, name"):
        listings = conn.execute("SELECT * FROM listings WHERE company_id = ? AND valid_to IS NULL ORDER BY id",
                                (c["id"],)).fetchall()
        if not listings:
            rows.append([c["name"], "—", c["country"], label(c["radar_status"]), label(c["category"]),
                         label(c["verdict"]), "NEOVĚŘENO"])
        for l in listings:
            xtb = latest_xtb_check(conn, l["id"], as_of=now)
            if xtb is None:
                xtb_text = "NEOVĚŘENO"
            else:
                xtb_text = label(xtb["status"]) + (f" ({xtb['instruments']})" if xtb["instruments"] else "")
                if now - parse_iso(xtb["checked_at"]) > XTB_CHECK_MAX_AGE:
                    xtb_text += " — kontrola zastaralá"
            rows.append([c["name"], f"{l['ticker']}:{l['exchange']}", c["country"], label(c["radar_status"]),
                         label(c["category"]), label(c["verdict"]), xtb_text])
    print("FIRMY NA RADARU")
    print(_table(["Firma", "Listing", "Země", "Radar", "Kat.", "Verdikt", "XTB"], rows) if rows else "(žádné)")
    print()

    soon = upcoming_catalysts(conn, today=now.date(), within_days=args.days)
    print(f"KATALYZÁTORY V PŘÍŠTÍCH {args.days} DNECH")
    if soon:
        print(_table(["Firma", "Typ", "Datum", "Popis"],
                     [[k["company_name"], k["type_code"], date_text(k), k["description"]] for k in soon]))
    else:
        print("(žádné zapsané)")
    print()

    week_ago = to_iso(now - timedelta(days=7))
    changes = conn.execute(
        "SELECT s.*, c.name FROM status_changes s JOIN companies c ON c.id = s.company_id"
        " WHERE s.changed_at >= ? ORDER BY s.changed_at DESC, s.id DESC", (week_ago,)).fetchall()
    print("ZMĚNY VERDIKTŮ ZA 7 DNÍ")
    if changes:
        print(_table(["Kdy", "Firma", "Pole", "Původně", "Nově", "Důvod"],
                     [[s["changed_at"], s["name"], s["field"], label(s["old_value"]), label(s["new_value"]),
                       s["reason"]] for s in changes]))
    else:
        print("(žádné)")
    print()
    main_pick = conn.execute(
        "SELECT p.made_at, l.ticker FROM predictions p JOIN listings l ON l.id = p.listing_id"
        " WHERE p.is_main_pick = 1 AND p.mode = 'LIVE' ORDER BY p.made_at DESC LIMIT 1").fetchone()
    print("POSLEDNÍ MAIN PICK: " + (f"{main_pick['ticker']} ({main_pick['made_at']})" if main_pick else "ŽÁDNÝ"))
    return 0


def cmd_ledger(args) -> int:
    conn = _open(create=False)
    rows = register_rows(conn)
    if not rows:
        print("Prediction ledger je prázdný — zatím nebyla zapsána žádná predikce.")
        return 0
    print("REGISTER (§28) — predikce")
    print(_table(
        ["#", "Ticker", "Datum nalezení", "Cena", "Market cap", "Katalyzátor", "Datum", "SETUP", "Rocket",
         "Verdikt", "XTB", "Data"],
        [[r["id"], r["ticker"], r["made_at"][:10], f"{r['price']:g} {r['currency']}", _fmt_num(r["market_cap"]),
          r["catalyst_text"], r["catalyst_date_text"], r["score_overall_setup"], r["score_rocket"],
          label(r["verdict"]) + (" ★MAIN" if r["is_main_pick"] else ""), label(r["xtb_status"]),
          freshness_label(r["price_freshness"]) + (" BACKTEST" if r["mode"] == "BACKTEST" else "")]
         for r in rows]))
    print()
    print("REGISTER (§28) — vyhodnocení")
    print(_table(
        ["#", "Ticker", "Cena při predikci", "+7d", "+14d", "+30d", "Max", "Min", "Výsledek"],
        [[r["id"], r["ticker"], f"{r['price']:g}", r["price_7d"], r["price_14d"], r["price_30d"],
          r["period_max"], r["period_min"], label(r["result"]) if r["result"] else "čeká"] for r in rows]))
    return 0


def cmd_lessons(args) -> int:
    conn = _open(create=False)
    rows = conn.execute("SELECT * FROM lessons ORDER BY id").fetchall()
    if not rows:
        print("Žádná poučení. Případy z §31 založíš: python -m stockradar seed-lessons")
        return 0
    for r in rows:
        print(f"[{r['outcome_type']}] {r['title']}")
        for item in json.loads(r["lessons_json"]):
            print(f"   - {item}")
        if r["model_correction"]:
            print(f"   Oprava modelu: {r['model_correction']}")
        print(f"   Zdroj: {r['source']}")
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stockradar", description="Global Future Winners / Stock Radar")
    parser.add_argument("--version", action="version", version=f"stockradar {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="vytvoří DB (obnoví ze state/, pokud existuje)").set_defaults(func=cmd_init)
    sub.add_parser("restore", help="smaže pracovní DB a sestaví ji znovu ze state/").set_defaults(func=cmd_restore)
    sub.add_parser("export", help="zapíše DB do state/ (pak commit)").set_defaults(func=cmd_export)
    sub.add_parser("seed-lessons", help="založí učební případy z §31").set_defaults(func=cmd_seed_lessons)
    p_status = sub.add_parser("status", help="přehled radaru, katalyzátorů a změn")
    p_status.add_argument("--days", type=int, default=14, help="horizont katalyzátorů (default 14)")
    p_status.set_defaults(func=cmd_status)
    sub.add_parser("ledger", help="historický register predikcí (§28)").set_defaults(func=cmd_ledger)
    sub.add_parser("lessons", help="učební případy a poučení (§30, §31)").set_defaults(func=cmd_lessons)
    p_snap = sub.add_parser("snapshot", help="historický snapshot stavu (§53)")
    p_snap.add_argument("--label", default=None)
    p_snap.set_defaults(func=cmd_snapshot)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
