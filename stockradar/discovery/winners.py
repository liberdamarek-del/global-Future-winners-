"""První vrstva (§2): najdi vítěze — historické raketové události i dnešní vítěze za 3/6/12/24 měsíců."""

from dataclasses import dataclass

from stockradar.discovery.cache import Bars

# kód, okno (obchodní dny), práh, popis
EVENT_TYPES = {
    "W1_30": (5, 0.30, "≥ +30 % za týden"),
    "M1_50": (21, 0.50, "≥ +50 % za měsíc"),
    "M3_50": (63, 0.50, "≥ +50 % za 3 měsíce"),
    "M6_100": (126, 1.00, "≥ +100 % za 6 měsíců"),
}

# §2: filtry pro dnešní vítěze (obchodní dny ≈ měsíce)
TRAILING = {
    "3M": (63, (0.20, 0.30, 0.50)),
    "6M": (126, (0.30, 0.50, 1.00)),
    "12M": (252, (0.30, 0.50, 1.00)),
    "24M": (504, (0.50, 1.00, 2.00)),
}


@dataclass
class Event:
    symbol: str
    kind: str
    t0: int          # index báze (minimum v okně) — okamžik, ke kterému se počítají znaky
    end: int         # index, kdy byl práh překročen
    ret: float       # výnos T0 -> end
    peak_ret: float  # maximum do 63 dní po end vůči T0
    held: float | None  # cena 63 dní po end / cena v end (udržel se růst?)


def is_bad_tick(c: list[float], e: int) -> bool:
    """Skok a okamžitý návrat na původní úroveň = pravděpodobně chyba dat."""
    if e < 1 or e + 1 >= len(c):
        return False
    jump = c[e] / c[e - 1] > 2.0 and c[e + 1] / c[e - 1] < 1.3
    crash = c[e] / c[e - 1] < 0.5 and c[e + 1] / c[e - 1] > 0.77
    return jump or crash


# Zrcadlové propady (log-symetrické: +30 % ~ −23 %, +50 % ~ −33 %) — pro model asymetrie raketa vs propad.
DROP_OF = {"W1_30": "D1_23", "M3_50": "D3_33"}
EVENT_TYPES["D1_23"] = (5, 1 / 1.30 - 1, "≤ −23 % za týden")
EVENT_TYPES["D3_33"] = (63, 1 / 1.50 - 1, "≤ −33 % za 3 měsíce")


def find_events(bars: Bars, kind: str, *, min_volume_days: int = 3) -> list[Event]:
    window, threshold, _ = EVENT_TYPES[kind]
    up = threshold > 0
    c, v = bars.closes, bars.volumes
    out, e, n = [], window, len(c)
    while e < n:
        start = e - window
        move = c[e] / c[start] - 1 if c[start] > 0 else 0.0
        if (move >= threshold if up else move <= threshold) and not is_bad_tick(c, e):
            seg = range(start, e + 1)
            t0 = min(seg, key=lambda k: c[k]) if up else max(seg, key=lambda k: c[k])
            traded = sum(1 for k in range(t0 + 1, e + 1) if v[k] > 0)
            if t0 < e and traded >= min(min_volume_days, e - t0):
                after = c[e:min(n, e + 64)]
                held = c[e + 63] / c[e] if e + 63 < n else None
                out.append(Event(bars.symbol, kind, t0, e, c[e] / c[t0] - 1, max(after) / c[t0] - 1, held))
                e += window  # bez překryvu
                continue
        e += 1
    return out


def outcome_label(held: float | None) -> str:
    if held is None:
        return "PŘÍLIŠ BRZY"
    if held >= 0.85:
        return "UDRŽEL"
    if held <= 0.6:
        return "VYFOUKL"
    return "ČÁSTEČNĚ"


def trailing_returns(bars: Bars) -> dict[str, float | None]:
    c, i = bars.closes, len(bars.closes) - 1
    return {k: (c[i] / c[i - w] - 1 if i >= w and c[i - w] > 0 else None) for k, (w, _) in TRAILING.items()}


def phase(trailing: dict, recent_event: bool) -> str:
    """§38 TOO LATE detector — kolik z možného pohybu už proběhlo."""
    r6 = trailing.get("6M")
    if recent_event:
        return "ALREADY TRIGGERED"
    if r6 is None:
        return "NEOVĚŘENO"
    if r6 >= 1.0:
        return "LATE"
    if r6 >= 0.5:
        return "PARTIALLY PRICED"
    if r6 >= 0.15:
        return "DEVELOPING"
    return "EARLY"


# Neupravený zpětný split (reverse split): cena přes noc ×10 / ×20 … a objem spadne na zlomek → falešná „raketa“.
# (Nalezeno 2026-10-04: DHY 1,61 → 16,05 USD s objemem 0,1×; WCT reverse split 1:5 k 8. 9. 2026 podle GlobeNewswire;
# celkem 26 z 12 774 řad.) Pokles o celý násobek se jako split
# NEBERE — u biotechu jsou propady −50 % s obrovským objemem skutečné (selhání studie).
SPLIT_FACTORS = (3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 35, 40, 50, 60, 75, 80, 100, 150, 200, 250, 300)


def reverse_split_points(bars: Bars) -> list[tuple[int, float]]:
    """Indexy dnů s pravděpodobným neupraveným zpětným splitem a jeho poměr."""
    c, v = bars.closes, bars.volumes
    out = []
    for k in range(11, len(c)):
        if c[k - 1] <= 0:
            continue
        r = c[k] / c[k - 1]
        if r < 2.9:
            continue
        near = min(SPLIT_FACTORS, key=lambda x: abs(r / x - 1))
        if abs(r / near - 1) > 0.04:
            continue
        base = sorted(v[k - 10:k])[5]
        if base <= 0 or v[k] / base > 0.5:
            continue
        if k + 1 < len(c) and not (0.7 <= c[k + 1] / c[k] <= 1.4):
            continue
        out.append((k, r))
    return out


def adjust_reverse_splits(bars: Bars) -> tuple[Bars, int]:
    """Zpětně upraví historii před každým nalezeným splitem (ceny × poměr, objemy ÷ poměr)."""
    points = reverse_split_points(bars)
    if not points:
        return bars, 0
    import array
    closes, vols = array.array("d", bars.closes), array.array("d", bars.volumes)
    for k, r in points:
        for i in range(k):
            closes[i] *= r
            vols[i] /= r
    return Bars(bars.symbol, bars.currency, bars.days, closes, vols), len(points)
