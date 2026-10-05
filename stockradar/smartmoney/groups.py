"""Skupiny událostí pro srovnání (předem dané, ne vybrané podle výsledku)."""

from collections import defaultdict

ACTIVE = "insider:AKTIVNÍ NÁKUP"


def _m(r, k, default=None):
    return (r.get("meta") or {}).get(k, default)


def insider_groups(rows: list[dict]) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        k = r["kind"]
        if not k.startswith("insider:"):
            continue
        if k != ACTIVE:
            g[{"insider:AUTOMATICKÝ": "Insider: automatický nákup (plán 10b5-1)",
               "insider:PASIVNÍ (přidělení)": "Insider: přidělené akcie (odměna)",
               "insider:PASIVNÍ (opce)": "Insider: uplatnění opce",
               "insider:NEJASNÉ": "Insider: nejasné (bez ceny)",
               "insider:NEJASNÉ (hned prodáno)": "Insider: nákup a do 10 dní prodej (např. zaměstnanecký plán)"}.get(k, k)].append(r)
            continue
        g["Insider: AKTIVNÍ nákup (všechny)"].append(r)
        v, dd = _m(r, "value", 0) or 0, r.get("dd52")
        if _m(r, "ceo"):
            g["Insider aktivní: CEO"].append(r)
        if _m(r, "cfo"):
            g["Insider aktivní: CFO"].append(r)
        if _m(r, "director") and not _m(r, "officer") and not _m(r, "ten"):
            g["Insider aktivní: jen člen představenstva"].append(r)
        if _m(r, "ten") and not _m(r, "officer") and not _m(r, "director"):
            g["Insider aktivní: 10% vlastník (fond, majitel)"].append(r)
        if (_m(r, "cluster") or 1) >= 3:
            g["Insider aktivní: 3+ insideři do 30 dní"].append(r)
        if v >= 1_000_000:
            g["Insider aktivní: hodnota ≥ 1 mil. USD"].append(r)
        elif v >= 100_000:
            g["Insider aktivní: 100 tis.–1 mil. USD"].append(r)
        elif v < 25_000:
            g["Insider aktivní: pod 25 tis. USD"].append(r)
        if (_m(r, "pct") or 0) >= 0.2:
            g["Insider aktivní: pozice navýšena o 20 %+"].append(r)
        if dd is not None and dd <= -0.3:
            g["Insider aktivní: po propadu 30 %+ od ročního maxima"].append(r)
        if (r.get("r126_before") or 0) >= 0.5:
            g["Insider aktivní: po růstu 50 %+ za 6 měsíců"].append(r)
        if (_m(r, "ceo") or _m(r, "cfo")) and dd is not None and dd <= -0.3:
            g["Insider aktivní: CEO/CFO po propadu 30 %+"].append(r)
        if (_m(r, "cluster") or 1) >= 3 and dd is not None and dd <= -0.3:
            g["Insider aktivní: 3+ insideři po propadu 30 %+"].append(r)
        t = r.get("turnover") or 0
        g["Insider aktivní: mikro (obrat < 1 mil. USD/den)" if t < 1e6 else
          "Insider aktivní: malé (1–20 mil. USD/den)" if t < 2e7 else "Insider aktivní: velké (obrat > 20 mil. USD/den)"].append(r)
    return dict(g)


def stake_groups(rows):
    g = defaultdict(list)
    for r in rows:
        if r["kind"].startswith("podíl:"):
            g["Velký podíl: " + r["kind"].split(":", 1)[1]].append(r)
    return dict(g)


def buyback_groups(rows):
    g = defaultdict(list)
    for r in rows:
        if not r["kind"].startswith("buyback:"):
            continue
        g["Buyback " + r["kind"].split(":", 1)[1]].append(r)
        y = _m(r, "yield") or 0
        if _m(r, "nove_nebo_zvysene"):
            g["Buyback nový nebo výrazně zvýšený (≥ 2 %)"].append(r)
        if y >= 0.02 and (_m(r, "dilution") is not None and _m(r, "dilution") <= -0.03):
            g["Buyback ≥ 2 % a počet akcií klesl o 3 %+"].append(r)
        if y >= 0.02 and _m(r, "rev_yoy") is not None:
            g["Buyback ≥ 2 % při " + ("rostoucích" if _m(r, "rev_yoy") >= 0 else "klesajících") + " tržbách"].append(r)
    return dict(g)


