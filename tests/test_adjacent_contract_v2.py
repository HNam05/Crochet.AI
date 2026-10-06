from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest
import rfc8785

from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.models import DesignSpec, MaterialProfile
from crochet_ai.schema import schema_documents, validate_schema
from crochet_ai.target_mesh_openings import diagnose_target_mesh_openings
from crochet_ai.v0_adjacent_profile import (
    PROFILE_DOMAIN,
    PROFILE_FILENAME,
    PROFILE_ID,
    PROFILE_SHA256,
    AdjacentProfileError,
    parse_adjacent_exclusion_zone,
    resolve_v0_adjacent_numeric_profile,
)
from crochet_ai.v0_numeric_profile import resolve_v0_numeric_profile
from crochet_ai.validation import SemanticValidator

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "profiles" / PROFILE_FILENAME
FIXTURES = ROOT / "tests" / "fixtures" / "schema-valid"


def _design(version: str = "1.1.0", *, new_profile: bool, zone: object = None) -> dict:
    value = json.loads((FIXTURES / "design-spec.analytic-sphere.valid.json").read_text())
    material = json.loads((FIXTURES / "material-profile.minimal.valid.json").read_text())
    value["schema_version"] = version
    value["material_profile"]["sha256"] = canonical_hash(
        material, CanonicalProfile.MATERIAL_PROFILE
    )
    target = {
        "geometry_type": "MESH_3D",
        "artifact": {
            "artifact_id": "asset_fixture_mesh",
            "uri": "mesh.json",
            "sha256": "1" * 64,
            "media_type": "application/vnd.crochet.indexed-triangle-mesh+json",
        },
        "coordinate_frame": {
            "coordinate_frame_id": "frame_fixture_target",
            "handedness": "RIGHT_HANDED",
            "length_unit": "MILLIMETER",
            "up_axis": "POSITIVE_Y",
            "front_axis": "POSITIVE_Z",
        },
        "preflight_profile_id": "V0_AMIGURUMI_CLOSED_SURFACE_V1",
        "preflight_numerical_profile_id": PROFILE_ID if new_profile else "v0_num_mesh_binary64_v1",
        "topology_expectation": {
            "expected_connected_components": 1,
            "boundary_policy": "FORBIDDEN",
            "expected_boundary_components": 0,
            "orientability": "ORIENTABLE",
            "manifold_policy": "TWO_MANIFOLD",
            "self_intersection_policy": "FORBID",
            "inter_component_contact_policy": "FORBID",
        },
    }
    if zone is not None:
        target["adjacent_exclusion_zone"] = zone
    value["target_geometry"] = target
    return value


def _semantic(value: dict) -> tuple[str, ...]:
    material = json.loads((FIXTURES / "material-profile.minimal.valid.json").read_text())
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    return tuple(item.message_key for item in validator.validate_design_spec(value).diagnostics)


def _design_hash(value: dict) -> str:
    material = json.loads((FIXTURES / "material-profile.minimal.valid.json").read_text())
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    return canonical_hash(value, CanonicalProfile.DESIGN_SPEC, validator=validator)


def test_v1_remains_valid_and_rejects_v2_profile_and_zone() -> None:
    legacy = _design("1.0.0", new_profile=False)
    assert validate_schema("design_spec", legacy).ok
    legacy["target_geometry"]["preflight_numerical_profile_id"] = PROFILE_ID
    assert not validate_schema("design_spec", legacy).ok
    legacy["target_geometry"]["preflight_numerical_profile_id"] = "v0_num_mesh_binary64_v1"
    legacy["target_geometry"]["adjacent_exclusion_zone"] = {
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1", "lambda": {"numerator": "1", "denominator": "2"}
    }
    assert not validate_schema("design_spec", legacy).ok
    assert resolve_v0_numeric_profile("v0_num_mesh_binary64_v1").profile_version == "1.0.0"


