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


def _note(args, **kw) -> None:
    """Souhrn běhu do deníku (`system_runs`) — co příkaz udělal."""
    j = getattr(args, "journal", None)
    if isinstance(j, dict):
        j.update(kw)


def _refresh_hub(args, conn, cconn=None) -> None:
    """Po každém příkazu, který mění výstupy modulů: centrum důkazů → paměť (hub_runs) + web (stav/prehled).
    Selhání centra neshodí hlavní příkaz (jeho práce je hotová), ale zapíše se do deníku a ukáže v `system`."""
    from stockradar.hub import integrate
    from stockradar.site import write_prehled_doc
    try:
        if cconn is None:
            from stockradar.discovery import cache as dcache
            cconn = dcache.connect()
        res = integrate.refresh(conn, cconn)
        size = write_prehled_doc(res, web_dir())
        export_state(conn, state_dir())
        n = res["pocty"]
        print(f"Centrum: {n['firem']} firem (příležitost {n['PŘÍLEŽITOST']}, riziko {n['RIZIKO']}, rozpor {n['ROZPOR']}),"
              f" záznam {res['beh']['stav']} #{res['beh']['id']}, web {size // 1024} kB")
        _note(args, centrum=res["beh"]["stav"], centrum_beh=res["beh"]["id"])
    except Exception as exc:
        print(f"Centrum: CHYBA — {exc}")
        _note(args, centrum=f"CHYBA: {exc}"[:300])


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
    _note(args, den_dat=result.get("data_day"), beh=result["run_id"], varovani=len(result["warnings"]),
          kroky={k: str(v)[:60] for k, v in result["steps"].items()})
    _refresh_hub(args, conn)
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
    _note(args, beh=run_id, firem=st["firem_s_daty"], rakety=st["rakety"], do_ledgeru=len(created) + len(rockets))
    _refresh_hub(args, conn, cconn)
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
    _note(args, beh=run_id, signalu=len(result["aktualni"]["top"]), do_ledgeru=len(created))
    _refresh_hub(args, conn, cconn)
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
    if not args.force:                    # neopakovat výpočet bez důvodu (stejná data, stejná verze, žádný nový vstup)
        from stockradar.hub.registry import signals_unchanged
        why = signals_unchanged(conn, cconn, srun.MODELS)
        if why:
            print(f"Signály PŘESKOČENY: {why}. Přepočet vynutíš přepínačem --force.")
            _note(args, preskoceno=why)
            return 0
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
    runs = {}
    for name, r in res["modely"].items():
        r["vysledky_karet"] = sstore.scorecard(conn, r["obchodnich_dni"])
        r["nove_vyhodnoceno"] = len(evaluated)
        r = srun.clean(r)
        run_id = sstore.save_run(conn, r, name, r["konfigurace"])
        ids = sstore.save_forecasts(conn, run_id, r["karty"])
        runs[name] = run_id
        d = r["dnes"]["rozhodnuti"]
        t = r["zamceny_test"]
        print(f"{name} (běh #{run_id}): {len(ids)} nových karet; dnes RŮST {d['RŮST']}, POKLES {d['POKLES']},"
              f" NEVÍM {d['NEVÍM']}; zamčený test ({t.get('_stav')}): AUC růst {t.get('up5', {}).get('auc')},"
              f" pokles {t.get('down5', {}).get('auc')}")
    export_state(conn, state_dir())
    sizes = write_signals_doc(conn, web_dir())
    print(f"Vyhodnoceno dřívějších karet: {len(evaluated)}; web: " + ", ".join(f"{k} {v // 1024} kB" for k, v in sizes.items()))
    _note(args, behy=runs, vyhodnoceno=len(evaluated), xtb_dotazu=xsum["dotazu"])
    _refresh_hub(args, conn, cconn)
    _print_email_today(conn)
    return 0