def congress_groups(rows):
    g = defaultdict(list)
    for r in rows:
        if not r["kind"].startswith("politik:"):
            continue
        cls = r["kind"].split(":", 1)[1]
        if "(" in (_m(r, "member") or ""):
            g["Senát: kandidáti a bývalí (nejsou zákonodárci)"].append(r)
            continue
        if cls != "AKTIVNÍ NÁKUP":
            g[f"Politici: {cls.lower()}"].append(r)
            continue
        g["Politici: AKTIVNÍ nákup (všichni)"].append(r)
        g["Politici: " + ("Sněmovna" if _m(r, "chamber") == "HOUSE" else "Senát")].append(r)
        if _m(r, "member") == "Nancy Pelosi":
            g["Politici: Nancy Pelosi (většinou manžel)"].append(r)
        if _m(r, "asset_type") == "OP":
            g["Politici: nákup opcí"].append(r)
        if (_m(r, "amount_min") or 0) >= 250_001:
            g["Politici: částka ≥ 250 tis. USD"].append(r)
    return dict(g)


def by_year(rows: list[dict]) -> dict[str, list[dict]]:
    g = defaultdict(list)
    for r in rows:
        g[r["public"][:4]].append(r)
    return dict(sorted(g.items()))


def by_member(rows: list[dict], min_n: int = 15) -> dict[str, list[dict]]:
    g = defaultdict(list)
    for r in rows:
        if r["kind"] == "politik:AKTIVNÍ NÁKUP" and "(" not in (_m(r, "member") or ""):
            g[_m(r, "member")].append(r)
    return {k: v for k, v in g.items() if len(v) >= min_n}


PASSIVE = ("insider:PASIVNÍ (přidělení)", "insider:PASIVNÍ (opce)")
CONDITIONS = {
    "vše": lambda r: True,
    "po propadu 30 %+": lambda r: r.get("dd52") is not None and r["dd52"] <= -0.3,
    "bez propadu (do −10 %)": lambda r: r.get("dd52") is not None and r["dd52"] > -0.1,
    "mikro (obrat < 1 mil. USD/den)": lambda r: (r.get("turnover") or 0) < 1e6,
    "malé (1–20 mil.)": lambda r: 1e6 <= (r.get("turnover") or 0) < 2e7,
    "velké (> 20 mil.)": lambda r: (r.get("turnover") or 0) >= 2e7,
}
ACTIVE_SUBSETS = {
    "aktivní nákup (vše)": lambda r: True,
    "CEO": lambda r: _m(r, "ceo"),
    "CFO": lambda r: _m(r, "cfo"),
    "jen člen představenstva": lambda r: _m(r, "director") and not _m(r, "officer") and not _m(r, "ten"),
    "10% vlastník": lambda r: _m(r, "ten") and not _m(r, "officer") and not _m(r, "director"),
    "3+ insideři do 30 dní": lambda r: (_m(r, "cluster") or 1) >= 3,
    "hodnota ≥ 1 mil. USD": lambda r: (_m(r, "value") or 0) >= 1e6,
    "pozice +20 %": lambda r: (_m(r, "pct") or 0) >= 0.2,
}


def active_vs_passive(rows: list[dict], h: str = "6m") -> list[dict]:
    """Přínos aktivního nákupu = výsledek aktivních nákupů MINUS výsledek pasivních transakcí (přidělení, opce)
    u firem ve STEJNÉ situaci (propad, velikost) a ve stejném měsíci. Pasivní transakce o budoucnosti nic neříkají,
    takže zachycují, jak by si firmy vedly i bez nákupu (stejná populace firem podávajících Form 4)."""
    import math
    import statistics
    act = [r for r in rows if r["kind"] == ACTIVE and r.get(f"ex_ctrl_{h}") is not None]
    pas = [r for r in rows if r["kind"] in PASSIVE and r.get(f"ex_ctrl_{h}") is not None]
    out = []
    for cname, cond in CONDITIONS.items():
        pm: dict[str, list[float]] = defaultdict(list)
        for r in pas:
            if cond(r):
                pm[r["public"][:7]].append(r[f"ex_ctrl_{h}"])
        for sname, sub in ACTIVE_SUBSETS.items():
            am: dict[str, list[float]] = defaultdict(list)
            for r in act:
                if cond(r) and sub(r):
                    am[r["public"][:7]].append(r[f"ex_ctrl_{h}"])
            diffs = [statistics.fmean(am[m]) - statistics.fmean(pm[m]) for m in am if m in pm and len(pm[m]) >= 5]
            n = sum(len(am[m]) for m in am if m in pm)
            if len(diffs) < 6:
                continue
            sd = statistics.stdev(diffs)
            t = statistics.fmean(diffs) / (sd / math.sqrt(len(diffs))) if sd > 0 else None
            out.append({"situace": cname, "skupina": sname, "horizont": h, "n": n, "mesicu": len(diffs),
                        "rozdil": round(statistics.fmean(diffs), 4), "t": round(t, 2) if t is not None else None,
                        "mesicu_kladnych": round(sum(1 for d in diffs if d > 0) / len(diffs), 3)})
    return out
