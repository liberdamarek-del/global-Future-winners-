"""Centrum důkazů: výstupy všech modulů v jednom jazyce. Moduly se nemění — důkazy se čtou z jejich uložených běhů.

Důkaz (dict):
  entita, typ   ticker (firma) / obor / komodita / trh
  modul, role   kdo ho vytvořil; role = to, jehož spolehlivost měří zpětná vazba (feedback.ROLES), u faktů None
  druh          prilezitost / riziko / katalyzator / kontext / dostupnost
  smer          +1 růst, −1 pokles, 0 bez směru;  horizont (dní)
  p, zaklad     pravděpodobnost cíle a běžná četnost (když jsou)
  text, zdroj, url, data_do (den dat), stav  OVĚŘENO (fakt s primárním zdrojem) / AUTO (výstup modelu) / NEOVĚŘENO
Ruční výzkum se ukládá do `research_evidence` (append-only, zdroj a platnost povinné).
"""

import json
import sqlite3
from datetime import date, datetime, timedelta

from stockradar.hub.feedback import HORIZON_DAYS, SIGNAL_MODELS, signal_role
from stockradar.timeutil import to_iso, utcnow

KINDS = ("prilezitost", "riziko", "katalyzator", "kontext")
ENTITY_TYPES = ("firma", "obor", "komodita", "trh")
SIGNAL_HORIZON = {"SIGNAL_14D": 14, "SIGNAL_1M": 30, "SIGNAL_6M": 182}


def _ev(entita, *, modul, druh, smer, horizont, text, zdroj, data_do, stav="AUTO", role=None, typ="firma",
        p=None, zaklad=None, url=None, **extra) -> dict:
    return {"entita": entita, "typ": typ, "modul": modul, "role": role, "druh": druh, "smer": smer, "horizont": horizont,
            "p": p, "zaklad": zaklad, "text": text, "zdroj": zdroj, "url": url, "data_do": data_do, "stav": stav, **extra}


def _pct(v) -> str:
    return "–" if v is None else f"{v * 100:.0f} %"


def _thr(v) -> str:
    return "–" if v is None else f"{v * 100:+.0f} %".replace("-", "−")


# ---------------------------------------------------------------- výstupy modulů

def from_signals(conn) -> tuple[list[dict], dict]:
    """Karty modelů 14 dní / 1 měsíc / 6 měsíců + celé pořadí modelu (kde je firma, i když není v TOP 20)."""
    out, ranks = [], {}
    for model in SIGNAL_MODELS:
        r = conn.execute("SELECT id, data_through, result_json FROM signal_runs WHERE model_name = ? ORDER BY id DESC LIMIT 1",
                         (model,)).fetchone()
        if r is None:
            continue
        full = json.loads(r["result_json"])
        order = [s for s in (full.get("poradi_vse") or "").split(",") if s]
        ranks[model] = {"celkem": len(order), "poradi": {s: i + 1 for i, s in enumerate(order)}, "data_do": r["data_through"]}
        base = full.get("zaklad") or {}
        up, down = full.get("prah_rust"), full.get("prah_pokles")
        h = SIGNAL_HORIZON[model]
        for c in full.get("karty", []):
            role = signal_role(model, c)
            if role is None:
                continue
            src = f"signal_runs #{r['id']} ({model})"
            common = dict(modul=model, role=role, horizont=h, zdroj=src, data_do=c.get("den_ceny") or r["data_through"],
                          nazev=c.get("firma"), obor=c.get("obor"), zeme=c.get("zeme"))
            if role.endswith(":vyber"):
                where = f"#{c['poradi']} v žebříčku" if c.get("poradi") else f"#{c['poradi_velke']} mezi velkými firmami"
                out.append(_ev(c["ticker"], druh="prilezitost", smer=1, p=c.get("p_up"), zaklad=base.get("up5"), **common,
                               text=f"{where}: šance {_thr(up)} {_pct(c.get('p_up'))} (běžně {_pct(base.get('up5'))}), "
                                    f"pokles {_thr(down)} {_pct(c.get('p_down'))}, důvěra {c.get('duvera')}"))
            else:
                what = "nejslabší akcie modelu" if role.endswith(":varovani") else "rozhodnutí POKLES"
                out.append(_ev(c["ticker"], druh="riziko", smer=-1, p=c.get("p_down"), zaklad=base.get("down5"), **common,
                               text=f"{what}: pokles {_thr(down)} {_pct(c.get('p_down'))} (běžně {_pct(base.get('down5'))})"))
    return out, ranks


