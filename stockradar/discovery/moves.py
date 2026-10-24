"""Co stálo za velkým pohybem akcie a co následovalo (v0.17.0, zadání uživatele 2026-10-23).

Navazuje na raketový deník (`diary.py`, tabulka rocket_events) — nic z něj neopakuje:
  1. Podání u SEC: ke každému novému pohybu jeden dotaz na EDGAR submissions API → podání firmy v okně pohybu
     (8-K s čísly bodů, 10-Q/10-K, emise akcií, 13D/13G, fúze, vyřazení z burzy) s odkazem na dokument. Primární
     zdroj, ale čte se jen TYP podání, ne obsah → příčina „SEC: typ podání“, pořád jen kvalifikovaný odhad.
  2. Co následovalo: cena 5 / 20 / 60 obchodních dní po posledním dni pohybu proti S&P 500 (move_outcomes).
  3. Historická studie: stejná pravidla (`diary.detect_at`) na 5 letech cen z cache → co obvykle následovalo podle
     směru, typu pohybu, objemu, velikosti firmy a podání u SEC (move_studies). Popis historie, ne předpověď:
     seznamy firem jsou dnešní (zkrachovalé chybí → výsledky po propadech vycházejí lépe, než byly), pohyby se shlukují
     v čase (krach 2022, duben 2025), takže nejsou nezávislé.
Pořadí důvěry příčiny: ruční OVĚŘENO (rocket_causes) > SEC (typ podání) > AUTO z titulků > neznámá.
"""

import bisect
import json
import math
import statistics
from collections import Counter
from datetime import date, timedelta

from stockradar.discovery import cache as dcache
from stockradar.discovery import diary, news
from stockradar.timeutil import to_iso, utcnow

HORIZONS = (5, 20, 60)
STUDY_VERSION = "4"                  # 2–3: + neupravené zpětné splity vyřazeny (FRGT); 4: kotva okna = medián 3 dnů (STFS)
STUDY_EVERY_DAYS = 7
SEC_LIMIT = 60                       # nejvýš tolik dotazů na SEC za běh (nové pohyby; zbytek příště)
MIN_GROUP = 30                       # menší skupina historie = MALÝ VZOREK
LIVE_MIN = 20                        # živé výsledky: pod 20 pohybů jen orientačně

# Body formuláře 8-K (SEC Form 8-K, General Instructions B)
ITEMS = {
    "1.01": "významná smlouva", "1.02": "ukončení významné smlouvy", "1.03": "bankrot / nucená správa",
    "1.04": "bezpečnost dolů", "1.05": "kybernetický incident", "2.01": "dokončená akvizice / prodej majetku",
    "2.02": "výsledky hospodaření", "2.03": "nový dluh", "2.04": "zesplatnění dluhu", "2.05": "náklady na útlum provozu",
    "2.06": "odpis majetku", "3.01": "upozornění burzy / vyřazení z burzy", "3.02": "prodej akcií mimo veřejnou nabídku",
    "3.03": "změna práv akcionářů (často zpětný split)", "4.01": "změna auditora",
    "4.02": "dřívější výkazy neplatí (oprava účetnictví)", "5.01": "změna kontroly nad firmou", "5.02": "změna ve vedení",
    "5.03": "změna stanov", "5.07": "hlasování akcionářů", "7.01": "informace pro investory", "8.01": "jiná událost",
    "9.01": "přílohy",
}
ITEM_CAUSE = {"1.01": "CONTRACT", "1.02": "CONTRACT", "1.03": "DELISTING", "2.01": "ACQUISITION", "2.02": "EARNINGS",
              "2.03": "FINANCING", "2.04": "FINANCING", "2.06": "EARNINGS", "3.01": "DELISTING", "3.02": "FINANCING",
              "4.02": "LEGAL", "5.01": "ACQUISITION"}
