"""Raketový deník (zadání uživatele 2026-10-13, propady a jednodenní skoky od v0.17.0 — zadání 2026-10-23):
velké pohyby akcií za 1 / 5 / 10 / 21 obchodních dní → příčina (SEC, titulky, ruční ověření) → co následovalo.

Data: týdenní ceny z Yahoo (cache objevování) + denní snímek Nasdaq screeneru (1 dotaz denně, všechny americké akcie:
poslední závěr, změna, objem). Z „poslední cena − změna“ je i předchozí závěr → kontrola návaznosti: když nesedí na cenu
z Yahoo o víc než 25 %, jde skoro jistě o split nebo chybu dat (poučení CHYBA-DAT-REVERSE-SPLIT) a firma se přeskočí.

Raketa: ≥ +25 % za 1, ≥ +30 % za 5, ≥ +40 % za 10 nebo ≥ +50 % za 21 obchodních dní. Propad: zrcadlově v logaritmech
(−20 % / −23 % / −29 % / −33 %, stejně jako zrcadlové propady v objevování). Likvidní (medián obratu 20 dní ≥ 1 mil. USD)
a cena ≥ 1 USD (u propadu cena na začátku okna). Epizoda = jedna firma a jeden směr v okně 21 kalendářních dní
(týdenní a měsíční raketa téže firmy je jeden příběh; raketa a pak propad jsou dva).
Příčina: AUTO z titulků Google News (neověřeno) → ruční ověření z primárního zdroje (8-K, tisková zpráva, FDA, SEC)
v tabulce `rocket_causes`. Příčina je známá až po pohybu, proto sama nic nepředpovídá — slouží ke studiu předzvěstí
a toho, co následuje po raketě (hypotéza H-R1, docs/agent_vyzkum/README.md).
"""

import json
import math
import statistics
from datetime import date, datetime, timedelta, timezone

from stockradar.discovery import cache as dcache
from stockradar.discovery import news
from stockradar.timeutil import to_iso, utcnow

UP = {"1d": (1, 0.25), "5d": (5, 0.30), "10d": (10, 0.40), "21d": (21, 0.50)}
DOWN = {k: (n, 1 / (1 + th) - 1) for k, (n, th) in UP.items()}      # −20 % / −23 % / −29 % / −33 %
WINDOWS = {1: UP, -1: DOWN}
MIN_TURNOVER, MIN_PRICE = 1_000_000, 1.0
MAX_GAP = 0.25                 # nesoulad předchozího závěru se snímkem → split / chyba dat
EPISODE_DAYS = 21
CODES = {c[0] for c in news.CAUSES} | {"JINE", "CHYBA_DAT"}
SNAP_SCHEMA = """
CREATE TABLE IF NOT EXISTS nasdaq_snap (
    day         TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    close       REAL NOT NULL,
    prev_close  REAL,
    volume      REAL,
    mcap        REAL,
    name        TEXT,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (day, symbol)
);
"""
try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:          # bez tzdata: letní čas USA jako výchozí odhad
    _NY = timezone(timedelta(hours=-4))


