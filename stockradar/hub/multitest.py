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
