"""N-10 simulace (2026-10-22). Pravidla dána PŘED během:
- SOUCASNE: od 6. týdne každý týden t >= 2 (správný směr) -> OVĚŘENO.
- E-PROCES: Bayesův faktor t-testu (Gönen a kol. 2005; normální prior na efekt d ~ N(0, g), Jeffreys/right-Haar na sd),
  OVĚŘENO při BF >= 20 a průměru > 0, kontrola každý týden od 6. týdne. Primární g = 0.25 (sd efektu 0,5 týdenní sd,
  odpovídá efektům 0,3–0,5, které nás zajímají); g = 1 jen jako citlivost.
- BODY: kontrola jen v týdnech 8, 16, 26, 52 s Bonferroniho prahem (jednostranně 0,05/4 na pohled).
Scénáře: týdenní průměry iid N(mu, 1), mu = 0 (žádný efekt), 0,3, 0,5; 52 týdnů.
"""
import math, random, statistics, sys

def t_pdf(x, df):
    return math.exp(math.lgamma((df + 1) / 2) - math.lgamma(df / 2)) / math.sqrt(df * math.pi) * (1 + x * x / df) ** (-(df + 1) / 2)

def t_sf(x, df, steps=4000, hi=60.0):
    h = (hi - x) / steps
    s = t_pdf(x, df) + t_pdf(hi, df)
    for i in range(1, steps):
        s += (4 if i % 2 else 2) * t_pdf(x + i * h, df)
    return s * h / 3

def t_quantile_upper(p, df):
    lo, hi = 0.0, 20.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if t_sf(mid, df) > p: lo = mid
        else: hi = mid
    return (lo + hi) / 2

def bf10(t, n, g):
    nu = n - 1
    return (1 + n * g) ** -0.5 * ((1 + t * t / ((1 + n * g) * nu)) / (1 + t * t / nu)) ** (-(nu + 1) / 2)

CHECK = (8, 16, 26, 52)
TH = {w: t_quantile_upper(0.05 / 4, w - 1) for w in CHECK}

def run(mu, reps, seed, W=52):
    rng = random.Random(seed)
    first = {"SOUCASNE": [], "E-PROCES g=0,25": [], "E-PROCES g=1": [], "BODY": []}
    for _ in range(reps):
        s = ss = 0.0
        hit = {k: None for k in first}
        for w in range(1, W + 1):
            x = rng.gauss(mu, 1.0); s += x; ss += x * x
            if w < 6:
                continue
            m = s / w; var = (ss - w * m * m) / (w - 1); t = m / math.sqrt(var / w)
            if hit["SOUCASNE"] is None and t >= 2: hit["SOUCASNE"] = w
            for key, g in (("E-PROCES g=0,25", 0.25), ("E-PROCES g=1", 1.0)):
                if hit[key] is None and m > 0 and bf10(t, w, g) >= 20: hit[key] = w
            if hit["BODY"] is None and w in TH and t >= TH[w]: hit["BODY"] = w
        for k in first: first[k].append(hit[k])
    return first

def summary(first, reps):
    out = {}
    for k, v in first.items():
        by = lambda W: sum(1 for x in v if x is not None and x <= W) / reps
        got = sorted(x for x in v if x is not None)
        med = got[len(got) // 2] if len(got) >= reps / 2 else None     # medián jen když potvrdí aspoň polovina
        out[k] = (by(16), by(26), by(52), med)
    return out

if __name__ == "__main__":
    print("prahy BODY:", {w: round(v, 3) for w, v in TH.items()})
    for mu, reps in ((0.0, 10000), (0.3, 4000), (0.5, 4000)):
        res = summary(run(mu, reps, seed=20261022), reps)
        print(f"mu = {mu}:")
        for k, (a, b, c, med) in res.items():
            print(f"  {k:16s} OVĚŘENO do 16 t. {a:.3f} | do 26 t. {b:.3f} | do 52 t. {c:.3f} | medián týdne {med}")
