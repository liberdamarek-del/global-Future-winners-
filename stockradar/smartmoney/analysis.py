"""Historická analýza smart money: skupiny událostí → event study → tabulky (viz events.py).

Typy transakcí se nikdy nesměšují (zadání §3):
  AKTIVNÍ NÁKUP  — kód P (nákup na trhu za vlastní peníze), bez plánu 10b5-1
  AUTOMATICKÝ    — kód P v předem nastaveném plánu 10b5-1; u politiků reinvestice dividend
  PASIVNÍ        — kód A (přidělené akcie / odměna), kód M (uplatnění opce); u politiků uplatnění opce nebo správce
  NEJASNÉ        — chybí cena, není jasné, kdo o obchodu rozhodl, nebo insider koupené akcie do 10 dní prodal
                   (typicky zaměstnanecký plán ESPP: koupí se slevou a hned prodá)
"""

import csv
import json
import math
import re
import statistics
from collections import defaultdict
from datetime import date

from stockradar.discovery import study
from stockradar.discovery.fundamentals import Fundamentals
from stockradar.smartmoney.events import Event, Market, measure, ordinal, table

CEO = re.compile(r"\bCEO\b|Chief Executive|Co-CEO", re.I)
CFO = re.compile(r"\bCFO\b|Chief Financial", re.I)
CLUSTER_DAYS = 30


FLIP_DAYS = 10      # prodej do 10 dní po nákupu …
FLIP_SHARE = 0.5    # … aspoň poloviny koupených akcií = nejde o aktivní nákup


def classify_insider(code: str, plan: int, price, sold_soon: float = 0.0, shares: float | None = None) -> str:
    if code == "P":
        if not price or price <= 0:
            return "NEJASNÉ"
        if shares and sold_soon >= FLIP_SHARE * shares:
            return "NEJASNÉ (hned prodáno)"
        return "AUTOMATICKÝ" if plan else "AKTIVNÍ NÁKUP"
    return "PASIVNÍ"


def sales_after(cache_conn) -> dict:
    """Prodeje osob, které tutéž firmu koupily: (vlastník, firma) → seřazené (den, akcie)."""
    out = defaultdict(list)
    for r in cache_conn.execute("SELECT owner_cik, issuer_cik, trans_date, shares FROM insider_tx"
                                " WHERE code = 'S' AND trans_date IS NOT NULL"):
        out[(r["owner_cik"], r["issuer_cik"])].append((ordinal(r["trans_date"]), r["shares"] or 0.0))
    return out


def sold_within(sales: dict, owner_cik, issuer_cik, day: int | None, days: int = FLIP_DAYS) -> float:
    if day is None:
        return 0.0
    return sum(n for d, n in sales.get((owner_cik, issuer_cik), []) if day <= d <= day + days)


def classify_congress(tx_type: str, description: str | None) -> str:
    d = (description or "").lower()
    if tx_type != "P":
        return "PRODEJ"
    if "exercis" in d:
        return "PASIVNÍ"          # uplatnění dříve koupených opcí
    if "reinvest" in d or "dividend" in d:
        return "AUTOMATICKÝ"
    if "managed" in d or "advisor" in d or "discretion" in d:
        return "PASIVNÍ"          # obchod externího správce
    return "AKTIVNÍ NÁKUP"


# ------------------------------------------------------------------ insideři

