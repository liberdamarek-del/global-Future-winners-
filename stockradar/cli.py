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
from stockradar.config import XTB_CHECK_MAX_AGE, db_path, state_dir, web_dir
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


def cmd_update(args) -> int:
    from stockradar.update import run_update

    conn = _open()
    result = run_update(conn, state_dir=state_dir(), web_dir=web_dir())
    print(f"UPDATE {result.get('data_day', '?')}  (běh #{result['run_id']})")
    for step, state in result["steps"].items():
        print(f"  {step:<22} {state}")
    if result.get("reason"):
        print(f"Model: {result['reason']}")
    for w in result["warnings"]:
        print(f"  ! {w}")
    print(f"Data pro web: {web_dir()}")
    _print_email_today(conn)
    return 0 if result["run_id"] else 1


def _print_email_today(conn) -> None:
    from stockradar.contact import usage_summary
    today = utcnow().date().isoformat()
    day = next((d for d in usage_summary(conn, days=1)["dny"] if d["den"] == today), None)
    print("E-mail dnes: " + (f"{day['celkem']}× — " + ", ".join(f"{h} {n}×" for h, n in day["servery"].items())
                             if day else "nepoužit"))


def cmd_sources(args) -> int:
    """Obnoví SEC (fundamenty, filingy) a ClinicalTrials.gov v cache objevování."""
    from stockradar.discovery import cache as dcache
    from stockradar.sources import clinicaltrials, sec

    conn = _open()
    cconn = dcache.connect()
    log = lambda m: print(f"  {m}", flush=True)
    print("SEC EDGAR:", sec.refresh(cconn, log=log))
    print("ClinicalTrials.gov:", clinicaltrials.refresh(cconn, log=log))
    export_state(conn, state_dir())  # evidence použití e-mailu je součást stavu
    _print_email_today(conn)
    return 0