# formulář → (druh, kód příčiny nebo None, popis)
FORMS = {
    "8-K": ("8K", None, "oznámení 8-K"), "8-K/A": ("8K", None, "oprava 8-K"), "6-K": ("8K", None, "oznámení zahraniční firmy 6-K"),
    "10-Q": ("REPORT", "EARNINGS", "čtvrtletní zpráva 10-Q"), "10-K": ("REPORT", "EARNINGS", "výroční zpráva 10-K"),
    "20-F": ("REPORT", "EARNINGS", "výroční zpráva 20-F"), "40-F": ("REPORT", "EARNINGS", "výroční zpráva 40-F"),
    "NT 10-Q": ("REPORT", None, "oznámení o opožděné zprávě (NT 10-Q)"),
    "NT 10-K": ("REPORT", None, "oznámení o opožděné zprávě (NT 10-K)"),
    "S-1": ("OFFER", "FINANCING", "registrace emise S-1"), "S-3": ("OFFER", "FINANCING", "registrace emise S-3"),
    "F-1": ("OFFER", "FINANCING", "registrace emise F-1"), "F-3": ("OFFER", "FINANCING", "registrace emise F-3"),
    "424B1": ("OFFER", "FINANCING", "prospekt emise"), "424B3": ("OFFER", "FINANCING", "prospekt emise"),
    "424B4": ("OFFER", "FINANCING", "prospekt emise"), "424B5": ("OFFER", "FINANCING", "prospekt emise"),
    "424B7": ("OFFER", "FINANCING", "prospekt prodeje akcií"),
    "SC 13D": ("13D", "ACTIVIST", "nový velký akcionář 13D"), "SCHEDULE 13D": ("13D", "ACTIVIST", "nový velký akcionář 13D"),
    "SC 13D/A": ("13D", "ACTIVIST", "změna podílu 13D/A"), "SCHEDULE 13D/A": ("13D", "ACTIVIST", "změna podílu 13D/A"),
    "SC 13G": ("13G", None, "pasivní podíl nad 5 % (13G)"), "SCHEDULE 13G": ("13G", None, "pasivní podíl nad 5 % (13G)"),
    "SC TO-T": ("MERGER", "ACQUISITION", "nabídka převzetí (SC TO-T)"), "SC 14D9": ("MERGER", "ACQUISITION", "stanovisko k nabídce převzetí"),
    "DEFM14A": ("MERGER", "ACQUISITION", "hlasování o fúzi"), "PREM14A": ("MERGER", "ACQUISITION", "návrh hlasování o fúzi"),
    "425": ("MERGER", "ACQUISITION", "sdělení k fúzi (425)"), "SC TO-I": ("MERGER", None, "nabídka zpětného odkupu (SC TO-I)"),
    "25-NSE": ("DELIST", "DELISTING", "vyřazení z burzy (25-NSE)"), "25": ("DELIST", "DELISTING", "vyřazení z burzy (25)"),
    "15-12B": ("DELIST", "DELISTING", "ukončení registrace"), "15-12G": ("DELIST", "DELISTING", "ukončení registrace"),
}
# Které podání pohyb pravděpodobně spustilo, když jich je víc: u raket převzetí a výsledky, u propadů bankrot, opravy
# účetnictví a emise (prodej akcií po raketě je spíš důsledek než příčina — proto u raket až na konci).
PRIORITY = {1: ("ACQUISITION", "EARNINGS", "CONTRACT", "ACTIVIST", "LEGAL", "DELISTING", "FINANCING"),
            -1: ("DELISTING", "LEGAL", "FINANCING", "EARNINGS", "ACQUISITION", "CONTRACT", "ACTIVIST")}
LABEL = {c[0]: c[1] for c in news.CAUSES} | {"JINE": "jiná příčina", "CHYBA_DAT": "chyba dat (split)"}
# Historie: druhy z kvartálního indexu SEC (sources/sec.py FORMS) — body 8-K v indexu nejsou
HIST_KINDS = {"REPORT": "s výsledky (10-Q/10-K)", "OFFER": "s emisí akcií", "8K": "s oznámením 8-K",
              "13D": "s velkým akcionářem (13D/13G)", "13DA": "s velkým akcionářem (13D/13G)", "13G": "s velkým akcionářem (13D/13G)"}


