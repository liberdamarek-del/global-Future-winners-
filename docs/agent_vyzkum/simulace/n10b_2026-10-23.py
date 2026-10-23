"""N-10 varianta (2026-10-23). Pravidla dána PŘED během:
- SOUCASNE: od 6. týdne každý týden t >= 2 (pro srovnání, stejné jako 22. 10.).
- KALIBROVANY TYDEN: kontrola každý týden od 6. do 52. týdne, konstantní práh c pro t (Pocockův typ) zvolený tak,
  aby bez efektu bylo falešně OVĚŘENO nejvýš 5 % (95. percentil maxima t přes kontroly; kalibrace jen na nulových
  datech, semeno 1); hodnocení na nových datech (semeno 20261023).
- KALIBROVANE 4 TYDNY: totéž, ale kontrola jen v týdnech 8, 12, ..., 52 (12 kontrol).
Kritérium N-10 (předem): falešně OVĚŘENO <= 5 % a medián týdne potvrzení u efektu 0,5 sd nejvýš o 4 týdny později než
současné pravidlo (11. týden).
"""
import math, random

W = 52
LOOKS = {"KALIBROVANY TYDEN": list(range(6, W + 1)), "KALIBROVANE 4 TYDNY": list(range(8, W + 1, 4))}

def path_t(rng, mu):
    s = ss = 0.0
    out = {}
    for w in range(1, W + 1):
        x = rng.gauss(mu, 1.0); s += x; ss += x * x
        if w >= 2:
            m = s / w; var = (ss - w * m * m) / (w - 1)
            out[w] = m / math.sqrt(var / w) if var > 0 else 0.0
    return out

def calibrate(reps=20000, seed=1, q=0.95):
    rng = random.Random(seed)
    mx = {k: [] for k in LOOKS}
    for _ in range(reps):
        t = path_t(rng, 0.0)
        for k, looks in LOOKS.items():
            mx[k].append(max(t[w] for w in looks))
    return {k: sorted(v)[int(q * reps)] for k, v in mx.items()}

def evaluate(c, mu, reps, seed):
    rng = random.Random(seed)
    first = {"SOUCASNE": [], **{k: [] for k in LOOKS}}
    for _ in range(reps):
        t = path_t(rng, mu)
        first["SOUCASNE"].append(next((w for w in range(6, W + 1) if t[w] >= 2), None))
        for k, looks in LOOKS.items():
            first[k].append(next((w for w in looks if t[w] >= c[k]), None))
    res = {}
    for k, v in first.items():
        by = lambda lim: sum(1 for x in v if x is not None and x <= lim) / reps
        got = sorted(x for x in v if x is not None)
        res[k] = (by(16), by(26), by(52), got[len(got) // 2] if len(got) >= reps / 2 else None)
    return res

if __name__ == "__main__":
    c = calibrate()
    print("kalibrované prahy t:", {k: round(v, 3) for k, v in c.items()})
    for mu, reps in ((0.0, 20000), (0.3, 5000), (0.5, 5000)):
        print(f"mu = {mu}:")
        for k, (a, b, d, med) in evaluate(c, mu, reps, seed=20261023).items():
            print(f"  {k:20s} OVĚŘENO do 16 t. {a:.3f} | do 26 t. {b:.3f} | do 52 t. {d:.3f} | medián týdne {med}")
