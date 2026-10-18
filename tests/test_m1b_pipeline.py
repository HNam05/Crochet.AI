from __future__ import annotations

from dataclasses import asdict

import pytest
from conftest import make_reserve_ir, make_split_join_ir, resolved_artifacts
from test_analytic_solver import PROVENANCE
from test_flat_solver import _inputs

from crochet_ai.backend_api import BackendAPI
from crochet_ai.pattern import TerminologyProfile
from crochet_ai.pattern_context import PatternParseContext, PatternYarnBinding
from crochet_ai.pattern_m1b import PROFILE, verify_semantic_round_trip_m1b
from crochet_ai.validation import SemanticValidator
from crochet_ai.verification_pipeline import GateOutcome, OverallState, verify_artifacts


@pytest.mark.parametrize("factory", [make_reserve_ir, make_split_join_ir])
def test_explicit_m1b_adapter_checks_export_without_claiming_physics(factory):
    design, material = resolved_artifacts()
    source = factory()
    old = verify_artifacts(design, material, source, diagnostic_mode=True)
    new = verify_artifacts(design, material, source, diagnostic_mode=True, pattern_profile=PROFILE)
    v9 = next(gate for gate in new.gates if gate.gate_id == "V9")
    assert v9.outcome is GateOutcome.PASS
    assert len(v9.produced_artifact_hashes) == 3
    assert new.overall_state is not OverallState.VERIFIED
    assert old.evidence_bundle_hash != new.evidence_bundle_hash
    assert "pattern_export_profile" in dict(v9.input_hashes)
    with pytest.raises(ValueError, match="unsupported pattern"):
        verify_artifacts(design, material, source, pattern_profile="unknown")


def test_flat_wire_to_m1b_round_trip_and_pipeline():
    design, material, target, config, _ = _inputs()
    api = BackendAPI(PROVENANCE)
    request = {
        "api_version": "1.0.0",
        "operation": "generate_flat_rows",
        "design_spec": design,
        "material_profile": material,
        "target_json": target.decode(),
        "run_config": asdict(config),
    }
    generated = api.handle(request)
    assert generated["ok"], generated
    ir = generated["data"]["candidate"]
    assert ir is not None
    color = design["colors"][0]
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    context = PatternParseContext(
        design, (PatternYarnBinding("Yarn A", material, color["label"], color["srgb_hex"]),)
    )
    for term in TerminologyProfile:
        report = verify_semantic_round_trip_m1b(ir, term, context=context, validator=validator)
        assert report.ok, report.diagnostics
    checked = api.handle(
        {
            "api_version": "1.0.0",
            "operation": "verify_m1b_candidate",
            "design_spec": design,
            "material_profile": material,
            "crochet_ir": ir,
            "mesh_json": None,
            "diagnostic_mode": True,
        }
    )
    assert checked["ok"], checked
    v9 = next(gate for gate in checked["data"]["gates"] if gate["gate_id"] == "V9")
    assert v9["outcome"] == "PASS"
    assert checked["data"]["verification_state"] != "VERIFIED"
    request["run_config"]["software_commit"] = "a" * 40
    assert api.handle(request)["ok"] is False