# ------------------------------------------------------------------ 1. podání u SEC

def filing_causes(f: dict) -> list[str]:
    form = (f.get("form") or "").upper()
    kind = FORMS.get(form)
    codes = [ITEM_CAUSE[i] for i in (f.get("items") or "").split(",") if i.strip() in ITEM_CAUSE] if form.startswith(("8-K", "6-K")) else []
    if kind and kind[1]:
        codes.append(kind[1])
    return list(dict.fromkeys(codes))


def describe(f: dict) -> str:
    """Česky, co podání je: „8-K: výsledky hospodaření, přílohy“."""
    form = (f.get("form") or "").upper()
    items = [ITEMS.get(i.strip(), i.strip()) for i in (f.get("items") or "").split(",") if i.strip() and i.strip() != "9.01"]
    base = FORMS.get(form, (None, None, form))[2]
    return f"{form}: {', '.join(items)}" if items and form.startswith(("8-K", "6-K")) else base


def sec_cause(filings: list[dict], direction: int) -> dict | None:
    """Nejpravděpodobnější spouštěč pohybu podle typu podání (obsah se nečte → kvalifikovaný odhad)."""
    found = {}
    for f in filings:
        for code in filing_causes(f):
            found.setdefault(code, f)
    for code in PRIORITY[1 if direction > 0 else -1]:
        if code in found:
            f = found[code]
            return {"kod": code, "pricina": LABEL.get(code, code), "podani": describe(f), "datum": f["datum"], "url": f["url"]}
    return None


def in_window(rows: list[dict], start: str, end: str, *, limit: int = 15) -> list[dict]:
    keep = [r for r in rows if start <= r["datum"] <= end and (r["form"] or "").upper() in FORMS]
    keep.sort(key=lambda r: (r["datum"], r.get("prijato") or ""))
    return keep[-limit:]


def attach_sec(conn, cache_conn, *, limit: int = SEC_LIMIT, fetch=None, log=print) -> dict:
    """Podání u SEC k pohybům, které je ještě nemají (nejnovější první). Jeden dotaz na pohyb, evidovaný v email_usage.
    Chyba dotazu nic nezapíše — pohyb se zkusí znovu příští běh."""
    from stockradar import contact
    from stockradar.sources import sec

    todo = conn.execute("SELECT e.id, e.symbol, e.start_day, e.end_day FROM rocket_events e LEFT JOIN move_sec s"
                        " ON s.event_id = e.id WHERE s.id IS NULL ORDER BY e.end_day DESC, e.id DESC").fetchall()
    out = {"cekalo": len(todo), "dotazu": 0, "zapsano": 0, "bez_cik": 0, "chyb": 0}
    if not todo:
        return out
    if fetch is None and contact.email() is None:
        return {**out, "stav": "VYPNUTO — e-mail pro SEC není nastaven"}
    try:
        tick = {r[0]: r[1] for r in cache_conn.execute("SELECT ticker, cik FROM sec_tickers")}
    except Exception:
        tick = {}
    if not tick:
        return {**out, "stav": "BLOKOVÁNO — chybí seznam tickerů SEC (týdenní objevování)"}
    fetch = fetch or sec.fetch_submissions
    for ev in todo:
        cik = tick.get(ev["symbol"]) or tick.get(ev["symbol"].replace("-", "."))
        if cik is None:
            _store(conn, ev["id"], None, "BEZ_CIK", [])
            out["bez_cik"] += 1
            continue
        if out["dotazu"] >= limit:
            continue
        out["dotazu"] += 1
        try:
            rows = sec.recent_filings(fetch(cik), cik)
        except Exception as exc:
            out["chyb"] += 1
            log(f"SEC podání {ev['symbol']}: {str(exc)[:80]}")
            continue
        _store(conn, ev["id"], cik, "OK", in_window(rows, ev["start_day"], ev["end_day"]))
        out["zapsano"] += 1
    out["zbyva"] = max(0, len(todo) - out["bez_cik"] - out["zapsano"] - out["chyb"])
    return out


