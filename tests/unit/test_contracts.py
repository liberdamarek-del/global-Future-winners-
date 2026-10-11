"""Federální zakázky (USAspending): stránkování bez sítě, párování příjemce s firmou (E3, 2026-10-11)."""

import sqlite3

from stockradar.discovery import contracts as C
from stockradar.sources import usaspending as U


def test_fetch_month_pages_until_amount_falls_below_limit():
    pages = {1: [{"Award ID": "A1", "Mod": "0", "Recipient Name": "KRATOS DEFENSE & SECURITY SOLUTIONS, INC.",
                  "Action Date": "2024-01-10", "Transaction Amount": 50e6, "Awarding Agency": "DoD"},
                 {"Award ID": "A2", "Mod": "P00003", "Recipient Name": "X", "Action Date": "2024-01-11",
                  "Transaction Amount": 20e6}],
             2: [{"Award ID": "A3", "Mod": "0", "Recipient Name": "Y", "Action Date": "2024-01-12", "Transaction Amount": 12e6},
                 {"Award ID": "A4", "Mod": "0", "Recipient Name": "Z", "Action Date": "2024-01-13", "Transaction Amount": 5e6}],
             3: [{"Award ID": "A5", "Mod": "0", "Recipient Name": "W", "Action Date": "2024-01-14", "Transaction Amount": 99e6}]}
    calls = []

    def post(payload):
        calls.append(payload["page"])
        return {"results": pages[payload["page"]], "page_metadata": {"hasNext": True}}

    rows = U.fetch_month(2024, 1, post=post, pause=0)
    assert calls == [1, 2]                                           # strana 2 končí pod limitem → dál se nestránkuje
    assert [r[0] for r in rows] == ["A1", "A2", "A3"]                # 5 mil. USD pod limitem se neuloží
    assert U.month_bounds(2024, 12) == ("2024-12-01", "2024-12-31")


def test_name_normalization_and_unique_matching():
    assert C.norm("KRATOS DEFENSE & SECURITY SOLUTIONS, INC.") == C.norm("Kratos Defense & Security Solutions, Inc. Common Stock")
    assert C.norm("Centrus Energy Corp. Class A Common Stock") == "centrus energy"
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE securities (symbol TEXT, name TEXT)")
    conn.executemany("INSERT INTO securities VALUES (?, ?)", [("KTOS", "Kratos Defense & Security Solutions, Inc. Common Stock"),
                                                              ("AAA", "Acme Corp"), ("AAB", "Acme Inc."), ("LEU", "Centrus Energy Corp.")])
    idx = C.name_index(conn, {"KTOS", "AAA", "AAB", "LEU"})
    assert idx[C.norm("KRATOS DEFENSE & SECURITY SOLUTIONS, INC.")] == "KTOS"
    assert "acme" not in idx                                         # dvě firmy se stejným jménem → nepárovat


def test_firm_key_matches_subsidiaries_sharing_first_two_words():
    key = C.firm_key("Kratos Defense & Security Solutions, Inc. Common Stock")
    assert key == "kratos defense"
    accept = lambda rec: (C.norm(rec) + " ").startswith(key + " ")
    assert accept("KRATOS DEFENSE & ROCKET SUPPORT SERVICES INC") and not accept("KRATOS UNMANNED AERIAL SYSTEMS")
    assert C.firm_key("Oklo Inc. Class A Common Stock") == "oklo" and C.firm_key("AB Inc.") is None


def test_strict_match_accepts_only_full_normalized_name():
    assert C.strict_match("Alamo Group, Inc.", "ALAMO GROUP INC")
    assert not C.strict_match("Alamo Group, Inc.", "ALAMO CITY ENGINEERING SERVICES, INC.")    # jednoslovný klíč jen přesně
    assert C.strict_match("Bridger Aerospace Group Holdings Inc. Common Stock", "BRIDGER AEROSPACE GROUP, LLC")
    assert not C.strict_match("Asia Pacific Wire & Cable Corporation Ltd", "ASIA PACIFIC AEROSPACE PTY. LTD.")   # obecná slova
    assert not C.strict_match("Energy Services of America Corporation", "ENERGY SERVICES GROUP INC")
    assert not C.strict_match("Oklo Inc.", "")
