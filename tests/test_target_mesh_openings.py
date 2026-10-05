from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.models import DesignSpec, MaterialProfile
from crochet_ai.target_mesh_decode import MESH_MEDIA_TYPE
from crochet_ai.target_mesh_openings import (
    TargetMeshOpeningError,
    diagnose_target_mesh_openings,
)
from crochet_ai.v0_adjacent_profile import PROFILE_ID as ADJACENT_PROFILE_ID

FRAME = "frame_fixture_target"
LIMITS = {
    "max_bytes": 100_000, "max_vertices": 100, "max_faces": 100,
    "max_openings": 10, "max_landmark_refs": 20, "max_landmarks": 10,
    "max_vertex_pairs": 100, "max_landmark_edge_tests": 100,
}
VERTICES = [
    (-2., -2., 0.), (2., -2., 0.), (2., 2., 0.), (-2., 2., 0.),
    (-1., -1., 0.), (1., -1., 0.), (1., 1., 0.), (-1., 1., 0.),
]
FACES = [(0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
         (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
ROOT = Path(__file__).parent / "fixtures" / "schema-valid"


def mesh_bytes(vertices=VERTICES, faces=FACES, frame=FRAME) -> bytes:
    value = {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {"length_unit": "MILLIMETER", "handedness": "RIGHT_HANDED",
                              "coordinate_frame_id": frame},
        "vertices": [{"position_mm": list(point)} for point in vertices],
        "faces": [{"vertex_indices": list(face)} for face in faces],
    }
    return json.dumps(value, separators=(",", ":")).encode()


def documents(raw: bytes, *, openings=None, profile=None):
    design = json.loads((ROOT / "design-spec.analytic-sphere.valid.json").read_text())
    material = json.loads((ROOT / "material-profile.minimal.valid.json").read_text())
    design["material_profile"] = {"binding_type": "INLINE", "profile": material}
    design["landmarks"] = [
        {"landmark_id": "landmark_outer", "coordinate_frame_id": FRAME,
         "label": "Outer boundary point", "importance": "HIGH",
         "position_mm": [-2., -2., 0.], "tolerance_mm": 0.},
        {"landmark_id": "landmark_inner", "coordinate_frame_id": FRAME,
         "label": "Inner boundary point", "importance": "HIGH",
         "position_mm": [-1., -1., 0.], "tolerance_mm": 0.},
    ]
    design["construction_constraints"]["intentional_openings"] = deepcopy(
        openings if openings is not None else [
            {"opening_requirement_id": "opening_req_outer", "purpose": "NECKLINE",
             "boundary_landmark_ids": ["landmark_outer"],
             "closure_expectation": "REMAIN_OPEN"},
            {"opening_requirement_id": "opening_req_inner", "purpose": "ARMHOLE",
             "boundary_landmark_ids": ["landmark_inner"],
             "closure_expectation": "REMAIN_OPEN"},
        ]
    )
    design["domain_constraints"]["surface_mode"] = "DECLARED_OPENINGS"
    design["target_geometry"] = {
        "geometry_type": "MESH_3D",
        "artifact": {"artifact_id": "asset_fixture_mesh", "uri": "mesh.json",
                     "sha256": hashlib.sha256(raw).hexdigest(),
                     "media_type": MESH_MEDIA_TYPE},
        "coordinate_frame": {"coordinate_frame_id": FRAME, "handedness": "RIGHT_HANDED",
                              "length_unit": "MILLIMETER", "up_axis": "POSITIVE_Y",
                              "front_axis": "POSITIVE_Z"},
        "preflight_profile_id": "V0_AMIGURUMI_DECLARED_BOUNDARY_SURFACE_V1",
        "preflight_numerical_profile_id": "v0_num_mesh_binary64_v1",
        "topology_expectation": {"expected_connected_components": 1,
                                  "boundary_policy": "DECLARED_ONLY",
                                  "expected_boundary_components": 2,
                                  "orientability": "ORIENTABLE", "manifold_policy": "TWO_MANIFOLD",
                                  "self_intersection_policy": "FORBID",
                                  "inter_component_contact_policy": "FORBID"},
    }
    return DesignSpec.from_dict(design), MaterialProfile.from_dict(material), design


def run(raw: bytes, design: DesignSpec | None = None, **kwargs):
    if design is None:
        design, _, _ = documents(raw)
    return diagnose_target_mesh_openings(design, raw, **LIMITS, **kwargs)


def test_two_openings_have_unique_landmark_supported_bijection() -> None:
    raw = mesh_bytes()
    design, _, _ = documents(raw)
    result = run(raw, design)
    assert result.status == "OPENING_BINDING_DIAGNOSTIC_ONLY"
    assert result.classification == "UNIQUE"
    assert [(item.opening_requirement_id, item.purpose) for item in result.bindings] == [
        ("opening_req_inner", "ARMHOLE"), ("opening_req_outer", "NECKLINE")]
    assert {item.loop_index for item in result.bindings} == {0, 1}


def test_v2_profile_binds_open_mesh_with_hash_locked_slack_evidence() -> None:
    raw = mesh_bytes()
    _, _, value = documents(raw)
    value["schema_version"] = "1.1.0"
    value["target_geometry"]["preflight_numerical_profile_id"] = ADJACENT_PROFILE_ID
    value["target_geometry"]["adjacent_exclusion_zone"] = {
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": "2"},
    }
    result = run(raw, DesignSpec.from_dict(value))
    assert result.status == "OPENING_BINDING_DIAGNOSTIC_ONLY"
    assert result.classification == "UNIQUE"
    assert result.numerical_profile_id == ADJACENT_PROFILE_ID
    assert result.numerical_profile_sha256
    assert result.landmark_diagnostic_sha256
    assert len(result.bindings) == 2


def test_v2_opening_binding_rejects_unreduced_zone_and_ambiguous_landmark() -> None:
    raw = mesh_bytes()
    _, _, value = documents(raw)
    value["schema_version"] = "1.1.0"
    value["target_geometry"]["preflight_numerical_profile_id"] = ADJACENT_PROFILE_ID
    value["target_geometry"]["adjacent_exclusion_zone"] = {
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "2", "denominator": "4"},
    }
    with pytest.raises(TargetMeshOpeningError, match="design_spec_semantically_invalid"):
        run(raw, DesignSpec.from_dict(value))

    _, _, value = documents(raw)
    value["schema_version"] = "1.1.0"
    value["target_geometry"]["preflight_numerical_profile_id"] = ADJACENT_PROFILE_ID
    value["target_geometry"]["adjacent_exclusion_zone"] = {
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": "2"},
    }
    value["landmarks"][0]["position_mm"] = [0., 0., 0.]
    value["landmarks"][0]["tolerance_mm"] = 3.
    result = run(raw, DesignSpec.from_dict(value))
    assert result.classification == "AMBIGUOUS"
    assert result.reason == "openings.landmark_ambiguous"


def test_opening_and_landmark_order_do_not_change_evidence() -> None:
    raw = mesh_bytes()
    design, _, value = documents(raw)
    first = run(raw, design)
    value["construction_constraints"]["intentional_openings"].reverse()
    value["landmarks"].reverse()
    second = run(raw, DesignSpec.from_dict(value))
    assert first == second


def test_remain_open_requires_landmarks_and_reports_unmatched() -> None:
    raw = mesh_bytes()
    empty = [{"opening_requirement_id": "opening_req_empty", "purpose": "NECKLINE",
              "boundary_landmark_ids": [], "closure_expectation": "REMAIN_OPEN"},
             {"opening_requirement_id": "opening_req_other", "purpose": "ARMHOLE",
              "boundary_landmark_ids": ["landmark_inner"],
              "closure_expectation": "REMAIN_OPEN"}]
    design, _, _ = documents(raw, openings=empty)
    with pytest.raises(TargetMeshOpeningError, match="remain_open_landmarks_required"):
        run(raw, design)
    unmatched = [{"opening_requirement_id": "opening_req_empty", "purpose": "NECKLINE",
                  "boundary_landmark_ids": ["landmark_outer"],
                  "closure_expectation": "REMAIN_OPEN"},
                 {"opening_requirement_id": "opening_req_other", "purpose": "ARMHOLE",
                  "boundary_landmark_ids": ["landmark_inner"],
                  "closure_expectation": "REMAIN_OPEN"}]
    design, _, value = documents(raw, openings=unmatched)
    value["landmarks"][0]["position_mm"] = [0., 0., 0.]
    value["landmarks"][0]["tolerance_mm"] = 0.
    result = run(raw, DesignSpec.from_dict(value))
    assert result.classification == "UNMATCHED"
    assert result.reason == "openings.landmark_unmatched"


def test_ambiguous_landmark_and_split_references_fail_closed() -> None:
    raw = mesh_bytes()
    opening = [{"opening_requirement_id": "opening_req_both", "purpose": "NECKLINE",
                "boundary_landmark_ids": ["landmark_outer"],
                "closure_expectation": "REMAIN_OPEN"},
               {"opening_requirement_id": "opening_req_other", "purpose": "ARMHOLE",
                "boundary_landmark_ids": ["landmark_inner"],
                "closure_expectation": "REMAIN_OPEN"}]
    _, _, value = documents(raw, openings=opening)
    value["landmarks"][0]["position_mm"] = [0., 0., 0.]
    value["landmarks"][0]["tolerance_mm"] = 3.
    result = run(raw, DesignSpec.from_dict(value))
    assert result.classification == "AMBIGUOUS"

    split = [{"opening_requirement_id": "opening_req_split", "purpose": "NECKLINE",
              "boundary_landmark_ids": ["landmark_outer", "landmark_inner"],
              "closure_expectation": "REMAIN_OPEN"},
             {"opening_requirement_id": "opening_req_second", "purpose": "SLEEVE_OPENING",
              "boundary_landmark_ids": ["landmark_outer"],
              "closure_expectation": "REMAIN_OPEN"}]
    _, _, value = documents(raw, openings=split)
    value["target_geometry"]["topology_expectation"]["expected_boundary_components"] = 2
    result = run(raw, DesignSpec.from_dict(value))
    assert result.classification == "UNMATCHED"
    assert result.reason == "openings.landmark_refs_split"


def test_shared_and_uncovered_loops_are_not_accepted() -> None:
    raw = mesh_bytes()
    shared = [
        {"opening_requirement_id": f"opening_req_{suffix}", "purpose": "OTHER",
         "boundary_landmark_ids": ["landmark_outer"], "closure_expectation": "REMAIN_OPEN"}
        for suffix in ("a", "b")]
    _, _, value = documents(raw, openings=shared)
    value["target_geometry"]["topology_expectation"]["expected_boundary_components"] = 2
    result = run(raw, DesignSpec.from_dict(value))
    assert result.reason == "openings.shared_loop"

    unmatched = [
        {"opening_requirement_id": "opening_req_outer", "purpose": "OTHER",
         "boundary_landmark_ids": ["landmark_outer"], "closure_expectation": "REMAIN_OPEN"},
        {"opening_requirement_id": "opening_req_inner", "purpose": "OTHER",
         "boundary_landmark_ids": ["landmark_inner"], "closure_expectation": "REMAIN_OPEN"},
    ]
    _, _, value = documents(raw, openings=unmatched)
    value["landmarks"][1]["position_mm"] = [0., 0., 0.]
    value["landmarks"][1]["tolerance_mm"] = 0.
    result = run(raw, DesignSpec.from_dict(value))
    assert result.reason == "openings.landmark_unmatched"


def test_construction_time_closure_is_not_bound_to_target_loop() -> None:
    raw = mesh_bytes(VERTICES, FACES)
    opening = [{"opening_requirement_id": "opening_req_temp", "purpose": "STUFFING_OPENING",
                "boundary_landmark_ids": [], "closure_expectation": "CLOSE_DURING_CONSTRUCTION"}]
    _, _, value = documents(raw, openings=opening)
    value["target_geometry"]["preflight_profile_id"] = "V0_AMIGURUMI_CLOSED_SURFACE_V1"
    value["target_geometry"]["topology_expectation"].update(
        {"boundary_policy": "FORBIDDEN", "expected_boundary_components": 0})
    value["domain_constraints"]["surface_mode"] = "CLOSED"
    value["landmarks"] = []
    # This open mesh is rejected by the explicit exact loop-count assertion.
    with pytest.raises(TargetMeshOpeningError, match="boundary_count_mismatch"):
        run(raw, DesignSpec.from_dict(value))


def test_closed_profile_zero_loop_binding_is_trivial() -> None:
    vertices = [(0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.)]
    faces = [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)]
    raw = mesh_bytes(vertices, faces)
    _, _, value = documents(raw, openings=[])
    value["landmarks"] = []
    value["target_geometry"]["preflight_profile_id"] = "V0_AMIGURUMI_CLOSED_SURFACE_V1"
    value["target_geometry"]["topology_expectation"].update(
        {"expected_connected_components": 1, "boundary_policy": "FORBIDDEN",
         "expected_boundary_components": 0})
    value["domain_constraints"]["surface_mode"] = "CLOSED"
    result = run(raw, DesignSpec.from_dict(value))
    assert result.classification == "UNIQUE"
    assert result.reason is None
    assert result.boundary_loop_count == 0
    assert result.bindings == ()


def test_source_digest_media_frame_and_expected_counts_are_checked() -> None:
    raw = mesh_bytes()
    design, _, value = documents(raw)
    with pytest.raises(TargetMeshOpeningError, match="asset_sha256_mismatch"):
        run(raw + b" ", design)
    value["target_geometry"]["artifact"]["media_type"] = "model/obj"
    with pytest.raises(TargetMeshOpeningError, match="asset_media_type_mismatch"):
        run(raw, DesignSpec.from_dict(value))
    value["target_geometry"]["artifact"]["media_type"] = MESH_MEDIA_TYPE
    value["target_geometry"]["coordinate_frame"]["coordinate_frame_id"] = "frame_other"
    value["landmarks"][0]["coordinate_frame_id"] = "frame_other"
    value["landmarks"][1]["coordinate_frame_id"] = "frame_other"
    with pytest.raises(TargetMeshOpeningError, match="mesh_diagnostic_invalid"):
        run(raw, DesignSpec.from_dict(value))
    value["target_geometry"]["coordinate_frame"]["coordinate_frame_id"] = FRAME
    value["landmarks"][0]["coordinate_frame_id"] = FRAME
    value["landmarks"][1]["coordinate_frame_id"] = FRAME
    value["target_geometry"]["topology_expectation"]["expected_connected_components"] = 2
    with pytest.raises(TargetMeshOpeningError, match="component_count_mismatch"):
        run(raw, DesignSpec.from_dict(value))


def test_semantic_reference_and_material_binding_are_validated() -> None:
    raw = mesh_bytes()
    _, _, value = documents(raw)
    value["construction_constraints"]["intentional_openings"][0]["boundary_landmark_ids"] = [
        "landmark_missing"]
    # Schema is valid; the validator must reject the dangling reference.
    design, _, _ = documents(raw)
    with pytest.raises(TargetMeshOpeningError, match="semantically_invalid"):
        run(raw, DesignSpec.from_dict(value))

    _, material, value = documents(raw)
    value["material_profile"] = {"binding_type": "REFERENCE", "profile_id": "mp_fixture_minimal",
                                 "revision": 1, "sha256": "0" * 64}
    design, _, _ = documents(raw)
    with pytest.raises(TargetMeshOpeningError, match="semantically_invalid"):
        diagnose_target_mesh_openings(design.from_dict(value), raw, **LIMITS)
    profile_value = material.to_dict()
    value["material_profile"]["sha256"] = "f" * 64
    with pytest.raises(TargetMeshOpeningError, match="semantically_invalid"):
        diagnose_target_mesh_openings(
            design.from_dict(value), raw,
            material_profile=MaterialProfile.from_dict(profile_value), **LIMITS,
        )

    _, material, value = documents(raw)
    value["material_profile"] = {
        "binding_type": "REFERENCE", "profile_id": "mp_fixture_minimal", "revision": 1,
        "sha256": canonical_hash(material.to_dict(), CanonicalProfile.MATERIAL_PROFILE),
    }
    referenced_design = DesignSpec.from_dict(value)
    assert diagnose_target_mesh_openings(
        referenced_design, raw, material_profile=material, **LIMITS,
    ).classification == "UNIQUE"


def test_explicit_work_budgets_are_checked_before_mesh_decode() -> None:
    raw = mesh_bytes()
    design, _, _ = documents(raw)
    with pytest.raises(TargetMeshOpeningError, match="opening_budget_exhausted"):
        diagnose_target_mesh_openings(design, raw, **(LIMITS | {"max_openings": 1}))
    with pytest.raises(TargetMeshOpeningError, match="landmark_ref_budget_exhausted"):
        diagnose_target_mesh_openings(design, raw, **(LIMITS | {"max_landmark_refs": 1}))
    with pytest.raises(TargetMeshOpeningError, match="landmark_budget_exhausted"):
        diagnose_target_mesh_openings(design, raw, **(LIMITS | {"max_landmarks": 1}))


@pytest.mark.parametrize("name", tuple(LIMITS))
@pytest.mark.parametrize("invalid", [0, -1, True, 1.5])
def test_all_work_limits_reject_invalid_values(name: str, invalid: object) -> None:
    raw = mesh_bytes()
    design, _, _ = documents(raw)
    with pytest.raises(TargetMeshOpeningError, match=f"{name}_invalid"):
        diagnose_target_mesh_openings(design, raw, **(LIMITS | {name: invalid}))


def test_invalid_mapping_is_independent_of_reference_order() -> None:
    raw = mesh_bytes()
    _, _, value = documents(raw)
    value["landmarks"][0]["position_mm"] = [0., 0., 0.]
    value["landmarks"][0]["tolerance_mm"] = 3.
    value["landmarks"][1]["position_mm"] = [0., 0., 1.]
    value["construction_constraints"]["intentional_openings"][0]["boundary_landmark_ids"] = [
        "landmark_outer", "landmark_inner"]
    first = run(raw, DesignSpec.from_dict(value))
    value["construction_constraints"]["intentional_openings"][0]["boundary_landmark_ids"].reverse()
    assert run(raw, DesignSpec.from_dict(value)) == first


def test_unused_landmarks_do_not_restrict_opening_bijection() -> None:
    raw = mesh_bytes()
    _, _, value = documents(raw)
    unused = deepcopy(value["landmarks"][0])
    unused.update({"landmark_id": "landmark_unused", "position_mm": [0., 0., 5.]})
    value["landmarks"].append(unused)
    result = run(raw, DesignSpec.from_dict(value))
    assert result.classification == "UNIQUE"
    assert len(result.landmark_classifications) == 2
