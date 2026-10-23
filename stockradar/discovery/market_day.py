"""Denní přehled trhu a sektorů (v0.17.0, zadání uživatele 2026-10-23: proč se hýbal sektor a co se na trhu děje).

Jen z dat, která radar už má — navíc nejvýš 2 dotazy na titulky Google News:
  * denní snímek Nasdaq screeneru (raketový deník; všechny americké akcie: závěr, předchozí závěr, tržní hodnota)
    → pohyb trhu, sektorů a oborů vážený tržní hodnotou, šíře (podíl rostoucích) a kdo pohyb táhl (příspěvek firmy);
  * S&P 500 a VIX z price_bars (jsou-li), komodity a dolar z cache (kauzální radar, Yahoo);
  * dnešní pohyby z raketového deníku v oboru a jejich příčiny;
  * u dvou oborů s největším pohybem proti trhu titulky o firmách, které pohyb táhly (AUTO, neověřeno).
Je to popis souvislostí, ne prokázaná příčina: to, že obor padal ve stejný den jako ropa, ještě neznamená, že kvůli ropě.
Vazba komodita → obor je hypotéza kauzálního radaru (causal/commodities.py), ne ověřený vztah.
"""

import bisect
import json
import statistics
import time
from datetime import date, timedelta

from stockradar.discovery import diary, news
from stockradar.timeutil import to_iso, utcnow

MIN_CAP = 300e6                # jen firmy nad 300 mil. USD (malé firmy by šumem přehlušily obor)
MIN_MEMBERS = 5
MAX_RATIO = 3.0                # denní pohyb nad 3× / pod 1/3 = skoro jistě chyba dat nebo split → vynechat
TOP_INDUSTRIES = 8
HEADLINE_INDUSTRIES = 2
Z_NOTABLE = 2.0                # komodita: pohyb aspoň 2× běžná denní volatilita (60 dní)


def _rows(cache_conn, day: str) -> list[dict]:
    meta = {r[0]: (r[1], r[2], r[3]) for r in cache_conn.execute("SELECT symbol, sector, industry, name FROM securities")}
    out = []
    for sym, close, prev, cap, name in cache_conn.execute(
            "SELECT symbol, close, prev_close, mcap, name FROM nasdaq_snap WHERE day = ?", (day,)):
        if not prev or prev <= 0 or not close or close < 1 or not cap or cap < MIN_CAP:
            continue
        ratio = close / prev
        if not (1 / MAX_RATIO < ratio < MAX_RATIO):
            continue
        sector, industry, mname = meta.get(sym, (None, None, None))
        out.append({"symbol": sym, "nazev": mname or name, "sektor": sector or "neuvedeno", "obor": industry or "neuvedeno",
                    "r": ratio - 1, "w": cap / ratio})          # váha = tržní hodnota na začátku dne
    return out


def aggregate(rows: list[dict]) -> dict:
    """Pohyb skupiny vážený tržní hodnotou, šíře a kdo ho táhl (příspěvek = váha × pohyb / součet vah)."""
    total = sum(r["w"] for r in rows)
    move = sum(r["w"] * r["r"] for r in rows) / total if total else 0.0
    contrib = sorted(({"ticker": r["symbol"], "nazev": r["nazev"], "zmena": round(r["r"], 4),
                       "prispevek": r["w"] * r["r"] / total} for r in rows), key=lambda c: c["prispevek"])
    lead = contrib[::-1][:3] if move >= 0 else contrib[:3]
    same = sum(c["prispevek"] for c in lead if c["prispevek"] * move > 0)
    return {"zmena": round(move, 4), "firem": len(rows), "rostlo": round(sum(1 for r in rows if r["r"] > 0) / len(rows), 3),
            "median_firmy": round(statistics.median(r["r"] for r in rows), 4),
            "tahouni": [{**c, "prispevek": round(c["prispevek"], 5)} for c in lead],
            # podíl pohybu, který udělaly 3 největší přispěvatelé (vysoký = spíš zprávy jednotlivých firem než celý obor)
            "podil_tri": round(same / move, 3) if abs(move) > 1e-4 else None}


