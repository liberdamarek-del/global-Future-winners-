"""Orchestrace signálů (signals/run.py): výběr přes XTB, pravidla řazení, varování trhu, katalyzátory, čištění JSON."""

import json
import math
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from stockradar.catalysts import add_catalyst
from stockradar.signals import run
from tests.conftest import NOW


def item(sym, up=0.3, down=0.2, raw=0.5):
    return {"sym": sym, "pred": {"up5": up, "down5": down, "dir": up - down, "raw": {"up5": raw}}}


def test_pick_tradable_without_check_keeps_model_order():
    xs = [item(s) for s in "ABCD"]
    top, info = run.pick_tradable(xs, None, lambda x: x["sym"], 2)
    assert [x["sym"] for x in top] == ["A", "B"] and info == {"kontrola": False}
    assert [x["poradi_celkem"] for x in xs] == [1, 2, 3, 4]


def test_pick_tradable_skips_non_shares_and_keeps_overall_rank():
    status = {"A": "CFD", "B": "AKCIE", "C": None, "D": "NE", "E": "AKCIE", "F": "AKCIE"}
    calls = []

    def check(sym, name):
        calls.append(sym)
        return {"status": status[sym]} if status[sym] else None

    xs = [item(s) for s in "ABCDEF"]
    top, info = run.pick_tradable(xs, check, lambda x: x["sym"].lower(), 2)
    assert [x["sym"] for x in top] == ["B", "E"]
    assert [x["poradi_celkem"] for x in top] == [2, 5]          # pořadí v celém modelu, ne v nabídce XTB
    assert top[0]["xtb_row"] == {"status": "AKCIE"}
    assert calls == list("ABCDE")                                # po naplnění se dál nekontroluje
    assert info == {"kontrola": True, "prohledano": 5, "vybrano": 2, "preskoceno": {"NE": 1, "CFD": 1, "NEOVĚŘENO": 1}}


def test_pick_tradable_respects_check_limit_and_sublist_rank():
    xs = [item(s) for s in "ABCDE"]
    run.pick_tradable(xs, None, lambda x: x["sym"], 5)
    sub = [xs[3], xs[1]]                                        # podseznam (velké firmy) si nese původní pořadí
    top, info = run.pick_tradable(sub, lambda s, n: {"status": "AKCIE"}, lambda x: x["sym"], 5, max_checks=1)
    assert [x["sym"] for x in top] == ["D"] and info["prohledano"] == 1
    assert top[0]["poradi_celkem"] == 4


def test_six_month_rank_uses_up_probability_then_raw_score():
    xs = [item("A", up=0.2, raw=0.9), item("B", up=0.3, raw=0.1), item("C", up=0.3, raw=0.5)]
    assert [x["sym"] for x in sorted(xs, key=run.rank_key_up, reverse=True)] == ["C", "B", "A"]


def test_market_warning():
    base = {"up5": 0.30, "down5": 0.25}
    assert run.market_warning(None, base) == "NEOVĚŘENO"
    assert "vyšší riziko poklesu" in run.market_warning({"up5": 0.30, "down5": 0.33}, base)
    assert "vyšší šanci na růst" in run.market_warning({"up5": 0.36, "down5": 0.25}, base)
    assert run.market_warning({"up5": 0.32, "down5": 0.27}, base) == "trh bez výrazného plošného posunu"
    # oba posuny velké → rozhoduje větší
    assert "riziko poklesu" in run.market_warning({"up5": 0.36, "down5": 0.33}, base)


def test_clean_replaces_non_finite_values_recursively():
    obj = {"a": float("nan"), 1: [float("inf"), 1.5, (2, -math.inf)], "b": {"c": "x", "d": None}}
    out = run.clean(obj)
    assert out == {"a": None, "1": [None, 1.5, [2, None]], "b": {"c": "x", "d": None}}
    json.dumps(out, allow_nan=False)


