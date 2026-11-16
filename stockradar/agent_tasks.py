"""N-22 (v0.17.22, zadání 2026-10-13 + Anthropic, harness pro dlouho běžící agenty Z-20261106-1): evidence slíbených
jednorázových úkolů s termínem. Rutiny smí měnit jen `stav` a `poznamka`, ne zadání. diag hlásí VAROVÁNÍ u úkolu po
termínu. Důvod: N-20 bylo slíbeno „během týdne“ a odložilo se pětkrát, aniž by na to cokoli upozornilo."""

import json
from datetime import date
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "docs" / "agent_vyzkum" / "ukoly.json"
STAVY = {"OTEVRENO", "HOTOVO", "ZRUSENO"}
POLE = ("id", "zadano", "termin", "popis", "hotovo_kdyz", "stav")


def load(path: Path = PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["ukoly"]


def overdue(tasks: list[dict], today: date) -> list[dict]:
    """Otevřené úkoly po termínu, nejstarší první: [{id, popis, termin, dni_po_terminu}]."""
    out = []
    for t in tasks:
        if t.get("stav") == "OTEVRENO" and t.get("termin") and date.fromisoformat(t["termin"]) < today:
            out.append({"id": t["id"], "popis": t["popis"], "termin": t["termin"],
                        "dni_po_terminu": (today - date.fromisoformat(t["termin"])).days})
    return sorted(out, key=lambda x: -x["dni_po_terminu"])


def due_soon(tasks: list[dict], today: date, days: int = 7) -> list[dict]:
    return sorted((t for t in tasks if t.get("stav") == "OTEVRENO" and t.get("termin")
                   and 0 <= (date.fromisoformat(t["termin"]) - today).days <= days), key=lambda t: t["termin"])
