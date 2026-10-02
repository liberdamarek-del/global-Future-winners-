"""End-to-end: CLI v samostatném procesu nad dočasnou DB a state/."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(tmp_path, *args):
    env = {**os.environ, "STOCKRADAR_DB": str(tmp_path / "db" / "radar.db"),
           "STOCKRADAR_STATE_DIR": str(tmp_path / "state")}
    proc = subprocess.run([sys.executable, "-m", "stockradar", *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_full_cli_flow(tmp_path):
    out = run(tmp_path, "init")
    assert "Historický stav nenalezen" in out

    run(tmp_path, "seed-lessons")
    companies = (tmp_path / "state" / "companies.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(companies) == 9
    assert json.loads(companies[0])["name"] == "Capricor Therapeutics"

    status = run(tmp_path, "status")
    assert "Beam Therapeutics" in status and "NEOVĚŘENO" in status
    assert "POSLEDNÍ MAIN PICK: ŽÁDNÝ" in status
    assert "neexportované" not in status

    assert "ledger je prázdný" in run(tmp_path, "ledger")
    assert "XTB kontrola musí být před doporučením." in run(tmp_path, "lessons")
    assert "Snapshot #1" in run(tmp_path, "snapshot", "--label", "e2e")

    # Smazání pracovní DB nesmí ztratit stav — vše se obnoví ze state/.
    (tmp_path / "db" / "radar.db").unlink()
    assert "obnovena" in run(tmp_path, "init")
    assert "lessons=9" in run(tmp_path, "status") and "snapshots=1" in run(tmp_path, "status")
    assert "lessons" in run(tmp_path, "restore")