def insider_events(cache_conn, symbols: set[str]) -> list[Event]:
    """Jedna událost = jedna firma × den zveřejnění × typ transakce (více řádků a osob se sčítá)."""
    groups: dict[tuple, dict] = {}
    sales = sales_after(cache_conn)
    for r in cache_conn.execute(
            "SELECT ticker, filing_date, trans_date, issuer_cik, owner_cik, owner, rel, title, code, shares, price,"
            " owned_after, direct, plan10b51 FROM insider_tx WHERE ticker IS NOT NULL AND code IN ('P','A','M')"):
        sym = r["ticker"]
        if sym not in symbols or not r["filing_date"]:
            continue
        sold = sold_within(sales, r["owner_cik"], r["issuer_cik"], ordinal(r["trans_date"])) if r["code"] == "P" else 0.0
        cls = classify_insider(r["code"], r["plan10b51"], r["price"], sold, r["shares"])
        sub = "PASIVNÍ (přidělení)" if r["code"] == "A" else "PASIVNÍ (opce)" if r["code"] == "M" else cls
        g = groups.setdefault((sym, r["filing_date"], sub), {
            "value": 0.0, "owners": {}, "trade_days": [], "ceo": False, "cfo": False, "director": False, "ten": False,
            "officer": False, "pct": 0.0, "indirect": False})
        value = (r["shares"] or 0) * (r["price"] or 0)
        g["value"] += value
        g["owners"][r["owner_cik"] or r["owner"]] = r["owner"]
        if r["trans_date"]:
            g["trade_days"].append(r["trans_date"])
        rel, title = r["rel"] or "", r["title"] or ""
        g["ceo"] |= bool(CEO.search(title))
        g["cfo"] |= bool(CFO.search(title))
        g["director"] |= "Director" in rel
        g["ten"] |= "TenPercent" in rel
        g["officer"] |= "Officer" in rel
        g["indirect"] |= r["direct"] == "I"
        if r["shares"] and r["owned_after"] and r["owned_after"] > r["shares"]:
            g["pct"] = max(g["pct"], r["shares"] / (r["owned_after"] - r["shares"]))
        elif r["shares"] and r["owned_after"] and r["owned_after"] <= r["shares"]:
            g["pct"] = max(g["pct"], 10.0)  # nová pozice
    events = []
    for (sym, filed, sub), g in groups.items():
        events.append(Event(sym, ordinal(filed), ordinal(min(g["trade_days"])) if g["trade_days"] else None,
                            f"insider:{sub}", {
                                "value": round(g["value"]), "n_owners": len(g["owners"]),
                                "owners": list(g["owners"].values())[:4], "owner_ids": list(g["owners"].keys())[:6],
                                "ceo": g["ceo"], "cfo": g["cfo"], "director": g["director"], "ten": g["ten"],
                                "officer": g["officer"], "pct": round(g["pct"], 3), "indirect": g["indirect"]}))
    # klastr: kolik RŮZNÝCH insiderů aktivně nakoupilo tutéž firmu za posledních 30 dní (včetně této události)
    active = defaultdict(list)
    for e in events:
        if e.kind == "insider:AKTIVNÍ NÁKUP":
            active[e.symbol].append(e)
    for evs in active.values():
        evs.sort(key=lambda e: e.public_day)
        for i, e in enumerate(evs):
            people = set()
            for f in evs[:i + 1]:
                if e.public_day - f.public_day <= CLUSTER_DAYS:
                    people.update(f.meta["owner_ids"])
            e.meta["cluster"] = len(people)
    return events


# ------------------------------------------------------------------ politici

def congress_events(cache_conn, symbols: set[str]) -> list[Event]:
    out, seen = [], set()
    for r in cache_conn.execute("SELECT * FROM congress_tx WHERE ticker IS NOT NULL AND tx_type = 'P' ORDER BY filed"):
        sym = r["ticker"]
        if sym not in symbols:
            continue
        key = (r["member"], sym, r["tx_date"], r["asset_type"], r["amount_min"])
        if key in seen:
            continue  # stejný obchod zopakovaný v opraveném výkazu
        seen.add(key)
        cls = classify_congress(r["tx_type"], r["description"])
        mid = None
        if r["amount_min"]:
            mid = (r["amount_min"] + (r["amount_max"] or r["amount_min"])) / 2
        out.append(Event(sym, ordinal(r["filed"]), ordinal(r["tx_date"]), f"politik:{cls}", {
            "member": r["member"], "chamber": r["chamber"], "owner": r["owner"], "asset_type": r["asset_type"],
            "amount_min": r["amount_min"], "amount_max": r["amount_max"], "value": mid, "doc_id": r["doc_id"],
            "description": r["description"]}))
    return out


# ------------------------------------------------------------------ velké podíly a buybacky