def _store(conn, event_id: int, cik: int | None, status: str, filings: list[dict]) -> None:
    with conn:
        conn.execute("INSERT INTO move_sec (event_id, cik, status, filings_json, checked_at) VALUES (?, ?, ?, ?, ?)",
                     (event_id, cik, status, json.dumps(filings, ensure_ascii=False), to_iso(utcnow())))


# ------------------------------------------------------------------ 2. co následovalo (živě)

def _merged(cache_conn, symbol: str, snaps: list[tuple]):
    from stockradar.discovery.winners import adjust_reverse_splits
    bars = dcache.load_series(cache_conn, symbol)
    if bars is None or not bars.days:
        return None
    bars, _ = adjust_reverse_splits(bars)
    d, c, _v, problem = diary.merge_series(bars.days, bars.closes, bars.volumes, snaps)
    return None if problem else (d, c)


def _spy_at(spy, day: int) -> float | None:
    i = bisect.bisect_right(spy.days, day) - 1
    return spy.values[i] if i >= 0 and day - spy.days[i] <= 3 and spy.values[i] > 0 else None


def record_outcomes(conn, cache_conn, *, today: date | None = None, spy=None) -> dict:
    """Výsledky 5 / 20 / 60 obchodních dní po pohybu. Zapisuje se jen se známou cenou akcie; bez SPY se čeká 10 dní,
    pak se zapíše bez srovnání s trhem. Řada s nevysvětleným skokem (split) se přeskočí, dokud ji Yahoo neopraví."""
    from stockradar.signals.regime import load_series
    today = today or utcnow().date()
    spy = spy if spy is not None else load_series(conn, "SPY")
    have = Counter(r[0] for r in conn.execute("SELECT event_id FROM move_outcomes"))
    rows = [r for r in conn.execute("SELECT id, symbol, end_day FROM rocket_events WHERE end_day <= ?",
                                    ((today - timedelta(days=6)).isoformat(),)) if have[r["id"]] < len(HORIZONS)]
    out = {"cekalo": len(rows), "zapsano": 0, "bez_ceny": 0}
    if not rows:
        return out
    cache_conn.executescript(diary.SNAP_SCHEMA)
    by_symbol: dict[str, list] = {}
    for r in rows:
        by_symbol.setdefault(r["symbol"], []).append(r)
    stamp = to_iso(utcnow())
    for sym, evs in by_symbol.items():
        snaps = [(date.fromisoformat(d).toordinal(), c, p, v) for d, c, p, v in cache_conn.execute(
            "SELECT day, close, prev_close, volume FROM nasdaq_snap WHERE symbol = ? ORDER BY day", (sym,))]
        series = _merged(cache_conn, sym, snaps)
        if series is None:
            out["bez_ceny"] += len(evs)
            continue
        d, c = series
        for ev in evs:
            base = date.fromisoformat(ev["end_day"]).toordinal()
            i0 = bisect.bisect_left(d, base)
            if i0 >= len(d) or d[i0] != base or c[i0] <= 0:
                out["bez_ceny"] += 1
                continue
            done = {h for (h,) in conn.execute("SELECT horizon FROM move_outcomes WHERE event_id = ?", (ev["id"],))}
            for h in HORIZONS:
                j = i0 + h
                if h in done or j >= len(d) or c[j] <= 0:
                    continue
                s0, s1 = _spy_at(spy, d[i0]), _spy_at(spy, d[j])
                if (s0 is None or s1 is None) and today.toordinal() - d[j] < 10:
                    continue                          # SPY za ten den ještě není — počkat
                with conn:
                    conn.execute("INSERT INTO move_outcomes (event_id, horizon, base_day, base_price, day, price, return_pct,"
                                 " spy_return_pct, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (ev["id"], h, date.fromordinal(d[i0]).isoformat(), c[i0], date.fromordinal(d[j]).isoformat(),
                                  c[j], round((c[j] / c[i0] - 1) * 100, 3),
                                  round((s1 / s0 - 1) * 100, 3) if s0 and s1 else None, stamp))
                out["zapsano"] += 1
    return out


