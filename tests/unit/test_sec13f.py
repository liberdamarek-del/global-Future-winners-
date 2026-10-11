"""SEC 13F (výzkum E4): výběr zpráv bez dodatků a pozdních podání, váhy správce, konsenzus, odkazy, CUSIP → symbol."""

from datetime import date

from stockradar.sources import sec13f as F


def test_select_filings_keeps_latest_timely_original_report():
    subs = [{"ACCESSION_NUMBER": "A1", "FILING_DATE": "10-AUG-2025", "SUBMISSIONTYPE": "13F-HR", "CIK": "1", "PERIODOFREPORT": "30-JUN-2025"},
            {"ACCESSION_NUMBER": "A2", "FILING_DATE": "12-AUG-2025", "SUBMISSIONTYPE": "13F-HR", "CIK": "1", "PERIODOFREPORT": "30-JUN-2025"},
            {"ACCESSION_NUMBER": "B1", "FILING_DATE": "20-AUG-2025", "SUBMISSIONTYPE": "13F-HR", "CIK": "2", "PERIODOFREPORT": "30-JUN-2025"},
            {"ACCESSION_NUMBER": "C1", "FILING_DATE": "01-AUG-2025", "SUBMISSIONTYPE": "13F-HR", "CIK": "3", "PERIODOFREPORT": "30-JUN-2025"},
            {"ACCESSION_NUMBER": "D1", "FILING_DATE": "01-AUG-2025", "SUBMISSIONTYPE": "13F-NT", "CIK": "4", "PERIODOFREPORT": "30-JUN-2025"}]
    covers = {"A1": {"REPORTTYPE": "13F HOLDINGS REPORT"}, "A2": {"REPORTTYPE": "13F COMBINATION REPORT"},
              "B1": {"REPORTTYPE": "13F HOLDINGS REPORT"}, "C1": {"REPORTTYPE": "13F HOLDINGS REPORT", "ISAMENDMENT": "Y"}}
    chosen = F.select_filings(subs, covers)
    assert set(chosen) == {"A2"}                     # B1 po 45 dnech, C1 dodatek, D1 bez pozic, A1 nahrazena pozdější
    assert chosen["A2"] == (1, "2025-06-30", "2025-08-12")
    assert F.sec_day("31-JUL-2025") == date(2025, 7, 31) and F.sec_day("x") is None


def test_reduce_holdings_weights_consensus_and_position_limits(monkeypatch):
    monkeypatch.setattr(F, "MIN_POS", 2)
    monkeypatch.setattr(F, "TOP", 2)
    chosen = {"A": (1, "2025-06-30", "2025-08-01"), "B": (2, "2025-06-30", "2025-08-02"), "C": (3, "2025-06-30", "2025-08-03")}
    row = lambda acc, cusip, v, kind="SH", pc="": {"ACCESSION_NUMBER": acc, "CUSIP": cusip, "VALUE": str(v), "SSHPRNAMTTYPE": kind,
                                                 "PUTCALL": pc, "NAMEOFISSUER": cusip.lower()}
    rows = [row("A", "AAAAAAAA1", 60), row("A", "BBBBBBBB1", 30), row("A", "AAAAAAAA1", 10),   # dvě řádky téže akcie
            row("A", "CCCCCCCC1", 999, pc="Put"), row("A", "DDDDDDDD1", 50, kind="PRN"),      # opce a dluhopis se ignorují
            row("B", "BBBBBBBB1", 1000), row("B", "CCCCCCCC1", 3000),                           # jiné jednotky nevadí (váhy)
            row("C", "AAAAAAAA1", 5)]                                                           # 1 pozice < MIN_POS
    managers, top, cons, per_period = F.reduce_holdings(rows, chosen)
    assert {m[0] for m in managers} == {"A", "B"} and per_period == {"2025-06-30": 2}
    assert [(t[0], t[2], round(t[4], 3)) for t in top if t[0] == "A"] == [("A", "AAAAAAAA1", 0.7), ("A", "BBBBBBBB1", 0.3)]
    assert round(cons[("2025-06-30", "BBBBBBBB1")][0], 3) == 0.55 and cons[("2025-06-30", "BBBBBBBB1")][1] == 2


def test_zip_links_and_ftd_parsing():
    html = ('<a href="/files/structureddata/data/form-13f-data-sets/2020q4_form13f.zip">x</a>'
            '<a href="/files/structureddata/data/form-13f-data-sets/2021q1_form13f.zip">x</a>'
            '<a href="/files/datastandardsinnovation/data/form-13f-data-sets/01jun2026-31aug2026_form13f.zip">x</a>')
    links = F.zip_links(html, 2021)
    assert [l.rsplit("/", 1)[-1] for l in links] == ["01jun2026-31aug2026_form13f.zip", "2021q1_form13f.zip"]
    assert links[0].startswith("https://www.sec.gov/")
    text = "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n20260901|B6S7WD106|NYXH|2508|NYXOAH S A|1.56\n20260901|bad|X|1|Y|2\n"
    assert F.parse_ftd(text, "2026-09") == [("B6S7WD106", "NYXH", "NYXOAH S A", "2026-09")]


def test_best_idea_is_largest_active_weight_among_mapped_stocks():
    import sqlite3
    from stockradar.discovery import bestideas as B
    assert B.symbol_for("BFB", {"BF-B"}) == "BF-B" and B.symbol_for("MSFT", {"MSFT"}) == "MSFT" and B.symbol_for("ZZZ", set()) is None
    conn = sqlite3.connect(":memory:")
    conn.executescript(F.SCHEMA)
    conn.executemany("INSERT INTO f13_mgr VALUES (?, ?, ?, ?, ?)", [("A", 1, "2025-06-30", "2025-08-01", 30),
                                                                   ("B", 2, "2025-06-30", "2025-08-01", 30)])
    # A: MSFT má největší váhu, ale i běžnou váhu → nejsilnější sázka je malá firma SMOL; ETF (nezmapované) se přeskočí
    conn.executemany("INSERT INTO f13_top VALUES (?, ?, ?, ?, ?)", [
        ("A", 0, "ETF000001", "ISHARES", 0.30), ("A", 1, "594918104", "MICROSOFT", 0.10), ("A", 2, "SMOL00001", "SMOL INC", 0.06),
        ("B", 0, "SMOL00001", "SMOL INC", 0.04), ("B", 1, "594918104", "MICROSOFT", 0.20)])
    conn.executemany("INSERT INTO f13_cons VALUES (?, ?, ?, ?)", [("2025-06-30", "594918104", 0.12, 2), ("2025-06-30", "SMOL00001", 0.02, 2),
                                                                 ("2025-06-30", "ETF000001", 0.3, 1)])
    conn.execute("INSERT INTO f13_period VALUES ('2025-06-30', 2)")
    cmap = {"594918104": ("MSFT", "MICROSOFT CORP"), "SMOL00001": ("SMOL", "SMOL INC")}
    ideas = B.best_ideas(conn, cmap)
    # A: MSFT 0.10 − 0.06 = 0.04, SMOL 0.06 − 0.01 = 0.05 → SMOL; B: MSFT 0.20 − 0.06 = 0.14 → MSFT
    assert ideas[("2025-06-30", "SMOL")]["spravcu"] == 1 and ideas[("2025-06-30", "MSFT")]["spravcu"] == 1