def _series_move(bars, day_ord: int) -> tuple[float, float] | None:
    """Denní pohyb řady k danému dni a jeho z-skóre proti 60 předchozím dnům."""
    i = bisect.bisect_right(bars.days, day_ord) - 1
    if i < 61 or bars.days[i] != day_ord or bars.closes[i - 1] <= 0:
        return None
    r = bars.closes[i] / bars.closes[i - 1] - 1
    hist = [bars.closes[k] / bars.closes[k - 1] - 1 for k in range(i - 60, i) if bars.closes[k - 1] > 0]
    sd = statistics.pstdev(hist) if len(hist) > 20 else 0
    return r, (r / sd if sd > 0 else 0.0)


def commodities(cache_conn, day: str) -> list[dict]:
    from stockradar.causal.commodities import COMMODITIES
    from stockradar.discovery import cache as dcache
    out = []
    d = date.fromisoformat(day).toordinal()
    for c in COMMODITIES:
        bars = dcache.load_series(cache_conn, c["symbol"])
        mv = _series_move(bars, d) if bars is not None and bars.days else None
        if mv:
            out.append({"id": c["id"], "nazev": c["nazev"], "zmena": round(mv[0], 4), "z": round(mv[1], 2)})
    out.sort(key=lambda x: -abs(x["z"]))
    return out


def market_context(main_conn, day: str) -> dict:
    out = {}
    # (výnos 10letých dluhopisů ^TNX záměrně ne: jednotku kotace Yahoo jsme neověřili)
    for sym, key in (("SPY", "sp500"), ("^VIX", "vix")):
        rows = main_conn.execute("SELECT date, close FROM price_bars WHERE symbol = ? AND date <= ? AND close > 0"
                                 " ORDER BY date DESC LIMIT 2", (sym, day)).fetchall()
        if len(rows) == 2 and rows[0][0] == day:
            cur, prev = rows[0][1], rows[1][1]
            out[key] = {"hodnota": round(cur, 2), "zmena": round(cur / prev - 1, 4)}
    return out


def _links(industry: str, move: float, comm: list[dict]) -> list[dict]:
    """Výrazné pohyby komodit, které kauzální radar s oborem spojuje — a zda směr sedí na hypotézu."""
    from stockradar.causal.commodities import chain_for
    out = []
    for c in comm:
        if abs(c["z"]) < Z_NOTABLE - 0.5:
            continue
        ch = chain_for(c["id"], industry)
        if ch:
            expected = ch[1] * (1 if c["zmena"] > 0 else -1)
            out.append({"komodita": c["nazev"], "zmena": c["zmena"], "z": c["z"], "rad": ch[0], "proc": ch[2],
                        "sedi_smer": expected * move > 0})
    return out[:3]


def headlines_for(lead: list[dict], day: str, *, fetch=news.fetch_headlines, pause: float = 1.0) -> dict:
    """Titulky o firmách, které pohyb oboru táhly (den pohybu a následující den). AUTO, neověřeno."""
    names = [news.short_name(x["nazev"]) for x in lead[:3] if x.get("nazev")]
    names = [n for n in names if len(n) >= 3]
    if not names:
        return {"stav": "NEOVĚŘENO — žádná jména k hledání"}
    query = "(" + " OR ".join(f'"{n}"' for n in names) + ") (stock OR shares)"
    d = date.fromisoformat(day)
    try:
        heads = fetch(query, d - timedelta(days=1), d + timedelta(days=2))
    except Exception as exc:
        return {"stav": "DATA NEDOSTUPNÁ", "duvod": str(exc)[:100]}
    finally:
        if pause:
            time.sleep(pause)
    causes = news.classify(heads)
    return {"stav": "AUTO (z titulků, neověřeno)" if heads else "NEOVĚŘENO — žádné titulky", "dotaz": query,
            "pricny": [{"kod": c["kod"], "pricina": c["pricina"], "titulku": c["titulku"]} for c in causes[:3]],
            "titulky": [{"datum": h["datum"], "titulek": h["titulek"][:160], "zdroj": h.get("zdroj"), "url": h.get("url")}
                        for h in sorted(heads, key=lambda h: 0 if news.EXPLAINER.search(h["titulek"]) else 1)[:3]]}


