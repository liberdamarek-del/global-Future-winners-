"""Co raketě předcházelo podle zpráv (§6 růstová mapa, §15 text mining) — Google News RSS, zdarma.

Pro každou událost: titulky v okně [T0 − 30 dní, konec + 3 dny], rozdělené na „před T0“ a „během růstu“.
Příčina se určuje automaticky podle klíčových slov v titulcích → vždy označeno AUTO (z titulků), dokud ji
člověk/Claude neověří.
"""

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

RSS = {
    "en": "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en",
    "ja": "https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja",
}

# (kód, český popis, vzor EN|JP, plánovaný termín? = trh věděl KDY, ne JAK to dopadne)
CAUSES = [
    ("ACQUISITION", "převzetí / fúze",
     r"\b(acquir\w*|acquisition|buyout|takeover|merger|to be bought|deal to buy|tender offer|go(ing)? private)\b|TOB|買収|経営統合|合併|完全子会社|ＭＢＯ|MBO", False),
    ("FDA", "regulatorní schválení (FDA/EMA)",
     r"\b(FDA|EMA|approv\w*|clearance|PDUFA|breakthrough therapy|fast track|reimbursement)\b|承認|認可", True),
    ("CLINICAL", "klinická data", r"\b(trial|phase [123i]+|topline|study (results|data)|efficacy|endpoint)\b|治験|臨床試験", False),
    ("EARNINGS", "výsledky / výhled",
     r"\b(earnings|quarter(ly)?|revenue|results|guidance|outlook|profit|beats?|sales)\b|上方修正|決算|増益|増収|業績|最高益|黒字", True),
    ("CONTRACT", "kontrakt / zakázka / partnerství",
     r"\b(contract|award(ed)?|order|partnership|agreement|deal with|collaboration|supply)\b|契約|受注|提携|協業|連携|採用", False),
    ("ACTIVIST", "aktivista / nový velký akcionář",
     r"\b(activist|stake|stakeholder|13D|board seat)\b|大株主|筆頭株主|物言う株主|アクティビスト|保有", False),
    ("GOVERNMENT", "vláda / politika / regulace",
     r"\b(government|pentagon|department of|executive order|tariff|subsid\w*|policy|white house|trump)\b|政府|経産省|防衛|補助金|政策|国策", False),
    ("SECTOR", "sektorová vlna", r"\b(\w+ stocks|sector|industry rally|peers)\b|関連株|関連銘柄|テーマ株", False),
    ("SQUEEZE", "spekulace / squeeze / limitní růst",
     r"\b(short squeeze|squeeze|meme|reddit|retail traders|wallstreetbets|frenzy)\b|ストップ高|Ｓ高|S高|思惑|仕手", False),
    ("CRYPTO", "krypto / treasury strategie",
     r"\b(bitcoin|crypto\w*|ethereum|blockchain|treasury strategy|digital asset|stablecoin|metaplanet)\b|ビットコイン|"
     r"暗号資産|仮想通貨|ステーブルコイン|ＪＰＹＣ|JPYC|メタプラネット", False),
    ("ANALYST", "doporučení analytika", r"\b(upgrade[sd]?|price target|initiat\w* coverage|overweight|outperform)\b|格上げ|目標株価", False),
    ("AI", "AI / datová centra", r"\b(AI|artificial intelligence|data cent(er|re)s?|nvidia|gpu)\b|生成ＡＩ|ＡＩ|データセンター|半導体", False),
    ("PRODUCT", "nový produkt / technologie", r"\b(launch\w*|unveil\w*|new product|breakthrough|patent|prototype)\b|新製品|発売|特許", False),
    ("FINANCING", "financování / emise", r"\b(offering|private placement|raises \$|financing|dilution)\b|増資|新株予約権|第三者割当", False),
]
_COMPILED = [(code, label, re.compile(pat, re.I), sched) for code, label, pat, sched in CAUSES]
STRIP = re.compile(r"\b(inc|corp|corporation|co|ltd|limited|plc|holdings?|group|common stock|class [ab]|ordinary shares|"
                   r"american depositary shares|ads|sa|ag|nv|se|asa|ab|oyj|spa|s\.p\.a|the)\b\.?", re.I)


