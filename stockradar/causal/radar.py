"""Dnešní kauzální radar: UDÁLOST → FAKTA → KAUZÁLNÍ VZTAH → DOPAD NA OBOR → FIRMY → PREDIKCE.

Karta vzniká u komodity, kde se něco děje: cenový šok (|z| ≥ 1,5), výstraha GDACS ve výrobní zemi, nebo nárůst
zpráv o narušení (aspoň 3 nové příběhy a 2× víc než obvykle). Ke každé kartě:
- fakta se zdroji (URL, datum), pohyb ceny, mediální pozornost,
- řetězec 1.–3. řádu z grafu (logika = NEOVĚŘENO) + citlivost oborů z minulých dat (empiricky, t-statistika),
- „je to v ceně?“: skutečný pohyb oboru za 4 týdny / očekávaný pohyb (beta × pohyb komodity),
- scénáře BASE / POZITIVNÍ / NEGATIVNÍ z historie TÉTO komodity po podobných šocích (ne odhad),
- příležitosti: obory a jejich největší firmy (XTB) seřazené podle skóre (čerstvost × nezapočítaný dopad × důkaz).
Historický test (chains.study) říká, jak rychle trh dopady obvykle započítá — karta to uvádí u každého řetězce.
"""

import math
import statistics
from datetime import date

from stockradar.causal import commodities as CM
from stockradar.causal import data as cdata
from stockradar.causal.chains import _past
from stockradar.causal.exposure import T_MIN, Exposure, shock

Z_EVENT = 1.5
T_STRONG = 3.0      # čistě datová vazba bez ekonomické logiky: přísnější práh (3 250 dvojic → ~160 náhodných při |t| ≥ 2)
HORIZON_BY_ORDER = {1: 30, 2: 90, 3: 90}


def _quant(v: list[float], q: float) -> float | None:
    v = sorted(v)
    return round(v[int(q * (len(v) - 1))], 4) if v else None


def scenarios(ex: Exposure, cid: str, w: int, sign: int, h: int = 13) -> dict:
    """Co dělala TATO komodita v dalších h týdnech po minulých šocích stejného směru (z ≥ 1,5)."""
    wk = ex.weekly
    series = wk.comm[cid]
    after = []
    for k in range(30, w - h):
        sh = shock(wk, cid, k)
        if sh is None or abs(sh[1]) < Z_EVENT or math.copysign(1, sh[0]) != sign:
            continue
        seg = series[k + 1:k + 1 + h]
        if any(v != v for v in seg):
            continue
        after.append(math.prod(1 + v for v in seg) - 1)
    if len(after) < 4:
        return {"pripadu": len(after), "poznamka": "málo podobných šoků v historii — scénáře NEOVĚŘENO"}
    cont = [a for a in after if math.copysign(1, a) == sign]
    return {"pripadu": len(after), "tydnu": h,
            "pokracovani": round(len(cont) / len(after), 2),
            "BASE": {"p": 0.6, "pohyb": _quant(after, 0.5), "popis": "střední výsledek (20.–80. percentil)"},
            "POZITIVNI": {"p": 0.2, "pohyb": _quant(after, 0.8 if sign > 0 else 0.2), "popis": "šok pokračuje"},
            "NEGATIVNI": {"p": 0.2, "pohyb": _quant(after, 0.2 if sign > 0 else 0.8), "popis": "šok se vrátí"}}


def firms(securities: list[dict], industry: str, *, n: int = 3, check=None) -> list[dict]:
    """Největší americké firmy oboru (kapitalizace ze seznamu firem), jen z nabídky XTB, když je kontrola."""
    out = []
    for s in sorted((x for x in securities if (x["industry"] or "").lower() == industry and x["market_cap_usd"]),
                    key=lambda x: -x["market_cap_usd"]):
        row = check(s["symbol"], s["name"]) if check else None
        if check and not (row and row["status"] == "AKCIE"):
            continue
        out.append({"ticker": s["symbol"], "firma": s["name"], "kapitalizace_mld": round(s["market_cap_usd"] / 1e9, 1),
                    "xtb": row["xtb_symbol"] if row else None})
        if len(out) >= n:
            break
    return out


