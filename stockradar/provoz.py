"""Souběh GitHub × rutiny Claude (experiment N-13, od 2026-10-26): otisk běhu a srovnání podle kritérií daných předem.

Otisk = stav na konci běhu. Deterministické části (všechny predikce, jejich vyhodnocení, vyhodnocené signální karty)
musí být při stejném dni dat stejné — GitHub ve stínu startuje ze state/ po večerní rutině Claude, takže se porovnává
celý konečný stav, ne „dnes nově“. Žebříčky se smí lišit jen s vysvětlením (jiný den dat). Kritéria (navrhy.jsonl,
N-13): vyhodnocení shodná ve 100 % dnů, překryv TOP 10 ≥ 0,6 nebo vysvětlený rozdíl, běhy bez chyby, e-mail evidovaný.
O přepnutí na GitHub rozhoduje uživatel.
"""

import json
import subprocess
from datetime import date
from pathlib import Path

JACCARD_MIN = 0.6
BRANCH = "provoz-zprava"
LISTS = ("h14", "h1m", "h6m", "6m", "6m_velke")


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError:
        return {}


def fingerprint(conn, web_dir: Path, *, day: str | None = None) -> dict:
    """Otisk běhu z databáze a dat pro web (bez e-mailové adresy — jen počty)."""
    day = day or date.today().isoformat()
    a, z, z6 = (_load(web_dir / f"stav_{n}.json") for n in ("aktualni", "zebricek", "zebricek6m"))
    preds = sorted(f"{r[0]}|{r[1]}|{r[2][:10]}" for r in conn.execute(
        "SELECT c.name, p.strategy, p.made_at FROM predictions p JOIN companies c ON c.id = p.company_id"))
    outs = sorted(f"{r[0]}|{r[1]}|{r[2][:10]}|{r[3]}|{r[4]}" for r in conn.execute(
        "SELECT c.name, p.strategy, p.made_at, o.horizon_days, o.result FROM prediction_outcomes o"
        " JOIN predictions p ON p.id = o.prediction_id JOIN companies c ON c.id = p.company_id"))
    cards = sorted(f"{r[0]}|{r[1]}|{r[2]}|{r[3]}" for r in conn.execute(
        "SELECT f.symbol, f.price_date, f.horizon_days, o.up5 FROM signal_outcomes o"
        " JOIN signal_forecasts f ON f.id = o.forecast_id"))
    tick = lambda rows: [f.get("ticker") for f in (rows or [])[:10]]  # noqa: E731
    lists = {h: tick((z.get(h) or {}).get("firmy")) for h in ("h14", "h1m", "h6m")}
    lists.update({"6m": tick(z6.get("firmy")), "6m_velke": tick(z6.get("velke"))})
    email = conn.execute("SELECT COALESCE(SUM(requests), 0) FROM email_usage WHERE day = ?", (day,)).fetchone()[0]
    return {"den": day, "den_dat": a.get("den_dat"), "verze": a.get("verze_aplikace"),
            "model": (a.get("model") or {}).get("verze"),
            "kroky_chyba": [k for k, v in (a.get("kroky") or {}).items() if str(v).startswith("CHYBA")],
            "predikce": preds, "vyhodnoceni": outs, "karty": cards, "zebricky": lists, "email": email}


def jaccard(a: list, b: list) -> float | None:
    sa, sb = set(a or []), set(b or [])
    return round(len(sa & sb) / len(sa | sb), 2) if sa | sb else None


def compare(gh: dict, cl: dict) -> dict:
    """Srovnání otisku GitHubu a Claude podle předem daných kritérií N-13."""
    same_day = gh.get("den_dat") == cl.get("den_dat")
    det = {}
    for key in ("predikce", "vyhodnoceni", "karty"):
        g, c = set(gh.get(key) or []), set(cl.get(key) or [])
        det[key] = {"github": len(g), "claude": len(c), "jen_github": sorted(g - c)[:10], "jen_claude": sorted(c - g)[:10],
                    "shoda": g == c}
    jac = {h: jaccard((gh.get("zebricky") or {}).get(h), (cl.get("zebricky") or {}).get(h)) for h in LISTS}
    problems = []
    if not same_day:
        problems.append(f"jiný den dat (GitHub {gh.get('den_dat')} × Claude {cl.get('den_dat')}) — srovnání jen orientační")
    for key, d in det.items():
        if not d["shoda"]:
            problems.append(f"{key}: GitHub {d['github']} × Claude {d['claude']} (rozdíl {len(d['jen_github']) + len(d['jen_claude'])}+)")
    low = [h for h, j in jac.items() if j is not None and j < JACCARD_MIN]
    if low and same_day:
        problems.append("překryv TOP 10 pod 0,6: " + ", ".join(f"{h} {jac[h]}" for h in low))
    if gh.get("kroky_chyba"):
        problems.append("GitHub: chyba v krocích " + ", ".join(gh["kroky_chyba"]))
    ok = same_day and all(d["shoda"] for d in det.values()) and not (low and same_day) and not gh.get("kroky_chyba")
    return {"splneno": ok, "stejny_den_dat": same_day, "deterministicke": det, "prekryv_top10": jac,
            "email": {"github": gh.get("email"), "claude": cl.get("email")}, "problemy": problems}


def fetch_github(root: Path, *, branch: str = BRANCH, run=subprocess.run) -> dict | None:
    """Otisk z poslední zprávy GitHubu (větev provoz-zprava); jen čtení, nic se nezapisuje."""
    run(["git", "fetch", "-q", "origin", branch], cwd=root, check=True, capture_output=True, timeout=120)
    out = run(["git", "show", f"origin/{branch}:otisk.json"], cwd=root, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except ValueError:
        return None


def report_md(res: dict, gh: dict, cl: dict) -> str:
    det = res["deterministicke"]
    rows = "\n".join(f"| {k} | {d['github']} | {d['claude']} | {'ano' if d['shoda'] else 'NE'} |" for k, d in det.items())
    top5 = lambda fp, h: ", ".join(str(t) for t in ((fp.get("zebricky") or {}).get(h) or [])[:5])  # noqa: E731
    jac = "\n".join(f"| {h} | {top5(gh, h)} | {top5(cl, h)} | {j} |" for h, j in res["prekryv_top10"].items())
    probs = "\n".join(f"- {p}" for p in res["problemy"]) or "- žádné"
    return (f"# Srovnání souběhu GitHub × Claude — {cl.get('den')}\n\n"
            f"Den dat: GitHub {gh.get('den_dat')} × Claude {cl.get('den_dat')} · verze {gh.get('verze')} × {cl.get('verze')}"
            f" · model {gh.get('model')} × {cl.get('model')}\n\n"
            f"**Kritéria N-13 dnes: {'SPLNĚNA' if res['splneno'] else 'NESPLNĚNA'}**\n\n"
            "| Konečný stav | GitHub | Claude | Shoda |\n|---|---|---|---|\n" + rows + "\n\n"
            "| Žebříček | GitHub (TOP 5) | Claude (TOP 5) | Překryv TOP 10 |\n|---|---|---|---|\n" + jac + "\n\n"
            f"E-mail za den: GitHub {gh.get('email')}× · Claude {cl.get('email')}×\n\nProblémy:\n{probs}\n")