def cmd_causal(args) -> int:
    """Kauzální radar: komodity → citlivost oborů → test řetězců (zamčený jednou) → události → karty → web."""
    from datetime import date as _date

    from stockradar.causal import chains, data as cdata, events, memo, radar
    from stockradar.causal import store as cstore
    from stockradar.discovery import cache as dcache
    from stockradar.signals import model as sm
    from stockradar.site import write_causal_doc
    from stockradar.sources import xtb

    conn = _open()
    cconn = dcache.connect()
    log = lambda m: print(f"  {m}", flush=True)
    if not args.no_download:
        cdata.download(cconn, log=log)
    comm = cdata.load(cconn)
    ex, data_end, from_memo = memo.load_or_build(cconn, log=log)     # ceny akcií se mění týdně → většinou z paměti
    weekly = ex.weekly
    periods = {"UCENI": (0, sm.TRAIN_END), "VALIDACE": sm.VAL, "TEST": sm.TEST}
    st = chains.study(ex, periods, log=log)
    reg = cstore.record_study(conn, st, periods)
    today = _date.fromordinal(data_end)
    gd_error = None
    try:
        gd = events.gdacs(_date.today())
    except Exception as exc:
        log(f"GDACS nedostupný: {exc}")
        gd, gd_error = [], str(exc)[:160]
    links = events.link_gdacs(gd)
    pulses = {} if args.no_news else {c: events.news_pulse(c, _date.today()) for c in comm}
    secs = [dict(r) for r in cconn.execute("SELECT symbol, name, industry, market_cap_usd FROM securities"
                                           " WHERE symbol NOT LIKE '%.%'")]
    checker = xtb.Checker(cconn)
    hist: dict[str, list[int]] = {}
    seen_days = {_date.today().isoformat()}                 # jeden běh za den, dnešní běhy se do základu nepočítají
    for r in conn.execute("SELECT run_at, result_json FROM causal_runs ORDER BY id DESC LIMIT 200"):
        if r[0][:10] in seen_days:
            continue
        seen_days.add(r[0][:10])
        for cid, n in (json.loads(r[1]).get("pulsy") or {}).items():     # počty zpráv u VŠECH komodit, ne jen karet
            if n is not None:
                hist.setdefault(cid, []).append(n)
        if len(seen_days) > 31:
            break
    res = radar.build(ex, comm, today, gdacs_links=links, pulses=pulses, securities=secs, study=st,
                      xtb_check=checker.check, pulse_history=hist)
    res["test_retezcu"] = reg
    res["pulsy"] = {c: p.get("pribehu_7d") for c, p in pulses.items()}
    res["gdacs"] = {"udalosti": len(gd), "navazane_komodity": sorted(links)} | ({"chyba": gd_error} if gd_error else {})
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
    _note(args, beh=run_id, karet=len(res["karty"]), prilezitosti=len(res["prilezitosti"]), predikci=len(ids),
          vyhodnoceno=len(evaluated), rady_z_pameti=from_memo, gdacs=gd_error or len(gd))
    _refresh_hub(args, conn, cconn)
    _print_email_today(conn)
    return 0


def cmd_hub(args) -> int:
    """Centrum: důkazy ze všech modulů → spolehlivost rolí → pohled na firmu, rozpory, kontroly → paměť + web."""
    conn = _open(create=False)
    _refresh_hub(args, conn)
    from stockradar.hub import integrate
    last = integrate.last_run(conn)
    if last:
        summ = last[1]
        for c in summ.get("kontroly", []):
            print(f"  [{c['uroven']}] {c['text']}")
        for z in (summ.get("zmeny") or [])[:15]:
            print(f"  změna: {z['ticker']} {z['z']} → {z['na']}")
    if args.firma:
        from stockradar.discovery import cache as dcache
        res = integrate.build(conn, dcache.connect(), utcnow().date())
        for tic in [t.strip().upper() for t in args.firma.split(",")]:
            d = next((x for x in res["firmy"] if x["ticker"] == tic), None)
            if d is None:
                print(f"\n{tic}: žádný modul o firmě nic neříká")
                continue
            print(f"\n{tic} {d['nazev'] or ''} — {d['souhrn']}")
            for line in d["retez"]:
                print(f"   · {line}")
            for r in d["rozpory"]:
                print(f"   ROZPOR: {r}")
            for l in d["pouceni"]:
                print(f"   POUČENÍ {l['klic']}: {l['bod']}")
            for k in d["kontrola"]:
                print(f"   KONTROLA: {k}")
            if d["poradi"]:
                print("   Pořadí v modelech: " + ", ".join(f"{m} {p}" for m, p in d["poradi"].items()))
    return 0


