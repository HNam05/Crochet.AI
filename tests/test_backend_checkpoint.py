from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
import rfc8785
from conftest import resolved_artifacts
from test_analytic_solver import PROVENANCE
from test_forward_closed_cells import admitted
from test_v0_mesh_preflight import FACES, VERTICES, _inputs, _raw

from crochet_ai.backend_api import BackendAPI
from crochet_ai.canonical import CanonicalProfile, canonical_hash, parse_json
from crochet_ai.cell_conformance import CellConformanceInputError
from crochet_ai.forward_closed_cells import build_closed_surface_cells
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one
from crochet_ai.physical_projection import PhysicalSemanticProjection
from crochet_ai.validation import SemanticValidator
from crochet_ai.verification_pipeline import GateOutcome, OverallState, verify_artifacts


def payload(design, material, ir) -> dict:
    return {
        "api_version": "1.0.0",
        "operation": "verify_candidate",
        "design_spec": design,
        "material_profile": material,
        "crochet_ir": ir,
        "mesh_json": None,
        "diagnostic_mode": False,
    }


def test_capability_matrix_is_explicit_and_cannot_be_edited_by_clients() -> None:
    api = BackendAPI(PROVENANCE)
    result = api.handle({"api_version": "1.0.0", "operation": "capabilities"})
    data = result["data"]
    assert "verify_candidate" in data["operations"]
    assert "derive_calibration_material" in data["operations"]
    assert "inspect_analytic_target" in data["operations"]
    assert data["capability_matrix"]["backend_release_ready"] is False
    assert data["verification_profiles"][0]["calibrated"] is False
    assert [row["package_id"] for row in data["capability_matrix"]["packages"]] == [
        f"B{i}" for i in range(13)
    ]
    data["capability_matrix"]["backend_release_ready"] = True
    assert (
        api.handle({"api_version": "1.0.0", "operation": "capabilities"})["data"][
            "capability_matrix"
        ]["backend_release_ready"]
        is False
    )


def test_analytic_target_inspection_matches_bound_v0_without_verification_claim(
    design_spec, material_profile, closed_ir
) -> None:
    api = BackendAPI(PROVENANCE)
    inspected = api.handle(
        {
            "api_version": "1.0.0",
            "operation": "inspect_analytic_target",
            "design_spec": design_spec,
            "material_profile": material_profile,
        }
    )
    assert inspected["ok"], inspected
    target = inspected["data"]["target"]
    assert target["ideal_topology"]["betti_numbers"] == [1, 0, 1]
    checkpoint = api.handle(payload(design_spec, material_profile, closed_ir))["data"]
    v0 = checkpoint["gates"][0]
    assert v0["outcome"] == "PASS"
    assert v0["produced_artifact_hashes"]["analytic_target"] == target["sha256"]
    assert v0["linked_evidence"] == target
    assert (
        checkpoint["verification_state"]
        == inspected["data"]["verification_state"]
        == "NOT_VERIFIED"
    )


def test_analytic_target_inspection_rejects_unbound_material(design_spec, material_profile) -> None:
    changed = deepcopy(material_profile)
    changed["yarn"]["description"] = "Changed test yarn"
    result = BackendAPI(PROVENANCE).handle(
        {
            "api_version": "1.0.0",
            "operation": "inspect_analytic_target",
            "design_spec": design_spec,
            "material_profile": changed,
        }
    )
    assert result["ok"] is False
    assert result["error"]["reason"] == "target.material_binding"


def test_closed_cells_api_builds_from_valid_ir_without_gate_or_physical_claim() -> None:
    ir, material, projection, _ = admitted((3, 4, 3))
    design, _ = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    result = BackendAPI(PROVENANCE).handle(
        {
            "api_version": "1.0.0",
            "operation": "inspect_closed_surface_cells",
            "design_spec": design,
            "material_profile": material,
            "crochet_ir": ir,
        }
    )
    assert result["ok"], result
    data = result["data"]
    assert data["surface_cells"]["status"] == "TOPOLOGY_ONLY"
    assert data["surface_cells"]["projection_sha256"] == projection.sha256
    # Ring anchors (3), then course loops 3,4,3: three annuli and two triangular caps.
    assert len(data["surface_cells"]["vertices"]) == 13
    assert len(data["surface_cells"]["faces"]) == 22
    assert data["verification_state"] == "NOT_VERIFIED"
    assert data["physical_status"] == "UNTESTED"


