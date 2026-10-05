"""XTB: převod symbolů, rozpoznání akcie / CFD / mimo nabídku, cache a výběr žebříčku jen z nabídky XTB (bez sítě)."""

import sqlite3
import urllib.error
from datetime import timedelta

from stockradar.signals import run
from stockradar.sources import xtb
from stockradar.timeutil import parse_iso


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def test_symbol_mapping():
    assert xtb.xtb_symbol("VST") == "VST.US"
    assert xtb.xtb_symbol("RR.L") == "RR.UK"
    assert xtb.xtb_symbol("NKT.CO") == "NKT.DK"
    assert xtb.xtb_symbol("FRO.OL") == "FRO.NO"
    assert xtb.xtb_symbol("BRK-B") == "BRKB.US"
    for foreign in ("PDI.AX", "8338.T", "010950.KS", "HPS-A.TO"):     # burzy, které XTB nenabízí
        assert xtb.xtb_symbol(foreign) is None


def test_classify_stock_cfd_and_other_exchange():
    items = [{"symbol": "KMX.US", "typeSlug": "cashstocks", "name": "CarMax Inc", "currencyCode": "USD"},
             {"symbol": "KMX.US", "typeSlug": "shares", "name": "CarMax Inc"},
             {"symbol": "VSTS.US", "typeSlug": "shares", "name": "Vestis"}]
    assert xtb.classify(items, "KMX.US", None)["status"] == "AKCIE"
    assert xtb.classify(items[1:], "KMX.US", None)["status"] == "CFD"            # jen CFD → do žebříčku ne
    assert xtb.classify(items, "VST.US", None)["status"] == "NE"                 # podobný symbol nestačí
    lasertec = [{"symbol": "6K8.DE", "typeSlug": "cashstocks", "name": "Lasertec Corp", "currencyCode": "EUR"}]
    r = xtb.classify(lasertec, None, "Lasertec Corporation")
    assert r["status"] == "AKCIE" and r["xtb_symbol"] == "6K8.DE" and r["other_exchange"] == 1
    metals = [{"symbol": "ACG.UK", "typeSlug": "cashstocks", "name": "ACG Metals Ltd"}]
    assert xtb.classify(metals, None, "Metals X Limited")["status"] == "NE"     # jiná firma se stejným slovem


def test_checker_caches_and_stops_after_network_errors():
    calls = []

    def search(q):
        calls.append(q)
        return [{"symbol": "VST.US", "typeSlug": "cashstocks", "name": "Vistra Corp", "currencyCode": "USD"}]

    conn = _conn()
    ch = xtb.Checker(conn, search=search, pause=0)
    assert ch.tradable("VST") and ch.check("VST")["xtb_symbol"] == "VST.US"
    assert calls == ["VST.US"] and ch.cached == 1                                 # druhý dotaz z cache
    assert not ch.tradable("PDI.AX", "Pdi Gold Limited")                          # jméno nenalezeno → NE
    later = xtb.Checker(conn, search=search, pause=0, now=parse_iso(ch.check("VST")["checked_at"]) + timedelta(days=31))
    later.check("VST")
    assert later.requests == 1                                                    # po 30 dnech se ověří znovu

    def broken(q):
        raise urllib.error.URLError("down")

    bad = xtb.Checker(_conn(), search=broken, pause=0)
    assert all(bad.check(f"X{i}") is None for i in range(7))
    assert bad.down and bad.requests == 5                                         # po 5 chybách už nezkouší
    assert bad.summary()["nedostupne"]


def test_name_fallback_finds_listing_under_other_symbol_or_exchange():
    offer = {"frontline": [{"symbol": "FRO.NO", "typeSlug": "cashstocks", "name": "Frontline Ltd", "currencyCode": "NOK"}],
             "tsakos energy navigation": [{"symbol": "TEN1.US", "typeSlug": "cashstocks",
                                           "name": "Tsakos Energy Navigation Ltd", "currencyCode": "USD"}]}
    ch = xtb.Checker(_conn(), search=lambda q: offer.get(q, []), pause=0)
    fro = ch.check("FRO", "Frontline Plc Ordinary Shares")                        # FRO.US XTB nemá, FRO.NO ano
    assert fro["status"] == "AKCIE" and fro["xtb_symbol"] == "FRO.NO" and fro["other_exchange"] == 1
    ten = ch.check("TEN", "Tsakos Energy Navigation Ltd Common Shares")            # stejná burza, jiný symbol
    assert ten["xtb_symbol"] == "TEN1.US" and ten["other_exchange"] == 0
    assert ch.check("EOLS", "Evolus Inc. Common Stock")["status"] == "NE" and ch.requests == 6


def test_ranking_takes_first_twenty_offered_by_xtb():
    ordered = [{"sym": s} for s in ("A", "B", "C", "D", "E")]
    offer = {"A": "NE", "B": "AKCIE", "C": "CFD", "E": "AKCIE"}                   # D nejde ověřit
    check = lambda s, n: {"status": offer[s]} if s in offer else None
    top, info = run.pick_tradable(ordered, check, lambda x: None, 2)
    assert [x["sym"] for x in top] == ["B", "E"] and [x["poradi_celkem"] for x in top] == [2, 5]
    assert info["preskoceno"] == {"NE": 1, "CFD": 1, "NEOVĚŘENO": 1}
    top, info = run.pick_tradable(ordered, None, lambda x: None, 2)
    assert [x["sym"] for x in top] == ["A", "B"] and not info["kontrola"]


def test_two_listings_of_one_company_are_one_row():
    rows = [{"ticker": "HBM.TO", "xtb": {"symbol": "HBM.US"}}, {"ticker": "ERO.TO", "xtb": {"symbol": "ERO.US"}},
            {"ticker": "HBM", "xtb": {"symbol": "HBM.US"}}, {"ticker": "X", "xtb": None}, {"ticker": "Y"}]
    assert [r["ticker"] for r in xtb.unique_listing(rows)] == ["HBM.TO", "ERO.TO", "X", "Y"]   # bez XTB se neslučuje
