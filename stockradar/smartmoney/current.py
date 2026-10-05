"""Aktuální nákupy insiderů (posledních ~60 dní), protože strukturovaná data SEC končí kvartálem 2026Q1.

1. Seznam čerstvých nákupů z openinsider.com (sekundární zdroj — přehled sestavený z Form 4; jen k nalezení).
2. Každý kandidát, který se dostane do výběru, se OVĚŘÍ v originálním Form 4 na sec.gov (primární zdroj):
   kód transakce, cena, počet akcií, příznak plánu 10b5-1. Dotaz na sec.gov nese e-mail → eviduje se.
"""

import html
import re
import urllib.request
import xml.etree.ElementTree as ET

from stockradar import contact

SCREENER = ("http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd={days}&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago="
            "&xp=1&vl={min_k}&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h="
            "&oc2l=&oc2h=&sortcol=0&cnt={cnt}&page={page}")


def _num(s: str) -> float | None:
    s = (s or "").replace("$", "").replace(",", "").replace("+", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def fetch_recent_purchases(days: int = 60, min_value_k: int = 25, pages: int = 5, template: str = SCREENER) -> list[dict]:
    """Pozor: openinsider po ~10. stránce vrací pořád stejnou stránku → duplicity se vyřazují a při stránce
    bez nových řádků se končí (pro delší období použij fetch_purchases_between po oknech)."""
    out, seen = [], set()
    for page in range(1, pages + 1):
        req = urllib.request.Request(template.format(days=days, min_k=min_value_k, cnt=500, page=page),
                                     headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        t = text[text.find('class="tinytable"'):]
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)[1:]
        if not rows:
            break
        new_rows = 0
        for r in rows:
            cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                     for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
            links = re.findall(r'href="(https?://www\.sec\.gov/Archives/edgar/data/[^"]+)"', r)
            if len(cells) < 13 or not cells[7].startswith("P"):
                continue
            ticker = re.sub(r"[^A-Z0-9.\-]", "", cells[3].split(">")[-1].upper()).rstrip(".")
            own = cells[11].replace("%", "").replace("+", "").strip()
            key = (cells[1], cells[3], cells[5], cells[9], cells[8])
            if key in seen:
                continue
            seen.add(key)
            new_rows += 1
            out.append({"filed": cells[1][:10], "trade": cells[2], "ticker": ticker.replace(".", "-"), "company": cells[4],
                        "insider": cells[5], "title": cells[6], "price": _num(cells[8]), "qty": _num(cells[9]),
                        "owned": _num(cells[10]), "delta_own": None if own in ("New", "") else _num(own) / 100 if _num(own) is not None else None,
                        "new_position": own == "New", "value": _num(cells[12]), "form4_url": links[0] if links else None,
                        "zdroj": "openinsider.com (přehled z Form 4)"})
        if len(rows) < 500 or new_rows == 0:
            break
    return out


def fetch_purchases_between(start, end, *, min_value_k: int = 0, chunk_days: int = 14, log=None) -> list[dict]:
    """Nákupy podle data podání v rozsahu [start, end] — po oknech, protože openinsider vrací nejvýš 40 stránek."""
    from datetime import timedelta
    from urllib.parse import quote
    out, d = [], start
    while d <= end:
        e = min(end, d + timedelta(days=chunk_days - 1))
        fdr = quote(f"{d:%m/%d/%Y} - {e:%m/%d/%Y}", safe="").replace("%20", "+")
        tmpl = SCREENER.replace("fd={days}&fdr=", "fd=-1&fdr=" + fdr.replace("{", "{{").replace("}", "}}"))
        part = fetch_recent_purchases(days=0, min_value_k=min_value_k, pages=40, template=tmpl)
        if log:
            log(f"openinsider {d} … {e}: {len(part)}")
        out += part
        d = e + timedelta(days=1)
    return out


def raw_xml_url(url: str) -> str:
    """Odkaz openinsider vede na XSLT zobrazení (…/xslF345X03/soubor.xml) — originální XML je o úroveň výš."""
    return re.sub(r"/xslF345X\d+/", "/", url.replace("http://", "https://"))


DISCOUNT = 0.88  # nákup za cenu pod 88 % tržní ceny téhož dne = zvýhodněný nákup (zaměstnanecký plán), ne trh


def form4_type(v: dict, market_close: float | None = None) -> str:
    """Typ transakce z originálního Form 4 (zadání §3)."""
    from datetime import date
    buys = [t for t in v["transakce"] if t["code"] == "P"]
    if not buys:
        return "NEJASNÉ"
    if v["plan10b51"]:
        return "AUTOMATICKÝ"
    bought = sum(t["shares"] or 0 for t in buys)
    first = min(date.fromisoformat(t["date"][:10]).toordinal() for t in buys if t["date"])
    sold = sum(t["shares"] or 0 for t in v["transakce"] if t["code"] == "S" and t["date"]
               and 0 <= date.fromisoformat(t["date"][:10]).toordinal() - first <= 10)
    if bought and sold >= 0.5 * bought:
        return "NEJASNÉ (hned prodáno)"
    price = sum((t["shares"] or 0) * (t["price"] or 0) for t in buys) / bought if bought else None
    if market_close and price and price < DISCOUNT * market_close:
        return "PASIVNÍ (nákup se slevou, zaměstnanecký plán)"
    return "AKTIVNÍ NÁKUP"


def verify_form4(url: str, cache_conn=None) -> dict:
    """Primární ověření v Form 4 (XML na sec.gov). Výsledek se uloží, aby se e-mail neposílal opakovaně."""
    import json
    if cache_conn is not None:
        cache_conn.execute("CREATE TABLE IF NOT EXISTS form4_verify (url TEXT PRIMARY KEY, result_json TEXT NOT NULL)")
        hit = cache_conn.execute("SELECT result_json FROM form4_verify WHERE url = ?", (url,)).fetchone()
        if hit:
            v = json.loads(hit[0])
            v["typ"] = form4_type(v)  # pravidla se mohla zpřísnit — typ se počítá vždy znovu z uložených transakcí
            return v
    xml = contact.http_get(raw_xml_url(url), "ověření nákupu insidera (Form 4 XML)").decode("utf-8", "replace")
    root = ET.fromstring(xml)
    plan = (root.findtext("aff10b5One") or "").strip().lower() in ("1", "true")
    txs = []
    for t in root.iter("nonDerivativeTransaction"):
        code = t.findtext("transactionCoding/transactionCode")
        shares = t.findtext("transactionAmounts/transactionShares/value")
        price = t.findtext("transactionAmounts/transactionPricePerShare/value")
        txs.append({"code": code, "date": t.findtext("transactionDate/value"),
                    "shares": float(shares) if shares else None, "price": float(price) if price else None,
                    "ad": t.findtext("transactionAmounts/transactionAcquiredDisposedCode/value")})
    owner = root.findtext("reportingOwner/reportingOwnerId/rptOwnerName")
    title = root.findtext("reportingOwner/reportingOwnerRelationship/officerTitle")
    buys = [t for t in txs if t["code"] == "P"]
    result = {"overeno": True, "plan10b51": plan, "owner": owner, "title": title, "transakce": txs,
              "nakupu_P": len(buys), "hodnota_P": round(sum((t["shares"] or 0) * (t["price"] or 0) for t in buys)),
              "url": raw_xml_url(url)}
    result["typ"] = form4_type(result)
    if cache_conn is not None:
        with cache_conn:
            cache_conn.execute("INSERT OR REPLACE INTO form4_verify (url, result_json) VALUES (?, ?)",
                               (url, json.dumps(result, ensure_ascii=False)))
    return result