def stake_events(cache_conn, symbols: set[str]) -> list[Event]:
    """Nové hlášení podílu nad 5 %: 13D (aktivní záměr) a 13G (pasivní investor). Dodatky /A se nepočítají."""
    tick = defaultdict(list)
    for r in cache_conn.execute("SELECT ticker, cik FROM sec_tickers"):
        if r["ticker"] in symbols:
            tick[r["cik"]].append(r["ticker"])
    out = []
    for r in cache_conn.execute("SELECT cik, form, filed FROM sec_filings WHERE form IN"
                                " ('SC 13D','SCHEDULE 13D','SC 13G','SCHEDULE 13G')"):
        for sym in tick.get(r["cik"], [])[:1]:
            kind = "podíl:13D aktivista" if "13D" in r["form"] else "podíl:13G pasivní investor"
            out.append(Event(sym, ordinal(r["filed"]), None, kind, {"form": r["form"]}))
    return out


def buyback_events(cache_conn, market: Market, fund: Fundamentals) -> list[Event]:
    """Roční skutečně vyplacené zpětné odkupy (výkaz peněžních toků) vůči tržní kapitalizaci v den podání 10-K."""
    cik_sym = {}
    for sym, cik in fund.cik.items():
        cik_sym.setdefault(cik, sym)
    reports = defaultdict(list)
    for r in cache_conn.execute("SELECT cik, filed FROM sec_filings WHERE form IN ('10-K','20-F','40-F')"):
        reports[r["cik"]].append(ordinal(r["filed"]))
    for v in reports.values():
        v.sort()
    bb = defaultdict(dict)
    for r in cache_conn.execute("SELECT cik, period, end_day, val FROM sec_facts WHERE concept = 'buyback'"):
        bb[r["cik"]][int(r["period"][2:6])] = (ordinal(r["end_day"]), r["val"])
    out = []
    for cik, years in bb.items():
        sym = cik_sym.get(cik)
        if sym is None or sym not in market.data.secs:
            continue
        for y, (end, val) in years.items():
            rep = [d for d in reports.get(cik, []) if end < d <= end + 120]
            public = rep[0] if rep else end + 90
            i = market.idx_after(sym, public)
            if i is None:
                continue
            s = market.data.secs[sym]
            rate = market.data.usd_rate(s.currency, s.prep.bars.days[i])
            f = fund.features(sym, public, s.prep.bars.closes[i] * rate if rate else None)
            if f.get("log_mcap") is None:
                continue
            mcap = math.exp(f["log_mcap"])
            yld = val / mcap if val and val > 0 else 0.0
            prev = years.get(y - 1, (None, None))[1]
            kind = ("buyback:≥5 % kapitalizace" if yld >= 0.05 else "buyback:2–5 %" if yld >= 0.02 else
                    "buyback:0–2 %" if yld > 0 else "buyback:žádný")
            out.append(Event(sym, public, None, kind, {
                "yield": round(yld, 4), "value": val, "rok": y, "dilution": f.get("dilution"), "rev_yoy": f.get("rev_yoy"),
                "nove_nebo_zvysene": bool(yld >= 0.02 and (not prev or prev <= 0.5 * val))}))
    return out


# ------------------------------------------------------------------ celý běh

def load_market(cache_conn, main_conn) -> Market:
    data = study.load_data(cache_conn)
    spy = main_conn.execute("SELECT date, close FROM price_bars WHERE symbol = 'SPY' ORDER BY date").fetchall()
    return Market(data, [date.fromisoformat(r[0]).toordinal() for r in spy], [r[1] for r in spy])


def run(cache_conn, main_conn, *, log=print) -> dict:
    market = load_market(cache_conn, main_conn)
    us = {s for s, sec in market.data.secs.items() if "." not in s}
    log(f"Ceny: {len(market.data.secs)} firem, z toho {len(us)} v USA")
    fund = Fundamentals(cache_conn, us)
    evs = insider_events(cache_conn, us) + congress_events(cache_conn, us) + stake_events(cache_conn, us)
    evs += buyback_events(cache_conn, market, fund)
    # pasivní přidělení a opce jsou jen srovnávací skupina → stačí deterministický vzorek 20 %
    evs = [e for e in evs if "PASIVNÍ (" not in e.kind or (e.public_day + sum(map(ord, e.symbol))) % 5 == 0]
    log(f"Událostí: {len(evs)}")
    measured = []
    for n, e in enumerate(evs):
        m = measure(market, e)
        if m:
            m["kind"] = e.kind
            m["trade_day"] = study.day_str(e.trade_day) if e.trade_day else None
            measured.append(m)
        if n % 50000 == 0:
            log(f"  změřeno {n}/{len(evs)}")
    return {"market": market, "fund": fund, "rows": measured}