def from_rockets(conn) -> list[dict]:
    r = conn.execute("SELECT id, data_through, result_json FROM discovery_runs ORDER BY id DESC LIMIT 1").fetchone()
    if r is None:
        return []
    rk = json.loads(r["result_json"]).get("rakety_6m") or {}
    out, seen = [], set()
    for c in (rk.get("kandidati_xtb") or []) + (rk.get("kandidati") or []):
        if c["ticker"] in seen:
            continue
        seen.add(c["ticker"])
        out.append(_ev(c["ticker"], modul="RAKETY_6M", role="RAKETY_6M:vyber", druh="prilezitost", smer=1, horizont=182,
                       p=c.get("p_raketa"), zaklad=c.get("zakladni_cetnost"), zdroj=f"discovery_runs #{r['id']}",
                       data_do=c.get("den") or r["data_through"], nazev=c.get("nazev"), obor=c.get("obor"), zeme=c.get("zeme"),
                       studie=bool(c.get("studie")),
                       text=f"#{c.get('poradi_celkem')} ve světě: raketa +50 % {_pct(c.get('p_raketa'))}, propad −33 % "
                            f"{_pct(c.get('p_propad'))} (běžně {_pct(c.get('zakladni_cetnost'))})"))
    return out


def from_smart_money(conn) -> list[dict]:
    r = conn.execute("SELECT id, data_through, result_json FROM smart_money_runs ORDER BY id DESC LIMIT 1").fetchone()
    if r is None:
        return []
    out = []
    for s in (json.loads(r["result_json"]).get("aktualni") or {}).get("top") or []:
        ver = s.get("overeni") or []
        ok = bool(ver) and all(v.get("overeno") for v in ver)
        url = next((v.get("url") for v in ver if v.get("url")), None)
        # vlastní verdikt modulu omezuje váhu: role „aktivní nákup“ je ověřená celkově, ale ne pro každý typ nákupu
        adj = {"NÍZKÁ": {"strop": 0.1, "stav": "NEOVĚŘENO", "duvod": "verdikt modulu NÍZKÁ — tento typ nákupu neměl výhodu v testu"},
               "STŘEDNÍ": {"nasobek": 0.5, "duvod": "verdikt modulu STŘEDNÍ — výhoda typu nákupu není statisticky potvrzená"}
               }.get(s.get("verdikt"))
        out.append(_ev(s["ticker"], modul="SMART_MONEY", role="SMART_MONEY:nakup", druh="prilezitost", smer=1, horizont=182,
                       uprava=adj,
                       zdroj=f"smart_money_runs #{r['id']} (SEC Form 4)", url=url, data_do=s.get("zverejneno") or r["data_through"],
                       stav="OVĚŘENO" if ok else "NEOVĚŘENO", nazev=s.get("firma"),
                       text=f"{s.get('insideru')} insiderů koupilo za {(s.get('hodnota_usd') or 0) / 1e6:.2f} mil. USD "
                            f"(zveřejněno {s.get('zverejneno')}), skóre {s.get('skore')}, verdikt {s.get('verdikt')}"))
    return out


def from_causal(conn) -> list[dict]:
    r = conn.execute("SELECT id, data_through, result_json FROM causal_runs ORDER BY id DESC LIMIT 1").fetchone()
    if r is None:
        return []
    out = []
    for o in json.loads(r["result_json"]).get("prilezitosti") or []:
        if o.get("dukaz") != "EMPIRICKY_I_LOGIKA":
            continue
        out.append(_ev(o["obor"], typ="obor", modul="KAUZALNI", role="KAUZALNI:prilezitost",
                       druh="prilezitost" if o["smer"] > 0 else "riziko", smer=o["smer"], horizont=o.get("horizont_dni") or 30,
                       zdroj=f"causal_runs #{r['id']}", data_do=r["data_through"], komodita=o.get("komodita"),
                       firmy=[f["ticker"] for f in o.get("firmy") or []],
                       text=f"{o.get('nazev_komodity')} → obor {o['obor']} {'↑' if o['smer'] > 0 else '↓'} "
                            f"({o.get('rad')}. řád, beta {o.get('beta')}, t {o.get('t')}); v ceně už "
                            f"{'–' if o.get('v_cene') is None else _pct(o['v_cene'])}: {o.get('proc')}"))
    return out