def build(main_conn, cache_conn, day: str | None = None, *, fetch=news.fetch_headlines, pause: float = 1.0) -> dict | None:
    cache_conn.executescript(diary.SNAP_SCHEMA)
    day = day or cache_conn.execute("SELECT MAX(day) FROM nasdaq_snap").fetchone()[0]
    if not day:
        return None
    rows = _rows(cache_conn, day)
    if len(rows) < 100:
        return {"den": day, "stav": "NEOVĚŘENO", "duvod": f"ve snímku jen {len(rows)} firem nad 300 mil. USD"}
    market = aggregate(rows)
    ctx = market_context(main_conn, day)
    spy = (ctx.get("sp500") or {}).get("zmena")
    if spy is not None and abs(market["zmena"] - spy) > 0.01:
        # celý trh vážený hodnotou se od S&P 500 liší o desetiny procenta; přes 1 p. b. = snímek je z jiného dne
        return {"den": day, "stav": "NEOVĚŘENO",
                "duvod": f"snímek {market['zmena'] * 100:+.2f} %, S&P 500 téhož dne {spy * 100:+.2f} % — ceny nejsou z {day}"}
    groups = {}
    for key in ("sektor", "obor"):
        by: dict[str, list] = {}
        for r in rows:
            by.setdefault(r[key], []).append(r)
        groups[key] = [{"nazev": k, **aggregate(v)} for k, v in by.items() if len(v) >= MIN_MEMBERS and k != "neuvedeno"]
        for g in groups[key]:
            g["proti_trhu"] = round(g["zmena"] - market["zmena"], 4)
    comm = commodities(cache_conn, day)
    events = [dict(r) for r in main_conn.execute("SELECT id, symbol, name, direction, windows, move_1d, move_5d, auto_cause"
                                                  " FROM rocket_events WHERE end_day = ?", (day,))]
    industry_of = {r[0]: r[1] for r in cache_conn.execute("SELECT symbol, industry FROM securities")}
    sectors = sorted(groups["sektor"], key=lambda g: g["zmena"], reverse=True)
    industries = sorted(groups["obor"], key=lambda g: -abs(g["proti_trhu"]))[:TOP_INDUSTRIES]
    for k, g in enumerate(industries):
        g["souvislosti"] = _links(g["nazev"], g["zmena"], comm)
        g["pohyby_dne"] = [{"ticker": e["symbol"], "nazev": e["name"], "smer": e["direction"], "okna": e["windows"],
                            "pohyb_1d": e["move_1d"], "auto": e["auto_cause"]} for e in events
                           if industry_of.get(e["symbol"]) == g["nazev"]][:5]
        if k < HEADLINE_INDUSTRIES and fetch is not None:
            g["titulky"] = headlines_for(g["tahouni"], day, fetch=fetch, pause=pause)
        g["vysvetleni"] = explain(g)
    return {
        "den": day, "stav": "OK", "trh": {**market, **ctx},
        "sektory": sectors, "obory": industries,
        "komodity": [c for c in comm if abs(c["z"]) >= Z_NOTABLE][:6] or comm[:3],
        "pohybu_v_deniku": {"rakety": sum(1 for e in events if e["direction"] > 0),
                            "propady": sum(1 for e in events if e["direction"] < 0)},
        "poznamky": ["Popis souvislostí, ne prokázaná příčina. Pohyb oboru je vážený tržní hodnotou firem nad 300 mil. USD.",
                     "Komodity jsou nejbližší futures kontrakty — v den přechodu na další kontrakt může být skok.",
                     "Titulky jsou AUTO (klíčová slova), dokud je člověk neověří."],
    }