def best_cause(conn, event: dict) -> dict:
    """Nejlepší dostupná příčina pohybu: OVĚŘENO > SEC (typ podání) > AUTO z titulků > neznámá."""
    c = conn.execute("SELECT cause_code, status, summary, source_url FROM rocket_causes WHERE event_id = ? ORDER BY id DESC"
                     " LIMIT 1", (event["id"],)).fetchone()
    if c and c["status"] == "OVĚŘENO":
        return {"kod": c["cause_code"], "zdroj": "OVĚŘENO", "text": c["summary"], "url": c["source_url"]}
    s = conn.execute("SELECT status, filings_json FROM move_sec WHERE event_id = ?", (event["id"],)).fetchone()
    sc = sec_cause(json.loads(s["filings_json"]), event.get("direction") or 1) if s else None
    if sc:
        return {"kod": sc["kod"], "zdroj": "SEC", "text": sc["podani"], "url": sc["url"]}
    if c:
        return {"kod": c["cause_code"], "zdroj": "NEOVĚŘENO", "text": c["summary"], "url": c["source_url"]}
    if event.get("auto_cause"):
        return {"kod": event["auto_cause"], "zdroj": "AUTO", "text": None, "url": None}
    return {"kod": None, "zdroj": None, "text": None, "url": None}


def _summ(rets: list[float], excess: list[float], direction: int) -> dict:
    n = len(rets)
    if not n:
        return {"n": 0}
    return {"n": n, "median": round(statistics.median(rets), 2),
            "pokracovalo": round(sum(1 for r in rets if r * direction > 0) / n, 3),
            "median_proti_trhu": round(statistics.median(excess), 2) if excess else None,
            "lepe_nez_trh": round(sum(1 for x in excess if x > 0) / len(excess), 3) if excess else None,
            "maly_vzorek": n < LIVE_MIN}


def live_stats(conn) -> dict:
    """Živé výsledky pohybů z deníku podle směru a nejlepší dostupné příčiny (vše v %)."""
    outs: dict[int, dict[int, tuple]] = {}
    for r in conn.execute("SELECT event_id, horizon, return_pct, spy_return_pct FROM move_outcomes"):
        outs.setdefault(r[0], {})[r[1]] = (r[2], r[3])
    events = [dict(r) for r in conn.execute("SELECT * FROM rocket_events")]
    errors = {r[0] for r in conn.execute("SELECT event_id FROM rocket_causes WHERE cause_code = 'CHYBA_DAT'")}
    res = {}
    for direction, key in ((1, "rakety"), (-1, "propady")):
        evs = [e for e in events if (e.get("direction") or 1) == direction and e["id"] not in errors]
        groups: dict[str, list] = {"všechny": evs}
        for e in evs:
            code = best_cause(conn, e)["kod"]
            groups.setdefault(LABEL.get(code, "příčina neznámá") if code else "příčina neznámá", []).append(e)
        res[key] = {"pohybu": len(evs), "skupiny": []}
        for name, members in sorted(groups.items(), key=lambda g: (g[0] != "všechny", -len(g[1]))):
            row = {"skupina": name, "pohybu": len(members)}
            for h in HORIZONS:
                vals = [outs[e["id"]][h] for e in members if h in outs.get(e["id"], {})]
                row[f"{h}d"] = _summ([v[0] for v in vals], [v[0] - v[1] for v in vals if v[1] is not None], direction)
            res[key]["skupiny"].append(row)
    return res