def from_energy(conn) -> list[dict]:
    r = conn.execute("SELECT id, data_date, scores_json FROM model_runs ORDER BY id DESC LIMIT 1").fetchone()
    if r is None:
        return []
    scores = json.loads(r["scores_json"])
    out = []
    for sym, s in sorted(scores.items(), key=lambda kv: kv[1].get("poradi") or 999)[:5]:
        out.append(_ev(sym, modul="ENERGIE", role="ENERGIE:vyber", druh="prilezitost", smer=1, horizont=30,
                       p=s.get("p_beat"), zaklad=0.5, zdroj=f"model_runs #{r['id']}", data_do=s.get("den") or r["data_date"],
                       nazev=s.get("nazev"),
                       text=f"#{s.get('poradi')} z {len(scores)} v řetězci AI → elektřina: šance porazit S&P 500 "
                            f"{_pct(s.get('p_beat'))}, raketa {_pct(s.get('p_rocket'))}"))
    return out


def _symbol_of(conn) -> dict[int, str]:
    """company_id → symbol primárního platného listingu (Yahoo symbol, jinak ticker)."""
    out = {}
    for cid, ysym, tic in conn.execute("SELECT company_id, yahoo_symbol, ticker FROM listings WHERE valid_to IS NULL"
                                       " ORDER BY is_primary DESC, id DESC"):
        out[cid] = ysym or tic
    return out


def from_ledger(conn) -> list[dict]:
    """Otevřené predikce = k čemu se systém už zavázal (paměť); uzavřené = výsledek."""
    out = []
    for p in conn.execute("SELECT p.id, p.made_at, p.horizon, p.strategy, p.source, p.verdict, p.target_move_pct,"
                          " COALESCE(l.yahoo_symbol, l.ticker) AS sym, c.name FROM predictions p"
                          " JOIN listings l ON l.id = p.listing_id JOIN companies c ON c.id = p.company_id WHERE p.mode = 'LIVE'"):
        h = HORIZON_DAYS.get(p["horizon"], 180)
        res = conn.execute("SELECT result, return_pct, excess_return_pct FROM prediction_outcomes WHERE prediction_id = ?"
                           " AND horizon_days = ?", (p["id"], h)).fetchone()
        end = (datetime.fromisoformat(p["made_at"].replace("Z", "")) + timedelta(days=h)).date().isoformat()
        kind = p["strategy"] or p["source"] or "RUČNÍ"
        text = (f"predikce #{p['id']} ({kind}, {p['verdict']}) z {p['made_at'][:10]}"
                + (f", cíl {p['target_move_pct']:+.0f} %" if p["target_move_pct"] else "")
                + (f" → {res['result']}, výnos {res['return_pct']:+.1f} %" if res else f", běží do {end}"))
        out.append(_ev(p["sym"], modul="LEDGER", druh="kontext", smer=0, horizont=h, text=text, zdroj=f"predictions #{p['id']}",
                       data_do=p["made_at"][:10], stav="OVĚŘENO", nazev=p["name"], predikce=p["id"], otevrena=res is None,
                       konec=end))
    return out


def from_catalysts(conn, today: date) -> list[dict]:
    sym = _symbol_of(conn)
    out = []
    for k in conn.execute("SELECT k.*, c.name FROM catalysts k JOIN companies c ON c.id = k.company_id"
                          " WHERE k.status IN ('UPCOMING', 'DELAYED')"):
        if k["company_id"] not in sym:
            continue
        when = k["event_date"] or (f"{k['window_start']} … {k['window_end']}" if k["window_start"] else "termín NEOVĚŘENO")
        first = k["event_date"] or k["window_start"]
        days = (date.fromisoformat(first) - today).days if first else None
        out.append(_ev(sym[k["company_id"]], modul="KATALYZATORY", druh="katalyzator", smer=0, horizont=max(days or 30, 1),
                       text=f"{k['type_code']}: {when} ({k['date_status']}) — {k['description'][:120]}",
                       zdroj=f"catalysts #{k['id']}", url=k["source_url"], data_do=(k["published_at"] or k["recorded_at"])[:10],
                       stav="OVĚŘENO" if k["date_status"] == "VERIFIED" else "NEOVĚŘENO", nazev=k["name"],
                       typ_katalyzatoru=k["type_code"], dni_do=days))
    return out