def cmd_discover(args) -> int:
    from stockradar.discovery import cache as dcache
    from stockradar.discovery import download, engine, listings, store
    from stockradar.sources import clinicaltrials, sec

    conn = _open()
    cconn = dcache.connect()
    log = lambda m: print(f"  {m}", flush=True)
    if args.universe:
        counts = listings.build_universe(cconn, log=log)
        print("Seznam firem: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    if args.download:
        print("Stahování cen:", download.run(log=log))
    if not args.no_sources:
        print("SEC EDGAR:", sec.refresh(cconn, log=log))
        print("ClinicalTrials.gov:", clinicaltrials.refresh(cconn, log=log))
    print("GLOBAL DISCOVERY …")
    from stockradar.sources import xtb
    checker = xtb.Checker(cconn)          # žebříček raket na webu jen z nabídky XTB (rozhodnutí uživatele 2026-10-05)
    result = engine.run_discovery(cconn, news_events=args.news, news_winners=args.news_winners, log=log,
                                  xtb_check=checker.check)
    xsum = checker.summary()
    print(f"XTB: {xsum['dotazu']} dotazů na xtb.com, {xsum['z_cache']} z cache, chyb {xsum['chyb']}")
    run_id = store.save_run(conn, result)
    created, notes = store.record_candidates(conn, cconn, result, run_id)
    rockets, rnotes = store.record_rockets(conn, cconn, result.get("rakety_6m") or {}, run_id)
    export_state(conn, state_dir())
    st = result["statistika"]
    print(f"Běh #{run_id}: {st['firem_s_daty']} firem, {st['zemi']} zemí, {st['oboru']} oborů, "
          f"rakety {st['rakety']}, titulků {st['dokumentu_titulku']}")
    print(f"Do ledgeru zapsáno {len(created)} kandidátů (týden/3 měsíce) a {len(rockets)} predikcí raket na 6 měsíců.")
    for n in notes + rnotes:
        print(f"  ! {n}")
    _print_email_today(conn)
    print("Data pro web se obnoví při příštím `update`.")
    return 0


def cmd_smart_money(args) -> int:
    """Smart money: insideři (SEC Form 4), politici (Sněmovna, Senát), 13D/13G, buybacky → test + aktuální signály."""
    from datetime import date

    from stockradar.discovery import cache as dcache
    from stockradar.smartmoney import report, sources
    from stockradar.smartmoney import store as sm_store
    from stockradar.sources import sec

    conn = _open()
    cconn = dcache.connect()
    log = lambda m: print(f"  {m}", flush=True)
    if not args.no_download:
        print("SEC insider:", sources.fetch_insiders(cconn, log=log))
        today = date.today()
        print("SEC index:", sec.fetch_index(cconn, start=date(2021, 1, 1), end=today, log=log))
        print("SEC buybacky:", sec.fetch_annual(cconn, log=log))
        print("Sněmovna:", sources.fetch_house(cconn, years=[today.year - 1, today.year], log=log))
        print("Senát:", sources.fetch_senate(cconn, start=f"01/01/{today.year - 1}", log=log))
        sources.senate_roles(cconn, start=f"01/01/{today.year - 1}")
    result = report.run(cconn, conn, log=log, csv_dir=db_path().parent)
    run_id = sm_store.save_run(conn, result)
    created, notes = sm_store.record_signals(conn, cconn, result, run_id)
    export_state(conn, state_dir())
    print(f"Běh smart money #{run_id}: {len(result['aktualni']['top'])} signálů, do ledgeru {len(created)}")
    for n in notes:
        print(f"  ! {n}")
    _print_email_today(conn)
    return 0


def cmd_signals(args) -> int:
    """Signální engine na 14 dní: karta pravděpodobností, důvěra, NEVÍM; zamčený test jen jednou na konfiguraci."""
    from stockradar.discovery import cache as dcache
    from stockradar.signals import model as sm_model
    from stockradar.signals import run as srun
    from stockradar.signals import store as sstore
    from stockradar.site import write_signals_doc
    from stockradar.smartmoney import current

    conn = _open()
    cconn = dcache.connect()
    log = lambda m: print(f"  {m}", flush=True)
    recent = None
    if not args.no_download:
        try:   # čtvrtletní sady SEC končí s odstupem → čerstvé nákupy insiderů z openinsider (sekundární přehled Form 4)
            from datetime import date as _date
            last = cconn.execute("SELECT MAX(filing_date) FROM insider_tx").fetchone()[0]
            start = _date.fromisoformat(last) if last else _date.today().replace(day=1)
            recent = current.fetch_purchases_between(start, _date.today(), log=log)
            print(f"openinsider: {len(recent)} nákupů od {start}")
        except Exception as exc:
            print(f"openinsider nedostupný: {exc}")
    if not args.no_download:              # ceny komodit pro kauzální znaky modelu na 6 měsíců (Yahoo, zdarma)
        from stockradar.causal import data as cdata
        cdata.download(cconn, log=log)
    from stockradar.sources import xtb
    checker = xtb.Checker(cconn)          # do žebříčku jen akcie z nabídky XTB (rozhodnutí uživatele 2026-10-05)
    res = srun.run(cconn, conn, log=log, with_news=not args.no_news, recent_insiders=recent, workers=args.workers,
                   xtb_check=checker.check)
    data = res.pop("_data")
    xsum = checker.summary()
    print(f"XTB: {xsum['dotazu']} dotazů na xtb.com, {xsum['z_cache']} z cache, chyb {xsum['chyb']}"
          + (" — XTB NEDOSTUPNÉ, část firem neověřena" if xsum["nedostupne"] else ""))
    evaluated = sstore.evaluate_forecasts(conn, data)
    for name, r in res["modely"].items():
        r["vysledky_karet"] = sstore.scorecard(conn, r["obchodnich_dni"])
        r["nove_vyhodnoceno"] = len(evaluated)
        r = srun.clean(r)
        run_id = sstore.save_run(conn, r, name, r["konfigurace"])
        ids = sstore.save_forecasts(conn, run_id, r["karty"])
        d = r["dnes"]["rozhodnuti"]
        t = r["zamceny_test"]
        print(f"{name} (běh #{run_id}): {len(ids)} nových karet; dnes RŮST {d['RŮST']}, POKLES {d['POKLES']},"
              f" NEVÍM {d['NEVÍM']}; zamčený test ({t.get('_stav')}): AUC růst {t.get('up5', {}).get('auc')},"
              f" pokles {t.get('down5', {}).get('auc')}")
    export_state(conn, state_dir())
    sizes = write_signals_doc(conn, web_dir())
    print(f"Vyhodnoceno dřívějších karet: {len(evaluated)}; web: " + ", ".join(f"{k} {v // 1024} kB" for k, v in sizes.items()))
    _print_email_today(conn)
    return 0


def cmd_causal(args) -> int:
    """Kauzální radar: komodity → citlivost oborů → test řetězců (zamčený jednou) → události → karty → web."""
    from datetime import date as _date

    from stockradar.causal import chains, data as cdata, events, radar
    from stockradar.causal import store as cstore
    from stockradar.causal.exposure import build_exposure, build_weekly
    from stockradar.discovery import cache as dcache, study
    from stockradar.signals import model as sm
    from stockradar.site import write_causal_doc
    from stockradar.sources import xtb

    conn = _open()
    cconn = dcache.connect()
    log = lambda m: print(f"  {m}", flush=True)
    if not args.no_download:
        cdata.download(cconn, log=log)
    data = study.load_data(cconn)
    comm = cdata.load(cconn)
    weekly = build_weekly(data, comm, log=log)
    ex = build_exposure(weekly)
    periods = {"UCENI": (0, sm.TRAIN_END), "VALIDACE": sm.VAL, "TEST": sm.TEST}
    st = chains.study(ex, periods, log=log)
    reg = cstore.record_study(conn, st, periods)
    today = _date.fromordinal(data.data_end)
    try:
        gd = events.gdacs(_date.today())
    except Exception as exc:
        log(f"GDACS nedostupný: {exc}")
        gd = []
    links = events.link_gdacs(gd)
    pulses = {} if args.no_news else {c: events.news_pulse(c, _date.today()) for c in comm}
    secs = [dict(r) for r in cconn.execute("SELECT symbol, name, industry, market_cap_usd FROM securities"
                                           " WHERE symbol NOT LIKE '%.%'")]
    checker = xtb.Checker(cconn)
    res = radar.build(ex, comm, today, gdacs_links=links, pulses=pulses, securities=secs, study=st,
                      xtb_check=checker.check)
    res["test_retezcu"] = reg
    res["gdacs"] = {"udalosti": len(gd), "navazane_komodity": sorted(links)}
    evaluated = cstore.evaluate(conn, weekly)
    res["vysledky"] = cstore.scorecard(conn)
    run_id = cstore.save_run(conn, res)
    ids = cstore.save_forecasts(conn, run_id, res)
    export_state(conn, state_dir())
    size = write_causal_doc(conn, web_dir())
    t = (reg.get("zamceny_test") or {}).get("empiricke") or {}
    print(f"Kauzální radar (běh #{run_id}): karet {len(res['karty'])}, příležitostí {len(res['prilezitosti'])}, "
          f"nových predikcí {len(ids)}, vyhodnoceno {len(evaluated)}; GDACS {len(gd)} výstrah; "
          f"test řetězců za 13 týdnů {(t.get('13t') or {}).get('prumer')} (t {(t.get('13t') or {}).get('t')}); web {size // 1024} kB")
    _print_email_today(conn)
    return 0


def cmd_email(args) -> int:
    from stockradar.contact import email, usage_summary
    conn = _open(create=False)
    summ = usage_summary(conn, days=args.days)
    print("E-mail: " + ("nastaven (data/kontakt.txt nebo STOCKRADAR_CONTACT_EMAIL)" if email() else "NENASTAVEN"))
    print("Posílá se jen na: " + ", ".join(summ["povolene_servery"]))
    print(f"Celkem od začátku: {summ['celkem_od_zacatku']} dotazů")
    rows = [[r["day"], r["host"], r["purpose"], r["requests"], r["first_at"][11:16], r["last_at"][11:16]]
            for r in summ["detail"]]
    print(_table(["Den", "Server", "Účel", "Dotazů", "Od (UTC)", "Do (UTC)"], rows) if rows else "(za období nepoužit)")
    return 0


def cmd_diag(args) -> int:
    from stockradar.diag import run_checks, to_json, worst
    from stockradar.discovery import cache as dcache

    conn = _open(create=False)
    checks = run_checks(conn, state_dir=state_dir(), web_dir=web_dir(), cache_conn=dcache.connect())
    if args.json:
        print(to_json(checks))
    else:
        print(_table(["Úroveň", "Kontrola", "Detail"], [[c["uroven"], c["kontrola"], c["detail"]] for c in checks]))
        print(f"\nCelkově: {worst(checks)}")
    return 1 if worst(checks) == "CHYBA" else 0


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
    p_status.add_argument("--days", type=int, default=45, help="horizont katalyzátorů (default 45 dní, §1)")
    p_status.set_defaults(func=cmd_status)
    sub.add_parser("ledger", help="historický register predikcí (§28)").set_defaults(func=cmd_ledger)
    sub.add_parser("update", help="denní běh: ceny, vyhodnocení, učení, predikce, web (§54)").set_defaults(
        func=cmd_update)
    p_disc = sub.add_parser("discover", help="globální objevování vítězů, vzorů a sektorů (Growth Engine)")
    p_disc.add_argument("--universe", action="store_true", help="znovu stáhnout seznamy firem (USA, ASX, JPX, Wikipedie)")
    p_disc.add_argument("--download", action="store_true", help="stáhnout/obnovit historii cen (dlouhé, ~1 h)")
    p_disc.add_argument("--news", type=int, default=120, help="kolik raket vysvětlit ze zpráv")
    p_disc.add_argument("--news-winners", type=int, default=40, help="kolik dnešních vítězů vysvětlit ze zpráv")
    p_disc.add_argument("--no-sources", action="store_true", help="neobnovovat SEC a ClinicalTrials.gov")
    p_disc.set_defaults(func=cmd_discover)
    sub.add_parser("lessons", help="učební případy a poučení (§30, §31)").set_defaults(func=cmd_lessons)
    sub.add_parser("sources", help="obnoví SEC EDGAR a ClinicalTrials.gov (cache objevování)").set_defaults(func=cmd_sources)
    p_sm = sub.add_parser("smart-money", help="nákupy insiderů, politiků, velké podíly a buybacky: test + signály")
    p_sm.add_argument("--no-download", action="store_true", help="nestahovat nová data (jen analýza)")
    p_sm.set_defaults(func=cmd_smart_money)
    p_sig = sub.add_parser("signals", help="signály na 14 dní: P(+5 %), P(−5 %), důvěra, NEVÍM; přísný test")
    p_sig.add_argument("--no-download", action="store_true", help="bez stažení čerstvých nákupů insiderů")
    p_sig.add_argument("--no-news", action="store_true", help="bez titulků (novost a kvalita informací)")
    p_sig.add_argument("--workers", type=int, default=4, help="počet procesů pro učení")
    p_sig.set_defaults(func=cmd_signals)
    p_cau = sub.add_parser("causal", help="kauzální radar: událost → komodita → obory → firmy (+ test řetězců)")
    p_cau.add_argument("--no-download", action="store_true", help="bez stažení cen komodit")
    p_cau.add_argument("--no-news", action="store_true", help="bez zpráv o narušení (Google News)")
    p_cau.set_defaults(func=cmd_causal)
    p_email = sub.add_parser("email", help="kolikrát a kde byl použit e-mail uživatele")
    p_email.add_argument("--days", type=int, default=14)
    p_email.set_defaults(func=cmd_email)
    p_diag = sub.add_parser("diag", help="diagnostika: čerstvost dat, vyhodnocení, uložení, web, e-mail")
    p_diag.add_argument("--json", action="store_true")
    p_diag.set_defaults(func=cmd_diag)
    p_snap = sub.add_parser("snapshot", help="historický snapshot stavu (§53)")
    p_snap.add_argument("--label", default=None)
    p_snap.set_defaults(func=cmd_snapshot)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
