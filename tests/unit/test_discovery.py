import io
import json
import zipfile
from datetime import date

import pytest

from stockradar.discovery import cache, listings, news, study
from stockradar.discovery.features import features_at, prepare
from stockradar.discovery.winners import find_events, outcome_label, phase


def bars(closes, start=date(2023, 1, 2), vol=1e6, symbol="T"):
    days = [start.toordinal() + k for k in range(len(closes))]
    return cache.Bars(symbol, "USD", days, list(closes), [vol] * len(closes))


def test_cache_roundtrip():
    conn = cache.connect(":memory:")
    cache.store_series(conn, "ABC", "USD", [("2026-01-02", 10.5, 100.0), ("2026-01-05", 11.0, None)],
                       source="test", fetched_at="2026-01-06T00:00:00Z")
    b = cache.load_series(conn, "ABC")
    assert list(b.closes) == [10.5, 11.0] and list(b.volumes) == [100.0, 0.0] and b.date(1) == "2026-01-05"
    cache.store_error(conn, "BAD", "HTTP 404", fetched_at="2026-01-06T00:00:00Z")
    assert cache.load_series(conn, "BAD") is None


def test_find_week_rocket_from_base():
    closes = [10.0] * 30 + [9.5, 10.0, 11.5, 12.5, 13.5] + [13.5] * 70
    evs = find_events(bars(closes), "W1_30")
    assert len(evs) == 1
    ev = evs[0]
    assert ev.t0 == 30 and ev.ret == pytest.approx(13.5 / 9.5 - 1)
    assert outcome_label(ev.held) == "UDRŽEL"


def test_bad_tick_is_ignored():
    closes = [10.0] * 30 + [35.0] + [10.2] * 40
    assert find_events(bars(closes), "W1_30") == []


def test_anomalous_series_detected():
    assert study.anomalous(bars([10.0] * 10 + [10.0 * 60] * 10))
    assert not study.anomalous(bars([10.0] * 10 + [30.0] * 10))


def test_phase_levels():
    assert phase({"6M": 0.05}, False) == "EARLY"
    assert phase({"6M": 0.3}, False) == "DEVELOPING"
    assert phase({"6M": 0.7}, False) == "PARTIALLY PRICED"
    assert phase({"6M": 1.5}, False) == "LATE"
    assert phase({"6M": 0.05}, True) == "ALREADY TRIGGERED"


def test_features_use_only_past_data():
    closes = [10 + (k % 7) * 0.1 for k in range(300)]
    b1 = bars(closes)
    b2 = bars(closes[:200] + [99.0] * 100)  # jiná budoucnost
    f1 = features_at(prepare(b1, b1.days[0]), 199, 1.0)
    f2 = features_at(prepare(b2, b2.days[0]), 199, 1.0)
    assert f1 == f2


def test_listing_parsers():
    us = listings.us_securities(json.dumps({"data": {"rows": [
        {"symbol": "ABC", "name": "ABC Corp Common Stock", "marketCap": "1000000", "country": "United States",
         "ipoyear": "2020", "industry": "Software", "sector": "Technology"},
        {"symbol": "ABCW", "name": "ABC Corp Warrants", "marketCap": "", "country": "", "ipoyear": "", "industry": "",
         "sector": ""},
        {"symbol": "BRK/B", "name": "Berkshire Class B", "marketCap": "1", "country": "United States", "ipoyear": "",
         "industry": "", "sector": ""}]}}))
    assert [r["symbol"] for r in us] == ["ABC", "BRK-B"]
    asx = listings.asx_securities('ASX listed companies as at today\n\nCompany name,ASX code,GICS industry group\n'
                                  '"ACME MINING",AMX,Materials\n')
    assert asx[0]["symbol"] == "AMX.AX" and asx[0]["industry"] == "Materials"
    html_page = ('<table class="wikitable"><tr><th>Company</th><th>Ticker</th><th>Sector</th></tr>'
                 + "".join(f"<tr><td>Firm {k}</td><td>F{k}.AS</td><td>Tech</td></tr>" for k in range(5))
                 + '<tr><td>Spaced</td><td>VOLV B</td><td>Ind</td></tr></table>')
    wiki = listings.wiki_securities(("Test", "u", "Netherlands", "AMS", listings._sfx(".AS")), html_page)
    assert {r["symbol"] for r in wiki} == {"F0.AS", "F1.AS", "F2.AS", "F3.AS", "F4.AS", "VOLV-B.AS"}