def test_independent_surface_audit_is_bound_and_persists_as_a_local_job(tmp_path: Path) -> None:
    ir, material, _, _ = admitted((3, 4, 3))
    design, _ = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    request = {
        "api_version": "1.0.0",
        "operation": "inspect_closed_surface_topology",
        "design_spec": design,
        "material_profile": material,
        "crochet_ir": ir,
    }
    api = BackendAPI(PROVENANCE)
    result = api.handle(request)
    assert result["ok"], result
    data = result["data"]
    audit = data["surface_topology"]
    assert audit["status"] == "PASS"
    assert audit["counts"] == {
        "vertices": 13,
        "edges": 33,
        "faces": 22,
        "components": 1,
        "euler_characteristic": 2,
    }
    assert audit["rational_homology_betti"] == {"b0": 1, "b1": 0, "b2": 1}
    assert data["verification_state"] == "NOT_VERIFIED"
    assert data["physical_status"] == "UNTESTED"
    assert api.handle_json(rfc8785.dumps(request)) == result
    assert data["cell_conformance"]["status"] == "PASS"
    assert len(data["cell_conformance_sha256"]) == 64
    request["operation"] = "inspect_closed_cell_conformance"
    assert api.handle(request) == result
    store = JobStore(tmp_path / "surface-audit.sqlite3")
    job_id = store.submit(rfc8785.dumps(request), "surface-topology")
    assert execute_one(store, api)
    completed = store.get(job_id)
    assert completed["status"] == "SUCCEEDED"
    assert completed["result"] == result


@pytest.mark.parametrize("field", ["faces", "vertices", "surface_cells", "max_faces", "evidence"])
def test_surface_audit_rejects_external_geometry_or_trusted_evidence(field: str) -> None:
    ir, material, _, _ = admitted((3,))
    design, _ = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    result = BackendAPI(PROVENANCE).handle(
        {
            "api_version": "1.0.0",
            "operation": "inspect_closed_surface_topology",
            "design_spec": design,
            "material_profile": material,
            "crochet_ir": ir,
            field: [],
        }
    )
    assert result["ok"] is False
    assert result["error"]["reason"] == "request.fields"


def _surface_case() -> tuple[dict, dict, dict, PhysicalSemanticProjection]:
    ir, material, projection, _ = admitted((3, 4, 3))
    design, _ = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    return design, material, ir, projection


def test_v4_links_independent_surface_proof_without_claiming_complete_topology() -> None:
    design, material, ir, _ = _surface_case()
    result = verify_artifacts(design, material, ir)
    v4 = result.gates[4]
    assert v4.outcome is GateOutcome.PASS
    assert dict(v4.assertions)["closed_surface_topology"] is True
    assert dict(v4.assertions)["source_cell_conformance"] is True
    assert dict(v4.assertions)["requested_topology"] is True
    assert not v4.missing_checks
    linked = json.loads(v4.linked_evidence_json)
    assert linked["cell_conformance"]["status"] == "PASS"
    assert linked["surface_topology"]["rational_homology_betti"] == {
        "b0": 1,
        "b1": 0,
        "b2": 1,
    }
    assert len(v4.produced_artifact_hashes) == 4
    assert v4.implementation_version == "closed-cell-source-adapter/1.0.0"
    assert json.loads(v4.work_budget_json)["surface_audit"]["max_faces"] == 60_000
    assert json.loads(v4.metric_vector_json)[1]["value"] == 2
    assert result.overall_state is OverallState.NOT_VERIFIED


