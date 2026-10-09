from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from typing import cast

import pytest
from conftest import resolved_artifacts

from crochet_ai.backend_provenance import implementation_identity_hash, runtime_provenance
from crochet_ai.canonical import jcs_bytes
from crochet_ai.numerical_verification import (
    NumericalGateRunners,
    NumericalVerificationContext,
    admit_numerical_run,
)
from crochet_ai.verification_pipeline import (
    GATES,
    GateOutcome,
    GateResult,
    OverallState,
    verify_artifacts,
)


def _context() -> NumericalVerificationContext:
    from test_numerical_verification import _context as raw_context

    return admit_numerical_run(raw_context())


def test_default_pipeline_keeps_numerical_gates_unavailable(
    closed_ir: dict[str, object],
) -> None:
    design, material = resolved_artifacts()
    result = verify_artifacts(design, material, closed_ir)
    assert all(
        record.implementation_version == "adapter/1.0.0"
        for record in result.gates
        if record.gate_id in {"V6", "V7", "V8", "V10"}
    )
    assert not {"numerical_context", "software_commit", "source_snapshot"} & set(
        dict(result.gates[0].input_hashes)
    )
    assert result.physical_validation_status == "UNTESTED"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"numerical_context": "raw"},
        {"software_commit": "a" * 40},
        {"source_snapshot": {"source_snapshot_sha256": "b" * 64}},
        {"numerical_context": "raw", "software_commit": "a" * 40},
    ],
)
def test_partial_or_unadmitted_numerical_identity_is_rejected(
    closed_ir: dict[str, object], kwargs: dict[str, object]
) -> None:
    design, material = resolved_artifacts()
    with pytest.raises(ValueError, match="requires admitted context and server identity"):
        verify_artifacts(design, material, closed_ir, **cast(dict[str, object], kwargs))


def test_numerical_hashes_are_bound_into_each_gate_before_execution(
    monkeypatch: pytest.MonkeyPatch,
    closed_ir: dict[str, object],
) -> None:
    import crochet_ai.verification_pipeline as pipeline

    design, material = resolved_artifacts()
    context = _context()
    commit = "a" * 40
    provenance = runtime_provenance(commit)
    source_snapshot = {
        "source_snapshot_sha256": provenance.source_snapshot_sha256,
        "implementation_identity": implementation_identity_hash(),
    }
    seen: dict[str, object] = {}

    def factory(
        design_value: Mapping[str, object],
        material_value: Mapping[str, object],
        ir_value: Mapping[str, object],
        validator: object,
        admitted: NumericalVerificationContext,
        software_commit: str,
        snapshot: Mapping[str, str],
        *,
        mesh_json: bytes | None = None,
        mesh_budgets: object | None = None,
    ) -> NumericalGateRunners:
        del design_value, material_value, ir_value, validator
        assert admitted is context
        assert software_commit == commit
        assert dict(snapshot) == source_snapshot
        assert mesh_json is None and mesh_budgets is None
        seen["calls"] = int(cast(int, seen.get("calls", 0))) + 1
        seen["input_hashes"] = {
            "numerical_context": admitted.sha256,
            "software_commit": sha256(software_commit.encode("utf-8")).hexdigest(),
            "source_snapshot": sha256(
                b"SOURCE_SNAPSHOT_V1\0" + jcs_bytes(dict(snapshot))
            ).hexdigest(),
        }
        return NumericalGateRunners(
            {
                gate: lambda: GateResult(
                    GateOutcome.PASS, assertions=(("synthetic_test_callback", True),)
                )
                for gate in ("V6", "V7", "V8", "V10")
            },
            cast(dict[str, str], seen["input_hashes"]),
            {},
        )


    monkeypatch.setattr(pipeline, "build_numerical_gate_runners", factory)
    result = verify_artifacts(
        design,
        material,
        closed_ir,
        numerical_context=context,
        software_commit=commit,
        source_snapshot=source_snapshot,
    )
    assert seen["calls"] == 1
    assert result.physical_validation_status == "UNTESTED"
    for gate in ("V6", "V7", "V8", "V10"):
        record = next(item for item in result.gates if item.gate_id == gate)
        assert record.implementation_version == "numerical-verification/1.0.0"
        assert dict(record.input_hashes)["numerical_context"] == context.sha256
        assert dict(record.input_hashes)["source_snapshot"] == cast(
            str, seen["input_hashes"]["source_snapshot"]
        )
    assert tuple(record.gate_id for record in result.gates) == GATES
    assert result.overall_state.value != "VERIFIED"
    changed_snapshot = dict(source_snapshot)
    changed_snapshot["source_snapshot_sha256"] = "f" * 64
    with pytest.raises(
        ValueError, match="server_source_snapshot_or_implementation_identity_mismatch"
    ):
        verify_artifacts(
            design,
            material,
            closed_ir,
            numerical_context=context,
            software_commit=commit,
            source_snapshot=changed_snapshot,
        )


