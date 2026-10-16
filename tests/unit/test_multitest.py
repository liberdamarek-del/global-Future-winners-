"""Experiment N-1 (2026-10-14): registr testů hypotéz a přísné pravidlo (t ≥ 3 a Benjamini–Yekutieli q ≤ 0,10)."""

import json

import pytest

from stockradar.hub import multitest as M


def test_p_and_q_values():
    assert M.p_two_sided(1.96) == pytest.approx(0.05, abs=1e-3)
    q_bh = M.q_values([0.01, 0.04, 0.03, 0.5], dependent=False)
    assert q_bh == pytest.approx([0.04, 0.0533, 0.0533, 0.5], abs=1e-3)               # ruční výpočet BH pro m = 4
    q_by = M.q_values([0.01, 0.04, 0.03, 0.5], dependent=True)
    assert all(b >= a for a, b in zip(q_bh, q_by))                        # BY je vždy přísnější


def test_strict_rule_flags_weak_verified_role():
    rel = {"A": {"t": 3.98, "stav": "OVĚŘENO"}, "B": {"t": 2.56, "stav": "OVĚŘENO"}, "C": {"t": 0.5, "stav": "NEOVĚŘENO"},
           "D": {"t": None, "stav": "NEOVĚŘENO"}}
    reg = [{"id": f"x{i}", "t": t} for i, t in enumerate([0.3, -0.4, 1.1, 3.4, 2.7, -1.5])]
    s = M.strict(rel, reg)
    assert s["A"]["stav"] == "OVĚŘENO" and s["B"]["stav"] == "NEPROŠLO" and s["C"]["stav"] == "NEOVĚŘENO"
    assert s["D"] == {"stav": "NEOVĚŘENO", "testu": 9}


def test_registry_file_is_valid():
    reg = M.load_registry()
    assert reg and len({r["id"] for r in reg}) == len(reg)
    for r in reg:
        assert {"id", "datum", "experiment", "skupina", "t", "predem", "hlavni", "zdroj"} <= set(r)
        assert isinstance(r["predem"], bool) and isinstance(r["hlavni"], bool)


def test_smart_money_rows_take_every_group_with_t():
    res = {"insideri": {"Insider: nákup": {"1m": {"mesicu": 53, "t_mesice": 2.1}, "6m": {"mesicu": 53, "t_mesice": None}}},
           "politici_osoby": [{"osoba": "X", "mesicu": 4, "t_mesice": 1.98}],
           "aktivni_vs_pasivni": {"uceni": [{"situace": "vše", "skupina": "aktivní", "horizont": "6m", "mesicu": 38, "t": 3.23}]},
           "zpozdeni_zverejneni": {"INSIDER": {"median_dni": 2}}}
    rows = M.smart_money_rows(res, 4, "2026-10-15")
    assert [r["t"] for r in rows] == [2.1, 1.98, 3.23] and len({r["id"] for r in rows}) == 3
    assert all(r["predem"] is False and r["hlavni"] is False and r["zdroj"] == "smart_money_runs #4" for r in rows)


def test_model_evaluation_rows_keep_latest_rerun_and_skip_registered():
    ev = [{"id": 3, "model_name": "M", "config_hash": "abc12345", "split": "POST", "n_independent": 10,
           "metrics": {"horni_desetina": {"t": 1.0}}},
          {"id": 11, "model_name": "M", "config_hash": "abc12345", "split": "POST", "n_independent": 12,
           "metrics": {"horni_desetina": {"t": 1.1}, "rezim": {"A": {"t": -2.0}}}},
          {"id": 14, "model_name": "E1", "config_hash": "def67890", "split": "LOCKED_TEST", "n_independent": 7,
           "metrics": {"R0": {"t": 0.4}, "R10": {"t": 0.5}}}]
    rows = M.model_evaluation_rows(ev, "2026-10-16", skip={(14, "R0.t")})
    assert [(r["zdroj"], r["skupina"], r["t"]) for r in rows] == [
        ("model_evaluations #11", "horni_desetina.t", 1.1), ("model_evaluations #11", "rezim.A.t", -2.0),
        ("model_evaluations #14", "R10.t", 0.5)]
    assert rows[-1]["predem"] is True and rows[0]["predem"] is False
