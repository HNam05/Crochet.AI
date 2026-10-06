"""Hand-authored geometric counterexamples independent of adapter predicates."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from math import nextafter

import pytest
import rfc8785
from conftest import make_closed_ir, resolved_artifacts
from test_analytic_solver import PROVENANCE

from crochet_ai.analytic_target import AnalyticTargetError, admit_analytic_target
from crochet_ai.backend_api import BackendAPI
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one_isolated
from crochet_ai.validation import SemanticValidator

PROFILE = "SURFACE_OF_REVOLUTION_COORDINATE_PROFILE_CANONICAL_JSON_V1"


def explicit_design(points: list[tuple[float, float]]):
    design, material = resolved_artifacts()
    design["schema_version"] = "1.2.0"
    measurement = design["dimensions"]["measurements"][0]
    measurement.update(
        semantic="LENGTH",
        label="Full axial extent",
        value_mm=max(z for _, z in points) - min(z for _, z in points),
        tolerance_mm=0,
    )
    profile = {
        "canonicalization_profile": PROFILE,
        "samples": [
            {"sample_index": index, "radius_mm": radius, "axial_mm": z}
            for index, (radius, z) in enumerate(points)
        ],
        "start_boundary": {"boundary_type": "CLOSED_POLE"},
        "end_boundary": {"boundary_type": "CLOSED_POLE"},
    }
    # Hash the declared payload directly; no production profile projection/helper.
    profile["sha256"] = sha256(
        b"Crochet.AI\x00" + PROFILE.encode("ascii") + b"\x00" + rfc8785.dumps(profile)
    ).hexdigest()
    target = design["target_geometry"]
    target.update(
        primitive="SURFACE_OF_REVOLUTION",
        parameters=[{"parameter": "AXIAL_LENGTH", "measurement_id": measurement["measurement_id"]}],
        axis_direction=[0, 1, 0],
        radial_profile=profile,
    )
    return design, material


def admit(design, material):
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    return admit_analytic_target(design, validator)


def rehash_profile(design):
    profile = design["target_geometry"]["radial_profile"]
    payload = {key: value for key, value in profile.items() if key != "sha256"}
    profile["sha256"] = sha256(
        b"Crochet.AI\x00"
        + payload["canonicalization_profile"].encode("ascii")
        + b"\x00"
        + rfc8785.dumps(payload)
    ).hexdigest()


def verification(design, material):
    design = deepcopy(design)
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    ir = make_closed_ir()
    ir["design_spec_ref"]["sha256"] = canonical_hash(design, CanonicalProfile.DESIGN_SPEC)
    response = BackendAPI(PROVENANCE).handle(
        {
            "api_version": "1.0.0",
            "operation": "verify_candidate",
            "design_spec": design,
            "material_profile": material,
            "crochet_ir": ir,
            "mesh_json": None,
            "diagnostic_mode": True,
        }
    )
    assert response["ok"], response
    return response["data"]


@pytest.mark.parametrize(
    "points",
    [
        [(0, 0), (4, 4), (1, 4), (4, 1), (0, 5)],  # proper crossing at (2.5, 2.5)
        [(0, 0), (4, 4), (4, 0), (2, 2), (0, 5)],  # later knot touches first segment
        [(0, 0), (4, 0), (2, 0), (2, 4), (0, 4)],  # adjacent positive-length overlap
        [(0, 0), (4, 0), (4, 4), (2, 0), (0, 5)],  # exact contact with earlier disk cap
        [(0, 0), (4, 0), (4, 4), (2, nextafter(0.0, -1.0)), (0, 5)],
    ],
)
def test_hand_authored_contacts_and_crossings_reject(points):
    design, material = explicit_design(points)
    assert SemanticValidator().validate_design_spec(design).ok
    with pytest.raises(AnalyticTargetError) as caught:
        admit(design, material)
    assert caught.value.status == "INVALID_SOLVER_INPUT"


def test_smallest_positive_gap_is_not_rounded_into_a_contact():
    design, material = explicit_design(
        [
            (0, 0),
            (4, 0),
            (4, 4),
            (2, nextafter(0.0, 1.0)),
            (0, 5),
        ]
    )
    target = admit(design, material)
    assert target.to_dict()["ideal_topology"]["genus"] == 0


def test_collinear_forward_continuation_does_not_count_as_overlap():
    design, material = explicit_design(
        [
            (0, 0),
            (2, 0),
            (4, 0),
            (4, 2),
            (4, 4),
            (0, 4),
        ]
    )
    assert admit(design, material).to_dict()["ideal_topology"]["genus"] == 0


def test_full_extent_is_not_inferred_from_endpoint_displacement():
    design, material = explicit_design([(0, 1), (4, 0), (4, 6), (2, 4), (0, 5)])
    assert admit(design, material).characteristic_length_mm == 8
    design["dimensions"]["measurements"][0]["value_mm"] = 4
    with pytest.raises(AnalyticTargetError) as caught:
        admit(design, material)
    assert caught.value.status == "INVALID_SOLVER_INPUT"


@pytest.mark.parametrize("scale", [1e-6, 1.0, 1e6])
def test_exact_topological_classification_preserves_scale_without_epsilon(scale):
    valid = [(0, 0), (4, 0), (4, 4), (2, 2), (1, 4), (0, 5)]
    invalid = [(0, 0), (4, 4), (1, 4), (4, 1), (0, 5)]
    design, material = explicit_design([(r * scale, z * scale) for r, z in valid])
    assert admit(design, material).to_dict()["ideal_topology"]["genus"] == 0
    crossed, _ = explicit_design([(r * scale, z * scale) for r, z in invalid])
    with pytest.raises(AnalyticTargetError) as caught:
        admit(crossed, material)
    assert caught.value.status == "INVALID_SOLVER_INPUT"


@pytest.mark.parametrize(
    "axis,up,front",
    [
        ([1, 0, 0], "POSITIVE_X", "POSITIVE_Y"),
        ([-1, 0, 0], "NEGATIVE_X", "POSITIVE_Y"),
        ([0, 1, 0], "POSITIVE_Y", "POSITIVE_Z"),
        ([0, -1, 0], "NEGATIVE_Y", "POSITIVE_Z"),
        ([0, 0, 1], "POSITIVE_Z", "POSITIVE_X"),
        ([0, 0, -1], "NEGATIVE_Z", "POSITIVE_X"),
    ],
)
def test_signed_cardinal_frames_preserve_nonmonotone_profile(axis, up, front):
    points = [(0, 0), (4, 0), (4, 4), (2, 2), (1, 4), (0, 5)]
    design, material = explicit_design(points)
    geometry = design["target_geometry"]
    geometry["axis_direction"] = axis
    geometry["coordinate_frame"].update(up_axis=up, front_axis=front)
    geometry["origin_mm"] = [10, -20, 30]
    target = admit(design, material)
    metadata = target.to_dict()
    assert metadata["frame_basis"]["up_axis"] == axis
    assert metadata["characteristic_length_mm"] == 8
    assert metadata["ideal_topology"]["betti_numbers"] == [1, 0, 1]
    snapshot = deepcopy(metadata)
    geometry["radial_profile"]["samples"][2]["axial_mm"] = 123
    metadata["origin_mm"][0] = 999
    assert target.to_dict() == snapshot


def test_axial_reflection_changes_identity_without_guessing_direction():
    points = [(0, 0), (3, 1), (2, 4), (0, 5)]
    first, material = explicit_design(points)
    reflected, _ = explicit_design([(r, -z) for r, z in points])
    first_target = admit(first, material)
    second_target = admit(reflected, material)
    assert first_target.sha256 != second_target.sha256
    assert first_target.to_dict()["ideal_topology"] == second_target.to_dict()["ideal_topology"]
    assert (
        first["target_geometry"]["radial_profile"]["sha256"]
        != reflected["target_geometry"]["radial_profile"]["sha256"]
    )


def test_coordinate_inspection_survives_isolated_job_and_store_reopen(tmp_path):
    import json

    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    request = {
        "api_version": "1.0.0",
        "operation": "inspect_analytic_target",
        "design_spec": design,
        "material_profile": material,
    }
    snapshot = deepcopy(request)
    expected = BackendAPI(PROVENANCE).handle(request)
    assert expected["ok"], expected
    assert expected["data"]["verification_state"] == "NOT_VERIFIED"
    assert expected["data"]["physical_status"] == "UNTESTED"
    assert request == snapshot
    metadata = deepcopy(expected["data"]["target"])
    digest = metadata.pop("sha256")
    assert (
        digest
        == sha256(
            b"Crochet.AI\x00ANALYTIC_COORDINATE_TARGET_V1\x00" + rfc8785.dumps(metadata)
        ).hexdigest()
    )
    assert metadata["profile_sha256"] == design["target_geometry"]["radial_profile"]["sha256"]
    path = tmp_path / "jobs.sqlite3"
    store = JobStore(path)
    job_id = store.submit(json.dumps(request), "explicit-coordinate-test")
    assert execute_one_isolated(store, BackendAPI(PROVENANCE), max_wall_seconds=15)
    delivered = JobStore(path).get(job_id)
    assert delivered["status"] == "SUCCEEDED"
    assert delivered["result"] == expected


@pytest.mark.parametrize("coordinate_id", [True, False])
def test_profile_discriminator_cannot_select_the_other_sample_shape(coordinate_id):
    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    profile = design["target_geometry"]["radial_profile"]
    profile.pop("sha256")
    if coordinate_id:
        for sample in profile["samples"]:
            sample.pop("axial_mm")
            sample["s_mm"] = sample["sample_index"] * 5
    else:
        profile["canonicalization_profile"] = "SURFACE_OF_REVOLUTION_PROFILE_CANONICAL_JSON_V1"
        design["target_geometry"]["parameters"][0]["parameter"] = "MERIDIONAL_LENGTH"
    profile["sha256"] = sha256(
        b"Crochet.AI\x00"
        + profile["canonicalization_profile"].encode("ascii")
        + b"\x00"
        + rfc8785.dumps(profile)
    ).hexdigest()
    report = SemanticValidator().validate_design_spec(design)
    assert not report.ok
    assert any(diagnostic.code.value == "E_SCHEMA" for diagnostic in report.diagnostics)
    response = BackendAPI(PROVENANCE).handle(
        {
            "api_version": "1.0.0",
            "operation": "inspect_analytic_target",
            "design_spec": design,
            "material_profile": material,
        }
    )
    assert not response["ok"]
    assert response["error"]["code"] == "E_INPUT"


@pytest.mark.parametrize("malformed", [None, [], False, {"radial_profile": []}])
def test_invalid_target_still_returns_structured_verification_rejection(malformed):
    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    design["target_geometry"] = malformed
    response = BackendAPI(PROVENANCE).handle(
        {
            "api_version": "1.0.0",
            "operation": "verify_candidate",
            "design_spec": design,
            "material_profile": material,
            "crochet_ir": make_closed_ir(),
            "mesh_json": None,
            "diagnostic_mode": True,
        }
    )
    assert response["ok"], response
    assert response["data"]["verification_state"] == "REJECTED"
    v1 = next(gate for gate in response["data"]["gates"] if gate["gate_id"] == "V1")
    assert v1["outcome"] == "FAIL"
    assert any(diagnostic["code"] == "E_SCHEMA" for diagnostic in v1["diagnostics"])


def test_fixed_knot_ceiling_has_complete_pair_and_witness_accounting():
    points = [(0, 0), *[(1, z) for z in range(1, 128)], (0, 128)]
    design, material = explicit_design(points)
    target = admit(design, material)
    assert target.segment_pair_checks == target.segment_pair_limit == 8128
    assert target.to_dict()["admission"]["finite_distinct_cardinal_witness_count"] == 510
    too_large, _ = explicit_design([(0, 0), *[(1, z) for z in range(1, 129)], (0, 129)])
    assert not SemanticValidator().validate_design_spec(too_large).ok
    with pytest.raises(AnalyticTargetError):
        admit(too_large, material)


@pytest.mark.parametrize(
    "points",
    [
        [(1, 0), (2, 2), (0, 4)],
        [(0, 0), (2, 2), (1, 4)],
        [(0, 0), (2, 1), (0, 2), (2, 3), (0, 4)],
        [(0, 0), (2, 2), (2, 2), (0, 4)],
        [(0, 0), (2, 2), (0, 0)],
    ],
)
def test_pole_and_nonzero_segment_preconditions_are_geometric_failures(points):
    design, material = explicit_design(points)
    assert SemanticValidator().validate_design_spec(design).ok
    with pytest.raises(AnalyticTargetError) as error:
        admit(design, material)
    assert error.value.status == "INVALID_SOLVER_INPUT"


@pytest.mark.parametrize("axis", [[0, -1, 0], [0.6, 0.8, 0]])
def test_valid_but_unsupported_axes_remain_inapplicable(axis):
    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    design["target_geometry"]["axis_direction"] = axis
    assert SemanticValidator().validate_design_spec(design).ok
    with pytest.raises(AnalyticTargetError) as error:
        admit(design, material)
    assert error.value.status == "NOT_APPLICABLE"


def test_boundary_classification_is_not_inferred_from_zero_radius():
    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    design["target_geometry"]["radial_profile"]["start_boundary"]["boundary_type"] = (
        "CONSTRUCTION_INTERFACE"
    )
    rehash_profile(design)
    assert SemanticValidator().validate_design_spec(design).ok
    with pytest.raises(AnalyticTargetError) as error:
        admit(design, material)
    assert error.value.status == "NOT_APPLICABLE"


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
def test_frozen_versions_reject_coordinate_extension(version):
    design, _ = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    design["schema_version"] = version
    assert not SemanticValidator().validate_design_spec(design).ok


def test_additive_version_preserves_native_sphere_and_ambiguous_old_profile():
    sphere, material = resolved_artifacts()
    sphere["schema_version"] = "1.2.0"
    assert admit(sphere, material).to_dict()["version"] == "ANALYTIC_TARGET_V1"
    design, _ = explicit_design([(0, 0), (3, 4), (0, 8)])
    design["dimensions"]["measurements"][0]["value_mm"] = 10
    design["target_geometry"]["parameters"][0]["parameter"] = "MERIDIONAL_LENGTH"
    profile = design["target_geometry"]["radial_profile"]
    profile["canonicalization_profile"] = "SURFACE_OF_REVOLUTION_PROFILE_CANONICAL_JSON_V1"
    profile["samples"] = [
        {"sample_index": 0, "s_mm": 0, "radius_mm": 0},
        {"sample_index": 1, "s_mm": 5, "radius_mm": 3},
        {"sample_index": 2, "s_mm": 10, "radius_mm": 0},
    ]
    rehash_profile(design)
    assert SemanticValidator().validate_design_spec(design).ok
    with pytest.raises(AnalyticTargetError) as error:
        admit(design, material)
    assert error.value.status == "NOT_APPLICABLE"


@pytest.mark.parametrize("mutation", ["hash", "index", "extra_s"])
def test_malformed_coordinate_profile_fails_before_target_decoding(mutation):
    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    profile = design["target_geometry"]["radial_profile"]
    if mutation == "hash":
        profile["sha256"] = "0" * 64
    elif mutation == "index":
        profile["samples"][1]["sample_index"] = 7
        rehash_profile(design)
    else:
        profile["samples"][1]["s_mm"] = 5
        rehash_profile(design)
    assert not SemanticValidator().validate_design_spec(design).ok
    with pytest.raises(AnalyticTargetError) as error:
        admit(design, material)
    assert error.value.status == "INVALID_SOLVER_INPUT"


@pytest.mark.parametrize(
    "radius,origin",
    [
        (1, [1e308, 1e308, 1e308]),
        (1e308, [0, 0, 0]),
        (1e308, [1e308, 0, 0]),
    ],
)
def test_binary64_world_witness_or_extent_failure_rejects(radius, origin):
    design, material = explicit_design([(0, 0), (radius, 0), (radius, 6), (0, 6)])
    design["target_geometry"]["origin_mm"] = origin
    with pytest.raises(AnalyticTargetError) as error:
        admit(design, material)
    assert error.value.status == "INVALID_SOLVER_INPUT"


def test_v0_distinguishes_ideal_target_proof_contradiction_and_unsupported_scope():
    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    data = verification(design, material)
    v0 = data["gates"][0]
    assert v0["outcome"] == "PASS"
    assert v0["implementation_version"] == "analytic-coordinate-target-adapter/1.0.0"
    assert v0["linked_evidence"]["version"] == "ANALYTIC_COORDINATE_TARGET_V1"
    assert v0["work_budget"]["maximum_segment_pairs"] == 8128
    assert v0["work_budget"]["finite_distinct_cardinal_witness_count"] == 10
    assert data["verification_state"] != "VERIFIED"
    assert data["physical_status"] == "UNTESTED"
    crossed, _ = explicit_design([(0, 0), (4, 4), (1, 4), (4, 1), (0, 5)])
    bad = verification(crossed, material)["gates"][0]
    assert bad["outcome"] == "FAIL"
    assert bad["diagnostics"][0]["code"] == "E_INPUT"
    design["target_geometry"]["axis_direction"] = [0, -1, 0]
    unsupported = verification(design, material)["gates"][0]
    assert unsupported["outcome"] == "INDETERMINATE"
    assert unsupported["diagnostics"][0]["code"] == "E_UNSUPPORTED_FEATURE"


def test_inspection_requires_exact_resolved_material_binding():
    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    material["revision"] += 1
    response = BackendAPI(PROVENANCE).handle(
        {
            "api_version": "1.0.0",
            "operation": "inspect_analytic_target",
            "design_spec": design,
            "material_profile": material,
        }
    )
    assert not response["ok"]
    assert response["error"]["code"] == "E_INPUT"