@pytest.mark.parametrize("namespace", ["backend_api", "verification_pipeline"])
def test_faulty_builder_cannot_hide_open_surface_from_independent_audit(
    monkeypatch, namespace
) -> None:
    import importlib

    design, material, ir, projection = _surface_case()
    cells = build_closed_surface_cells(projection)
    corrupted = cells.to_dict()
    corrupted["faces"].pop()
    monkeypatch.setattr(
        importlib.import_module("crochet_ai." + namespace),
        "build_closed_surface_cells",
        lambda _projection: replace(cells, canonical_bytes=rfc8785.dumps(corrupted)),
    )
    if namespace == "backend_api":
        result = BackendAPI(PROVENANCE).handle(
            {
                "api_version": "1.0.0",
                "operation": "inspect_closed_surface_topology",
                "design_spec": design,
                "material_profile": material,
                "crochet_ir": ir,
            }
        )
        assert result["ok"]
        assert result["data"]["surface_topology"]["status"] == "FAIL"
        assert result["data"]["verification_state"] == "REJECTED"
    else:
        verified = verify_artifacts(design, material, ir)
        assert verified.gates[4].outcome is GateOutcome.FAIL
        assert verified.gates[4].diagnostics
        assert verified.overall_state is OverallState.REJECTED


def test_wrong_but_spherical_builder_output_cannot_pass_full_v4(monkeypatch) -> None:
    from test_surface_topology import tetrahedron

    design, material, ir, projection = _surface_case()
    cells = build_closed_surface_cells(projection)
    wrong_mapping = cells.to_dict()
    wrong_mapping["vertices"], wrong_mapping["faces"] = tetrahedron()
    refreshed_hash = sha256(
        b"Crochet.AI\0" + cells.profile.encode("ascii") + b"\0"
        + cells.projection_sha256.encode("ascii") + b"\0"
        + cells.rule_id.encode("ascii") + b"\0" + rfc8785.dumps(wrong_mapping)
    ).hexdigest()
    monkeypatch.setattr(
        "crochet_ai.verification_pipeline.build_closed_surface_cells",
        lambda _projection: replace(
            cells, canonical_bytes=rfc8785.dumps(wrong_mapping), sha256=refreshed_hash,
        ),
    )
    result = verify_artifacts(design, material, ir)
    assert dict(result.gates[4].assertions)["closed_surface_topology"] is True
    assert dict(result.gates[4].assertions)["source_cell_conformance"] is False
    assert result.gates[4].outcome is GateOutcome.FAIL
    assert result.overall_state is OverallState.REJECTED


def test_v4_checks_design_component_requirement_independently_of_source_mapping() -> None:
    design, material, ir, _ = _surface_case()
    mesh_design, _ = _inputs(_raw(VERTICES, FACES))
    design["schema_version"] = "1.1.0"
    design["target_geometry"] = mesh_design.to_dict()["target_geometry"]
    design["target_geometry"]["topology_expectation"]["expected_connected_components"] = 2
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    ir["design_spec_ref"]["sha256"] = canonical_hash(
        design, CanonicalProfile.DESIGN_SPEC, validator=validator,
    )
    result = verify_artifacts(design, material, ir)
    v4 = result.gates[4]
    assert dict(v4.assertions)["closed_surface_topology"] is True
    assert dict(v4.assertions)["source_cell_conformance"] is True
    assert dict(v4.assertions)["requested_topology"] is False
    assert v4.outcome is GateOutcome.FAIL
    assert json.loads(v4.diagnostics[0])["message_key"] == (
        "cell_conformance.design_topology_mismatch"
    )
    assert result.overall_state is OverallState.REJECTED


def test_v4_budget_exhaustion_is_indeterminate_and_never_passes(monkeypatch) -> None:
    design, material, ir, _ = _surface_case()

    def exhausted(*args, **kwargs):
        raise CellConformanceInputError("cell_conformance.source_table_budget_exceeded")

    monkeypatch.setattr(
        "crochet_ai.verification_pipeline.inspect_closed_cell_conformance", exhausted,
    )
    result = verify_artifacts(design, material, ir)
    assert result.gates[4].outcome is GateOutcome.INDETERMINATE
    assert "budget exhausted" in result.gates[4].missing_checks[0]
    assert result.overall_state is OverallState.NOT_VERIFIED