def from_research(conn, today: date) -> tuple[list[dict], int]:
    """Platný ruční výzkum (valid_until ≥ dnes); vrací i počet prošlých záznamů."""
    out, expired = [], 0
    for r in conn.execute("SELECT * FROM research_evidence ORDER BY id"):
        if r["valid_until"] < today.isoformat():
            expired += 1
            continue
        out.append(_ev(r["entity"], typ=r["entity_type"], modul="VYZKUM", role="VYZKUM", druh=r["kind"], smer=r["direction"],
                       horizont=r["horizon_days"], text=r["summary"], zdroj=r["source"], url=r["source_url"],
                       data_do=r["published_on"], stav=r["status"], platnost=r["valid_until"], vyzkum=r["id"]))
    return out, expired


def from_xtb(cache_conn, symbols: set[str]) -> list[dict]:
    if cache_conn is None or not symbols:
        return []
    out = []
    marks = ",".join("?" * len(symbols))
    try:
        rows = cache_conn.execute(f"SELECT symbol, status, xtb_symbol, checked_at FROM xtb_offer WHERE symbol IN ({marks})",
                                  sorted(symbols)).fetchall()
    except sqlite3.OperationalError:                   # tabulka vzniká při první kontrole XTB
        return []
    for r in rows:
        out.append(_ev(r[0], modul="XTB", druh="dostupnost", smer=0, horizont=30, data_do=r[3][:10], stav="OVĚŘENO",
                       zdroj="xtb.com (cache 30 dní)", xtb=r[1],
                       text={"AKCIE": f"XTB nabízí jako akcii ({r[2]})", "CFD": "XTB jen jako CFD", "NE": "XTB nenabízí"}[r[1]]))
    return out


def securities(cache_conn) -> dict[str, dict]:
    """Seznam firem z cache (název, obor, kapitalizace) — pro propojení firma → obor."""
    if cache_conn is None:
        return {}
    try:
        rows = cache_conn.execute("SELECT symbol, name, industry, country FROM securities").fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r[0]: {"nazev": r[1], "obor": (r[2] or "").lower() or None, "zeme": r[3]} for r in rows}


def collect(conn, cache_conn, today: date) -> dict:
    """Všechny důkazy + pořadí modelů + seznam firem; nic se nepočítá znovu, jen čte z uložených výstupů."""
    sig, ranks = from_signals(conn)
    research, expired = from_research(conn, today)
    items = sig + from_rockets(conn) + from_smart_money(conn) + from_causal(conn) + from_energy(conn) + \
        from_ledger(conn) + from_catalysts(conn, today) + research
    firms = {e["entita"] for e in items if e["typ"] == "firma"}
    firms |= {f for e in items for f in e.get("firmy") or []}
    items += from_xtb(cache_conn, firms)
    return {"dukazy": items, "poradi": ranks, "firmy": securities(cache_conn), "vyzkum_proslo": expired}


# ---------------------------------------------------------------- ruční výzkum (trvalá paměť)

def add_research(conn: sqlite3.Connection, *, entity_type: str, entity: str, kind: str, direction: int, horizon_days: int,
                 summary: str, source: str, source_url: str, published_on: str, valid_until: str | None = None,
                 status: str = "OVĚŘENO", now: datetime | None = None) -> int:
    """Zapíše ověřenou zprávu jako trvalý důkaz. Bez URL zdroje nelze; nový názor = nový záznam (append-only)."""
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"typ entity musí být jeden z {ENTITY_TYPES}")
    if kind not in KINDS:
        raise ValueError(f"druh musí být jeden z {KINDS}")
    if direction not in (-1, 0, 1):
        raise ValueError("směr musí být −1, 0 nebo 1")
    if not summary.strip() or not source.strip() or not published_on:
        raise ValueError("výzkum potřebuje shrnutí, název zdroje a den zveřejnění")
    if not str(source_url).startswith("https://"):
        raise ValueError("výzkum potřebuje URL zdroje (https://)")
    if status not in ("OVĚŘENO", "NEOVĚŘENO"):
        raise ValueError("stav musí být OVĚŘENO nebo NEOVĚŘENO")
    pub = date.fromisoformat(published_on)
    until = valid_until or (pub + timedelta(days=horizon_days)).isoformat()
    date.fromisoformat(until)
    if entity_type == "firma":
        entity = entity.strip().upper()
    elif entity_type == "obor":
        entity = entity.strip().lower()
    with conn:
        cur = conn.execute(
            "INSERT INTO research_evidence (entity_type, entity, kind, direction, horizon_days, summary, source, source_url,"
            " published_on, valid_until, status, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entity_type, entity, kind, direction, horizon_days, summary.strip(), source.strip(), source_url,
             pub.isoformat(), until, status, to_iso(now or utcnow())))
    return cur.lastrowid