def cause_agreement(conn) -> dict:
    """Jak často AUTO z titulků a SEC (typ podání) souhlasí s ručně OVĚŘENOU příčinou — kolik jim věřit."""
    out = {"AUTO": [0, 0], "SEC": [0, 0]}
    for r in conn.execute("SELECT e.id, e.auto_cause, e.direction, c.cause_code FROM rocket_events e JOIN rocket_causes c"
                          " ON c.event_id = e.id WHERE c.status = 'OVĚŘENO' AND c.cause_code NOT IN ('CHYBA_DAT')"
                          " AND c.id = (SELECT MAX(id) FROM rocket_causes WHERE event_id = e.id)"):
        if r["auto_cause"]:
            out["AUTO"][1] += 1
            out["AUTO"][0] += r["auto_cause"] == r["cause_code"]
        s = conn.execute("SELECT filings_json FROM move_sec WHERE event_id = ? AND status = 'OK'", (r["id"],)).fetchone()
        sc = sec_cause(json.loads(s[0]), r["direction"] or 1) if s else None
        if sc:
            out["SEC"][1] += 1
            out["SEC"][0] += sc["kod"] == r["cause_code"]
    return {k: {"shoda": a, "z": n, "podil": round(a / n, 3) if n else None} for k, (a, n) in out.items()}


# ------------------------------------------------------------------ 3. historická studie (5 let)

def _sec_index(cache_conn) -> tuple[dict, dict]:
    tick, filings = {}, {}
    try:
        tick = {r[0]: r[1] for r in cache_conn.execute("SELECT ticker, cik FROM sec_tickers")}
        from stockradar.sources.sec import FORMS as INDEX_FORMS
        for cik, form, filed in cache_conn.execute("SELECT cik, form, filed FROM sec_filings"):
            kind = INDEX_FORMS.get(form)
            if kind in HIST_KINDS:
                filings.setdefault(cik, []).append((date.fromisoformat(filed).toordinal(), kind))
    except Exception:
        return {}, {}
    for v in filings.values():
        v.sort()
    return tick, filings


def _size(cap) -> str:
    if not cap:
        return "velikost neznámá"
    return "velké (nad 2 mld. USD)" if cap >= 2e9 else "střední (300 mil.–2 mld.)" if cap >= 3e8 else "malé (pod 300 mil. USD)"


