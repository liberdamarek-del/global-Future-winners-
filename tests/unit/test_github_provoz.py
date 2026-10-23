"""Provoz na GitHub Actions (v0.16.0, docs/GITHUB_PROVOZ.md): klíče běhů, režim, termín další aktualizace, stránka bez
e-mailu, souhrn pro telefon. Bez sítě."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import github_beh as G  # noqa: E402

U = lambda *a: datetime(*a, tzinfo=timezone.utc)  # noqa: E731


@pytest.mark.parametrize("now, denni, tyden", [
    (U(2026, 10, 23, 20, 47), "2026-10-23", "2026-10-17"),   # pátek 22:47 Praha (letní čas)
    (U(2026, 10, 24, 1, 17), "2026-10-23", "2026-10-17"),    # záložní slot v noci patří k pátečnímu večeru
    (U(2026, 10, 23, 5, 30), "2026-10-22", "2026-10-17"),    # ruční běh přes den patří k předchozímu večeru
    (U(2026, 10, 24, 6, 30), "2026-10-23", "2026-10-17"),    # sobota 8:30 Praha: týdenní běh ještě nenastal
    (U(2026, 10, 24, 7, 41), "2026-10-23", "2026-10-24"),    # sobota 9:41 Praha
    (U(2026, 10, 26, 7, 0), "2026-10-23", "2026-10-24"),     # pondělí ráno: poslední večer je páteční
    (U(2026, 11, 2, 20, 47), "2026-11-02", "2026-10-31"),    # zimní čas: 21:47 Praha
])
def test_keys(now, denni, tyden):
    assert G.keys(now) == {"denni": denni, "tyden": tyden}


def test_mode(tmp_path, monkeypatch):
    f = tmp_path / "github.json"
    monkeypatch.setattr(G, "MODE_FILE", f)
    assert G.mode() == "stin"                                 # chybí soubor
    f.write_text('{"rezim": "zapis vsechno"}')
    assert G.mode() == "stin"                                 # neznámá hodnota = nezapisovat
    f.write_text('{"rezim": "ostry"}')
    assert G.mode() == "ostry"


def test_deadline():
    assert G.deadline(U(2026, 10, 23, 5, 30)) == datetime(2026, 10, 24, 4, 47, tzinfo=G.PRAGUE)      # pátek večer + 6 h
    assert G.deadline(U(2026, 10, 23, 21, 0)) == datetime(2026, 10, 24, 19, 41, tzinfo=G.PRAGUE)     # sobota + 10 h
    assert G.deadline(U(2026, 10, 24, 12, 0)) == datetime(2026, 10, 27, 4, 47, tzinfo=G.PRAGUE)      # pondělí večer


def _web(tmp_path, extra=None):
    web = tmp_path / "web"
    web.mkdir()
    (web / "stav_aktualni.json").write_text(json.dumps({"aktualizovano": "2026-10-23T20:49:18Z", "kroky": {
        "Nové predikce": "DONE (1 nových)", "Vyhodnocení predikcí": "DONE (2 nových)", "Učení modelu": "DONE (verze 16)"},
        "email": {"detail": [{"day": "2026-10-23", "host": "data.sec.gov", "requests": 3}]}}))
    (web / "stav_zebricek.json").write_text(json.dumps({"h14": {"firmy": [{"ticker": "KE"}, {"ticker": "AB"}]},
                                                        "h6m": {"firmy": [{"ticker": "SATL"}]}}))
    for name, doc in (extra or {}).items():
        (web / f"stav_{name}.json").write_text(json.dumps(doc))
    return web


def test_build_site(tmp_path):
    web = _web(tmp_path)
    out = tmp_path / "site"
    pv = G.build_site(out, web, U(2026, 10, 23, 21, 0), "https://beh", "https://behy", "stin")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>") and "noindex" in html and "function bootWeb" in html
    assert html.index("</style>") < html.index("</head>") < html.index('id="status"') < html.index("</body>")
    assert sorted(pv["dokumenty"]) == ["aktualni", "zebricek"] and (out / "stav_zebricek.json").exists()
    assert json.loads((out / "provoz.json").read_text())["dalsi_aktualizace_do"] == "2026-10-24T17:41+00:00"


def test_build_site_refuses_email(tmp_path):
    web = _web(tmp_path, {"prehled": {"kontakt": "nekdo@example.com"}})
    with pytest.raises(SystemExit, match="e-mailová adresa"):
        G.build_site(tmp_path / "site", web, U(2026, 10, 23, 21, 0), None, None, "stin")


def test_build_site_needs_main_doc(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    with pytest.raises(SystemExit, match="stav_aktualni"):
        G.build_site(tmp_path / "site", web, U(2026, 10, 23, 21, 0), None, None, "stin")


def test_check_dom():
    assert G.check_dom('<div id="status">Aktualizováno 23. 10.</div><script>x="nepodařilo načíst"</script>') == []
    assert len(G.check_dom('<div id="status">Data se nepodařilo načíst.</div>')) == 2
    assert "e-mailová" in " ".join(G.check_dom('<p>Aktualizováno</p><p>a@b.cz</p>'))


def test_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "WEB_DATA", _web(tmp_path))
    s = G.summary("denni")
    assert s["poslat"] and s["title"] == "Radar: denní běh" and s["priority"] == 3
    assert "Žebříček 14 dní: KE, AB" in s["lines"] and "Žebříček 6 měsíců: SATL" in s["lines"]
    monkeypatch.setattr(G, "WEB_DATA", tmp_path / "chybi")
    assert G.summary("tyden")["priority"] == 4


def test_post_without_topic(monkeypatch):
    monkeypatch.delenv("NTFY_TEMA", raising=False)
    assert G.post({"title": "x", "lines": []}) == 0


def test_failure_message(tmp_path):
    log = tmp_path / "beh.txt"
    log.write_text("Kauzální radar BLOKOVÁNO: v cache objevování nejsou ceny akcií", encoding="utf-8")
    m = G.failure_message("denni", "update=success causal=failure rakety=success stranka=success", "https://beh", [log])
    assert m["title"] == "Radar: Denní běh radaru – chyba (kauzální radar)" and m["priority"] == 3
    assert m["lines"][0] == "Nepovedlo se: kauzální radar." and "stránka je obnovená" in m["lines"][1]
    assert any("týdenní objevování" in x for x in m["lines"]) and m["lines"][-1] == "Podrobnosti: https://beh"
    m = G.failure_message("tyden", "objevovani=failure update=success stranka=skipped", "")
    assert m["priority"] == 4 and "poslední úspěšná data" in m["lines"][1] and "objevování" in m["title"]
