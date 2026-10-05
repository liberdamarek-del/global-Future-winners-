"""Smart money: parsování primárních zdrojů, rozlišení typů transakcí, event study, verdikt (bez sítě)."""

import io
import random
import zipfile
from array import array
from datetime import date, timedelta

import pytest

from stockradar.discovery import study
from stockradar.discovery.cache import Bars
from stockradar.discovery.features import prepare
from stockradar.smartmoney import analysis, current, events, groups, sources, store


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def test_insider_dataset_keeps_purchases_awards_exercises_and_plan_flag():
    sub = ("ACCESSION_NUMBER\tFILING_DATE\tPERIOD_OF_REPORT\tDOCUMENT_TYPE\tISSUERCIK\tISSUERNAME\tISSUERTRADINGSYMBOL\tAFF10B5ONE\n"
           "A1\t05-JAN-2025\t03-JAN-2025\t4\t0000000001\tAcme Inc\tACME\t\n"
           "A2\t06-JAN-2025\t03-JAN-2025\t4\t0000000001\tAcme Inc\tACME\t1\n"
           "A3\t06-JAN-2025\t03-JAN-2025\t4\t0000000001\tAcme Inc\tACME\t\n")
    own = ("ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP\tRPTOWNER_TITLE\n"
           "A1\t0000000009\tDoe Jane\tDirector,Officer\tChief Financial Officer\n"
           "A2\t0000000008\tRoe Rick\tOfficer\tCEO\n"
           "A3\t0000000007\tPoe Pat\tDirector\t\n")
    tx = ("ACCESSION_NUMBER\tNONDERIV_TRANS_SK\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\t"
          "TRANS_ACQUIRED_DISP_CD\tSHRS_OWND_FOLWNG_TRANS\tDIRECT_INDIRECT_OWNERSHIP\n"
          "A1\t1\t03-JAN-2025\tP\t1000\t10.5\tA\t5000\tD\n"
          "A1\t2\t03-JAN-2025\tS\t100\t11\tD\t4900\tD\n"
          "A2\t3\t03-JAN-2025\tP\t500\t10\tA\t900\tD\n"
          "A2\t4\t03-JAN-2025\tA\t200\t0\tA\t1100\tD\n"
          "A3\t5\t03-JAN-2025\tS\t300\t11\tD\t0\tD\n")
    rows = sources.parse_insider_zip(_zip({"SUBMISSION.tsv": sub, "REPORTINGOWNER.tsv": own, "NONDERIV_TRANS.tsv": tx}))
    by = {(r[0], r[1]): r for r in rows}
    # prodej se ukládá jen u toho, kdo tutéž firmu koupil (pozná se „koupil a hned prodal“)
    assert set(by) == {("A1", 1), ("A1", 2), ("A2", 3), ("A2", 4)}
    a1 = by[("A1", 1)]
    assert a1[2] == "2025-01-05" and a1[5] == "ACME" and a1[9] == "Director,Officer" and a1[11] == "P" and a1[17] == 0
    assert by[("A2", 3)][17] == 1
    assert analysis.classify_insider("P", 0, 10.5) == "AKTIVNÍ NÁKUP"
    assert analysis.classify_insider("P", 1, 10.0) == "AUTOMATICKÝ"
    assert analysis.classify_insider("A", 0, 0) == "PASIVNÍ"
    assert analysis.classify_insider("P", 0, 0) == "NEJASNÉ"
    assert analysis.classify_insider("P", 0, 10.5, sold_soon=100, shares=1000) == "AKTIVNÍ NÁKUP"
    assert analysis.classify_insider("P", 0, 10.5, sold_soon=600, shares=1000) == "NEJASNÉ (hned prodáno)"
    sales = {(9, 1): [(date(2025, 1, 10).toordinal(), 600.0), (date(2025, 2, 20).toordinal(), 900.0)]}
    assert analysis.sold_within(sales, 9, 1, date(2025, 1, 3).toordinal()) == 600.0   # prodej v únoru se nepočítá


def test_form4_type_detects_espp_flip_and_discount():
    def v(txs, plan=False):
        return {"plan10b51": plan, "transakce": [{"code": c, "date": d, "shares": n, "price": p} for c, d, n, p in txs]}
    # WIX 2026-08-31: koupeno 479 ks za 59,89 při tržní ceně 88,25 a druhý den vše prodáno
    wix = v([("P", "2026-08-31", 479.0, 59.89), ("S", "2026-09-01", 479.0, 95.0)])
    assert current.form4_type(wix, 88.25) == "NEJASNÉ (hned prodáno)"
    assert current.form4_type(v([("P", "2026-08-31", 479.0, 59.89)]), 88.25).startswith("PASIVNÍ")
    assert current.form4_type(v([("P", "2026-08-31", 1000.0, 87.9)]), 88.25) == "AKTIVNÍ NÁKUP"
    assert current.form4_type(v([("P", "2026-08-31", 1000.0, 87.9)], plan=True)) == "AUTOMATICKÝ"
    assert current.form4_type(v([("A", "2026-08-31", 1000.0, 0.0)])) == "NEJASNÉ"


HOUSE_TEXT = """
          SP          Alphabet Inc. - Class A Common           P                 01/14/2025 01/14/2025           $250,001 -
                      Stock (GOOGL) [OP]                                                                         $500,000
                      F      S      : New
                      D           : Purchased 50 call options with a strike price of $150 and an expiration date of 1/16/26.
          SP         NVIDIA Corporation (NVDA) [ST]          P                 06/17/2022 06/17/2022             $1,000,001 -
                     FIlINg STATuS: New
                     DESCRIPTION: Exercised 200 call options (20,000 shares).
                                                                                                                 $5,000,000
          SP         Apple Inc. (AAPl) [ST]                  S (partial)       12/31/2024 12/31/2024             $5,000,001 -
                                                                                                                 $25,000,000
"""


