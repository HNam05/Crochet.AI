from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_analytic_solver import PROVENANCE
from test_target_mesh_openings import FACES as OPEN_FACES
from test_target_mesh_openings import VERTICES as OPEN_VERTICES
from test_target_mesh_openings import documents as open_documents
from test_target_mesh_openings import mesh_bytes as open_mesh_bytes

from crochet_ai import v0_mesh_preflight
from crochet_ai.backend_api import BackendAPI
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.models import DesignSpec, MaterialProfile
from crochet_ai.target_mesh_decode import MESH_MEDIA_TYPE
from crochet_ai.v0_adjacent_profile import PROFILE_ID
from crochet_ai.v0_mesh_preflight import (
    V0MeshBudgets,
    V0MeshPreflightError,
    inspect_v0_closed_mesh_v2,
    inspect_v0_mesh_v2,
)

ROOT = Path(__file__).resolve().parents[1]
FRAME = "frame_fixture_target"
VERTICES = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
FACES = [(1, 2, 3), (0, 2, 1), (0, 1, 3), (0, 3, 2)]
BUDGETS = V0MeshBudgets(100_000, 100, 100, 100, 100, 100, 512, 2_400,
                        16, 64, 32, 16_384)


def _raw(
    vertices: list[tuple[int | float, int | float, int | float]],
    faces: list[tuple[int, int, int]],
) -> bytes:
    return json.dumps({
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {"length_unit": "MILLIMETER", "handedness": "RIGHT_HANDED",
                              "coordinate_frame_id": FRAME},
        "vertices": [{"position_mm": list(point)} for point in vertices],
        "faces": [{"vertex_indices": list(face)} for face in faces],
    }, separators=(",", ":")).encode()


def _inputs(raw: bytes) -> tuple[DesignSpec, MaterialProfile]:
    fixtures = ROOT / "tests" / "fixtures" / "schema-valid"
    design = json.loads((fixtures / "design-spec.analytic-sphere.valid.json").read_text())
    material = json.loads((fixtures / "material-profile.minimal.valid.json").read_text())
    design["schema_version"] = "1.1.0"
    design["material_profile"]["sha256"] = canonical_hash(
        material, CanonicalProfile.MATERIAL_PROFILE
    )
    design["target_geometry"] = {
        "geometry_type": "MESH_3D",
        "artifact": {"artifact_id": "asset_fixture_mesh", "uri": "mesh.json",
                     "sha256": hashlib.sha256(raw).hexdigest(), "media_type": MESH_MEDIA_TYPE},
        "coordinate_frame": {"coordinate_frame_id": FRAME, "handedness": "RIGHT_HANDED",
                             "length_unit": "MILLIMETER", "up_axis": "POSITIVE_Y",
                             "front_axis": "POSITIVE_Z"},
        "preflight_profile_id": "V0_AMIGURUMI_CLOSED_SURFACE_V1",
        "preflight_numerical_profile_id": PROFILE_ID,
        "adjacent_exclusion_zone": {
            "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
            "lambda": {"numerator": "1", "denominator": "2"},
        },
        "topology_expectation": {
            "expected_connected_components": 1, "boundary_policy": "FORBIDDEN",
            "expected_boundary_components": 0, "orientability": "ORIENTABLE",
            "manifold_policy": "TWO_MANIFOLD", "self_intersection_policy": "FORBID",
            "inter_component_contact_policy": "FORBID",
        },
    }
    return DesignSpec.from_dict(design), MaterialProfile.from_dict(material)


def _inspect(raw: bytes):
    design, material = _inputs(raw)
    return inspect_v0_closed_mesh_v2(
        design, raw, material_profile=material, budgets=BUDGETS
    )


def test_closed_tetra_passes_v0_and_reversed_component_normalizes_identically() -> None:
    positive = _inspect(_raw(VERTICES, FACES))
    negative = _inspect(_raw(VERTICES, [tuple(reversed(face)) for face in FACES]))
    assert positive.outcome == negative.outcome == "PASS"
    assert positive.normalized_mesh_sha256 == negative.normalized_mesh_sha256
    assert positive.reversed_source_components == ()
    assert negative.reversed_source_components == ((0, 1, 2, 3),)
    assert positive.evidence_sha256 != negative.evidence_sha256
    preimage = (
        b"Crochet.AI\0INDEXED_TRIANGLE_MESH_CANONICAL_JSON_V1\0"
        + positive.normalized_mesh_jcs.encode()
    )
    assert hashlib.sha256(preimage).hexdigest() == positive.normalized_mesh_sha256
    assert positive.certified_orientation_tests > 0
    assert positive.predicate_backend_version == "1.0.0"


