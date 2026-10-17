"""CLI v procesu testu (počítá se do pokrytí): příkazy nad dočasnou DB, deník běhů a návratové kódy.

Síť se nepoužívá — příkazy, které stahují, se volají jen s přepínači bez stahování nebo s podvrženou funkcí."""

import io
import json
import sys
from datetime import timedelta

import pytest

from stockradar import cli
from stockradar.catalysts import add_catalyst
from stockradar.db import open_db
from stockradar.ledger import PredictionInput, Scores, record_prediction
from stockradar.timeutil import utcnow


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKRADAR_DB", str(tmp_path / "db" / "radar.db"))
    monkeypatch.setenv("STOCKRADAR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("STOCKRADAR_WEB_DIR", str(tmp_path / "web"))
    monkeypatch.setenv("STOCKRADAR_MARKET_CACHE", str(tmp_path / "cache.db"))
    monkeypatch.setenv("STOCKRADAR_CONTACT_FILE", str(tmp_path / "kontakt.txt"))
    monkeypatch.delenv("STOCKRADAR_CONTACT_EMAIL", raising=False)
    return tmp_path


@pytest.fixture
def cli_run(env, monkeypatch):
    def run(*argv: str, code: int = 0) -> str:
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        rc = cli.main(list(argv))
        assert rc == code, buf.getvalue()
        return buf.getvalue()
    return run


def journal(env) -> list[dict]:
    conn = open_db(env / "db" / "radar.db")
    rows = [dict(r) for r in conn.execute("SELECT command, status, summary_json, error FROM system_runs ORDER BY id")]
    conn.close()
    return rows


def test_parser_wires_every_command():
    parser = cli.build_parser()
    commands = set(parser._subparsers._group_actions[0].choices)
    assert cli.JOURNALED <= commands                      # deník jen pro existující příkazy
    for name in commands:
        assert callable(parser.parse_args([name] if name != "research" else [name]).func), name
    with pytest.raises(SystemExit):
        parser.parse_args([])                             # příkaz je povinný


def test_read_commands_need_initialised_db(cli_run):
    for name in ("status", "ledger", "lessons", "export", "email", "system"):
        with pytest.raises(SystemExit, match="spusť nejdřív"):
            cli_run(name)


def test_restore_without_state_fails(cli_run):
    with pytest.raises(SystemExit, match="není z čeho obnovit"):
        cli_run("restore")


def test_init_is_idempotent_and_reports_schema(cli_run):
    assert "Nová prázdná databáze" in cli_run("init")
    assert "Databáze už existuje" in cli_run("init")


def test_read_only_commands_are_not_journaled(cli_run, env):
    cli_run("init")
    cli_run("status")
    cli_run("ledger")
    cli_run("research")                                   # bez --entita = jen výpis
    assert journal(env) == []


def test_journaled_command_records_ok_and_summary(cli_run, env):
    cli_run("init")
    cli_run("seed-lessons")
    out = cli_run("diag", "--json", code=1)               # čerstvá DB → CHYBA, kód 1
    checks = json.loads(out)
    assert {c["kontrola"] for c in checks} >= {"Schéma databáze", "Denní běh (update)"}
    runs = journal(env)
    assert [r["command"] for r in runs] == ["seed-lessons", "diag"]
    assert runs[0]["status"] == "OK"
    assert runs[1]["status"] == "CHYBA" and runs[1]["error"] == "návratový kód 1"
    summary = json.loads(runs[1]["summary_json"])
    assert summary["celkove"] == "CHYBA" and "Denní běh (update)" in summary["chyby"]
    # deník se hned exportuje do state/ (jinak by se ztratil s kontejnerem)
    assert (env / "state" / "system_runs.jsonl").read_text(encoding="utf-8").count("\n") == 2


def test_exception_is_journaled_and_reraised(cli_run, env, monkeypatch):
    cli_run("init")

    def boom(args):
        raise RuntimeError("selhalo")
    parser = cli.build_parser()
    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    parser._subparsers._group_actions[0].choices["snapshot"].set_defaults(func=boom)
    with pytest.raises(RuntimeError):
        cli_run("snapshot")
    assert journal(env)[-1] == {"command": "snapshot", "status": "CHYBA", "summary_json": "{}",
                                "error": "RuntimeError: selhalo"}


def test_skipped_signals_are_journaled_as_skipped(cli_run, env, monkeypatch):
    from stockradar.hub import registry
    cli_run("init")
    monkeypatch.setattr(registry, "signals_unchanged", lambda conn, cconn, models: "stejná data")
    assert "Signály PŘESKOČENY: stejná data" in cli_run("signals", "--no-download", "--no-news")
    last = journal(env)[-1]
    assert last["status"] == "PŘESKOČENO" and json.loads(last["summary_json"]) == {"preskoceno": "stejná data"}


def test_state_survives_db_loss(cli_run, env):
    cli_run("init")
    cli_run("seed-lessons")
    assert "Snapshot #1" in cli_run("snapshot", "--label", "t")
    assert "lessons=9" in cli_run("export")
    (env / "db" / "radar.db").unlink()
    assert "obnovena" in cli_run("init")
    out = cli_run("restore")
    assert "lessons" in out and "snapshots" in out
    assert "Capricor Therapeutics" in cli_run("status")


def test_research_writes_evidence_and_refreshes_hub(cli_run, env):
    cli_run("init")
    out = cli_run("research", "--entita", "VLO, MPC,", "--druh", "riziko", "--smer", "-1", "--datum", "2026-10-10",
                  "--zdroj", "test", "--url", "https://example.com", "--text", "FAKT: test")
    assert "Zapsáno 2 záznamů výzkumu" in out and "Centrum:" in out
    listing = cli_run("research")
    assert "VLO" in listing and "MPC" in listing and "OVĚŘENO" in listing
    last = journal(env)[-1]
    assert last["command"] == "research" and json.loads(last["summary_json"])["zapsano"] == [1, 2]
    assert any((env / "web").glob("stav_*.json"))


def test_hub_and_system_overview(cli_run):
    cli_run("init")
    assert "Centrum:" in cli_run("hub")
    out = cli_run("hub", "--firma", "zzz")
    assert "ZZZ: žádný modul o firmě nic neříká" in out
    out = cli_run("system")
    assert out.startswith("SYSTÉM v") and "DENÍK" in out and "hub" in out


def test_email_report_without_address(cli_run):
    cli_run("init")
    out = cli_run("email", "--days", "1")
    assert "NENASTAVEN" in out and "www.sec.gov" in out and "(za období nepoužit)" in out


def test_status_and_ledger_show_records(cli_run, env):
    cli_run("init")
    cli_run("seed-lessons")
    conn = open_db(env / "db" / "radar.db")
    company_id, listing_id = conn.execute("SELECT company_id, id FROM listings ORDER BY id LIMIT 1").fetchone()
    now = utcnow()
    add_catalyst(conn, company_id, "FDA_DECISION", "rozhodnutí FDA", date_status="VERIFIED",
                 event_date=(now + timedelta(days=10)).date().isoformat(), source="test",
                 source_url="https://example.com", published_at=now - timedelta(days=1))
    record_prediction(conn, PredictionInput(
        listing_id=listing_id, horizon="D0_14", price=4.2, currency="USD", price_as_of=now - timedelta(minutes=5),
        price_source="test", category="A", verdict="WATCH", rationale="test", market_cap=2.5e9,
        market_cap_currency="USD", scores=Scores(overall_setup=70, rocket=60)))
    conn.close()
    status = cli_run("status", "--days", "30")
    assert "rozhodnutí FDA" in status and "KATALYZÁTORY V PŘÍŠTÍCH 30 DNECH" in status
    assert "neexportované změny" in status                 # zápis přes Python API bez exportu se hlásí
    ledger = cli_run("ledger")
    assert "REGISTER (§28) — predikce" in ledger and "2.50B" in ledger and "čeká" in ledger


def test_lessons_listing(cli_run):
    cli_run("init")
    assert "Žádná poučení" in cli_run("lessons")
    cli_run("seed-lessons")
    out = cli_run("lessons")
    assert "Zdroj:" in out and out.count("[") >= 9


def test_table_and_number_format():
    t = cli._table(["A", "Bb"], [[1, None], ["xyz", 2]]).splitlines()
    assert t[0] == "A   | Bb" and t[1] == "----+---" and t[2] == "1   |   "
    assert [cli._fmt_num(v) for v in (None, 2.5e9, 3.25e6, 42.0)] == [None, "2.50B", "3.2M", "42"]


def test_note_only_updates_journal_dict():
    class A:
        pass
    a = A()
    cli._note(a, x=1)                                     # bez deníku nic nedělá
    a.journal = {}
    cli._note(a, x=1)
    assert a.journal == {"x": 1}