def save_rows(rows: list[dict], path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


CSV_COLUMNS = ("druh", "trida", "ticker", "kdo", "funkce_nebo_komora", "datum_obchodu", "zverejneno", "vstup",
               "hodnota_usd", "cena_vstup", "pohyb_obchod_az_zverejneni", "odstup_od_max_52t", "pohyb_6m_pred",
               "vynos_1t", "vynos_1m", "vynos_3m", "vynos_6m", "vynos_12m", "max_rust_6m", "max_pokles_6m",
               "nad_spy_6m", "nad_spy_12m", "nad_kontrolou_6m", "nad_kontrolou_12m",
               "dalsi_vysledky_dni", "pocet_8k_do_90_dni", "zdroj")


def _role(r: dict) -> str:
    m = r.get("meta") or {}
    if r["kind"].startswith("politik:"):
        return f"{m.get('chamber', '')} {m.get('owner') or ''} {m.get('asset_type') or ''}".strip()
    if r["kind"].startswith("insider:"):
        return ",".join(k for k in ("ceo", "cfo", "director", "ten", "officer") if m.get(k))
    return ""


def event_row(r: dict, fund: Fundamentals | None = None) -> dict:
    """Jeden řádek „pro každý případ“ (zadání §2): kdo, kdy, kolik, typ, ceny po 1 t – 12 m, max/min, srovnání.
    Katalyzátor po nákupu: jen to, co je v primárních datech — další 10-Q/10-K a počet 8-K do 90 dní (SEC)."""
    m, ret = r.get("meta") or {}, r.get("ret") or {}
    kind, _, cls = r["kind"].partition(":")
    nxt = n8k = None
    if fund is not None and fund.cik.get(r["symbol"]) is not None:
        fl = fund.filings.get(fund.cik[r["symbol"]], {})
        e = ordinal(r["entry"])
        later = [d for d in fl.get("REPORT", []) if d > e]
        nxt = min(later) - e if later else None
        n8k = sum(1 for d in fl.get("8K", []) if e < d <= e + 90)

    def pct(v):
        return round(100 * v, 2) if v is not None else None
    who = m.get("member") or ", ".join(m.get("owners") or []) or m.get("form") or ""
    src = (f"PTR {m.get('doc_id')}" if kind == "politik" else "SEC Form 4 (Insider Transactions Data Sets)"
           if kind == "insider" else "SEC EDGAR full-index" if kind == "podíl" else "SEC XBRL (PaymentsForRepurchase)")
    return dict(zip(CSV_COLUMNS, (
        kind, cls, r["symbol"], who, _role(r), r.get("trade_day"), r["public"], r["entry"], m.get("value"),
        round(r["entry_price"], 4), pct(r.get("move_trade_to_public")), pct(r.get("dd52")), pct(r.get("r126_before")),
        pct(ret.get("1t")), pct(ret.get("1m")), pct(ret.get("3m")), pct(ret.get("6m")), pct(ret.get("12m")),
        pct(ret.get("max6m")), pct(ret.get("min6m")), pct(r.get("ex_spy_6m")), pct(r.get("ex_spy_12m")),
        pct(r.get("ex_ctrl_6m")), pct(r.get("ex_ctrl_12m")), nxt, n8k, src)))


def export_csv(rows: list[dict], path, fund: Fundamentals | None = None, kinds: tuple[str, ...] = ()) -> int:
    n = 0
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["kind"], x["public"], x["symbol"])):
            if kinds and not r["kind"].startswith(kinds):
                continue
            w.writerow(event_row(r, fund))
            n += 1
    return n


def median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None