def scan_history(cache_conn, spy, *, symbols: set[str] | None = None, log=print) -> list[dict]:
    """Všechny historické pohyby podle pravidel deníku + výnos po 5 / 20 / 60 dnech (bez přesahu do budoucnosti
    při výběru: rozhoduje jen cena do dne pohybu)."""
    from stockradar.discovery.bestideas import is_fund
    from stockradar.discovery.study import anomalous
    from stockradar.discovery.winners import adjust_reverse_splits, is_bad_tick

    tick, sec_files = _sec_index(cache_conn)
    meta = {r[0]: (r[1], r[2], r[3]) for r in cache_conn.execute("SELECT symbol, name, market_cap_usd, industry FROM securities")}
    up_th = {k: 1 + th for k, th in diary.UP.values()}          # {1: 1.25, 5: 1.30, 10: 1.40, 21: 1.50}
    dn_th = {k: 1 + th for k, th in diary.DOWN.values()}        # zrcadlově 0.80 / 0.77 / 0.71 / 0.67
    events = []
    for bars in dcache.iter_series(cache_conn):
        sym = bars.symbol
        if "." in sym or sym.startswith("^") or (symbols is not None and sym not in symbols):
            continue
        name, cap, industry = meta.get(sym, (None, None, None))
        if is_fund(name, industry) or anomalous(bars):
            continue
        bars, _ = adjust_reverse_splits(bars)
        d, c, v = bars.days, bars.closes, bars.volumes
        n = len(c)
        cik = tick.get(sym)
        files = sec_files.get(cik, []) if cik else []
        last = {1: -10**9, -1: -10**9}
        for i in range(21, n):
            ci = c[i]
            if ci <= 0:
                continue
            a1, a5, a10, a21 = c[i - 1], c[i - 5], c[i - 10], c[i - 21]
            up = (a1 > 0 and ci >= a1 * up_th[1]) or (a5 > 0 and ci >= a5 * up_th[5]) or \
                 (a10 > 0 and ci >= a10 * up_th[10]) or (a21 > 0 and ci >= a21 * up_th[21])
            dn = (ci <= a1 * dn_th[1]) or (ci <= a5 * dn_th[5]) or (ci <= a10 * dn_th[10]) or (ci <= a21 * dn_th[21])
            if not (up or dn):
                continue
            for direction, flag in ((1, up), (-1, dn)):
                if not flag or d[i] - last[direction] <= diary.EPISODE_DAYS:
                    continue
                hit = diary.detect_at(d, c, v, i, direction)
                # chyby dat typu „skok a návrat do 5 dní“ (VWAV) — jediné místo, kde výběr hledí dopředu; u skutečných
                # akcií tenhle vzor prakticky nenastává, chyba dat by ale zkreslila „co následovalo“
                if hit is None or diary.same_story(hit, last[direction] if last[direction] > 0 else None) or \
                        is_bad_tick(c, i) or diary.glitch(c[max(0, i - 41):i + 6], lookback=46) or \
                        (direction > 0 and diary.unadjusted_split(c, v, i, until=min(n - 1, i + 5))):
                    continue
                last[direction] = d[i]
                s0 = _spy_at(spy, d[i])
                row = {"smer": direction, "den": d[i], "jednodenni": "1d" in hit["okna"],
                       "objem": hit["rel_objem"], "velikost": _size(cap), "cik": bool(cik), "druhy": set(), "vynos": {}}
                if files:
                    lo = bisect.bisect_left(files, (hit["start"], ""))
                    hi = bisect.bisect_right(files, (d[i], "~"))
                    row["druhy"] = {HIST_KINDS[k] for _, k in files[lo:hi]}
                for h in HORIZONS:
                    j = i + h
                    if j < n and c[j] > 0:
                        r = (c[j] / ci - 1) * 100
                        s1 = _spy_at(spy, d[j])
                        row["vynos"][h] = (r, r - (s1 / s0 - 1) * 100 if s0 and s1 else None)
                events.append(row)
    log(f"Historie pohybů: {sum(1 for e in events if e['smer'] > 0)} raket, {sum(1 for e in events if e['smer'] < 0)} propadů")
    return events


def _hist_summ(members: list[dict], direction: int) -> dict:
    row = {"pohybu": len(members), "maly_vzorek": len(members) < MIN_GROUP}
    for h in HORIZONS:
        vals = [m["vynos"][h] for m in members if h in m["vynos"]]
        rets = [r for r, _ in vals]
        exc = [x for _, x in vals if x is not None]
        row[f"{h}d"] = {"n": len(rets),
                        "median": round(statistics.median(rets), 2) if rets else None,
                        "pokracovalo": round(sum(1 for r in rets if r * direction > 0) / len(rets), 3) if rets else None,
                        "median_proti_trhu": round(statistics.median(exc), 2) if exc else None,
                        "lepe_nez_trh": round(sum(1 for x in exc if x > 0) / len(exc), 3) if exc else None,
                        # pro představu o chvostu: čtvrtina nejhorších / nejlepších (medián nic neříká o extrémech)
                        "dolni_ctvrtina": round(_q(rets, 0.25), 1) if len(rets) >= 8 else None,
                        "horni_ctvrtina": round(_q(rets, 0.75), 1) if len(rets) >= 8 else None}
    return row