def cmd_system(args) -> int:
    """Celý systém na jedné obrazovce: moduly a jejich stavy, zdroje, spolehlivost rolí, deník, poslední centrum."""
    from stockradar.discovery import cache as dcache
    from stockradar.hub import feedback, integrate, registry

    conn = _open(create=False)
    cconn = dcache.connect()
    rel = feedback.reliability(conn)
    ov = registry.overview(conn, cconn, rel)
    print(f"SYSTÉM v{__version__} (schema v{schema_version(conn)}) — " + ", ".join(f"{k} {v}" for k, v in ov["pocty"].items()))
    print()
    print(_table(["Modul", "Stav", "Příkaz", "Poslední výstup", "Proč"],
                 [[m["nazev"][:44], m["stav"], m["prikaz"][:26], (m.get("posledni") or "–")[:16], m["duvod"][:90]]
                  for m in ov["moduly"]]))
    print()
    print(_table(["Zdroj", "Stav", "Detail"], [[z["zdroj"], z["stav"], z["detail"][:100]] for z in ov["zdroje"]]))
    print()
    print(_table(["Role modulu", "Stav", "Váha", "t", "Důkaz", "Živě (n/týdnů)"],
                 [[r["nazev"][:46], r["stav"], r["vaha"], r["t"], r["typ"][:38], f"{r['zive']['n']}/{r['zive']['tydnu']}"]
                  for r in rel.values()]))
    print()
    last = integrate.last_run(conn)
    if last:
        s = last[1]
        print(f"CENTRUM (běh #{last[0]}, {s['den']}): " + ", ".join(f"{k} {v}" for k, v in s["pocty"].items()))
        for c in s.get("kontroly", []):
            print(f"  [{c['uroven']}] {c['text']}")
    else:
        print("CENTRUM: zatím neběželo (python -m stockradar hub)")
    print()
    print("DENÍK (posledních 10 běhů)")
    rows = [[j["id"], j["prikaz"], j["zacatek"][:16], j["trvani_s"], j["stav"], (j["chyba"] or json.dumps(j["souhrn"], ensure_ascii=False))[:80]]
            for j in ov["denik"][:10]]
    print(_table(["#", "Příkaz", "Začátek (UTC)", "s", "Stav", "Souhrn / chyba"], rows) if rows else "(prázdný — deník se plní od v0.10.0)")
    return 0


