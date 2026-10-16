"""Mnohonásobné testování (návrh N-1, experiment od 2026-10-14): registr všech testů hypotéz + přísné pravidlo.

Proč: role se ověřují při t ≥ 2, ale testů děláme desítky (E1–E4, varianty modelů) → část „objevů“ je náhoda.
Literatura (docs/agent_vyzkum/zdroje.jsonl): Harvey–Liu–Zhu doporučují t > 3; Benjamini–Yekutieli (BY) drží podíl
falešných objevů i při libovolné závislosti testů. Přísné pravidlo: t ≥ 3 A q (BY) ≤ 0,10 v rodině všech evidovaných
testů + testů rolí. Zatím NEROZHODUJE o váze rolí — jen se zapisuje vedle stávajícího pravidla (experiment N-1,
vyhodnocení po 12 týdnech podle živých výsledků rolí).
"""

import json
import math
from pathlib import Path

from stockradar.config import PROJECT_ROOT

REGISTRY = PROJECT_ROOT / "docs" / "testy_hypotez.jsonl"
HLZ_T, Q = 3.0, 0.10


def p_two_sided(t: float) -> float:
    return math.erfc(abs(t) / math.sqrt(2))


def q_values(pvals: list[float], *, dependent: bool = True) -> list[float]:
    """q-hodnoty Benjamini–Hochberg (dependent=False) nebo Benjamini–Yekutieli (libovolná závislost)."""
    m = len(pvals)
    if not m:
        return []
    c = sum(1 / i for i in range(1, m + 1)) if dependent else 1.0
    order = sorted(range(m), key=lambda i: pvals[i])
    q, prev = [0.0] * m, 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, pvals[i] * m * c / rank)
        q[i] = min(prev, 1.0)
    return q


def load_registry(path: Path | None = None) -> list[dict]:
    p = Path(path or REGISTRY)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def strict(rel: dict[str, dict], registry: list[dict] | None = None) -> dict[str, dict]:
    """Přísný pohled na role: t ≥ 3 a q (BY) ≤ 0,10 v rodině všech testů. Role bez t = NEOVĚŘENO."""
    reg = load_registry() if registry is None else registry
    fam = [(f"test:{r['id']}", r["t"]) for r in reg if r.get("t") is not None]
    fam += [(f"role:{k}", v["t"]) for k, v in rel.items() if v.get("t") is not None]
    q_by = q_values([p_two_sided(t) for _, t in fam], dependent=True)
    q_bh = q_values([p_two_sided(t) for _, t in fam], dependent=False)
    qq = {k: (a, b) for (k, _), a, b in zip(fam, q_by, q_bh)}
    out = {}
    for role, v in rel.items():
        t = v.get("t")
        if t is None:
            out[role] = {"stav": "NEOVĚŘENO", "testu": len(fam)}
            continue
        a, b = qq[f"role:{role}"]
        ok = t >= HLZ_T and a <= Q
        out[role] = {"stav": "OVĚŘENO" if ok else ("NEPROŠLO" if v.get("stav") == "OVĚŘENO" else "NEOVĚŘENO"),
                     "t": t, "hlz": t >= HLZ_T, "q_by": round(a, 4), "q_bh": round(b, 4), "testu": len(fam)}
    return out


def smart_money_rows(result: dict, run_id: int, datum: str) -> list[dict]:
    """Všechny t-statistiky jedné studie smart money (`smart_money_runs.result_json`) jako řádky registru.
    Pravidlo dané předem (2026-10-15): bere se KAŽDÁ skupina s t (pole `t` nebo `t_mesice`), bez výběru podle výsledku;
    nezávislé jednotky = měsíce. Jde o průzkumné testy (predem = False), i když z nich vyšla ověřená role."""
    rows: list[dict] = []

    def add(section: str, group: str, d: dict) -> None:
        t = d.get("t", d.get("t_mesice"))
        if not isinstance(t, (int, float)):
            return
        rows.append({"id": f"SM{run_id}-{len(rows) + 1:04d}", "datum": datum, "experiment": f"Smart money (studie #{run_id})",
                     "skupina": f"{section}: {group}", "n_nezavislych": d.get("mesicu"), "t": t, "predem": False,
                     "hlavni": False, "zdroj": f"smart_money_runs #{run_id}"})

    for section in ("insideri", "po_zverejneni", "podily", "buybacky", "politici"):
        for group, by_h in (result.get(section) or {}).items():
            for h, d in (by_h or {}).items():
                if isinstance(d, dict):
                    add(section, f"{group} / {h}", d)
    for year, d in (result.get("insider_po_letech") or {}).items():
        add("insider_po_letech", year, d)
    for d in result.get("politici_osoby") or []:
        add("politici_osoby", d.get("osoba", "?"), d)
    for d in result.get("politici_sektory") or []:
        add("politici_sektory", d.get("sektor", "?"), d)
    for period, items in (result.get("aktivni_vs_pasivni") or {}).items():
        for d in items or []:
            add(f"aktivni_vs_pasivni/{period}", f"{d.get('situace')} · {d.get('skupina')} / {d.get('horizont')}", d)
    return rows


def model_evaluation_rows(evaluations: list[dict], datum: str, *, skip: set[tuple[int, str]] = frozenset()) -> list[dict]:
    """Všechny t-statistiky vyhodnocení modelů (`model_evaluations`) jako řádky registru. Pravidlo dané předem
    (2026-10-16): každá t ve metrikách; u opakovaného vyhodnocení téhož (model, konfigurace, období) jen poslední
    (novější data nahrazují starší, nejde o novou hypotézu); `skip` = (id vyhodnocení, cesta) už evidované jinde."""
    latest: dict[tuple, dict] = {}
    for e in sorted(evaluations, key=lambda e: e["id"]):
        latest[(e["model_name"], e["config_hash"], e["split"])] = e
    rows: list[dict] = []
    for e in sorted(latest.values(), key=lambda e: e["id"]):
        found: list[tuple[str, float]] = []

        def walk(o, path: str) -> None:
            if isinstance(o, dict):
                for k, v in o.items():
                    if (k == "t" or k.startswith("t_")) and isinstance(v, (int, float)):
                        found.append((path + k, v))
                    else:
                        walk(v, path + k + ".")
        walk(e["metrics"], "")
        for path, t in found:
            if (e["id"], path) in skip:
                continue
            rows.append({"id": f"ME{e['id']}-{len(rows) + 1:04d}", "datum": datum,
                         "experiment": f"{e['model_name']} ({e['config_hash'][:8]}, {e['split']})", "skupina": path,
                         "n_nezavislych": e.get("n_independent"), "t": t, "predem": e["split"] == "LOCKED_TEST",
                         "hlavni": False, "zdroj": f"model_evaluations #{e['id']}"})
    return rows
