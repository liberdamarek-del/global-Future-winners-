"""GitHub Actions provoz radaru (v0.16.0, rozhodnutí uživatele 2026-10-23; docs/GITHUB_PROVOZ.md).

Nástroj provozu, ne analytický modul (proto mimo balíček stockradar a mimo centrum).

    python tools/github_beh.py plan            # klíče běhů -> GITHUB_OUTPUT (denni, tyden)
    python tools/github_beh.py rezim           # stin / ostry z provoz/github.json -> GITHUB_OUTPUT
    python tools/github_beh.py stranka [--ven _site] [--beh-url URL] [--behy-url URL]
                                               # web/index.html + data/web/stav_*.json + provoz.json -> _site
    python tools/github_beh.py kontrola-prohlizec _site [--dom soubor]   # stránka ve skutečném prohlížeči
    python tools/github_beh.py souhrn DRUH     # krátký souhrn -> GITHUB_STEP_SUMMARY, stdout, zprava/oznameni.json
    python tools/github_beh.py oznam DRUH      # souhrn na telefon přes ntfy.sh (jen se secretem NTFY_TEMA)
    python tools/github_beh.py oznam-chyba DRUH

Klíče: `denni` = poslední všední večer (od 21:30 Praha), který už nastal - záložní slot ve 3:17 ráno i ruční běh přes den
patří k předchozímu večeru; `tyden` = poslední sobota od 9:00 Praha (týdenní objevování). Workflow si podle klíče najde značku v cache GitHubu
a když už běh proběhl, nespustí ho znovu (GitHub plánované běhy zpožďuje nebo zahazuje, proto je slotů víc).
Režim: "stin" = GitHub počítá a zveřejní stránku, ale do gitu nic nezapíše (zapisují rutiny Claude); "ostry" = GitHub
je jediný zapisovatel state/.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PRAGUE = ZoneInfo("Europe/Prague")
MODE_FILE = ROOT / "provoz" / "github.json"
WEB_DATA = ROOT / "data" / "web"
NOTE = ROOT / "zprava" / "oznameni.json"
MODES = ("stin", "ostry")
DOCS = ("aktualni", "predikce", "retezec", "objevy", "smartmoney", "signaly", "zebricek", "zebricek6m", "kauzalni",
        "prehled")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DAILY_AT = time(22, 47)          # po–pá večer v Praze (dřív rutina Claude „denní aktualizace radaru“)
WEEKLY_AT = time(9, 41)          # sobota ráno v Praze (týdenní objevování)
GRACE_DAILY = timedelta(hours=6)
GRACE_WEEKLY = timedelta(hours=10)   # týdenní běh sám trvá hodiny
POPIS = {"stin": "Obnova po–pá večer a v sobotu (GitHub, zkušební souběh)",
         "ostry": "Obnova po–pá večer a v sobotu (GitHub)"}


EVENING_FROM = time(21, 30)      # od kdy už večerní běh daného dne „proběhl“ (sloty 21:47 / 22:47 Praha)
SATURDAY_FROM = time(9, 0)


def keys(now: datetime) -> dict:
    """Poslední večer (po–pá od 21:30 Praha) a poslední sobota (od 9:00 Praha), které už nastaly. Ruční běh přes den
    tak patří k předchozímu večeru a večerní běh téhož dne nevynechá."""
    p = now.astimezone(PRAGUE)
    d = p.date()
    while not (d.weekday() < 5 and datetime.combine(d, EVENING_FROM, PRAGUE) <= p):
        d -= timedelta(days=1)
    s = p.date() - timedelta(days=(p.weekday() - 5) % 7)
    if datetime.combine(s, SATURDAY_FROM, PRAGUE) > p:
        s -= timedelta(days=7)
    return {"denni": d.isoformat(), "tyden": s.isoformat()}


def mode() -> str:
    try:
        m = json.loads(MODE_FILE.read_text(encoding="utf-8")).get("rezim")
    except (OSError, ValueError):
        m = None
    return m if m in MODES else "stin"           # neznámý nebo chybějící režim: nikdy nezapisovat


def output(pairs: dict) -> None:
    lines = [f"{k}={v}" for k, v in pairs.items()]
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def next_run(now: datetime) -> tuple[datetime, timedelta]:
    """Nejbližší plánovaný běh po `now` (pražský čas) a jeho tolerance."""
    p = now.astimezone(PRAGUE)
    best = None
    for add in range(0, 8):
        d = p.date() + timedelta(days=add)
        cands = []
        if d.weekday() < 5:
            cands.append((datetime.combine(d, DAILY_AT, PRAGUE), GRACE_DAILY))
        if d.weekday() == 5:
            cands.append((datetime.combine(d, WEEKLY_AT, PRAGUE), GRACE_WEEKLY))
        for at, grace in cands:
            if at > p and (best is None or at < best[0]):
                best = (at, grace)
        if best:
            return best
    raise RuntimeError("žádný plánovaný běh do týdne")


def deadline(now: datetime) -> datetime:
    at, grace = next_run(now)
    return at + grace


def emails_in(path: Path) -> list[str]:
    return sorted(set(EMAIL_RE.findall(path.read_text(encoding="utf-8", errors="replace"))))


def html_document(page: str) -> str:
    """web/index.html je tělo artefaktu (title, odkazy, styl, obsah, skript); GitHub Pages potřebuje celý dokument."""
    cut = page.find("</style>")
    head, body = (page[:cut + len("</style>")], page[cut + len("</style>"):]) if cut >= 0 else ("", page)
    return ("<!doctype html>\n<html lang=\"cs\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<meta name=\"robots\" content=\"noindex, nofollow\">\n"
            f"{head}\n</head>\n<body>\n{body.strip()}\n</body>\n</html>\n")


def build_site(ven: Path, web_data: Path, now: datetime, beh_url: str | None, behy_url: str | None,
               rezim: str) -> dict:
    """Složí stránku. Chybějící dokument se vynechá (stránka ho nevykreslí); e-mailová adresa v datech = chyba
    (stránka i repozitář jsou veřejné, uživatel chce e-mail jen u SEC)."""
    found = {n: web_data / f"stav_{n}.json" for n in DOCS if (web_data / f"stav_{n}.json").exists()}
    if "aktualni" not in found:
        raise SystemExit(f"CHYBA: {web_data}/stav_aktualni.json chybí - stránka by byla prázdná")
    leaks = {n: emails_in(p) for n, p in found.items() if emails_in(p)}
    if leaks:
        raise SystemExit(f"CHYBA: v datech pro web je e-mailová adresa ({', '.join(leaks)}) - nezveřejňuji")
    if ven.exists():
        shutil.rmtree(ven)
    ven.mkdir(parents=True)
    (ven / "index.html").write_text(html_document((ROOT / "web" / "index.html").read_text(encoding="utf-8")),
                                    encoding="utf-8")
    for n, p in found.items():
        shutil.copyfile(p, ven / f"stav_{n}.json")
    provoz = {"zdroj": "GitHub Actions", "rezim": rezim, "popis": POPIS.get(rezim, POPIS["stin"]),
              "sestaveno": now.astimezone(timezone.utc).isoformat(timespec="minutes"),
              "dalsi_aktualizace_do": deadline(now).astimezone(timezone.utc).isoformat(timespec="minutes"),
              "beh_url": beh_url, "behy_url": behy_url, "dokumenty": sorted(found)}
    (ven / "provoz.json").write_text(json.dumps(provoz, ensure_ascii=False), encoding="utf-8")
    (ven / ".nojekyll").write_text("")
    return provoz


def check_dom(dom: str) -> list[str]:
    dom = re.sub(r"<script\b.*?</script>", "", dom, flags=re.S | re.I)   # texty kódu skriptu nejsou obsah stránky
    problems = []
    if "Aktualizováno" not in dom:
        problems.append("stav se nevykreslil (chybí 'Aktualizováno')")
    if "nepodařilo načíst" in dom:
        problems.append("stránka hlásí, že data nešla načíst")
    if EMAIL_RE.search(re.sub(r"<[^>]+>", " ", dom)):
        problems.append("na stránce je e-mailová adresa")
    return problems


def browser_check(site: Path, dump: Path | None = None) -> list[str]:
    import functools
    import http.server
    import threading
    from playwright.sync_api import sync_playwright
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    problems: list[str] = []
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(channel="chrome")         # Chrome předinstalovaný na serveru GitHubu
            except Exception:
                browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 900}, locale="cs-CZ", timezone_id="Europe/Prague")
            page.on("pageerror", lambda e: problems.append(f"chyba skriptu: {e}"))
            page.on("console", lambda m: problems.append(f"konzole: {m.text}")
                    if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
            page.goto(f"http://127.0.0.1:{srv.server_address[1]}/", wait_until="networkidle")
            try:
                page.wait_for_function("document.getElementById('status').innerText.includes('Aktualizováno')", timeout=20000)
            except Exception:
                problems.append("stav se do 20 s nevykreslil")
            html = page.content()
            if dump:
                dump.write_text(html, encoding="utf-8")
            problems += check_dom(html)
            width = page.evaluate("document.documentElement.scrollWidth")
            if width > 390 + 2:
                problems.append(f"stránka je na šířce telefonu (390 px) široká {width} px")
            browser.close()
    finally:
        srv.shutdown()
    return problems


def _doc(name: str) -> dict | None:
    p = WEB_DATA / f"stav_{name}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except ValueError:
        return None


def summary(kind: str) -> dict:
    """Krátký souhrn běhu pro telefon: kroky s chybou, nové a vyhodnocené predikce, první firmy žebříčků, e-mail."""
    a = _doc("aktualni")
    if not a:
        return {"title": "Radar: běh bez výsledku", "lines": ["Data pro web chybí – běh selhal před aktualizací."],
                "priority": 4, "poslat": True}
    steps = a.get("kroky") or {}
    bad = [k for k, v in steps.items() if str(v).startswith("CHYBA")]
    lines = []
    for key in ("Nové predikce", "Vyhodnocení predikcí", "Učení modelu"):
        if key in steps:
            lines.append(f"{key}: {steps[key]}")
    z = _doc("zebricek") or {}
    names = {"h14": "14 dní", "h1m": "1 měsíc", "h6m": "6 měsíců"}
    for h, label in names.items():
        firms = ((z.get(h) or {}).get("firmy") or [])[:3]
        if firms:
            lines.append(f"Žebříček {label}: " + ", ".join(str(f.get("ticker")) for f in firms))
    em = a.get("email") or {}
    today = datetime.now(timezone.utc).date().isoformat()
    used = sum(int(d.get("requests") or 0) for d in em.get("detail") or [] if d.get("day") == today)
    lines.append(f"E-mail dnes: {used}×" + (" (jen SEC)" if used else ""))
    if bad:
        lines.append("CHYBA v krocích: " + ", ".join(bad))
    title = {"tyden": "Radar: týdenní objevování", "denni": "Radar: denní běh"}.get(kind, "Radar")
    return {"title": title + (" – chyba" if bad else ""), "lines": lines, "priority": 4 if bad else 3, "poslat": True}


def post(msg: dict) -> int:
    topic = os.environ.get("NTFY_TEMA", "").strip()
    if not topic:
        print("oznameni: tema ntfy neni nastavene (secret NTFY_TEMA) - nic se neposila")
        return 0
    body = {"topic": topic, "title": msg["title"], "message": "\n".join(msg["lines"]) or msg["title"],
            "priority": int(msg.get("priority", 3))}
    if os.environ.get("STRANKA_URL"):
        body["click"] = os.environ["STRANKA_URL"]
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"oznameni: odeslano ({r.status})")
    except Exception as exc:                                   # oznámení nikdy neshodí běh
        print(f"oznameni: neodeslano ({type(exc).__name__}: {exc})")
    return 0


STEP_CZ = {"update": "aktualizace", "causal": "kauzální radar", "rakety": "raketový deník", "objevovani": "objevování",
           "smartmoney": "smart money", "signals": "signály", "testy": "testy", "stranka": "stránka"}


def failure_message(kind: str, kroky: str, url: str, logs=()) -> dict:
    """Které kroky selhaly (KROKY = "update=success causal=failure ..."), zda se stránka přesto obnovila, a známá
    příčina: kauzální radar na prázdné cache hlásí BLOKOVÁNO, dokud ji nenaplní první týdenní objevování."""
    what = {"denni": "Denní běh radaru", "tyden": "Týdenní objevování radaru"}.get(kind, "Běh radaru")
    steps = dict(p.split("=", 1) for p in kroky.split() if "=" in p)
    failed = [STEP_CZ.get(k, k) for k, v in steps.items() if v in ("failure", "cancelled")]
    page_ok = steps.get("stranka") == "success"
    lines = [f"Nepovedlo se: {', '.join(failed)}." if failed else f"{what} na GitHubu skončil chybou.",
             "Ostatní kroky proběhly a stránka je obnovená." if page_ok else "Stránka ukazuje poslední úspěšná data."]
    if any("Kauzální radar BLOKOVÁNO" in Path(f).read_text(encoding="utf-8", errors="replace") for f in logs):
        lines.append("Kauzální radar čeká na ceny akcií - doplní je první týdenní objevování (dočasné).")
    lines.append(f"Podrobnosti: {url}" if url else "Podrobnosti: GitHub → Actions.")
    return {"title": f"Radar: {what} – " + (f"chyba ({', '.join(failed)})" if failed else "selhal"),
            "priority": 3 if page_ok else 4, "lines": lines}


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    kind = argv[1] if len(argv) > 1 and not argv[1].startswith("-") else "denni"
    opt = lambda name, default=None: argv[argv.index(name) + 1] if name in argv else default  # noqa: E731
    now = datetime.now(timezone.utc)
    if cmd == "plan":
        output(keys(now))
        return 0
    if cmd == "rezim":
        output({"rezim": mode()})
        return 0
    if cmd == "stranka":
        pv = build_site(Path(opt("--ven", str(ROOT / "_site"))), WEB_DATA, now, opt("--beh-url"), opt("--behy-url"), mode())
        print(f"stranka: {len(pv['dokumenty'])} dokumentu, dalsi aktualizace do {pv['dalsi_aktualizace_do']}")
        return 0
    if cmd == "kontrola-prohlizec":
        problems = browser_check(Path(argv[1]), Path(opt("--dom")) if opt("--dom") else None)
        for p in problems:
            print(f"CHYBA stranky: {p}")
        print("stranka OK (prohlizec)" if not problems else "stranka NENI v poradku")
        return 1 if problems else 0
    if cmd == "souhrn":
        msg = summary(kind)
        NOTE.parent.mkdir(parents=True, exist_ok=True)
        NOTE.write_text(json.dumps(msg, ensure_ascii=False, indent=1), encoding="utf-8")
        text = f"### {msg['title']}\n\n" + "\n".join(f"- {x}" for x in msg["lines"]) + "\n"
        path = os.environ.get("GITHUB_STEP_SUMMARY")
        if path:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text)
        print(text)
        return 0
    if cmd == "oznam":
        msg = json.loads(NOTE.read_text(encoding="utf-8")) if NOTE.exists() else summary(kind)
        return post(msg) if msg.get("poslat") else 0
    if cmd == "oznam-chyba":
        return post(failure_message(kind, os.environ.get("KROKY", ""), os.environ.get("BEH_URL", ""),
                                    (ROOT / "zprava").glob("*.txt")))
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