def short_name(name: str | None) -> str:
    n = STRIP.sub("", name or "")
    n = re.sub(r"[^\w&\- ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def fetch_headlines(query: str, start: date, end: date, *, lang: str = "en", timeout: int = 20) -> list[dict]:
    """Titulky Google News pro dotaz v daném období. `query` je celý vyhledávací výraz."""
    full = f"{query} after:{start.isoformat()} before:{end.isoformat()}"
    url = RSS[lang].format(q=urllib.parse.quote(full))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        root = ET.fromstring(r.read())
    out = []
    for it in root.iter("item"):
        try:
            when = parsedate_to_datetime(it.findtext("pubDate")).date()
        except (TypeError, ValueError):
            continue
        src = it.find("source")
        out.append({"datum": when.isoformat(), "titulek": (it.findtext("title") or "")[:220],
                    "zdroj": src.text if src is not None else None, "url": it.findtext("link")})
    out.sort(key=lambda h: h["datum"])
    return out


def search_plan(name: str | None, symbol: str | None) -> tuple[str | None, str, callable]:
    """Dotaz, jazyk a filtr relevance titulku. Japonsko: podle kódu akcie v japonských zprávách."""
    sym = symbol or ""
    base = sym.split(".")[0]
    if sym.endswith(".T") and base:
        return f'"{base}" 株', "ja", lambda h: True
    q = short_name(name)
    if len(q) < 3:
        return None, "en", lambda h: False
    words = [re.escape(q)]
    if len(base) >= 3 and base.isalpha():
        words.append(rf"\b{re.escape(base)}\b")
    rel = re.compile("|".join(words), re.I)
    return f'"{q}" (stock OR shares)', "en", lambda h: bool(rel.search(h["titulek"]))


EXPLAINER = re.compile(r"\b(why|what's behind|here's why|soar\w*|surg\w*|jump\w*|skyrocket\w*|rall\w*|pop\w*|"
                       r"spik\w*|rocket\w*|doubl\w*|tripl\w*)\b|急騰|急伸|ストップ高|Ｓ高|大幅高|続伸", re.I)


def classify(headlines: list[dict]) -> list[dict]:
    """Seřazené příčiny podle váhy titulků. Vysvětlující titulky („Why X soared…“) mají trojnásobnou váhu."""
    counts = {}
    for h in headlines:
        weight = 3 if EXPLAINER.search(h["titulek"]) else 1
        for code, label, pat, sched in _COMPILED:
            if pat.search(h["titulek"]):
                c = counts.setdefault(code, {"kod": code, "pricina": label, "titulku": 0, "vaha": 0,
                                             "planovany_termin": sched})
                c["titulku"] += 1
                c["vaha"] += weight
    return sorted(counts.values(), key=lambda c: (c["vaha"], c["titulku"]), reverse=True)


def explain_event(name: str, t0: date, end: date, *, symbol: str | None = None, fetch=fetch_headlines,
                  pause: float = 1.0) -> dict:
    """Růstová mapa z titulků: co bylo známo PŘED T0 a co se objevilo během růstu (jen relevantní titulky)."""
    query, lang, relevant = search_plan(name, symbol)
    if query is None:
        return {"stav": "NEOVĚŘENO", "duvod": "příliš krátké jméno pro vyhledávání"}
    try:
        heads = [h for h in fetch(query, t0 - timedelta(days=30), end + timedelta(days=3), lang=lang) if relevant(h)]
    except Exception as exc:
        return {"stav": "DATA NEDOSTUPNÁ", "duvod": str(exc)[:120]}
    finally:
        if pause:
            time.sleep(pause)
    before = [h for h in heads if h["datum"] < t0.isoformat()]
    during = [h for h in heads if h["datum"] >= t0.isoformat()]
    causes = classify(during)
    pre = classify(before)
    # „limitní růst / spekulace“ je spíš příznak než příčina — přednost má skutečný důvod, pokud ho titulky uvádějí
    main = next((c for c in causes if c["kod"] != "SQUEEZE"), causes[0] if causes else None)
    return {
        "stav": "AUTO (z titulků, neověřeno ručně)" if heads else "NEOVĚŘENO — žádné relevantní titulky",
        "dotaz": query, "jazyk": lang, "titulku_pred": len(before), "titulku_behem": len(during),
        "hlavni_pricina": main["pricina"] if main else None, "kod": main["kod"] if main else None,
        "pricny": causes[:4], "signaly_predem": pre[:3],
        "planovany_termin": bool(main and main["planovany_termin"]),
        "titulky": sorted(during, key=lambda h: 0 if EXPLAINER.search(h["titulek"]) else 1)[:4],
        "titulky_predem": before[-3:],
    }


def iso_to_date(s: str) -> date:
    return datetime.fromisoformat(s).date()