def cmd_research(args) -> int:
    """Ruční výzkum jako trvalý důkaz (se zdrojem a platností). Bez --entita jen vypíše platné záznamy."""
    from stockradar.hub.evidence import add_research

    conn = _open(create=False)
    if args.entita:
        ids = [add_research(conn, entity_type=args.typ, entity=e.strip(), kind=args.druh, direction=args.smer,
                            horizon_days=args.horizont, summary=args.text, source=args.zdroj, source_url=args.url,
                            published_on=args.datum, valid_until=args.platnost,
                            status="NEOVĚŘENO" if args.neovereno else "OVĚŘENO")
               for e in args.entita.split(",") if e.strip()]
        export_state(conn, state_dir())
        print(f"Zapsáno {len(ids)} záznamů výzkumu: #{', #'.join(map(str, ids))}")
        _note(args, zapsano=ids)
        _refresh_hub(args, conn)
        return 0
    today = utcnow().date().isoformat()
    rows = [[r["id"], r["entity_type"], r["entity"], r["kind"], r["direction"], r["published_on"], r["valid_until"], r["status"],
             r["summary"][:70]] for r in conn.execute("SELECT * FROM research_evidence WHERE valid_until >= ? ORDER BY id", (today,))]
    print(_table(["#", "Typ", "Entita", "Druh", "Směr", "Zveřejněno", "Platí do", "Stav", "Shrnutí"], rows) if rows
          else "Žádný platný ruční výzkum.")
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
    _note(args, celkove=worst(checks), chyby=[c["kontrola"] for c in checks if c["uroven"] == "CHYBA"],
          varovani=[c["kontrola"] for c in checks if c["uroven"] == "VAROVÁNÍ"])
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
    p_sig = sub.add_parser("signals", help="signály na 14 dní, 1 měsíc a 6 měsíců: P(+5 %%), P(−5 %%), důvěra, NEVÍM; přísný test")
    p_sig.add_argument("--no-download", action="store_true", help="bez stažení čerstvých nákupů insiderů")
    p_sig.add_argument("--no-news", action="store_true", help="bez titulků (novost a kvalita informací)")
    p_sig.add_argument("--workers", type=int, default=4, help="počet procesů pro učení")
    p_sig.add_argument("--force", action="store_true", help="přepočítat i bez nových dat (jinak se běh přeskočí)")
    p_sig.set_defaults(func=cmd_signals)
    p_cau = sub.add_parser("causal", help="kauzální radar: událost → komodita → obory → firmy (+ test řetězců)")
    p_cau.add_argument("--no-download", action="store_true", help="bez stažení cen komodit")
    p_cau.add_argument("--no-news", action="store_true", help="bez zpráv o narušení (Google News)")
    p_cau.set_defaults(func=cmd_causal)
    p_hub = sub.add_parser("hub", help="centrum: důkazy ze všech modulů, spolehlivost, pohled na firmu, rozpory, kontroly")
    p_hub.add_argument("--firma", default=None, help="vypsat důkazní řetězec firem (např. VLO,MSFT)")
    p_hub.set_defaults(func=cmd_hub)
    sub.add_parser("system", help="stav celého systému: moduly, zdroje, spolehlivost, deník").set_defaults(func=cmd_system)
    p_res = sub.add_parser("research", help="ruční výzkum se zdrojem jako trvalý důkaz (bez --entita jen výpis)")
    p_res.add_argument("--entita", default=None, help="ticker(y) oddělené čárkou, nebo obor / komodita")
    p_res.add_argument("--typ", default="firma", choices=["firma", "obor", "komodita", "trh"])
    p_res.add_argument("--druh", default="kontext", choices=["prilezitost", "riziko", "katalyzator", "kontext"])
    p_res.add_argument("--smer", type=int, default=0, choices=[-1, 0, 1])
    p_res.add_argument("--horizont", type=int, default=90, help="dní")
    p_res.add_argument("--text", default="", help="shrnutí: fakt se zdrojem; úsudek označ jako úsudek")
    p_res.add_argument("--zdroj", default="", help="název zdroje")
    p_res.add_argument("--url", default="", help="https:// adresa zdroje")
    p_res.add_argument("--datum", default=None, help="den zveřejnění YYYY-MM-DD")
    p_res.add_argument("--platnost", default=None, help="platí do YYYY-MM-DD (jinak datum + horizont)")
    p_res.add_argument("--neovereno", action="store_true", help="zdroj je sekundární / fakt není potvrzen")
    p_res.set_defaults(func=cmd_research)
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


# Příkazy, které se zapisují do deníku (`system_runs`): mění data nebo kontrolují systém. Čistě čtecí příkazy
# (status, ledger, system, email…) a obnova ze state/ se nezapisují — deník nemá měnit stav jen tím, že se díváme.
JOURNALED = {"update", "discover", "smart-money", "signals", "causal", "sources", "hub", "research", "diag", "snapshot",
             "seed-lessons"}


def _journal(args, started, status: str, error: str | None = None) -> None:
    if not db_path().exists():
        return
    try:
        from stockradar.hub.registry import record_run
        conn = open_db(db_path())
        params = {k: v for k, v in vars(args).items() if k not in ("func", "journal", "command")}
        record_run(conn, args.command, params, started, status, getattr(args, "journal", {}), error)
        export_state(conn, state_dir())
    except Exception as exc:          # deník nesmí shodit hotovou práci
        print(f"Deník: zápis selhal ({exc})", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command not in JOURNALED or (args.command == "research" and not args.entita):
        return args.func(args)
    started = utcnow()
    args.journal = {}
    try:
        rc = args.func(args)
    except BaseException as exc:
        _journal(args, started, "CHYBA", f"{type(exc).__name__}: {exc}")
        raise
    status = "PŘESKOČENO" if args.journal.get("preskoceno") else "OK" if rc == 0 else "CHYBA"
    _journal(args, started, status, None if rc == 0 else f"návratový kód {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