def test_v1_1_accepts_legacy_profile_without_zone_and_v2_with_zone() -> None:
    legacy = _design(new_profile=False)
    assert validate_schema("design_spec", legacy).ok
    assert not any("adjacent" in key for key in _semantic(legacy))

    adjacent = _design(new_profile=True, zone={
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": "2"},
    })
    assert validate_schema("design_spec", adjacent).ok
    assert not any("adjacent" in key for key in _semantic(adjacent))


def test_v2_zone_is_required_and_forbidden_for_legacy_profile() -> None:
    assert not validate_schema("design_spec", _design(new_profile=True)).ok
    legacy = _design(new_profile=False, zone={
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": "2"},
    })
    assert not validate_schema("design_spec", legacy).ok


def test_new_schema_dispatch_keeps_design_v1_and_profile_v0_gate_assignments() -> None:
    design = _design(new_profile=True, zone={
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": "2"},
    })
    design["schema_version"] = "1.2.0"
    assert validate_schema("design_spec", design).ok
    design["schema_version"] = "1.3.0"
    assert validate_schema("design_spec", design).diagnostics[0].gate == "V1"
    profile = json.loads(PROFILE_PATH.read_text())
    profile["profile_version"] = "2.1.0"
    assert validate_schema("numerical_geometry_profile", profile).diagnostics[0].gate == "V0"
    assert set(schema_documents()) == {
        "design_spec", "material_profile", "crochet_ir", "crochet_ir_1_1",
        "indexed_triangle_mesh", "numerical_geometry_profile",
    }
    assert set(schema_documents(include_additive_versions=True)) == {
        "design_spec", "design_spec_1_1", "design_spec_1_2", "material_profile", "crochet_ir",
        "crochet_ir_1_1", "indexed_triangle_mesh", "numerical_geometry_profile",
        "numerical_geometry_profile_1_1",
    }


@pytest.mark.parametrize("bad", [
    None,
    {"policy_id": "BARYCENTRIC_PAIR_LOCAL_V1", "lambda": {"numerator": 1, "denominator": "2"}},
    {"policy_id": "BARYCENTRIC_PAIR_LOCAL_V1", "lambda": {"numerator": True, "denominator": "2"}},
    {"policy_id": "BARYCENTRIC_PAIR_LOCAL_V1", "lambda": {"numerator": 1.0, "denominator": "2"}},
    {"policy_id": "BARYCENTRIC_PAIR_LOCAL_V1", "lambda": {"numerator": "01", "denominator": "2"}},
    {"policy_id": "BARYCENTRIC_PAIR_LOCAL_V1", "lambda": {"numerator": "1\n", "denominator": "2"}},
    {"policy_id": "BARYCENTRIC_PAIR_LOCAL_V1", "lambda": {"numerator": " 1", "denominator": "2"}},
    {"policy_id": "BARYCENTRIC_PAIR_LOCAL_V1", "lambda": {"numerator": "+1", "denominator": "2"}},
    {
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "\u0661", "denominator": "2"},
    },
    {"policy_id": "BARYCENTRIC_PAIR_LOCAL_V1", "lambda": {"numerator": "2", "denominator": "4"}},
    {"policy_id": "BARYCENTRIC_PAIR_LOCAL_V1", "lambda": {"numerator": "2", "denominator": "2"}},
    {"policy_id": "BARYCENTRIC_PAIR_LOCAL_V1", "lambda": {"numerator": "3", "denominator": "2"}},
    {
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": str(1 << 513)},
    },
    {
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": "2"},
        "extra": 0,
    },
])
def test_invalid_zone_is_rejected(bad: object) -> None:
    with pytest.raises(AdjacentProfileError):
        parse_adjacent_exclusion_zone(bad)


def test_trailing_newline_that_schema_pattern_can_admit_fails_semantics() -> None:
    value = _design(new_profile=True, zone={
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1\n", "denominator": "2"},
    })
    report = validate_schema("design_spec", value)
    if report.ok:
        assert "design.adjacent_exclusion_zone_invalid" in _semantic(value)
    else:
        assert all(item.code.value == "E_SCHEMA" for item in report.diagnostics)


