"""Body 5 a 6 zadání: kvalita a NOVOST informací (originál vs. přepisy) a čas, kdy byla informace známá trhu.

Kvalita zdroje (0–100) je předem daná tabulka: SEC/vláda/centrální banka nejvýš, firemní oznámení (IR, tiskové
agentury Business Wire, PR Newswire, GlobeNewswire) vysoko, Reuters/Bloomberg/AP vysoko, ostatní média středně,
komentáře a souhrny (Seeking Alpha, Motley Fool, Zacks, Benzinga…) nízko, sociální sítě skoro nula.
Novost: titulky se shluknou do „příběhů“ (podobnost slov ≥ 0,45 do 4 dnů) — 40 článků o jednom kontraktu je
1 informace × 40 přepisů. Příběh je NOVÝ, když se nepodobá ničemu z předchozích 30 dní.
Den, kdy se příběh poprvé objevil = kdy ho trh mohl znát.

Omezení: titulky Google News RSS (zdarma). Historický panel zprávy neobsahuje, takže novost a kvalita jsou
na kartě jen popis — jako prediktor NEOVĚŘENO.
"""

import re
import time
from datetime import date, timedelta

from stockradar.discovery import news as dnews

QUALITY = [
    (r"\bsec\.gov\b|securities and exchange commission", 100, "úřad (SEC)"),
    (r"federal reserve|white house|department of|\.gov\b|european central bank|ministry", 90, "vláda / centrální banka"),
    (r"business wire|businesswire|pr newswire|prnewswire|globe ?newswire|accesswire|newsfile|investor relations|\bir\b",
     85, "oznámení firmy"),
    (r"reuters|bloomberg|associated press|\bap news\b|financial times|wall street journal|\bwsj\b", 80, "tisková agentura"),
    (r"cnbc|barron|marketwatch|investor'?s business daily|fortune|forbes|axios|the information|yahoo finance|"
     r"new york times|washington post|the economist|nikkei|techcrunch|the verge", 65, "renomované médium"),
    (r"seeking alpha|motley fool|fool\.com|zacks|benzinga|tipranks|investorplace|simply wall|marketbeat|nasdaq|"
     r"24/7 wall|insidermonkey|gurufocus|stocktitan|ainvest|finviz|tradingview|investing\.com|stocktwits", 40,
     "komentář / souhrn"),
    (r"reddit|twitter|\bx\.com\b|stocktwits|youtube|tiktok|facebook", 15, "sociální síť"),
]
_Q = [(re.compile(p, re.I), q, lbl) for p, q, lbl in QUALITY]
UNKNOWN_QUALITY = 35
STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "as", "at", "by", "with", "is", "are", "its",
        "stock", "stocks", "shares", "inc", "corp", "says", "after", "from", "new", "why", "today", "this", "that"}
SIMILAR = 0.45
SAME_STORY_DAYS = 4


def source_quality(source: str | None) -> tuple[int, str]:
    for pat, q, lbl in _Q:
        if source and pat.search(source):
            return q, lbl
    return UNKNOWN_QUALITY, "neznámý zdroj"


def tokens(title: str) -> set[str]:
    t = re.sub(r"\s+-\s+[^-]+$", "", title or "")          # „… - Reuters“ (název zdroje na konci titulku)
    return {w for w in re.findall(r"[a-z0-9$%]+", t.lower()) if len(w) > 2 and w not in STOP}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def stories(headlines: list[dict]) -> list[dict]:
    """Shluky titulků = příběhy; první výskyt, nejlepší zdroj, počet přepisů."""
    out: list[dict] = []
    for h in sorted(headlines, key=lambda x: x["datum"]):
        tk = tokens(h["titulek"])
        d = date.fromisoformat(h["datum"])
        q, lbl = source_quality(h.get("zdroj"))
        for st in out:
            if (d - st["_last"]).days <= SAME_STORY_DAYS and jaccard(tk, st["_tok"]) >= SIMILAR:
                st["kopii"] += 1
                st["_last"] = d
                if q > st["kvalita"]:
                    st["kvalita"], st["typ_zdroje"], st["nejlepsi_zdroj"] = q, lbl, h.get("zdroj")
                break
        else:
            out.append({"poprve": h["datum"], "titulek": h["titulek"], "prvni_zdroj": h.get("zdroj"),
                        "nejlepsi_zdroj": h.get("zdroj"), "kvalita": q, "typ_zdroje": lbl, "kopii": 1,
                        "url": h.get("url"), "_tok": tk, "_last": d})
    return out


def assess(headlines: list[dict], day: date, recent_days: int = 7) -> dict:
    """Novost a kvalita informací k danému dni."""
    sts = stories(headlines)
    cut = day - timedelta(days=recent_days)
    old = [s for s in sts if date.fromisoformat(s["poprve"]) <= cut]
    new = []
    for s in sts:
        if date.fromisoformat(s["poprve"]) > cut:
            seen = any(jaccard(s["_tok"], o["_tok"]) >= SIMILAR for o in old)
            s["nova"] = not seen
            new.append(s)
    fresh = [s for s in new if s.get("nova")]
    novelty = min(100, 35 * len(fresh)) if new else 0
    quality = max((s["kvalita"] for s in fresh), default=None)
    causes = dnews.classify([{"titulek": s["titulek"]} for s in fresh])
    clean = lambda s: {k: v for k, v in s.items() if not k.startswith("_")}
    return {"titulku": len(headlines), "pribehu": len(sts), "prepisu": len(headlines) - len(sts),
            "pribehu_7d": len(new), "novych_7d": len(fresh), "novost": novelty, "kvalita": quality,
            "typ": [c["pricina"] for c in causes[:3]],
            "nove": [clean(s) for s in sorted(fresh, key=lambda s: -s["kvalita"])[:4]],
            "opakovane": [clean(s) for s in new if not s.get("nova")][:2]}


NAME_NOISE = re.compile(r"\((?:[^)]*)\)|\b(ordinary|common|preferred)\s+shares?\b|\bcommon\s+stock\b|\bnew\b|"
                        r"\bclass\s+[a-c]\b|\bamerican depositary\b.*$|\bdepositary\b.*$|\bunits?\b|\bwarrants?\b",
                        re.I)


def clean_name(name: str) -> str:
    """„Carnival Corporation Ltd. Common Shares“ → „Carnival Corporation Ltd.“ (jinak Google News nic nenajde)."""
    return re.sub(r"\s+", " ", NAME_NOISE.sub(" ", name or "")).strip(" ,.-")


def for_symbol(name: str, symbol: str, day: date, *, fetch=dnews.fetch_headlines, pause: float = 1.0) -> dict:
    query, lang, relevant = dnews.search_plan(clean_name(name), symbol)
    if query is None:
        return {"stav": "NEOVĚŘENO", "duvod": "příliš krátké jméno pro vyhledávání"}
    try:
        heads = [h for h in fetch(query, day - timedelta(days=37), day + timedelta(days=1), lang=lang) if relevant(h)]
    except Exception as exc:
        return {"stav": "DATA NEDOSTUPNÁ", "duvod": str(exc)[:120]}
    finally:
        if pause:
            time.sleep(pause)
    return {"stav": "AUTO (titulky Google News)", **assess(heads, day)}