def test_face_and_vertex_permutation_preserves_normalized_identity() -> None:
    first = _inspect(_raw(VERTICES, FACES))
    permutation = [2, 0, 3, 1]
    remap = {old: new for new, old in enumerate(permutation)}
    vertices = [VERTICES[index] for index in permutation]
    faces = [tuple(remap[index] for index in face) for face in reversed(FACES)]
    second = _inspect(_raw(vertices, faces))
    assert second.normalized_mesh_sha256 == first.normalized_mesh_sha256
    assert second.source_sha256 != first.source_sha256


def test_disjoint_closed_components_use_canonical_volume_order() -> None:
    vertices = VERTICES + [(x + 4, y, z) for x, y, z in VERTICES]
    faces = FACES + [tuple(index + 4 for index in face) for face in FACES]
    first_raw = _raw(vertices, faces)
    second_raw = _raw(vertices, list(reversed(faces)))
    first_design, material = _inputs(first_raw)
    second_design, _ = _inputs(second_raw)
    first_value = first_design.to_dict()
    second_value = second_design.to_dict()
    for value in (first_value, second_value):
        value["target_geometry"]["topology_expectation"]["expected_connected_components"] = 2
    first = inspect_v0_closed_mesh_v2(
        DesignSpec.from_dict(first_value), first_raw,
        material_profile=material, budgets=BUDGETS,
    )
    second = inspect_v0_closed_mesh_v2(
        DesignSpec.from_dict(second_value), second_raw,
        material_profile=material, budgets=BUDGETS,
    )
    assert first.normalized_mesh_sha256 == second.normalized_mesh_sha256
    assert first.volume_reference_source_vertices == (0, 4)
    assert second.volume_reference_source_vertices == (0, 4)


def test_declared_component_mismatch_and_original_overlap_fail() -> None:
    raw = _raw(VERTICES, FACES)
    design, material = _inputs(raw)
    changed = copy.deepcopy(design.to_dict())
    changed["target_geometry"]["topology_expectation"]["expected_connected_components"] = 2
    with pytest.raises(V0MeshPreflightError):
        inspect_v0_closed_mesh_v2(
            DesignSpec.from_dict(changed), raw, material_profile=material, budgets=BUDGETS
        )
    overlapping = _raw(VERTICES, [FACES[0], FACES[1], FACES[1], FACES[3]])
    with pytest.raises(V0MeshPreflightError):
        _inspect(overlapping)


def test_too_small_work_budget_cannot_pass() -> None:
    raw = _raw(VERTICES, FACES)
    design, material = _inputs(raw)
    with pytest.raises(V0MeshPreflightError) as error:
        inspect_v0_closed_mesh_v2(
            design, raw, material_profile=material,
            budgets=V0MeshBudgets(100_000, 100, 100, 5, 100, 100, 512, 2_400,
                                  16, 64, 32, 16_384),
        )
    assert error.value.outcome == "INDETERMINATE"


def test_near_folded_adjacent_faces_fail_the_new_hard_rule() -> None:
    vertices = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0.5, 2, 2 ** -45)]
    raw = _raw(vertices, FACES)
    with pytest.raises(V0MeshPreflightError) as error:
        _inspect(raw)
    assert error.value.reason == "geometry.adjacent_contact"


def test_api_exposes_v0_result_without_physical_release() -> None:
    raw = _raw(VERTICES, FACES)
    design, material = _inputs(raw)
    response = BackendAPI(PROVENANCE).handle({
        "api_version": "1.0.0", "operation": "inspect_v0_closed_mesh_v2",
        "design_spec": design.to_dict(), "material_profile": material.to_dict(),
        "mesh_json": raw.decode(),
    })
    assert response["ok"], response
    assert response["data"]["mesh_preflight_state"] == "PASS"
    assert response["data"]["verification_state"] == "NOT_VERIFIED"
    assert response["data"]["physical_status"] == "UNTESTED"
    assert response["data"]["diagnostic"]["outcome"] == "PASS"


def test_truncated_adjacent_evidence_cannot_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    original = v0_mesh_preflight.diagnose_indexed_triangle_mesh_adjacent_clearance
    monkeypatch.setattr(
        v0_mesh_preflight, "diagnose_indexed_triangle_mesh_adjacent_clearance",
        lambda *args, **kwargs: replace(original(*args, **kwargs), pairs=()),
    )
    with pytest.raises(V0MeshPreflightError) as error:
        _inspect(_raw(VERTICES, FACES))
    assert error.value.outcome == "INDETERMINATE"
    assert error.value.reason == "geometry.adjacent_evidence_incomplete"


def test_disagreeing_orientation_backend_cannot_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = v0_mesh_preflight.orientation3d

    def wrong_sign(*args, **kwargs):
        result = original(*args, **kwargs)
        return replace(result, sign=-1 if result.sign >= 0 else 1)

    monkeypatch.setattr(v0_mesh_preflight, "orientation3d", wrong_sign)
    with pytest.raises(V0MeshPreflightError) as error:
        _inspect(_raw(VERTICES, FACES))
    assert error.value.outcome == "INDETERMINATE"
    assert error.value.reason == "geometry.orientation_backend_disagreement"


