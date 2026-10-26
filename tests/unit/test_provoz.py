"""Souběh GitHub × Claude (N-13, 2026-10-26): otisk běhu a srovnání podle předem daných kritérií."""

import json

from stockradar import provoz


def _fp(**kw):
    base = {"den": "2026-10-26", "den_dat": "2026-10-26", "verze": "0.17.3", "model": 17, "kroky_chyba": [],
            "predikce": ["A|ENERGY|2026-10-20"], "vyhodnoceni": ["A|ENERGY|2026-10-20|7|HIT"],
            "karty": ["AAA|2026-10-09|10|1"], "email": 3,
            "zebricky": {h: [f"T{i}" for i in range(10)] for h in provoz.LISTS}}
    base.update(kw)
    return base


def test_same_state_meets_criteria():
    res = provoz.compare(_fp(), _fp(email=0))
    assert res["splneno"] and not res["problemy"] and res["prekryv_top10"]["h14"] == 1.0


def test_missing_evaluations_fail_and_are_listed():
    """24. 10.: GitHub vyhodnotil 0 karet z 9. 10. (ceny jen do 22. 10.) — srovnání to musí ukázat."""
    gh = _fp(karty=[])
    res = provoz.compare(gh, _fp())
    assert not res["splneno"] and res["deterministicke"]["karty"]["jen_claude"] == ["AAA|2026-10-09|10|1"]


def test_ranking_difference_on_other_data_day_is_only_noted():
    other = {h: [f"X{i}" for i in range(10)] for h in provoz.LISTS}
    res = provoz.compare(_fp(den_dat="2026-10-22", zebricky=other), _fp())
    assert not res["stejny_den_dat"] and not res["splneno"]
    assert any("jiný den dat" in p for p in res["problemy"]) and not any("pod 0,6" in p for p in res["problemy"])
    res2 = provoz.compare(_fp(zebricky=other), _fp())
    assert any("pod 0,6" in p for p in res2["problemy"])


def test_fingerprint_from_database(conn, tmp_path):
    (tmp_path / "stav_aktualni.json").write_text(json.dumps({"den_dat": "2026-10-23", "verze_aplikace": "x",
                                                             "model": {"verze": 5}, "kroky": {"Ceny": "CHYBA sítě"}}))
    (tmp_path / "stav_zebricek.json").write_text(json.dumps({"h14": {"firmy": [{"ticker": "AAA"}]}}))
    fp = provoz.fingerprint(conn, tmp_path, day="2026-10-26")
    assert fp["den_dat"] == "2026-10-23" and fp["model"] == 5 and fp["kroky_chyba"] == ["Ceny"]
    assert fp["zebricky"]["h14"] == ["AAA"] and fp["predikce"] == [] and fp["email"] == 0
    md = provoz.report_md(provoz.compare(fp, fp), fp, fp)
    assert "SPLNĚNA" in md or "NESPLNĚNA" in md
