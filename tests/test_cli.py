import json
from pathlib import Path

from crochet_ai.cli import main


def test_cli_doctor_is_offline_and_machine_readable(capsys) -> None:
    assert main(["--json", "doctor"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["auth_required"] is False
    assert payload["data"]["physical_verification_available"] is False
    assert payload["data"]["generation_commit_supplied"] is False
    assert "crochet_ir_1_1" in payload["data"]["schema_kinds"]


def test_cli_argument_errors_are_json(capsys) -> None:
    assert main(["--json", "jobs", "get"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "E_INPUT"


def test_read_command_does_not_create_database(tmp_path: Path, capsys) -> None:
    path = tmp_path / "missing.sqlite"
    assert main(["--json", "jobs", "get", "--db", str(path), "job_missing"]) == 2
    assert not path.exists()
    assert not json.loads(capsys.readouterr().out)["ok"]