def test_semantic_rejection_reports_input_for_unreduced_zone() -> None:
    value = _design(new_profile=True, zone={
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "2", "denominator": "4"},
    })
    diagnostic = next(
        item for item in SemanticValidator().validate_design_spec(value).diagnostics
        if item.message_key == "design.adjacent_exclusion_zone_invalid"
    )
    assert diagnostic.code.value == "E_INPUT"
    assert diagnostic.gate == "V1"
    assert diagnostic.json_pointers == ("/target_geometry/adjacent_exclusion_zone",)


def test_exact_rational_semantics_and_hash_binding() -> None:
    zone = {
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "3", "denominator": "7"},
    }
    assert parse_adjacent_exclusion_zone(zone) == Fraction(3, 7)
    value = _design(new_profile=True, zone=zone)
    changed = copy.deepcopy(value)
    changed["target_geometry"]["adjacent_exclusion_zone"]["lambda"]["numerator"] = "2"
    changed["target_geometry"]["adjacent_exclusion_zone"]["lambda"]["denominator"] = "5"
    assert _design_hash(value) != _design_hash(changed)
    reordered = json.loads(json.dumps(value))
    reordered["target_geometry"]["adjacent_exclusion_zone"] = {
        "lambda": {"denominator": "7", "numerator": "3"},
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
    }
    assert _design_hash(value) == _design_hash(reordered)


def test_profile_hash_is_independently_recomputed_and_resolver_is_hash_locked() -> None:
    value = json.loads(PROFILE_PATH.read_text())
    preimage = b"Crochet.AI\x00" + PROFILE_DOMAIN + b"\x00" + rfc8785.dumps(value)
    independent_digest = hashlib.sha256(preimage).hexdigest()
    assert independent_digest == PROFILE_SHA256
    assert resolve_v0_adjacent_numeric_profile(PROFILE_ID).record_sha256 == independent_digest
    mutated = PROFILE_PATH.read_bytes().replace(
        b"not a physical clearance", b"not physical clearance", 1
    )
    with pytest.raises(AdjacentProfileError):
        resolve_v0_adjacent_numeric_profile(PROFILE_ID, mutated)
    with pytest.raises(AdjacentProfileError):
        resolve_v0_adjacent_numeric_profile("unknown-profile")


def test_profile_schema_rejects_semantic_mutation_and_thresholds_match_v1() -> None:
    value = json.loads(PROFILE_PATH.read_text())
    assert validate_schema("numerical_geometry_profile", value).ok
    old = resolve_v0_numeric_profile("v0_num_mesh_binary64_v1")
    new = resolve_v0_adjacent_numeric_profile(PROFILE_ID)
    assert new.thresholds == old.thresholds
    bad = copy.deepcopy(value)
    bad["adjacent_exclusion_policy"]["exclusion"] = "PAIR_EITHER_INSIDE"
    assert not validate_schema("numerical_geometry_profile", bad).ok


