"""Web ukazuje v každé sekci nejvýš 10 firem (rozhodnutí uživatele 2026-10-11); modely a ledger dál pracují s TOP 20."""

import json

from stockradar import site


def _cards(n: int) -> list[dict]:
    return [{"ticker": f"T{i}", "firma": f"Firma {i}", "poradi": i + 1, "poradi_velke": i + 1, "den_ceny": "2026-10-09",
             "final": "POKLES" if i == n - 1 else "NEVÍM", "p_up": 0.3, "p_down": 0.2} for i in range(n)]


def test_rankings_on_web_are_cut_to_ten_firms(conn):
    assert site.WEB_TOP == 10
    for model in ("SIGNAL_14D", "SIGNAL_1M", "SIGNAL_6M"):
        conn.execute("INSERT INTO signal_runs (run_at, data_through, model_name, config_hash, result_json, app_version)"
                     " VALUES (?, ?, ?, ?, ?, ?)", ("2026-10-11T05:00:00Z", "2026-10-09", model, "c",
                                                    json.dumps({"karty": _cards(25)}), "t"))
    z = site.build_zebricek_doc(conn)
    assert len(z["h14"]["firmy"]) == 10 and len(z["h1m"]["firmy"]) == 10
    assert [c["ticker"] for c in z["h14"]["firmy"]][:2] == ["T0", "T1"]          # pořadí modelu se zachová
    z6 = site.build_zebricek6m_doc(conn)
    assert len(z6["firmy"]) == 10 and len(z6["velke"]) == 10 and len(z6["vyhnout"]) <= 10