@pytest.mark.parametrize("field", ["target_mesh", "projection_sha256", "max_faces"])
def test_closed_cells_api_rejects_external_geometry_hash_and_budget_overrides(field: str) -> None:
    ir, material, _, _ = admitted((3,))
    design, _ = resolved_artifacts()
    request = {
        "api_version": "1.0.0",
        "operation": "inspect_closed_surface_cells",
        "design_spec": design,
        "material_profile": material,
        "crochet_ir": ir,
        field: {},
    }
    result = BackendAPI(PROVENANCE).handle(request)
    assert result["ok"] is False
    assert result["error"]["reason"] == "request.fields"


def test_wire_checkpoint_is_stable_and_has_all_eleven_gates(
    design_spec, material_profile, closed_ir
) -> None:
    request = payload(design_spec, material_profile, closed_ir)
    api = BackendAPI(PROVENANCE)
    result = api.handle(request)
    assert result["ok"], result
    assert api.handle_json(json.dumps(request)) == result
    assert parse_json(rfc8785.dumps(result)) == result
    assert result["data"]["verification_state"] == "NOT_VERIFIED"
    assert [gate["gate_id"] for gate in result["data"]["gates"]] == [f"V{i}" for i in range(11)]
    assert result["data"]["gates"][9]["outcome"] == "PASS"


@pytest.mark.parametrize(
    "name,value",
    [
        ("verification_profile", {"calibrated": True}),
        ("resume", []),
        ("server_provenance", {}),
        ("diagnostic_mode", 1),
        ("mesh_json", {}),
        ("crochet_ir", []),
        ("material_profile", None),
    ],
)
def test_client_cannot_supply_trusted_profile_evidence_or_invalid_types(
    name,
    value,
    design_spec,
    material_profile,
    closed_ir,
) -> None:
    request = payload(design_spec, material_profile, closed_ir)
    request[name] = value
    result = BackendAPI(PROVENANCE).handle(request)
    assert not result["ok"]
    assert result["error"]["code"] == "E_INPUT"


def test_real_mesh_v0_retains_raw_hash_profile_budget_and_full_evidence(closed_ir) -> None:
    raw = _raw(VERTICES, FACES)
    design, material = _inputs(raw)
    request = payload(design.to_dict(), material.to_dict(), closed_ir)
    request["crochet_ir"]["design_spec_ref"] = {
        "design_spec_id": request["design_spec"]["design_spec_id"],
        "sha256": canonical_hash(
            request["design_spec"],
            CanonicalProfile.DESIGN_SPEC,
            validator=SemanticValidator(
                material_profiles={
                    request["material_profile"]["profile_id"]: request["material_profile"]
                }
            ),
        ),
    }
    request["mesh_json"] = raw.decode("utf-8")
    result = BackendAPI(PROVENANCE).handle(request)
    assert result["ok"], result
    v0 = result["data"]["gates"][0]
    assert v0["outcome"] == "PASS"
    assert v0["input_hashes"]["raw_mesh"] == sha256(raw).hexdigest()
    assert v0["linked_evidence"]["source_sha256"] == sha256(raw).hexdigest()
    assert v0["parameters"]["numerical_profile_sha256"]
    assert v0["work_budget"]["max_vertices"] == 128
    assert v0["produced_artifact_hashes"]["normalized_mesh"]
    assert result["data"]["verification_state"] != "VERIFIED"
    request["mesh_json"] += " "  # Same data model, different immutable source bytes.
    altered = BackendAPI(PROVENANCE).handle(request)
    assert altered["ok"]
    assert altered["data"]["gates"][0]["outcome"] == "FAIL"
    assert altered["data"]["verification_state"] == "REJECTED"


def test_succeeded_durable_job_retains_unverified_artifact_state(
    tmp_path: Path,
    design_spec,
    material_profile,
    closed_ir,
) -> None:
    request = payload(design_spec, material_profile, closed_ir)
    store = JobStore(tmp_path / "jobs.sqlite3")
    job_id = store.submit(rfc8785.dumps(request), "verification-checkpoint")
    assert execute_one(store, BackendAPI(PROVENANCE))
    completed = store.get(job_id)
    assert completed["status"] == "SUCCEEDED"
    assert completed["result"]["data"]["verification_state"] == "NOT_VERIFIED"
    reopened = JobStore(tmp_path / "jobs.sqlite3")
    assert reopened.get(job_id)["result"] == completed["result"]