def test_xlsx_reader():
    buf = io.BytesIO()
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", f'<sst {ns}><si><t>Local Code</t></si><si><t>1301</t></si></sst>')
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData><row><c t="s"><v>0</v></c></row>'
                                                f'<row><c t="s"><v>1</v></c></row></sheetData></worksheet>')
    assert listings.read_xlsx_rows(buf.getvalue()) == [["Local Code"], ["1301"]]


def test_news_classification_and_explanation():
    heads = [{"datum": "2025-05-01", "titulek": "Acme signs supply agreement", "zdroj": "x", "url": "u"},
             {"datum": "2025-05-12", "titulek": "Why Acme stock soared: FDA approval", "zdroj": "x", "url": "u"},
             {"datum": "2025-05-13", "titulek": "Acme Q1 earnings", "zdroj": "x", "url": "u"}]
    assert news.classify(heads[1:])[0]["kod"] == "FDA"
    info = news.explain_event("Acme Inc. Common Stock", date(2025, 5, 10), date(2025, 5, 14),
                              fetch=lambda q, a, b, lang="en": heads, pause=0)
    assert info["dotaz"] == '"Acme" (stock OR shares)' and info["titulku_pred"] == 1 and info["titulku_behem"] == 2
    assert info["kod"] == "FDA" and info["planovany_termin"] is True
    assert info["stav"].startswith("AUTO")


def test_search_plan_relevance_and_japan():
    q, lang, rel = news.search_plan("Image Information Inc.", "3803.T")
    assert (q, lang) == ('"3803" 株', "ja")
    q, lang, rel = news.search_plan("Liberta Co Ltd", "LBRT")
    assert lang == "en" and rel({"titulek": "Liberta shares jump on deal"})
    assert not rel({"titulek": "Resident recounts strange incident"})
    jp = [{"datum": "2026-02-12", "titulek": "地盤ＨＤ、今期最終を一転2.4倍増益に上方修正 - 株探"}]
    assert news.classify(jp)[0]["kod"] == "EARNINGS"


def test_logit_learns_signal_and_auc():
    rows = [{"y": int(k % 5 == 0), "f": {"a": (1.0 if k % 5 == 0 else 0.0) + (k % 3) * 0.01, "b": k % 7}}
            for k in range(500)]
    model = study.fit_logit(rows, ["a", "b"])
    scores = [model.score(r["f"]) for r in rows]
    assert study.auc(scores, [r["y"] for r in rows]) > 0.95
    assert model.coef[1] > 0


def test_unadjusted_reverse_split_is_not_a_rocket():
    from array import array
    from stockradar.discovery.cache import Bars
    from stockradar.discovery.winners import adjust_reverse_splits, find_events
    closes = [1.6] * 30 + [16.0] * 10              # 1:10 reverse split bez úpravy historie
    vols = [1_000_000.0] * 30 + [95_000.0] * 10    # objem spadne na desetinu
    b = Bars("DHY", "USD", array("i", range(738000, 738040)), array("d", closes), array("d", vols))
    assert find_events(b, "W1_30")  # bez úpravy by to byla „raketa“
    fixed, n = adjust_reverse_splits(b)
    assert n == 1 and not find_events(fixed, "W1_30") and fixed.closes[0] == pytest.approx(16.0)
    # skutečná raketa s obrovským objemem se neupravuje
    real = Bars("JAGX", "USD", b.days, array("d", [2.7] * 30 + [27.0] * 10), array("d", [2e5] * 30 + [2.8e7] * 10))
    assert adjust_reverse_splits(real)[1] == 0
