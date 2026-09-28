import json
from dataclasses import asdict

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from test_analytic_solver import PROVENANCE, config, inputs

from crochet_ai.backend_api import BackendAPI


def request():
    design, material = inputs()
    run = asdict(config())
    run["minimum_shaping_separation_turns"] = "1/12"
    return {
        "api_version": "1.0.0",
        "operation": "generate_analytic",
        "design_spec": design,
        "material_profile": material,
        "run_config": run,
    }


def test_wire_generation_and_independent_export_endpoint() -> None:
    api = BackendAPI(PROVENANCE)
    value = request()
    response = api.handle_json(json.dumps(value))
    assert response["ok"], response
    assert response["data"]["generation_status"] == "CANDIDATES_EMITTED"
    assert response["data"]["verification_state"] == "NOT_VERIFIED"
    candidate = response["data"]["candidates"][0]
    value.pop("run_config")
    value.update(operation="export_ir", crochet_ir=candidate["crochet_ir"], terminology="DE_DE")
    exported = api.handle(value)
    assert exported["ok"], exported
    assert "fM" in exported["data"]["pattern"]
    assert exported["data"]["verification_state"] == "NOT_VERIFIED"


@pytest.mark.parametrize(
    "path,value",
    [
        ("api_version", "2.0.0"),
        ("operation", []),
        ("extra", True),
        ("design_spec", {"design_spec_id": []}),
        ("material_profile", None),
        ("run_config", {}),
        ("run_config.max_courses", True),
        ("run_config.minimum_shaping_separation_turns", "1/0"),
        ("run_config.numerics.roundoff_allowance_mm", "tiny"),
        ("run_config.tension_profile_id", []),
    ],
)
def test_malformed_boundary_returns_structured_error(path: str, value: object) -> None:
    payload = request()
    target = payload
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    result = BackendAPI(PROVENANCE).handle_json(json.dumps(payload))
    assert not result["ok"]
    assert result["error"]["code"].startswith("E_")


@pytest.mark.parametrize(
    "raw",
    [
        b'{"api_version":"1.0.0","api_version":"1.0.0"}',
        b'{"x":NaN}',
        b'{"x":1e400}',
        b"\xff",
        b"[]",
        b"{" * 2000,
        b" " * 2000001,
    ],
    ids=["duplicate-key", "nan", "overflow", "bad-utf8", "array", "nested", "oversized"],
)
def test_untrusted_json_fails_closed(raw: bytes) -> None:
    result = BackendAPI(PROVENANCE).handle_json(raw)
    assert not result["ok"] and result["error"]["code"] == "E_INPUT"


@given(
    st.dictionaries(
        st.text(max_size=8),
        st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=40)),
        max_size=8,
    )
)
@settings(max_examples=100, deadline=None)
def test_arbitrary_json_never_escapes_as_unhandled_exception(payload: dict) -> None:
    result = BackendAPI(PROVENANCE).handle_json(json.dumps(payload))
    assert result["api_version"] == "1.0.0"
    assert not result["ok"]
