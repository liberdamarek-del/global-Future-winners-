"""Experiment N-5 (2026-10-19): živá kalibrace karet a pokrytí intervalu q20–q80, statický × ACI (bez pohledu do budoucnosti)."""

import pytest

from stockradar.signals import calibration as C


def _item(week, p, up, ret, base=0.1, med=0.0, q20=-0.05, q80=0.05):
    return {"model": "M", "tyden": week, "p_up": p, "up": up, "zaklad_up": base, "ret": ret, "med": med, "q20": q20, "q80": q80}


def test_reliability_brier_skill_and_bins():
    items = [_item(1, 0.3, 1, 0.0), _item(1, 0.3, 0, 0.0), _item(1, 0.05, 0, 0.0)]
    r = C.reliability(items)
    assert r["karet"] == 3 and r["brier"] == pytest.approx((0.49 + 0.09 + 0.0025) / 3, abs=1e-4)
    assert r["brier_zaklad"] == pytest.approx((0.81 + 0.01 + 0.01) / 3, abs=1e-4)
    assert [b["kos"] for b in r["tabulka"]] == ["0–10 %", "30–40 %"] and r["tabulka"][1]["skutecnost"] == 0.5


def test_aci_widens_after_undercoverage_using_only_past_weeks():
    # týden 1: všechny výnosy dvakrát dál než polovina intervalu → statický interval nepokryje nic
    wk1 = [_item(1, 0.3, 0, 0.10) for _ in range(20)]
    wk2 = [_item(2, 0.3, 0, 0.08) for _ in range(20)]
    c = C.coverage(wk1 + wk2)
    assert c["tydny"][0]["kvantil"] == 1.0 and c["tydny"][0]["pokryti_aci"] == 0.0     # 1. týden: bez minulosti = statický
    assert c["tydny"][1]["kvantil"] == pytest.approx(2.0) and c["tydny"][1]["pokryti_aci"] == 1.0   # z týdne 1 → širší
    assert c["pokryti_staticke"] == 0.0 and c["odchylka_aci"] < c["odchylka_staticka"]
    assert c["tydny"][1]["alfa"] < c["tydny"][0]["alfa"]                                  # málo pokrytí → menší α