def test_house_ptr_parsing_and_classification():
    rows = sources.parse_house_ptr(HOUSE_TEXT)
    assert [(r["ticker"], r["asset_type"], r["tx_type"], r["tx_date"]) for r in rows] == [
        ("GOOGL", "OP", "P", "2025-01-14"), ("NVDA", "ST", "P", "2022-06-17"), ("AAPL", "ST", "S (partial)", "2024-12-31")]
    assert rows[0]["owner"] == "SP" and rows[0]["amount_min"] == 250001 and rows[0]["amount_max"] == 500000
    assert analysis.classify_congress("P", rows[0]["description"]) == "AKTIVNÍ NÁKUP"
    assert analysis.classify_congress("P", rows[1]["description"]) == "PASIVNÍ"      # uplatnění opce
    assert analysis.classify_congress("S (partial)", None) == "PRODEJ"
    assert analysis.classify_congress("P", "Dividend reinvestment") == "AUTOMATICKÝ"


def test_senate_ptr_parsing():
    page = ("<table><tbody><tr><td>1</td><td>09/04/2026</td><td>Spouse</td><td><a>JPM</a></td><td>JP Morgan Chase</td>"
            "<td>Stock</td><td>Purchase</td><td>$15,001 - $50,000</td><td>--</td></tr></tbody></table>")
    r = sources.parse_senate_ptr(page)[0]
    assert (r["ticker"], r["tx_type"], r["asset_type"], r["amount_min"], r["amount_max"]) == ("JPM", "P", "ST", 15001, 50000)


def _market(n_stocks=12, days=520, seed=3):
    rng = random.Random(seed)
    start = date(2023, 1, 2).toordinal()
    secs = {}
    for k in range(n_stocks):
        closes, p = [], 10.0
        for _ in range(days):
            p *= 1 + rng.gauss(0.0005, 0.02)
            closes.append(p)
        bars = Bars(f"S{k}", "USD", array("i", range(start, start + days)), array("d", closes), array("d", [1e6] * days))
        secs[f"S{k}"] = study.Sec(f"S{k}", {"industry": "Tech", "sector": "Tech"}, prepare(bars, start), "USD", "tech")
    data = study.Data(secs, {}, start, start + days - 1)
    spy_days = list(range(start, start + days))
    return events.Market(data, spy_days, [100 * (1.0003 ** i) for i in range(days)])


def test_event_study_measures_from_first_close_after_publication():
    m = _market()
    pub = m.data.data_start + 200
    ev = events.Event("S1", pub, pub - 2, groups.ACTIVE, {"value": 1e5})
    r = events.measure(m, ev)
    c = m.data.secs["S1"].prep.bars.closes
    assert r["entry"] == study.day_str(pub + 1)  # vstup až den PO zveřejnění
    assert r["ret"]["1m"] == pytest.approx(c[201 + 21] / c[201] - 1)
    assert r["ex_ctrl_1m"] is not None and r["ex_spy_1m"] is not None
    rows = [events.measure(m, events.Event(f"S{k}", m.data.data_start + 150 + 7 * k, None, groups.ACTIVE, {}))
            for k in range(10)]
    s = events.summarize(rows, "1m")
    assert s["n"] == 10 and 0 <= s["porazilo_kontrolu"] <= 1


def test_active_vs_passive_compares_same_month():
    def row(kind, month, val):
        return {"kind": kind, "public": f"2024-{month:02d}-10", "ex_ctrl_6m": val, "dd52": -0.5, "turnover": 5e6, "meta": {}}
    rows = []
    for mth in range(1, 13):
        rows += [row(groups.ACTIVE, mth, 0.05 + 0.001 * mth) for _ in range(3)]
        rows += [row("insider:PASIVNÍ (opce)", mth, 0.01) for _ in range(6)]
    res = {(r["situace"], r["skupina"]): r for r in groups.active_vs_passive(rows, "6m")}
    assert res[("vše", "aktivní nákup (vše)")]["rozdil"] == pytest.approx(0.0465, abs=1e-3)
    assert res[("po propadu 30 %+", "aktivní nákup (vše)")]["mesicu"] == 12


def test_verdict_rules_are_conservative():
    ev = {"CFO": (0.03, 0.01), "CEO": (0.01, -0.03)}
    base = {"insideru": 2, "znaky": {"cfo": 1.0, "ceo": 0.0, "info_before": 0.0}}
    assert store.verdict({**base, "skore": 70}, ev)[0] == "STŘEDNÍ"   # bez statisticky potvrzené výhody nikdy VYSOKÁ
    assert store.verdict({**base, "skore": 70, "t_ok": True}, {"CFO": (0.03, 0.03)})[0] == "VYSOKÁ"
    assert store.verdict({**base, "skore": 50}, ev)[0] == "STŘEDNÍ"
    assert store.verdict({**base, "skore": 10}, ev)[0] == "NÍZKÁ"
    assert store.verdict({**base, "skore": 80, "znaky": {"cfo": 1.0, "info_before": 1.0}}, ev)[0] == "NÍZKÁ"
    assert store.verdict({"insideru": 3, "skore": 90, "znaky": {"ceo": 1.0}}, ev)[0] == "NÍZKÁ"


def test_control_group_does_not_depend_on_other_events():
    m = _market()
    day = m.data.data_start + 220
    first = m.controls("S1", day)
    for k in range(2, 9):  # jiné události měřené mezi tím nesmí změnit kontrolu pro S1
        m.controls(f"S{k}", day - k)
    assert m.controls("S1", day) == first and first
