"""Evidence výzkumu agenta (docs/agent_vyzkum): povinná pole, výčty, žádná opakovaná zjištění (zadání 2026-10-13)."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "docs" / "agent_vyzkum"
ZRALOST = {"PRAXE", "VYZKUM", "HYPOTEZA"}
DUVERA = {"VYSOKA", "STREDNI", "NIZKA"}
TYP = {"CLANEK_RECENZOVANY", "PREPRINT", "DOKUMENTACE", "OPEN_SOURCE", "BLOG", "DISKUSE"}
STAV_NAVRHU = {"NAVRZENO", "EXPERIMENT", "ZAVEDENO", "ZAMITNUTO", "ODLOZENO"}
STAV_SMERU = {"AKTIVNI", "UTLUMENY", "UZAVRENY"}
DATUM = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def _jsonl(name: str) -> list[dict]:
    text = (ROOT / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_directions_are_valid():
    d = json.loads((ROOT / "smery.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in d["smery"]]
    assert len(ids) == len(set(ids))
    for s in d["smery"]:
        assert 0 <= s["priorita"] <= 1 and s["stav"] in STAV_SMERU and s["behu"] >= 0 and s["prazdnych_behu_po_sobe"] >= 0
        assert s["nazev"] and s["proc_pro_nas"]


def test_findings_have_source_date_maturity_and_are_not_repeated():
    smery = {s["id"] for s in json.loads((ROOT / "smery.json").read_text(encoding="utf-8"))["smery"]}
    seen_url, seen_key, ids = set(), set(), set()
    for z in _jsonl("zdroje.jsonl"):
        for k in ("id", "beh", "smer", "klic", "nazev", "url", "datum_zdroje", "typ_zdroje", "zjisteni", "zralost",
                  "duveryhodnost", "duvod_duvery", "vyuziti", "overeno_primarnim_zdrojem"):
            assert k in z, f"{z.get('id')}: chybí {k}"
        assert z["id"] not in ids and z["smer"] in smery
        assert z["url"].startswith("https://") and DATUM.match(z["datum_zdroje"]) and DATUM.match(z["beh"])
        assert z["zralost"] in ZRALOST and z["duveryhodnost"] in DUVERA and z["typ_zdroje"] in TYP
        assert z["url"] not in seen_url, f"opakované zjištění (stejná URL): {z['url']}"
        assert z["klic"] not in seen_key, f"opakovaná myšlenka: {z['klic']}"
        ids.add(z["id"]); seen_url.add(z["url"]); seen_key.add(z["klic"])


def test_proposals_are_complete_and_status_changes_refer_to_them():
    full = {}
    for n in _jsonl("navrhy.jsonl"):
        assert n["stav"] in STAV_NAVRHU and DATUM.match(n["datum"])
        if n["id"] not in full:
            for k in ("nazev", "klic", "zdroje", "problem", "implementace", "naklady", "rizika", "zavislosti", "metrika",
                      "experiment", "priorita"):
                assert k in n and n[k] not in (None, ""), f"{n['id']}: chybí {k}"
            full[n["id"]] = n
        else:
            assert n.get("duvod"), f"{n['id']}: změna stavu bez důvodu"


KONTROLA_OD = "2026-11-12"          # N-30: poučení #32, #35, #36 — tři předem daná kritéria za 9 dní měřila něco jiného
KONTROLA_OTAZKY = ("trend_nebo_sum", "presnost_a_zachyt", "vzorek_odpovida_nasazeni")


def test_new_proposals_answer_the_criterion_checklist():
    """Návrh zapsaný od 12. 11. 2026 musí mít `kontrola_kriteria` s odpovědí na tři otázky (procedurální paměť jako
    kontrola v kódu, ne jen poučení v textu — ExpeL Z-20261107-2, Voyager Z-20261112-2)."""
    seen = set()
    for n in _jsonl("navrhy.jsonl"):
        first = n["id"] not in seen
        seen.add(n["id"])
        if first and n["datum"] >= KONTROLA_OD:
            k = n.get("kontrola_kriteria") or {}
            for q in KONTROLA_OTAZKY:
                assert len(str(k.get(q) or "").strip()) >= 15, f"{n['id']}: kontrola_kriteria.{q} chybí nebo je prázdná"