def test_mesh_numerical_pipeline_replays_f0_without_claiming_physical_acceptance() -> None:
    from test_analytic_solver import PROVENANCE
    from test_forward_closed_f0 import _recipe
    from test_numerical_verification import _context as raw_context
    from test_v0_mesh_preflight import BUDGETS, FACES, VERTICES, _inputs, _raw

    from crochet_ai.analytic_compile import compile_closed_schedule

    mesh_bytes = _raw(VERTICES, FACES)
    design_model, material_model = _inputs(mesh_bytes)
    design, material = design_model.to_dict(), material_model.to_dict()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    ir = compile_closed_schedule(
        design, material, (3, 4, 3), (0, 0), PROVENANCE, max_stitches=100
    )
    context_value = raw_context()
    context_value["target_sampling"] = {
        "profile": "MESH_ADMITTED_TARGET_SURFACE_V1",
        "schema_version": "1.0.0",
    }
    context_value["comparison_policy"]["coordinate_frame_id"] = "frame_fixture_target"
    recipe = _recipe()
    elastic = recipe["closed_recipe"]["elastic_recipe"]
    elastic["model_profile"]["stiffness_course_n_per_mm"] = 1e-12
    elastic["model_profile"]["stiffness_wale_n_per_mm"] = 1e-12
    elastic["rest_parameters"]["ring_stiffness_n_per_mm"] = 1e-12
    for name in ("ring_stiffness_n_per_mm", "close_stiffness_n_per_mm"):
        recipe["closed_recipe"]["closure_parameters"][name] = 1e-12
    recipe["closed_recipe"]["pressure_loading"]["pressure_n_per_mm2"] = 0
    recipe["closed_recipe"]["pressure_loading"]["volume_limit_mm3"] = 1e8
    recipe["shell_parameters"]["shear_stiffness_n_mm"] = 1e-12
    recipe["shell_parameters"]["bending_stiffness_n_mm"] = 1e-12
    recipe["contact_parameters"]["stiffness_n_per_mm"] = 1e-12
    recipe["solver_parameters"]["perturbation_mm"] = 1e-9
    context_value["forward_run"] = recipe
    context = admit_numerical_run(context_value)
    commit = PROVENANCE.software_commit
    provenance = runtime_provenance(commit)
    snapshot = {
        "source_snapshot_sha256": provenance.source_snapshot_sha256,
        "implementation_identity": implementation_identity_hash(),
    }
    result = verify_artifacts(
        design,
        material,
        ir,
        mesh_json=mesh_bytes,
        mesh_budgets=BUDGETS,
        numerical_context=context,
        software_commit=commit,
        source_snapshot=snapshot,
    )
    gates = {gate.gate_id: gate for gate in result.gates}
    assert gates["V0"].outcome is GateOutcome.PASS
    assert gates["V6"].outcome is GateOutcome.PASS, gates["V6"].linked_evidence_json
    evidence = json.loads(gates["V6"].linked_evidence_json)
    audit = evidence["independent_audit"]
    assert audit["status"] == "PASS"
    assert audit["authenticity"] == "NOT_ESTABLISHED"
    assert gates["V7"].outcome in {GateOutcome.PASS, GateOutcome.FAIL}
    comparison = json.loads(gates["V7"].linked_evidence_json)
    assert comparison["outcome"] == gates["V7"].outcome.value
    assert comparison["metrics"]
    assert json.loads(gates["V7"].metric_vector_json) == comparison["metrics"]
    assert json.loads(gates["V7"].parameters_json) == comparison["policy"]
    assert result.physical_validation_status == "UNTESTED"
    assert result.overall_state is not OverallState.VERIFIED