def _cz(x: float, nd: int = 1, sign: bool = True) -> str:
    """Číslo česky: desetinná čárka, znaménko minus."""
    s = f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"
    return s.replace(".", ",").replace("-", "−")


def explain(g: dict) -> list[str]:
    """Krátké věcné věty k pohybu oboru — co je změřené, ne domněnky."""
    out = []
    sign = "rostl" if g["zmena"] > 0 else "klesal"
    out.append(f"Obor {sign} o {_cz(g['zmena'] * 100)} % ({_cz(g['proti_trhu'] * 100)} p. b. proti trhu); "
               f"rostlo {_cz(g['rostlo'] * 100, 0, False)} % z {g['firem']} firem.")
    if g.get("podil_tri") is not None:
        lead = ", ".join(t["ticker"] for t in g["tahouni"])
        if g["podil_tri"] >= 0.6:
            out.append(f"Pohyb udělaly hlavně 3 firmy ({lead}: {_cz(min(g['podil_tri'], 1) * 100, 0, False)} % pohybu) — spíš zprávy"
                       " jednotlivých firem než celý obor.")
        elif (g["rostlo"] >= 0.75 and g["zmena"] > 0) or (g["rostlo"] <= 0.25 and g["zmena"] < 0):
            out.append(f"Pohyb byl široký (většina firem stejným směrem) — spíš společný vliv na celý obor; nejvíc {lead}.")
    for s in g.get("souvislosti") or []:
        out.append(f"Souvislost: {s['komodita']} {_cz(s['zmena'] * 100)} % ({_cz(abs(s['z']), 1, False)}× běžný denní pohyb); kauzální radar čeká "
                   f"{'stejný' if s['sedi_smer'] else 'opačný'} směr — {s['proc']} (hypotéza).")
    t = (g.get("titulky") or {}).get("pricny") or []
    if t:
        out.append("Titulky (AUTO): " + ", ".join(f"{c['pricina']} ({c['titulku']}×)" for c in t[:2]) + ".")
    return out


def record(conn, result: dict) -> bool:
    if not result or result.get("stav") != "OK":
        return False
    if conn.execute("SELECT 1 FROM market_days WHERE day = ?", (result["den"],)).fetchone():
        return False
    with conn:
        conn.execute("INSERT INTO market_days (day, result_json, recorded_at) VALUES (?, ?, ?)",
                     (result["den"], json.dumps(result, ensure_ascii=False), to_iso(utcnow())))
    return True


def run(conn, cache_conn, *, fetch=news.fetch_headlines, pause: float = 1.0, log=print) -> dict:
    """Přehled za den posledního snímku, pokud ještě není zapsaný (přehled dne se nepřepisuje)."""
    cache_conn.executescript(diary.SNAP_SCHEMA)
    day = cache_conn.execute("SELECT MAX(day) FROM nasdaq_snap").fetchone()[0]
    if not day:
        return {"stav": "BLOKOVÁNO", "duvod": "žádný snímek trhu"}
    if conn.execute("SELECT 1 FROM market_days WHERE day = ?", (day,)).fetchone():
        return {"stav": "UŽ JE", "den": day}
    res = build(conn, cache_conn, day, fetch=fetch, pause=pause)
    if not res or res.get("stav") != "OK":
        return res or {"stav": "NEOVĚŘENO"}
    record(conn, res)
    m = res["trh"]
    log(f"Přehled trhu {day}: trh {m['zmena'] * 100:+.2f} %, rostlo {m['rostlo'] * 100:.0f} %; nejvíc proti trhu "
        + ", ".join(f"{g['nazev']} {g['proti_trhu'] * 100:+.1f} p. b." for g in res["obory"][:3]))
    return {"stav": "OK", "den": day, "oboru": len(res["obory"])}


def recent(conn, *, days: int = 10) -> list[dict]:
    return [json.loads(r[0]) for r in conn.execute("SELECT result_json FROM market_days ORDER BY day DESC LIMIT ?", (days,))]