def test_declared_open_mesh_requires_unique_bindings_under_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = open_mesh_bytes()
    _, material, value = open_documents(raw)
    value["schema_version"] = "1.1.0"
    value["target_geometry"]["preflight_numerical_profile_id"] = PROFILE_ID
    value["target_geometry"]["adjacent_exclusion_zone"] = {
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": "2"},
    }
    design = DesignSpec.from_dict(value)
    result = inspect_v0_mesh_v2(design, raw, material_profile=material, budgets=BUDGETS)
    assert result.outcome == "PASS"
    assert result.open_source_components == (tuple(range(8)),)
    assert result.volume_reference_source_vertices == ()
    assert any(name == "opening_binding" for name, _ in result.predicate_evidence)
    response = BackendAPI(PROVENANCE).handle({
        "api_version": "1.0.0", "operation": "inspect_v0_mesh_v2",
        "design_spec": design.to_dict(), "material_profile": material.to_dict(),
        "mesh_json": raw.decode(),
    })
    assert response["ok"], response
    assert response["data"]["mesh_preflight_state"] == "PASS"
    assert response["data"]["physical_status"] == "UNTESTED"
    with pytest.raises(V0MeshPreflightError) as old_name:
        inspect_v0_closed_mesh_v2(
            design, raw, material_profile=material, budgets=BUDGETS
        )
    assert old_name.value.code == "E_UNSUPPORTED_FEATURE"
    original = v0_mesh_preflight.diagnose_target_mesh_openings
    monkeypatch.setattr(
        v0_mesh_preflight, "diagnose_target_mesh_openings",
        lambda *args, **kwargs: replace(
            original(*args, **kwargs), numerical_profile_sha256="0" * 64
        ),
    )
    with pytest.raises(V0MeshPreflightError) as forged:
        inspect_v0_mesh_v2(design, raw, material_profile=material, budgets=BUDGETS)
    assert forged.value.outcome == "INDETERMINATE"
    assert forged.value.reason == "geometry.opening_evidence_mismatch"


def test_garment_sheet_uses_same_v2_pair_policy_with_its_domain_profile() -> None:
    raw = open_mesh_bytes()
    _, material, value = open_documents(raw)
    value["schema_version"] = "1.1.0"
    value["project_type"] = "GARMENT"
    value["domain_constraints"] = {
        "domain": "GARMENT", "body_measurement_ids": ["dim_fixture_radius"],
        "ease_allowances": [], "allowed_constructions": ["PANELS"],
    }
    value["solver_options"]["allowed_solver_families"] = ["GARMENT"]
    value["solver_options"]["solver_family_preference"] = ["GARMENT"]
    target = value["target_geometry"]
    target["preflight_profile_id"] = "V0_GARMENT_DECLARED_BOUNDARY_SURFACE_V1"
    target["preflight_numerical_profile_id"] = PROFILE_ID
    target["adjacent_exclusion_zone"] = {
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": "2"},
    }
    result = inspect_v0_mesh_v2(
        DesignSpec.from_dict(value), raw, material_profile=material, budgets=BUDGETS
    )
    assert result.outcome == "PASS"
    assert result.domain_profile_id == "V0_GARMENT_DECLARED_BOUNDARY_SURFACE_V1"
    value["dimensions"]["measurements"].append({
        "measurement_id": "dim_fixture_chest", "semantic": "BODY_CHEST_CIRCUMFERENCE",
        "label": "Chest", "value_mm": 80, "tolerance_mm": 1,
    })
    value["domain_constraints"]["body_measurement_ids"] = [
        "dim_fixture_radius", "dim_fixture_chest"
    ]
    first_hash = canonical_hash(value, CanonicalProfile.DESIGN_SPEC)
    value["domain_constraints"]["body_measurement_ids"].reverse()
    assert canonical_hash(value, CanonicalProfile.DESIGN_SPEC) == first_hash


def test_mixed_open_and_closed_components_keep_open_winding_and_check_volume() -> None:
    tetra = [(x + 10, y, z) for x, y, z in VERTICES]
    vertices = OPEN_VERTICES + tetra
    faces = OPEN_FACES + [tuple(index + len(OPEN_VERTICES) for index in face)
                          for face in FACES]
    raw = open_mesh_bytes(vertices=vertices, faces=faces)
    _, material, value = open_documents(raw)
    value["schema_version"] = "1.1.0"
    value["target_geometry"]["preflight_numerical_profile_id"] = PROFILE_ID
    value["target_geometry"]["adjacent_exclusion_zone"] = {
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": "2"},
    }
    value["target_geometry"]["topology_expectation"]["expected_connected_components"] = 2
    result = inspect_v0_mesh_v2(
        DesignSpec.from_dict(value), raw, material_profile=material, budgets=BUDGETS
    )
    assert result.outcome == "PASS"
    assert len(result.open_source_components) == 1
    assert result.volume_reference_source_vertices == (8,)