def _q(values: list[float], q: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def summarize_history(events: list[dict]) -> dict:
    out = {"pohybu": len(events), "skupiny": {}}
    if not events:
        return out
    days = [e["den"] for e in events]
    out["obdobi"] = [date.fromordinal(min(days)).isoformat(), date.fromordinal(max(days)).isoformat()]
    for direction, key in ((1, "rakety"), (-1, "propady")):
        evs = [e for e in events if e["smer"] == direction]
        groups = [("všechny", evs),
                  ("jednodenní skok" if direction > 0 else "jednodenní pád", [e for e in evs if e["jednodenni"]]),
                  ("postupně (bez jednodenního skoku)", [e for e in evs if not e["jednodenni"]]),
                  ("objem aspoň 5× běžný", [e for e in evs if (e["objem"] or 0) >= 5]),
                  ("objem pod 5× běžný", [e for e in evs if e["objem"] is not None and e["objem"] < 5])]
        for label in sorted({x for e in evs for x in e["druhy"]}):
            groups.append((label, [e for e in evs if label in e["druhy"]]))
        groups.append(("bez podání u SEC v okně", [e for e in evs if e["cik"] and not e["druhy"]]))
        for size in ("velké (nad 2 mld. USD)", "střední (300 mil.–2 mld.)", "malé (pod 300 mil. USD)"):
            groups.append((size, [e for e in evs if e["velikost"] == size]))
        years = Counter(date.fromordinal(e["den"]).year for e in evs)
        by_year = []
        for y in sorted(years):
            ye = [e for e in evs if date.fromordinal(e["den"]).year == y]
            exc = [e["vynos"][20][1] for e in ye if 20 in e["vynos"] and e["vynos"][20][1] is not None]
            by_year.append({"rok": y, "pohybu": len(ye), "median_20d_proti_trhu": round(statistics.median(exc), 2) if exc else None})
        busiest = Counter(e["den"] for e in evs).most_common(3)
        out["skupiny"][key] = {
            "pohybu": len(evs), "dni_s_pohyby": len({e["den"] for e in evs}),
            "nejvic_v_jeden_den": [{"den": date.fromordinal(dy).isoformat(), "pohybu": k} for dy, k in busiest],
            "podle_roku": by_year,
            "tabulka": [{"skupina": g, **_hist_summ(m, direction)} for g, m in groups if m],
        }
    return out


def history_study(conn, cache_conn, *, force: bool = False, log=print) -> dict | None:
    """Přepočet historické studie nejvýš jednou za STUDY_EVERY_DAYS (nebo po změně verze). Vrací nový výsledek / None."""
    from stockradar.signals.regime import load_series
    last = conn.execute("SELECT run_at, version FROM move_studies ORDER BY id DESC LIMIT 1").fetchone()
    if last and not force and last["version"] == STUDY_VERSION and \
            (utcnow().date() - date.fromisoformat(last["run_at"][:10])).days < STUDY_EVERY_DAYS:
        return None
    spy = load_series(conn, "SPY")
    events = scan_history(cache_conn, spy, log=log)
    if not events:
        return None
    res = summarize_history(events)
    res["poznamky"] = [
        "Popis historie, ne předpověď: co obvykle následovalo po podobném pohybu (stejná pravidla jako deník).",
        "Seznam firem je dnešní — zkrachovalé a vyřazené firmy chybí, proto výsledky vycházejí lépe, než byly (nejvíc po propadech a u malých firem).",
        "Pohyby se shlukují v čase (stejný den padá mnoho akcií), takže nejsou nezávislé; viz dny s nejvíc pohyby a roky.",
        "Velikost firmy je dnešní tržní hodnota. Podání u SEC jen z kvartálního indexu (bez čísel bodů 8-K).",
        "Vyřazené chyby dat: skok a návrat do 5 dní (nastává jen u chybně upravených splitů).",
    ]
    res["spy"] = "S&P 500 (SPY) z price_bars" if spy.days else "SPY chybí — bez srovnání s trhem"
    data_through = date.fromordinal(max(e["den"] for e in events)).isoformat()
    with conn:
        conn.execute("INSERT INTO move_studies (run_at, data_through, version, result_json) VALUES (?, ?, ?, ?)",
                     (to_iso(utcnow()), data_through, STUDY_VERSION, json.dumps(res, ensure_ascii=False)))
    return res