def test_mesh_opening_diagnostic_binds_open_v2_mesh_and_rejects_ambiguous_mapping() -> None:
    mesh = {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER", "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": "frame_fixture_target",
        },
        "vertices": [{"position_mm": list(point)} for point in [
            (-2., -2., 0.), (2., -2., 0.), (2., 2., 0.), (-2., 2., 0.),
            (-1., -1., 0.), (1., -1., 0.), (1., 1., 0.), (-1., 1., 0.),
        ]],
        "faces": [{"vertex_indices": list(face)} for face in [
            (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
            (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
        ]],
    }
    raw = json.dumps(mesh, separators=(",", ":")).encode()
    design = _design(new_profile=True, zone={
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": "2"},
    })
    design["target_geometry"]["preflight_profile_id"] = (
        "V0_AMIGURUMI_DECLARED_BOUNDARY_SURFACE_V1"
    )
    design["target_geometry"]["topology_expectation"].update({
        "boundary_policy": "DECLARED_ONLY", "expected_boundary_components": 2,
    })
    design["domain_constraints"]["surface_mode"] = "DECLARED_OPENINGS"
    design["landmarks"] = [
        {"landmark_id": "landmark_outer", "coordinate_frame_id": "frame_fixture_target",
         "label": "Outer boundary", "importance": "HIGH",
         "position_mm": [-2., -2., 0.], "tolerance_mm": 0.},
        {"landmark_id": "landmark_inner", "coordinate_frame_id": "frame_fixture_target",
         "label": "Inner boundary", "importance": "HIGH",
         "position_mm": [-1., -1., 0.], "tolerance_mm": 0.},
    ]
    design["construction_constraints"]["intentional_openings"] = [
        {"opening_requirement_id": "opening_req_outer", "purpose": "NECKLINE",
         "boundary_landmark_ids": ["landmark_outer"],
         "closure_expectation": "REMAIN_OPEN"},
        {"opening_requirement_id": "opening_req_inner", "purpose": "ARMHOLE",
         "boundary_landmark_ids": ["landmark_inner"],
         "closure_expectation": "REMAIN_OPEN"},
    ]
    design["target_geometry"]["artifact"]["sha256"] = hashlib.sha256(raw).hexdigest()
    material_value = json.loads((FIXTURES / "material-profile.minimal.valid.json").read_text())
    design_model = DesignSpec.from_dict(design)
    material_model = MaterialProfile.from_dict(material_value)
    result = diagnose_target_mesh_openings(
        design_model, raw, material_profile=material_model, max_bytes=20_000,
        max_vertices=20, max_faces=20, max_openings=4, max_landmark_refs=8,
        max_landmarks=4, max_vertex_pairs=100, max_landmark_edge_tests=20,
    )
    assert result.status == "OPENING_BINDING_DIAGNOSTIC_ONLY"
    assert result.classification == "UNIQUE"
    design["landmarks"][0]["position_mm"] = [0., 0., 0.]
    design["landmarks"][0]["tolerance_mm"] = 3.
    ambiguous = diagnose_target_mesh_openings(
        DesignSpec.from_dict(design), raw, material_profile=material_model, max_bytes=20_000,
        max_vertices=20, max_faces=20, max_openings=4, max_landmark_refs=8,
        max_landmarks=4, max_vertex_pairs=100, max_landmark_edge_tests=20,
    )
    assert ambiguous.classification == "AMBIGUOUS"
    assert ambiguous.reason == "openings.landmark_ambiguous"


def test_zone_fraction_boundaries_include_one_over_largest_supported_denominator() -> None:
    denominator = (1 << 512) - 1
    assert parse_adjacent_exclusion_zone({
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": str(denominator)},
    }) == Fraction(1, denominator)
    assert math.gcd(1, denominator) == 1


def test_build_package_contains_byte_identical_v2_profile_and_schemas(tmp_path: Path) -> None:
    build_lib = tmp_path / "build"
    subprocess.run(
        [sys.executable, "setup.py", "build_py", "--build-lib", str(build_lib)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    package_root = build_lib / "crochet_ai"
    assert (package_root / "profiles" / PROFILE_FILENAME).read_bytes() == PROFILE_PATH.read_bytes()
    assert (package_root / "schemas" / "design-spec-1.1.schema.json").read_bytes() == (
        ROOT / "schemas" / "design-spec-1.1.schema.json"
    ).read_bytes()
    assert (
        package_root / "schemas" / "numerical-geometry-profile-1.1.schema.json"
    ).read_bytes() == (
        ROOT / "schemas" / "numerical-geometry-profile-1.1.schema.json"
    ).read_bytes()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(build_lib)
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from crochet_ai.v0_adjacent_profile import resolve_v0_adjacent_numeric_profile; "
            f"assert resolve_v0_adjacent_numeric_profile({PROFILE_ID!r}).record_sha256 "
            f"== {PROFILE_SHA256!r}",
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