def test_smart_money_top_from_latest_run(conn):
    assert run.smart_money_top(conn) == {}
    for top in ([{"ticker": "OLD", "skore": 1, "verdikt": "NÍZKÁ", "funkce": "CEO", "zverejneno": "2026-09-01"}],
                [{"ticker": "NEW", "skore": 80, "verdikt": "VYSOKÁ", "funkce": "CFO", "zverejneno": "2026-10-01"}]):
        conn.execute("INSERT INTO smart_money_runs (run_at, data_through, result_json, app_version) VALUES (?, ?, ?, 't')",
                     ("2026-10-01T00:00:00Z", "2026-10-01", json.dumps({"aktualni": {"top": top}})))
    assert run.smart_money_top(conn) == {"NEW": {"skore": 80, "verdikt": "VYSOKÁ", "kdo": "CFO", "zverejneno": "2026-10-01"}}


class FakeFund:
    def __init__(self, cik=None, reports=(), trials=()):
        self.cik = {"TBIO": cik} if cik else {}
        self.filings = {cik: {"REPORT": list(reports)}} if cik else {}
        self.trials = list(trials)

    def upcoming_trials(self, cache_conn, sym, today, horizon):
        assert horizon == 90
        return self.trials


def test_catalysts_from_filings_trials_and_database(conn, listing):
    company_id, listing_id = listing
    conn.execute("UPDATE listings SET yahoo_symbol = 'TBIO' WHERE id = ?", (listing_id,))
    add_catalyst(conn, company_id, "FDA_DECISION", "rozhodnutí FDA", date_status="ESTIMATED",
                 window=("2026-11-01", "2026-11-30"), source="test", source_url="https://example.com/fda",
                 published_at=NOW - timedelta(days=1))
    today = date(2026, 10, 2).toordinal()
    last_report = today - 200                                   # okno +80…+100 dní se posouvá o čtvrtletí do budoucna
    fund = FakeFund(cik=1, reports=[last_report - 91, last_report, today + 5],
                    trials=[{"phase": "PHASE3", "pcd": "2026-10-20", "pcd_type": "ESTIMATED", "nct": "NCT1"},
                            {"phase": "PHASE2", "pcd": "2026-12", "pcd_type": None, "nct": "NCT2"}])
    cats = run.catalysts_for("TBIO", fund, None, conn, today)
    assert [c["typ"] for c in cats] == ["klinická studie PHASE3", "výsledky (10-Q/10-K)", "klinická studie PHASE2",
                                        "rozhodnutí FDA"]
    rep = cats[1]
    assert rep["okno"] == f"{date.fromordinal(last_report + 262)} … {date.fromordinal(last_report + 282)}"
    assert rep["dni_do"] == last_report + 262 - today and rep["jistota"] == "ESTIMATED"
    assert cats[0]["dni_do"] == 18 and cats[2]["dni_do"] == date(2026, 12, 15).toordinal() - today
    db = cats[3]
    assert db["okno"] == "2026-11-01 … 2026-11-30" and db["duvera"] == 60 and db["dni_do"] is None


def test_catalysts_without_any_source_is_empty(conn):
    assert run.catalysts_for("NONE", FakeFund(), None, conn, date(2026, 10, 2).toordinal()) == []


def _panel(n, gap, ex):
    day0 = date(2024, 1, 1).toordinal()
    return SimpleNamespace(cols={"gap": [gap(k) for k in range(n)]}, ex_sec=[ex(k) for k in range(n)],
                           day=[day0 + 7 * (k % 60) for k in range(n)], group=[f"g{k % 7}" for k in range(n)])


def test_gap_evidence_needs_enough_rows():
    p = _panel(400, lambda k: float(k), lambda k: 0.0)
    assert run.gap_evidence(p, list(range(400))) == {"n": 400}


def test_gap_evidence_top_fifth_beats_bottom_and_ignores_nan():
    nan = float("nan")
    p = _panel(1000, lambda k: nan if k % 50 == 0 else float(k), lambda k: k / 1000 + (0.01 if k % 2 else -0.01))
    res = run.gap_evidence(p, list(range(1000)))
    assert res["n"] == 980                                      # řádky s NaN se vynechají
    assert res["horni_petina_nad_oborem"] > res["dolni_petina_nad_oborem"]
    assert res["t_horni"] > 3 and res["sum"] < 0.01
    assert res["nezavislych"] == len({(p.day[k] // 7, p.group[k]) for k in range(1000) if k % 50})


@pytest.mark.parametrize("name", run.MODELS)
def test_models_have_specs(name):
    from stockradar.signals import model as M
    spec = M.SPECS[name]
    assert {"h", "up", "down", "big", "nazev"} <= set(spec)
