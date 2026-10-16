"""Raketový deník (zadání uživatele 2026-10-13): rakety za 5 / 10 / 21 obchodních dní → ověřená příčina z internetu.

Data: týdenní ceny z Yahoo (cache objevování) + denní snímek Nasdaq screeneru (1 dotaz denně, všechny americké akcie:
poslední závěr, změna, objem). Z „poslední cena − změna“ je i předchozí závěr → kontrola návaznosti: když nesedí na cenu
z Yahoo o víc než 25 %, jde skoro jistě o split nebo chybu dat (poučení CHYBA-DAT-REVERSE-SPLIT) a firma se přeskočí.

Raketa: ≥ +30 % za 5, ≥ +40 % za 10 nebo ≥ +50 % za 21 obchodních dní; likvidní (medián obratu 20 dní ≥ 1 mil. USD) a
cena ≥ 1 USD. Epizoda = jedna firma v okně 21 kalendářních dní (týdenní a měsíční raketa téže firmy je jeden příběh).
Příčina: AUTO z titulků Google News (neověřeno) → ruční ověření z primárního zdroje (8-K, tisková zpráva, FDA, SEC)
v tabulce `rocket_causes`. Příčina je známá až po pohybu, proto sama nic nepředpovídá — slouží ke studiu předzvěstí
a toho, co následuje po raketě (hypotéza H-R1, docs/agent_vyzkum/README.md).
"""

import json
import statistics
from datetime import date, datetime, timedelta, timezone

from stockradar.discovery import cache as dcache
from stockradar.discovery import news
from stockradar.timeutil import to_iso, utcnow

WINDOWS = {"5d": (5, 0.30), "10d": (10, 0.40), "21d": (21, 0.50)}
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


def take_snapshot(cache_conn, *, now: datetime | None = None, fetch=None, log=print) -> dict:
    """Uloží denní snímek (jen po závěru obchodování); stejné ceny jako minulý snímek = svátek → neukládá se."""
    cache_conn.executescript(SNAP_SCHEMA)
    now = now or utcnow()
    day = session_day(now)
    if day is None:
        return {"stav": "PŘESKOČENO", "duvod": "trh v New Yorku právě obchoduje — snímek až po závěru"}
    if cache_conn.execute("SELECT 1 FROM nasdaq_snap WHERE day = ? LIMIT 1", (day.isoformat(),)).fetchone():
        return {"stav": "UŽ JE", "den": day.isoformat()}
    if fetch is None:
        from stockradar.discovery import listings
        fetch = lambda: json.loads(listings._get(listings.NASDAQ_SCREENER))["data"]["rows"]
    rows = parse_snapshot(fetch())
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


def merge_series(days, closes, volumes, snaps: list[tuple]) -> tuple[list, list, list, str | None]:
    """Yahoo řada + dny snímků po jejím konci. snaps = [(den_ordinal, close, prev_close, volume)] seřazené podle dne.
    Vrací (dny, ceny, objemy, problém); problém = důvod, proč řadu nepoužít (split, stará data)."""
    d, c, v = list(days), list(closes), list(volumes)
    for day, close, prev, vol in snaps:
        if d and day <= d[-1]:
            continue
        if not d or day - d[-1] > 7:
            return d, c, v, "stará data — mezi cenami z Yahoo a snímkem je mezera"
        if prev and c[-1] > 0 and abs(prev / c[-1] - 1) > MAX_GAP:
            return d, c, v, f"předchozí závěr {prev:.4g} nesedí na {c[-1]:.4g} — pravděpodobně split / chyba dat"
        d.append(day); c.append(close); v.append(vol or 0.0)
    return d, c, v, None


def detect(days, closes, volumes) -> dict | None:
    """Splněná okna k poslednímu dni řady (nebo None)."""
    n = len(closes)
    if n < 22 or closes[-1] < MIN_PRICE:
        return None
    turn = statistics.median(closes[i] * volumes[i] for i in range(n - 20, n))
    if turn < MIN_TURNOVER:
        return None
    moves, hit, start = {}, [], None
    for name, (k, th) in WINDOWS.items():
        base = closes[-1 - k]
        moves[name] = closes[-1] / base - 1 if base > 0 else None
        if moves[name] is not None and moves[name] >= th:
            hit.append(name)
            start = days[-1 - k]                      # nejdelší splněné okno určuje začátek
    if not hit:
        return None
    return {"okna": hit, "moves": moves, "start": start, "end": days[-1], "cena": closes[-1], "obrat": turn}


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
    """Rakety ke dni posledního snímku (americké akcie)."""
    cache_conn.executescript(SNAP_SCHEMA)
    snaps: dict[str, list[tuple]] = {}
    for day, sym, close, prev, vol in cache_conn.execute(
            "SELECT day, symbol, close, prev_close, volume FROM nasdaq_snap ORDER BY day"):
        snaps.setdefault(sym, []).append((date.fromisoformat(day).toordinal(), close, prev, vol))
    from stockradar.discovery.bestideas import is_fund
    from stockradar.discovery.study import anomalous
    from stockradar.discovery.winners import adjust_reverse_splits
    meta = {r[0]: (r[1], r[2], r[3]) for r in cache_conn.execute("SELECT symbol, name, market_cap_usd, industry FROM securities")}
    stats = {"rad": 0, "split_nebo_chyba": 0, "stara_data": 0, "fondy": 0, "raket": 0}
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
        hit = detect(d, c, v)
        if hit:
            found.append({"symbol": sym, "nazev": name, "mcap": cap, **hit})
    stats["raket"] = len(found)
    found.sort(key=lambda r: -max(x for x in r["moves"].values() if x is not None))
    return found, stats


def record_new(conn, found: list[dict], *, today: date, auto=None, top_auto: int = 10, log=print) -> list[dict]:
    """Zapíše nové epizody (firma bez rakety v posledních 21 dnech); u prvních `top_auto` příčinu z titulků (AUTO)."""
    new = []
    for r in found:
        end = date.fromordinal(r["end"])
        if conn.execute("SELECT 1 FROM rocket_events WHERE symbol = ? AND end_day >= ?",
                        (r["symbol"], (end - timedelta(days=EPISODE_DAYS)).isoformat())).fetchone():
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
                " price, turnover_usd, market_cap_usd, auto_cause, auto_json, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r["symbol"], r["nazev"], today.isoformat(), date.fromordinal(r["start"]).isoformat(),
                 date.fromordinal(r["end"]).isoformat(), ",".join(r["okna"]), m.get("5d"), m.get("10d"), m.get("21d"),
                 r["cena"], r["obrat"], r["mcap"], (info or {}).get("kod"),
                 json.dumps(_slim(info), ensure_ascii=False) if info else None, to_iso(utcnow())))
        r["id"] = cur.lastrowid
        r["auto"] = info
    log(f"Raketový deník: {len(found)} raket, nových epizod {len(new)}")
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
    """Ověřená (nebo výslovně neověřená) příčina rakety z primárního zdroje."""
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
    """Rakety posledních `days` dní s poslední zapsanou příčinou (pro centrum, web a report)."""
    since = ((today or utcnow().date()) - timedelta(days=days)).isoformat()
    out = []
    for r in conn.execute("SELECT * FROM rocket_events WHERE end_day >= ? ORDER BY end_day DESC, id DESC", (since,)):
        c = conn.execute("SELECT * FROM rocket_causes WHERE event_id = ? ORDER BY id DESC LIMIT 1", (r["id"],)).fetchone()
        out.append({**dict(r), "pricina": dict(c) if c else None})
    return out
