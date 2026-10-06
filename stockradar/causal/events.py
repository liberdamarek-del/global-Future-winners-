"""Události ve světě → uzly kauzálního grafu (komodity). Jen bezplatné zdroje.

- GDACS (OSN + EU JRC): hurikány, záplavy, sucha, zemětřesení, požáry, sopky s úrovní výstrahy a zeměmi.
- Google News RSS: zprávy o narušení nabídky/poptávky u každé komodity (sucho, stávka, clo, sankce, výpadek…),
  počet NOVÝCH příběhů za 7 dní proti předchozím 30 dnům = mediální pozornost (přepisy jedné zprávy = 1 příběh).
Přiřazení události ke komoditě přes výrobní země je NEOVĚŘENO, dokud podíl země není doložen zdrojem.
"""

import json
import time
import urllib.request
from datetime import date, timedelta

from stockradar.causal import commodities as CM
from stockradar.discovery import news as dnews
from stockradar.signals import news as snews

GDACS_URL = ("https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=TC,FL,DR,EQ,WF,VO"
             "&fromDate={start}&toDate={end}&alertlevel=Orange;Red")
TYPES = {"TC": "tropická cyklóna", "FL": "záplavy", "DR": "sucho", "EQ": "zemětřesení", "WF": "lesní požár", "VO": "sopka"}
# které typy přírodních událostí mohou zasáhnout kterou skupinu komodit
AFFECTS = {"zemědělství": {"TC", "FL", "DR", "WF"}, "kovy": {"EQ", "FL", "TC"}, "energie": {"TC", "EQ", "FL"},
           "stavba": {"WF", "TC"}, "doprava": {"TC", "DR"}, "makro": set()}
DISRUPT = ("drought OR flood OR hurricane OR cyclone OR frost OR heatwave OR strike OR shortage OR outage OR "
           "\"export ban\" OR tariff OR sanctions OR fire OR explosion OR accident OR attack OR blockade OR war OR disease")
SEARCH = {"BRENT": "oil", "WTI": "crude oil", "NATGAS": "natural gas", "DIESEL": "diesel", "GASOLINE": "gasoline",
          "GOLD": "gold mine", "SILVER": "silver mine", "COPPER": "copper", "ALUMINIUM": "aluminium", "IRONORE": "iron ore",
          "STEEL": "steel", "PLATINUM": "platinum", "PALLADIUM": "palladium", "URANIUM": "uranium", "CORN": "corn",
          "WHEAT": "wheat", "SOY": "soybean", "COFFEE": "coffee", "COCOA": "cocoa", "SUGAR": "sugar", "COTTON": "cotton",
          "ORANGEJUICE": "orange juice", "CATTLE": "cattle", "HOGS": "hog", "LUMBER": "lumber", "DRYBULK": "shipping",
          "USD": "dollar index"}


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def gdacs(today: date, days: int = 21, *, get=_get) -> list[dict]:
    """Výstrahy GDACS (oranžová, červená) za posledních `days` dní."""
    url = GDACS_URL.format(start=(today - timedelta(days=days)).isoformat(), end=today.isoformat())
    feats = json.loads(get(url)).get("features") or []
    out = []
    for f in feats:
        p = f.get("properties") or {}
        rep = p.get("url")
        out.append({"zdroj": "GDACS", "typ": p.get("eventtype"), "typ_cz": TYPES.get(p.get("eventtype"), p.get("eventtype")),
                    "nazev": p.get("name"), "uroven": p.get("alertlevel"), "zeme": p.get("country") or "",
                    "od": (p.get("fromdate") or "")[:10], "do": (p.get("todate") or "")[:10],
                    "popis": (p.get("severitydata") or {}).get("severitytext"),
                    "url": rep.get("report") if isinstance(rep, dict) else rep})
    return out


def link_gdacs(events: list[dict]) -> dict[str, list[dict]]:
    """Komodita → přírodní události ve výrobních zemích, které ji mohou zasáhnout (NEOVĚŘENO)."""
    out: dict[str, list[dict]] = {}
    for e in events:
        for cid in CM.producers_in(e["zeme"]):
            c = CM.BY_ID[cid]
            if e["typ"] in AFFECTS.get(c["skupina"], set()):
                out.setdefault(cid, []).append({**e, "vazba": "výrobní země (NEOVĚŘENO)"})
    return out


def news_pulse(cid: str, today: date, *, fetch=dnews.fetch_headlines, pause: float = 1.0) -> dict:
    """Zprávy o narušení u komodity: nové příběhy za posledních 7 dní vs. stejně dlouhé okno o měsíc dřív.
    Dvě stejně dlouhá okna — RSS vrací jen omezený počet nejnovějších titulků, delší okno by srovnání zkreslilo."""
    term = SEARCH.get(cid)
    if not term:
        return {"stav": "bez hledání"}
    query = f"\"{term}\" ({DISRUPT})" if " " in term else f"{term} ({DISRUPT})"
    windows = {"ted": (today - timedelta(days=7), today + timedelta(days=1)),
               "pred_mesicem": (today - timedelta(days=37), today - timedelta(days=29))}
    got = {}
    for key, (a, b) in windows.items():
        try:
            # Google News u širokých dotazů časové okno ignoruje → titulky se filtrují podle data samy
            got[key] = snews.stories([h for h in fetch(query, a, b) if a <= date.fromisoformat(h["datum"]) < b])
        except Exception as exc:
            return {"stav": "DATA NEDOSTUPNÁ", "duvod": str(exc)[:120]}
        finally:
            if pause:
                time.sleep(pause)
    recent, older = got["ted"], got["pred_mesicem"]
    ratio = len(recent) / len(older) if older else float(len(recent))
    top = sorted(recent, key=lambda s: (-s["kvalita"], -s["kopii"]))[:4]
    return {"stav": "AUTO (titulky Google News)", "pribehu_7d": len(recent), "pribehu_pred_mesicem": len(older),
            "pozornost": round(ratio, 2), "titulky": [{k: s.get(k) for k in ("poprve", "titulek", "nejlepsi_zdroj", "kvalita",
                                                                               "kopii", "url")} for s in top]}
