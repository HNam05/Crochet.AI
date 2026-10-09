from __future__ import annotations

from hashlib import sha256
from typing import Any

import pytest
from conftest import resolved_artifacts
from test_forward_closed_f0 import _recipe

from crochet_ai.analytic_compile import CompileProvenance, compile_closed_schedule
from crochet_ai.backend_provenance import implementation_identity_hash, runtime_provenance
from crochet_ai.canonical import jcs_bytes
from crochet_ai.numerical_verification import (
    NumericalVerificationError,
    _f0_gate_result,
    _f0_integrity,
    admit_numerical_run,
    build_numerical_gate_runners,
)
from crochet_ai.validation import SemanticValidator


def _snapshot(commit: str) -> dict[str, str]:
    return {
        "source_snapshot_sha256": runtime_provenance(commit).source_snapshot_sha256,
        "implementation_identity": implementation_identity_hash(),
    }


def _context() -> dict[str, Any]:
    from test_geometry_comparison import policy as comparison_policy
    from test_material_scenarios import scenario_policy

    comparison = comparison_policy()
    comparison["coordinate_frame_id"] = "frame_fixture_target"
    comparison["hard_thresholds"]["topology_match"]["value"] = 0
    comparison["hard_thresholds"].update(
        {
            name: {
                "value": 0.1,
                "unit": "degree" if name == "normal_p95_degrees" else "1",
                "owner": "synthetic fixture",
                "rationale": "test-only diagnostic bound",
                "validation_path": "test_numerical_verification",
            }
            for name in (
                "robust_hausdorff_normalized",
                "normal_p95_degrees",
                "landmark_max_normalized",
            )
        }
    )
    return {
        "profile": "NUMERICAL_VERIFICATION_CONTEXT_V1",
        "schema_version": "1.0.0",
        "forward_run": _recipe(),
        "target_sampling": {
            "profile": "ANALYTIC_TARGET_SURFACE_SAMPLING_V1",
            "schema_version": "1.0.0",
            "ring_count": 4,
            "azimuth_sectors": 8,
        },
        "comparison_policy": comparison,
        "scenario_policy": scenario_policy(),
        "audit_policy": {
            "profile": "FORWARD_F0_AUDIT_POLICY_V1",
            "max_replay_objective_evaluations": 5000,
            "max_contact_pair_evaluations": 500_000,
            "coordinate_abs_tolerance_mm": 0.0,
            "force_abs_tolerance_n": 0.0,
            "energy_abs_tolerance_n_mm": 0.0,
            "tolerance_owner": "synthetic fixture",
            "tolerance_rationale": "exact replay on deterministic fixture",
            "validation_path": "test_numerical_verification",
        },
        "rigid_alignment": [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        "max_scenario_runs": 5,
    }


def test_context_is_canonical_and_rejects_scale_reflection_or_extra_fields() -> None:
    raw = _context()
    admitted = admit_numerical_run(raw)
    assert admitted.sha256 == admit_numerical_run(_context()).sha256
    assert len(admitted.sha256) == 64
    raw["comparison_policy"]["coordinate_frame_id"] = "mutated_after_admission"
    assert admitted.comparison_policy["coordinate_frame_id"] == "frame_fixture_target"

    for mutation in (
        lambda doc: doc["rigid_alignment"][0].__setitem__(0, 2.0),
        lambda doc: doc["rigid_alignment"][0].__setitem__(0, -1.0),
        lambda doc: doc.update(supplied_results={"status": "PASS"}),
        lambda doc: doc["audit_policy"].update(max_contact_pair_evaluations=2_000_001),
        lambda doc: doc.pop("audit_policy"),
    ):
        value = _context()
        mutation(value)
        with pytest.raises(NumericalVerificationError):
            admit_numerical_run(value)


def test_mutated_admitted_context_is_rejected_at_factory_boundary() -> None:
    context = admit_numerical_run(_context())
    context.comparison_policy["coordinate_frame_id"] = "mutated_after_admission"
    with pytest.raises(NumericalVerificationError, match="changed_after_admission"):
        build_numerical_gate_runners({}, {}, {}, SemanticValidator(), context, "c" * 40, {})


def test_context_requires_full_comparison_vector_and_exact_source_snapshot() -> None:
    value = _context()
    del value["comparison_policy"]["hard_thresholds"]["curvature_error_normalized"]
    with pytest.raises(NumericalVerificationError, match="full_metric_vector"):
        admit_numerical_run(value)

    value = _context()
    value["comparison_policy"]["hard_thresholds"]["normal_p95_degrees"]["unit"] = "1"
    with pytest.raises(NumericalVerificationError, match="threshold_unit_invalid"):
        admit_numerical_run(value)

    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    ir = compile_closed_schedule(
        design,
        material,
        (3, 3),
        (0,),
        CompileProvenance("a" * 40, "b" * 64, (("test", "numerical"),)),
        max_stitches=100,
    )
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    context = admit_numerical_run(_context())
    with pytest.raises(NumericalVerificationError, match=r"source_snapshot\.fields_invalid"):
        build_numerical_gate_runners(
            design, material, ir, validator, context, "c" * 40, {"only_one": "d" * 64}
        )


def test_f0_claimed_convergence_requires_canonical_hash_and_complete_starts() -> None:
    forged: dict[str, Any] = {"profile": "FORWARD_CLOSED_F0_V1", "status": "CONVERGED"}
    forged["sha256"] = sha256(b"Crochet.AI\0FORWARD_CLOSED_F0_V1\0" + jcs_bytes(forged)).hexdigest()
    assert not _f0_integrity(forged, _recipe())
    forged["starts"] = []
    unsigned = {key: value for key, value in forged.items() if key != "sha256"}
    forged["sha256"] = sha256(
        b"Crochet.AI\0FORWARD_CLOSED_F0_V1\0" + jcs_bytes(unsigned)
    ).hexdigest()
    assert not _f0_integrity(forged, _recipe())


def test_f0_budget_exhaustion_is_incomplete_not_execution_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import crochet_ai.numerical_verification as numerical

    monkeypatch.setattr(numerical, "_f0_integrity", lambda _result, _recipe: True)
    gate = _f0_gate_result("V6", {"status": "BUDGET_EXHAUSTED"}, "a" * 64, _recipe(), None)
    assert gate.outcome.value == "INDETERMINATE"
    assert gate.missing_checks == ("forward_model_work_budget_exhausted_before_convergence",)


def test_factory_uses_fresh_f0_and_returns_scoped_numerical_gates() -> None:
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    ir = compile_closed_schedule(
        design,
        material,
        (3, 3),
        (0,),
        CompileProvenance("a" * 40, "b" * 64, (("test", "numerical"),)),
        max_stitches=100,
    )
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    runners = build_numerical_gate_runners(
        design,
        material,
        ir,
        validator,
        admit_numerical_run(_context()),
        "c" * 40,
        _snapshot("c" * 40),
    )
    assert set(runners.runners) == {"V6", "V7", "V8", "V10"}
    gate = runners.runners["V6"]()
    assert gate.outcome.value in {"PASS", "FAIL"}
    assert runners.runners["V6"]() is gate
    runners.runners["V7"]()
    runners.runners["V7"]()
    robustness = runners.runners["V8"]()
    runs = runners.artifacts["f0_runs"]
    assert isinstance(runs, list) and len(runs) == 5
    run = runs[0]
    assert isinstance(run, dict) and run["physical_status"] == "UNTESTED"
    assert run["comparison_eligible"] is (run["status"] == "CONVERGED")
    audits = runners.artifacts["f0_audits"]
    assert isinstance(audits, list)
    if run["status"] == "CONVERGED":
        assert gate.outcome.value == "PASS"
        assert len(audits) == 1
        assert isinstance(audits[0], dict) and audits[0]["status"] == "PASS"
    if gate.outcome.value == "PASS":
        assert len(audits) == 1
        audit = audits[0]
        assert isinstance(audit, dict)
        assert audit["status"] == "PASS"
        assert audit["authenticity"] == "NOT_ESTABLISHED"
        assert dict(gate.produced_artifact_hashes)["forward_f0_audit"] == audit["audit_sha256"]
    if robustness.outcome.value == "PASS":
        assert len(audits) == 5
        assert all(isinstance(audit, dict) and audit["status"] == "PASS" for audit in audits)


def test_mesh_target_requires_exact_sampling_profile_and_reference_bound_bytes() -> None:
    from test_v0_mesh_preflight import BUDGETS, FACES, VERTICES, _inputs, _raw

    raw_mesh = _raw(VERTICES, FACES)
    design_model, material_model = _inputs(raw_mesh)
    design, material = design_model.to_dict(), material_model.to_dict()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    ir = compile_closed_schedule(
        design,
        material,
        (3, 3),
        (0,),
        CompileProvenance("a" * 40, "b" * 64, (("test", "numerical-mesh"),)),
        max_stitches=100,
    )
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    raw_context = _context()
    raw_context["target_sampling"] = {
        "profile": "MESH_ADMITTED_TARGET_SURFACE_V1",
        "schema_version": "1.0.0",
    }
    raw_context["comparison_policy"]["coordinate_frame_id"] = "frame_fixture_target"
    context = admit_numerical_run(raw_context)
    args = (
        design,
        material,
        ir,
        validator,
        context,
        "c" * 40,
        _snapshot("c" * 40),
    )
    with pytest.raises(NumericalVerificationError, match="mesh_target_bytes_and_budgets_required"):
        build_numerical_gate_runners(*args)
    with pytest.raises(NumericalVerificationError, match="mesh_target_v0_admission_failed"):
        build_numerical_gate_runners(*args, mesh_json=raw_mesh + b" ", mesh_budgets=BUDGETS)
    raw_context["target_sampling"] = {
        "profile": "ANALYTIC_TARGET_SURFACE_SAMPLING_V1",
        "schema_version": "1.0.0",
        "ring_count": 4,
        "azimuth_sectors": 8,
    }
    with pytest.raises(NumericalVerificationError, match="mesh_target_sampling_profile_invalid"):
        build_numerical_gate_runners(
            *args[:4],
            admit_numerical_run(raw_context),
            *args[5:],
            mesh_json=raw_mesh,
            mesh_budgets=BUDGETS,
        )


@pytest.mark.parametrize("mutation", ["omitted", "invented", "position", "loose", "dangling"])
def test_factory_rejects_unbound_or_weakened_design_landmarks(mutation: str) -> None:
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["landmarks"] = [
        {
            "landmark_id": "landmark_fixture_tip",
            "label": "Required tip",
            "coordinate_frame_id": "frame_fixture_target",
            "position_mm": [0, 20, 0],
            "tolerance_mm": 0.5,
            "importance": "CRITICAL",
        }
    ]
    ir = compile_closed_schedule(
        design,
        material,
        (3, 3),
        (0,),
        CompileProvenance("a" * 40, "b" * 64, (("test", "landmark-binding"),)),
        max_stitches=100,
    )
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    raw = _context()
    nomination = {
        "name": "landmark_fixture_tip",
        "predicted_vertex_index": 0,
        "target_xyz_mm": [0, 20, 0],
    }
    raw["comparison_policy"]["landmarks"] = [nomination]
    commit = "c" * 40
    build_numerical_gate_runners(
        design, material, ir, validator, admit_numerical_run(raw), commit, _snapshot(commit)
    )
    if mutation == "omitted":
        raw["comparison_policy"]["landmarks"] = []
        expected = "requirement_set_mismatch"
    elif mutation == "invented":
        nomination["name"] = "landmark_invented"
        expected = "requirement_set_mismatch"
    elif mutation == "position":
        nomination["target_xyz_mm"] = [0, 0, 0]
        expected = "target_position_mismatch"
    elif mutation == "loose":
        raw["comparison_policy"]["hard_thresholds"]["landmark_max_normalized"]["value"] = 1
        expected = "exceeds_design_tolerance"
    else:
        nomination["predicted_vertex_index"] = 511
        expected = "prediction_vertex_invalid"
    with pytest.raises(NumericalVerificationError, match=expected):
        build_numerical_gate_runners(
            design, material, ir, validator, admit_numerical_run(raw), commit, _snapshot(commit)
        )


def test_context_rejects_oversized_integer_audit_tolerance_without_overflow() -> None:
    raw = _context()
    raw["audit_policy"]["energy_abs_tolerance_n_mm"] = 10**500
    with pytest.raises(NumericalVerificationError, match="tolerance_invalid"):
        admit_numerical_run(raw)
