import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / ".codex" / "agents"


def test_project_config_keeps_model_selection_per_chat_and_bounds_delegation():
    config = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
    agents = config["agents"]

    assert "model" not in config
    assert "model_reasoning_effort" not in config
    assert agents["enabled"] is True
    assert agents["default_subagent_model"] == "gpt-6-luna"
    assert agents["default_subagent_reasoning_effort"] == "low"
    assert 1 <= agents["max_concurrent_threads_per_session"] <= 3


def test_agent_profiles_have_unique_names_and_expected_efforts_and_sandboxes():
    profiles = [
        tomllib.loads(path.read_text(encoding="utf-8"))
        for path in sorted(AGENT_DIR.glob("*.toml"))
    ]
    by_name = {profile["name"]: profile for profile in profiles}

    assert len(by_name) == len(profiles)
    assert set(by_name) == {
        "explorer",
        "geometry_reviewer",
        "implementer",
        "implementer_medium",
        "mathematician",
        "researcher",
        "test_engineer",
        "verifier_reviewer",
    }
    for name, profile in by_name.items():
        assert profile["model"] == "gpt-6-luna"
        expected_effort = "medium" if name == "implementer_medium" else "low"
        assert profile["model_reasoning_effort"] == expected_effort

    read_only_roles = (
        "explorer",
        "geometry_reviewer",
        "mathematician",
        "researcher",
        "verifier_reviewer",
    )
    for name in read_only_roles:
        assert by_name[name]["sandbox_mode"] == "read-only"
    for name in ("implementer", "implementer_medium"):
        assert by_name[name]["sandbox_mode"] == "workspace-write"


def test_usage_record_template_leaves_unknown_metrics_null():
    record = json.loads(
        (ROOT / "docs" / "AGENT_USAGE_RECORD.example.json").read_text(encoding="utf-8")
    )

    assert record["record_kind"] == "TEMPLATE"
    assert record["measurement_scope"] in ("worker", "primary", "aggregate", None)
    assert record["measurement_source"] is None
    assert all(value is None for value in record["usage"].values())