def build(ex: Exposure, commodities: dict, today: date, *, gdacs_links: dict, pulses: dict, securities: list[dict],
          study: dict | None = None, xtb_check=None, pulse_history: dict | None = None) -> dict:
    """pulse_history: komodita → počty nových příběhů za 7 dní z předchozích běhů radaru (základ pro „víc zpráv
    než obvykle“; Google News starší týdny vrací neúplně, proto se základ bere z vlastní historie)."""
    wk = ex.weekly
    w = len(wk.weeks) - 1
    cards, opps = [], []
    for c in CM.COMMODITIES:
        cid = c["id"]
        if cid not in wk.comm:
            continue
        bars = commodities.get(cid)
        sh = shock(wk, cid, w)
        pulse = pulses.get(cid) or {}
        gd = gdacs_links.get(cid) or []
        price_shock = sh is not None and abs(sh[1]) >= Z_EVENT
        hist = sorted((pulse_history or {}).get(cid, []))
        base = hist[len(hist) // 2] if len(hist) >= 3 else None
        recent = pulse.get("pribehu_7d") or 0
        news_spike = base is not None and recent >= 5 and recent >= 2 * max(base, 1)
        if pulse:
            pulse = {**pulse, "zaklad_z_historie": base, "pozornost": round(recent / max(base, 1), 2) if base is not None else None}
        gd_hit = any(e["uroven"] == "Red" for e in gd) or (c["skupina"] == "zemědělství" and any(e["typ"] == "DR" for e in gd))
        if not (price_shock or news_spike or gd_hit):
            continue
        r4 = sh[0] if sh else None
        # směr: když se cena už pohnula, podle pohybu; jinak scénář „nabídka se zúží → cena roste“
        sign = int(math.copysign(1, r4)) if price_shock else 1
        basis = "pohyb ceny za 4 týdny" if price_shock else "SCÉNÁŘ: narušení nabídky → cena roste (zatím se nepohnula)"
        chain = []
        for g in wk.ind:
            beta, t = ex.beta[(g, cid)][w]
            logic = CM.chain_for(cid, g)
            emp = beta == beta and t == t and abs(t) >= (T_MIN if logic else T_STRONG)
            if not emp and logic is None:
                continue
            d_emp = int(math.copysign(1, beta)) * sign if emp else None
            d_log = logic[1] * sign if logic else None
            if emp and logic and d_emp != d_log:
                evidence = "EMPIRICKY"                    # data a logika se neshodují → platí data, logika jen poznámka
            elif emp and logic:
                evidence = "EMPIRICKY_I_LOGIKA"
            else:
                evidence = "EMPIRICKY" if emp else "LOGIKA_NEOVERENO"
            direction = d_emp if emp else d_log
            ref_move = r4 if price_shock else (statistics.pstdev([v for v in wk.comm[cid][-52:] if v == v]) * 2 * sign)
            expected = beta * ref_move if beta == beta else None
            realized = _past(wk.ind[g], w, 4)
            priced = (realized / expected) if expected and realized is not None and abs(expected) > 1e-4 else None
            order = logic[0] if logic else 1
            item = {"obor": g, "rad": order, "smer": direction, "dukaz": evidence,
                    "proc": logic[2] if logic else "obor se historicky pohybuje s touto komoditou",
                    "beta": round(beta, 3) if beta == beta else None, "t": round(t, 1) if t == t else None,
                    "ocekavany_pohyb": round(expected, 4) if expected is not None else None,
                    "skutecny_pohyb_4t": round(realized, 4) if realized is not None else None,
                    "v_cene": round(priced, 2) if priced is not None else None,
                    "horizont_dni": HORIZON_BY_ORDER.get(order, 30), "akcii_v_oboru": wk.n_stocks.get(g)}
            # příležitost jen tam, kde událost potvrzuje cena nebo zprávy; samotná výstraha GDACS = jen sledovat
            fresh = 1.0 if price_shock else 0.5 if news_spike else 0.0
            unpriced = 1.0 - min(max(priced, 0.0), 1.0) if priced is not None else 0.5
            weight = {"EMPIRICKY_I_LOGIKA": 1.0, "EMPIRICKY": 0.8, "LOGIKA_NEOVERENO": 0.3}[evidence]
            item["skore"] = round(fresh * unpriced * weight * min(abs(expected or 0.0) * 10, 1.0) * 100, 1)
            chain.append(item)
        chain.sort(key=lambda x: (x["rad"], -x["skore"]))
        # příležitost = vazbu potvrzují DATA i EKONOMICKÁ LOGIKA se stejným směrem (čistě datové vazby mezi 3 250
        # dvojicemi bývají náhodné, např. „železná ruda → farmacie“; čistá logika je neověřená)
        for it in sorted(chain, key=lambda x: -x["skore"])[:4]:
            if it["skore"] > 0 and it["dukaz"] == "EMPIRICKY_I_LOGIKA":
                opps.append({"komodita": cid, "nazev_komodity": c["nazev"], **it,
                             "firmy": firms(securities, it["obor"], check=xtb_check)})
        now = cdata.close_at(bars, wk.weeks[w]) if bars else None
        cards.append({
            "komodita": cid, "nazev": c["nazev"], "symbol": c["symbol"], "skupina": c["skupina"],
            "cena": round(now, 4) if now else None, "den": date.fromordinal(wk.weeks[w]).isoformat(),
            "pohyb_1t": round(wk.comm[cid][w], 4) if wk.comm[cid][w] == wk.comm[cid][w] else None,
            "pohyb_4t": round(r4, 4) if r4 is not None else None, "z": round(sh[1], 2) if sh else None,
            "spoustec": [x for x, on in (("cenový šok", price_shock), ("zprávy", news_spike), ("GDACS", gd_hit)) if on],
            "stav": "PŘÍLEŽITOST" if (price_shock or news_spike) else "SLEDOVAT (výstraha bez potvrzení cenou nebo zprávami)",
            "zaklad_smeru": basis, "vyrobci": c["vyrobci"], "vyrobci_stav": CM.NEOVERENO, "uzly": c["uzly"],
            "udalosti": gd[:4], "zpravy": pulse,
            "retez": chain[:14], "scenare": scenarios(ex, cid, w, sign),
        })
    opps.sort(key=lambda x: -x["skore"])
    hist = None
    if study:
        hist = {name: {"soku": p.get("soku"), "v_cene_4t": (p.get("empiricke") or {}).get("uz_v_cene_4t"),
                       "dalsi_13t": (p.get("empiricke") or {}).get("13t"), "dalsi_4t": (p.get("empiricke") or {}).get("4t")}
                for name, p in (study.get("obdobi") or {}).items()}
    return {"den": date.fromordinal(wk.weeks[w]).isoformat(), "karty": cards, "prilezitosti": opps[:20],
            "historie": hist,
            "princip": "SVĚT → UDÁLOST → KOMODITA → OBORY → FIRMY; každý krok se zdrojem nebo NEOVĚŘENO"}