def session_day(now: datetime) -> date | None:
    """Poslední UKONČENÝ obchodní den v New Yorku; None během obchodování (snímek by měl cenu uprostřed dne)."""
    ny = now.astimezone(_NY)
    t = ny.hour * 60 + ny.minute
    if ny.weekday() < 5 and 9 * 60 + 30 <= t < 16 * 60 + 15:
        return None
    d = ny.date() if ny.weekday() < 5 and t >= 16 * 60 + 15 else ny.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _num(s) -> float | None:
    try:
        return float(str(s).replace("$", "").replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def parse_snapshot(rows: list[dict]) -> list[tuple]:
    """Řádky screeneru → (symbol, close, prev_close, volume, mcap, name); bez ceny se přeskočí."""
    out = []
    for r in rows:
        sym = (r.get("symbol") or "").strip()
        close = _num(r.get("lastsale"))
        if not sym or "^" in sym or not close or close <= 0:
            continue
        chg = _num(r.get("netchange"))
        prev = close - chg if chg is not None and close - chg > 0 else None
        out.append((sym.replace("/", "-"), close, prev, _num(r.get("volume")), _num(r.get("marketCap")), r.get("name")))
    return out


def reference_closes(main_conn, *, days: int = 20) -> dict[str, dict[str, float]]:
    """Denní závěry amerických akcií ze sledovaných firem (price_bars, Yahoo s datem) — podle nich se pozná, ze kterého
    dne snímek screeneru opravdu je."""
    since = (utcnow().date() - timedelta(days=days)).isoformat()
    out: dict[str, dict[str, float]] = {}
    for sym, day, close in main_conn.execute("SELECT symbol, date, close FROM price_bars WHERE date >= ? AND close > 0", (since,)):
        if "." not in sym and "=" not in sym and not sym.startswith("^"):
            out.setdefault(sym, {})[day] = close
    return out


def data_day(rows, reference: dict[str, dict[str, float]], *, tol: float = 0.0015) -> tuple[str | None, int, int]:
    """Ze kterého obchodního dne ceny snímku jsou: závěr firmy se porovná se závěry z Yahoo; vyhraje den, na který sedí
    nejvíc firem. Vrací (den, shod, porovnaných firem)."""
    from collections import Counter
    votes, compared = Counter(), 0
    for r in rows:
        ref = reference.get(r[0])
        if not ref:
            continue
        compared += 1
        for day, c in ref.items():
            if abs(r[1] / c - 1) < tol:
                votes[day] += 1
    if not votes:
        return None, 0, compared
    day, n = votes.most_common(1)[0]
    return day, n, compared


def _trusted(day, n, compared) -> bool:
    return day is not None and n >= 3 and n >= 0.6 * compared


def repair_snapshots(cache_conn, reference: dict, *, log=print) -> list[str]:
    """Snímky s cenami jiného dne, než nesou (screener vydá závěr dne D až ráno D+1 — večerní běh tak dřív zapsal
    ceny z D−1 pod D, 2026-10-23): přejmenovat na skutečný den, nebo smazat, když ten už je. Cache, ne historie."""
    cache_conn.executescript(SNAP_SCHEMA)
    fixes = []
    for (label,) in cache_conn.execute("SELECT DISTINCT day FROM nasdaq_snap ORDER BY day DESC LIMIT 15").fetchall():
        rows = [tuple(r) for r in cache_conn.execute("SELECT symbol, close FROM nasdaq_snap WHERE day = ?", (label,))]
        day, n, comp = data_day(rows, reference)
        if not _trusted(day, n, comp) or day == label:
            continue
        with cache_conn:
            if cache_conn.execute("SELECT 1 FROM nasdaq_snap WHERE day = ? LIMIT 1", (day,)).fetchone():
                cache_conn.execute("DELETE FROM nasdaq_snap WHERE day = ?", (label,))
                fixes.append(f"{label}: ceny jsou z {day}, který už je → smazáno")
            else:
                cache_conn.execute("UPDATE nasdaq_snap SET day = ? WHERE day = ?", (day, label))
                fixes.append(f"{label}: ceny jsou z {day} → přejmenováno")
    for f in fixes:
        log(f"Snímek {f}")
    return fixes


def take_snapshot(cache_conn, *, now: datetime | None = None, fetch=None, reference: dict | None = None, log=print) -> dict:
    """Uloží denní snímek (jen mimo obchodní hodiny) pod dnem, ze kterého ceny opravdu jsou: podle `reference` (závěry
    z Yahoo), jinak podle hodin. Stejné ceny jako minulý snímek = svátek / zastaralá data → neukládá se."""
    cache_conn.executescript(SNAP_SCHEMA)
    now = now or utcnow()
    day = session_day(now)
    if day is None:
        return {"stav": "PŘESKOČENO", "duvod": "trh v New Yorku právě obchoduje — snímek až po závěru"}
    if not reference and cache_conn.execute("SELECT 1 FROM nasdaq_snap WHERE day = ? LIMIT 1", (day.isoformat(),)).fetchone():
        return {"stav": "UŽ JE", "den": day.isoformat()}
    if fetch is None:
        from stockradar.discovery import listings
        fetch = lambda: json.loads(listings._get(listings.NASDAQ_SCREENER))["data"]["rows"]
    rows = parse_snapshot(fetch())
    if reference:
        actual, n, comp = data_day(rows, reference)
        if _trusted(actual, n, comp):
            if actual != day.isoformat():
                log(f"Snímek: screener ukazuje závěr z {actual}, ne z {day} — ukládá se pod {actual}")
            day = date.fromisoformat(actual)
        elif comp >= 3:
            return {"stav": "NEOVĚŘENO", "duvod": f"ceny screeneru nesedí na žádný den z Yahoo ({n} z {comp} firem)"}
        if cache_conn.execute("SELECT 1 FROM nasdaq_snap WHERE day = ? LIMIT 1", (day.isoformat(),)).fetchone():
            return {"stav": "UŽ JE", "den": day.isoformat()}
    last = cache_conn.execute("SELECT MAX(day) FROM nasdaq_snap").fetchone()[0]
    if last:
        prev = {s: c for s, c in cache_conn.execute("SELECT symbol, close FROM nasdaq_snap WHERE day = ?", (last,))}
        common = [r for r in rows if r[0] in prev]
        if common and sum(1 for r in common if abs(prev[r[0]] - r[1]) < 1e-9) / len(common) > 0.95:
            return {"stav": "PŘESKOČENO", "duvod": f"ceny shodné se snímkem {last} (svátek nebo nová data ještě nejsou)"}
    stamp = to_iso(utcnow())
    with cache_conn:
        cache_conn.executemany("INSERT OR REPLACE INTO nasdaq_snap VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               [(day.isoformat(), *r, stamp) for r in rows])
    log(f"Snímek Nasdaq {day}: {len(rows)} akcií")
    return {"stav": "OK", "den": day.isoformat(), "akcii": len(rows)}


def safety_snapshot(main_conn, cache_conn, *, now: datetime | None = None, fetch=None, log=print) -> dict:
    """Snímek i z večerního `update`: 29. 10. se ranní deník spustil až po otevření trhu v New Yorku a závěr 28. 10. by
    chyběl natrvalo. Ukládá se pod dnem, ze kterého ceny opravdu jsou; chyba sítě denní běh nezastaví."""
    try:
        reference = reference_closes(main_conn)
        repair_snapshots(cache_conn, reference, log=log)
        return take_snapshot(cache_conn, now=now, fetch=fetch, reference=reference, log=log)
    except Exception as e:  # noqa: BLE001 — záchranný krok
        return {"stav": "CHYBA", "duvod": f"{type(e).__name__}: {str(e)[:100]}"}


def merge_series(days, closes, volumes, snaps: list[tuple]) -> tuple[list, list, list, str | None]:
    """Yahoo řada + dny snímků po jejím konci. snaps = [(den_ordinal, close, prev_close, volume)] seřazené podle dne.
    Vrací (dny, ceny, objemy, problém); problém = důvod, proč řadu nepoužít (split, stará data)."""
    d, c, v = list(days), list(closes), list(volumes)
    recent = dict(zip(d[-40:], c[-40:]))
    for day, close, prev, vol in snaps:
        if d and day <= d[-1]:
            # týž den v obou zdrojích: Yahoo někdy upraví zpětný split jen u části dnů (DKI 1:50 k 22. 10. 2026)
            y = recent.get(day)
            if y and y > 0 and abs(close / y - 1) > MAX_GAP:
                return d, c, v, f"Yahoo {y:.4g} a Nasdaq {close:.4g} za týž den nesedí — pravděpodobně split / chyba dat"
            continue
        if not d or day - d[-1] > 7:
            return d, c, v, "stará data — mezi cenami z Yahoo a snímkem je mezera"
        if prev and c[-1] > 0 and abs(prev / c[-1] - 1) > MAX_GAP:
            return d, c, v, f"předchozí závěr {prev:.4g} nesedí na {c[-1]:.4g} — pravděpodobně split / chyba dat"
        d.append(day); c.append(close); v.append(vol or 0.0)
    return d, c, v, None


def anchor(closes, i: int, k: int) -> float:
    """Kotva okna k dní: medián tří závěrů kolem dne i − k, ne jediný den — jednodenní výkyv v kotvě nesmí vyrobit pohyb
    (STFS 2026-10-21: 3,62 → 2,90 → 3,66 USD, 21denní „raketa“ +51 % jen z propadu v kotvě; bez něj +19 %). Okno 1 den
    kotví na včerejším závěru — jednodenní skok je definován proti předchozímu dni."""
    if k == 1 or i - k - 1 < 0:
        return closes[i - k]
    return statistics.median(closes[i - k - 1:i - k + 2])


def detect_at(days, closes, volumes, i: int, direction: int = 1) -> dict | None:
    """Splněná okna jednoho směru ke dni `i` (nebo None). Stejná funkce slouží živému deníku (poslední den) i historické
    studii (každý den) — pravidla jsou tak v obou stejná."""
    if i < 21 or closes[i] <= 0:
        return None
    moves, hit, k_max, starts = {}, [], 0, {}
    for name, (k, th) in WINDOWS[direction].items():
        base = anchor(closes, i, k)
        moves[name] = closes[i] / base - 1 if base > 0 else None
        m = moves[name]
        if m is not None and (m >= th if direction > 0 else m <= th):
            hit.append(name)
            starts[name] = days[i - k]
            k_max = k                                 # nejdelší splněné okno určuje začátek
    if not hit:
        return None
    if (closes[i] if direction > 0 else closes[i - k_max]) < MIN_PRICE:
        return None
    turn = statistics.median(closes[j] * volumes[j] for j in range(i - 19, i + 1))
    if turn < MIN_TURNOVER:
        return None
    usual = statistics.median(volumes[j] for j in range(i - 20, i))
    return {"smer": direction, "okna": hit, "moves": moves, "start": days[i - k_max], "starty": starts, "end": days[i],
            "cena": closes[i], "obrat": turn, "rel_objem": volumes[i] / usual if usual > 0 else None}


def same_story(hit: dict, last_end: int | None) -> bool:
    """Patří detekce k předchozí epizodě stejného směru? Ano do 21 kalendářních dní od jejího konce — a i později, dokud
    všechna splněná okna ještě začínají před jejím koncem (21 obchodních dní je ~30 kalendářních: měsíční okno by jinak
    tentýž skok po 22 dnech zapsalo podruhé)."""
    if last_end is None:
        return False
    if hit["end"] - last_end <= EPISODE_DAYS:
        return True
    starts = list((hit.get("starty") or {}).values()) or [hit["start"]]
    return all(s < last_end for s in starts)


def detect(days, closes, volumes, direction: int = 1) -> dict | None:
    """Splněná okna k poslednímu dni řady (nebo None)."""
    return detect_at(days, closes, volumes, len(closes) - 1, direction)


def strength(r: dict) -> float:
    """Velikost pohybu v logaritmech (raketa +100 % = propad −50 %) přes splněná okna — pořadí pro titulky a web."""
    return max(abs(math.log1p(r["moves"][k])) for k in r["okna"] if r["moves"].get(k) is not None and r["moves"][k] > -1)


def unadjusted_split(closes, volumes, i: int, *, lookback: int = 21, until: int | None = None) -> bool:
    """Skok aspoň 2,9× za den, po kterém se obchoduje méně než polovina běžného počtu kusů = skoro jistě neupravený
    zpětný split, ne raketa (FRGT 2026-10-19: split 1:10, v datech „+558 % za týden“, objem pak 0,1× běžného; v den
    splitu samotném bývá objem vysoký). Skutečná raketa má objem i po skoku vysoký. Rozhoduje medián objemu ode dne
    skoku do `until` (živě do dneška; historie smí kvůli chybám dat hledět 5 dní dopředu). Doplňuje
    `winners.reverse_split_points`, které chce poměr přesně na násobku splitu."""
    end = i if until is None else until
    for k in range(max(21, i - lookback + 1), i + 1):
        a = closes[k - 1]
        if a > 0 and closes[k] / a >= 2.9:
            usual = statistics.median(volumes[k - 20:k])
            after = statistics.median(volumes[k:end + 1])
            if usual > 0 and after <= 0.5 * usual:
                return True
    return False


def glitch(closes, *, lookback: int = 40, drop: float = 0.2, back: float = 0.3, within: int = 5) -> bool:
    """Chyba dat typu „propad a návrat“: cena během dne klesne aspoň 5× a do `within` dnů se vrátí aspoň na 30 %
    původní úrovně. U skutečných akcií prakticky nenastává; vzniká, když zdroj upraví zpětný split jen u části dnů
    (VWAV 2026-10-16: 9,06 → 0,53 → 0,38 → 7,32 kolem splitu 1:20; detektor splitu to nepoznal kvůli objemům)."""
    n = len(closes)
    for k in range(max(1, n - lookback), n):
        a, b = closes[k - 1], closes[k]
        if a > 0 and b / a <= drop and any(closes[j] / a >= back for j in range(k + 1, min(n, k + 1 + within))):
            return True
    return False


def scan(cache_conn, symbols: set[str] | None = None) -> tuple[list[dict], dict]:
    """Rakety a propady ke dni posledního snímku (americké akcie)."""
    cache_conn.executescript(SNAP_SCHEMA)
    snaps: dict[str, list[tuple]] = {}
    for day, sym, close, prev, vol in cache_conn.execute(
            "SELECT day, symbol, close, prev_close, volume FROM nasdaq_snap ORDER BY day"):
        snaps.setdefault(sym, []).append((date.fromisoformat(day).toordinal(), close, prev, vol))
    from stockradar.discovery.bestideas import is_fund
    from stockradar.discovery.study import anomalous
    from stockradar.discovery.winners import adjust_reverse_splits
    meta = {r[0]: (r[1], r[2], r[3]) for r in cache_conn.execute("SELECT symbol, name, market_cap_usd, industry FROM securities")}
    stats = {"rad": 0, "split_nebo_chyba": 0, "stara_data": 0, "fondy": 0, "raket": 0, "propadu": 0}
    found = []
    for bars in dcache.iter_series(cache_conn):
        sym = bars.symbol
        if "." in sym or (symbols is not None and sym not in symbols):
            continue
        stats["rad"] += 1
        name, cap, industry = meta.get(sym, (None, None, None))
        if is_fund(name, industry):                   # uzavřené fondy nejsou firmy (DHY)
            stats["fondy"] += 1
            continue
        if anomalous(bars) or glitch(bars.closes):    # kontrola kvality jako v objevování (NFE) + propad a návrat (VWAV)
            stats["split_nebo_chyba"] += 1
            continue
        bars, _ = adjust_reverse_splits(bars)         # neupravené zpětné splity (poučení CHYBA-DAT-REVERSE-SPLIT)
        d, c, v, problem = merge_series(bars.days, bars.closes, bars.volumes, snaps.get(sym, []))
        if problem:
            stats["split_nebo_chyba" if "split" in problem else "stara_data"] += 1
            continue
        for direction in (1, -1):
            hit = detect(d, c, v, direction)
            if hit and direction > 0 and unadjusted_split(c, v, len(c) - 1):
                stats["split_nebo_chyba"] += 1
                continue
            if hit:
                found.append({"symbol": sym, "nazev": name, "mcap": cap, "obor": industry, **hit})
    stats["raket"] = sum(1 for r in found if r["smer"] > 0)
    stats["propadu"] = len(found) - stats["raket"]
    found.sort(key=lambda r: -strength(r))
    return found, stats


def record_new(conn, found: list[dict], *, today: date, auto=None, top_auto: int = 10, log=print) -> list[dict]:
    """Zapíše nové epizody (firma bez pohybu stejného směru v posledních 21 dnech); u prvních `top_auto` (podle síly
    pohybu) příčinu z titulků (AUTO)."""
    new = []
    for r in found:
        r.setdefault("smer", 1)
        last = conn.execute("SELECT MAX(end_day) FROM rocket_events WHERE symbol = ? AND direction = ?",
                            (r["symbol"], r["smer"])).fetchone()[0]
        if same_story(r, date.fromisoformat(last).toordinal() if last else None):
            continue
        new.append(r)
    for i, r in enumerate(new):
        info = None
        if auto is not None and i < top_auto:
            try:
                info = auto(r["nazev"] or r["symbol"], date.fromordinal(r["start"]), date.fromordinal(r["end"]), symbol=r["symbol"])
            except Exception as exc:              # zprávy nesmí shodit zápis raket
                info = {"stav": "DATA NEDOSTUPNÁ", "duvod": str(exc)[:120]}
        m = r["moves"]
        with conn:
            cur = conn.execute(
                "INSERT INTO rocket_events (symbol, name, detected_on, start_day, end_day, windows, move_5d, move_10d, move_21d,"
                " price, turnover_usd, market_cap_usd, auto_cause, auto_json, recorded_at, direction, move_1d, rel_volume)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r["symbol"], r["nazev"], today.isoformat(), date.fromordinal(r["start"]).isoformat(),
                 date.fromordinal(r["end"]).isoformat(), ",".join(r["okna"]), m.get("5d"), m.get("10d"), m.get("21d"),
                 r["cena"], r["obrat"], r["mcap"], (info or {}).get("kod"),
                 json.dumps(_slim(info), ensure_ascii=False) if info else None, to_iso(utcnow()),
                 r["smer"], m.get("1d"), r.get("rel_objem")))
        r["id"] = cur.lastrowid
        r["auto"] = info
    up = sum(1 for r in found if r.get("smer", 1) > 0)
    log(f"Raketový deník: {up} raket, {len(found) - up} propadů, nových epizod {len(new)}")
    return new


def _slim(info: dict) -> dict:
    keep = ("stav", "hlavni_pricina", "kod", "planovany_termin", "titulku_pred", "titulku_behem")
    out = {k: info.get(k) for k in keep if k in info}
    out["titulky"] = [{"datum": h.get("datum"), "titulek": (h.get("titulek") or "")[:140], "zdroj": h.get("zdroj")}
                      for h in (info.get("titulky") or [])[:3]]
    out["signaly_predem"] = [s.get("pricina") for s in (info.get("signaly_predem") or [])]
    return out


def record_cause(conn, event_id: int, *, code: str, status: str, summary: str, source: str, source_url: str,
                 published_on: str, scheduled: bool | None = None, pre_signals: str | None = None) -> int:
    """Ověřená (nebo výslovně neověřená) příčina rakety / propadu z primárního zdroje."""
    if code not in CODES:
        raise ValueError(f"kód příčiny musí být jeden z {sorted(CODES)}")
    if conn.execute("SELECT 1 FROM rocket_events WHERE id = ?", (event_id,)).fetchone() is None:
        raise ValueError(f"raketa #{event_id} neexistuje")
    date.fromisoformat(published_on)
    with conn:
        cur = conn.execute(
            "INSERT INTO rocket_causes (event_id, cause_code, status, scheduled, pre_signals, summary, source, source_url,"
            " published_on, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, code, status, None if scheduled is None else int(scheduled), pre_signals, summary, source, source_url,
             published_on, to_iso(utcnow())))
    return cur.lastrowid


def recent(conn, *, days: int = 30, today: date | None = None) -> list[dict]:
    """Rakety a propady posledních `days` dní s poslední zapsanou příčinou (pro centrum, web a report)."""
    since = ((today or utcnow().date()) - timedelta(days=days)).isoformat()
    out = []
    for r in conn.execute("SELECT * FROM rocket_events WHERE end_day >= ? ORDER BY end_day DESC, id DESC", (since,)):
        c = conn.execute("SELECT * FROM rocket_causes WHERE event_id = ? ORDER BY id DESC LIMIT 1", (r["id"],)).fetchone()
        out.append({**dict(r), "pricina": dict(c) if c else None})
    return out
