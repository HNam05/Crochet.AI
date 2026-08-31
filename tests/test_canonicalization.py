from __future__ import annotations

import locale
from copy import deepcopy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from crochet_ai.canonical import (
    SAFE_INTEGER,
    CanonicalizationError,
    CanonicalProfile,
    canonical_bytes,
    canonical_hash,
    canonical_projection,
    jcs_bytes,
    parse_json,
)
from crochet_ai.diagnostics import ArtifactValidationError


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (
            CanonicalProfile.DESIGN_SPEC,
            "cdad409ca7db907c63cefbf9419ded3e5d98c912727fc679ca961c41e2f65fb7",
        ),
        (
            CanonicalProfile.CROCHET_IR,
            "24b70ba3e19d9fed9d745864bdabf3dbbc691c5c0fd562e118d126ac2e79facb",
        ),
        (
            CanonicalProfile.MATERIAL_PROFILE,
            "523c79e971d664987874a04775b9c77bb9bf53fc39addeaf53f3081d8fa305e5",
        ),
        (
            CanonicalProfile.SEMANTIC_EQUIVALENCE,
            "1738a2edfbdee2bcd7a179ad9fc7f28aaa393b0eab29535f3a27b23181729da4",
        ),
    ],
)
def test_project_golden_hash_vectors(profile: CanonicalProfile, expected: str) -> None:
    value = parse_json('{"b":1.0,"a":-0,"c":1e0}')
    assert isinstance(value, dict)
    assert canonical_hash(value, profile) == expected


def test_rfc_number_sample_vector() -> None:
    value = parse_json('{"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}')
    assert isinstance(value, dict)
    assert canonical_hash(value, CanonicalProfile.DESIGN_SPEC) == (
        "bae5838c18dfb2b1582606064ffbf24f7c838f753ffa8824baeab6f0445447bc"
    )


@pytest.mark.parametrize(
    "text",
    [
        '{"a":1,"a":2}',
        '{"number":NaN}',
        '{"number":Infinity}',
        '{"number":1e400}',
        '{"number":1,5}',
        '{"number":1} trailing',
    ],
)
def test_ijson_parser_fails_closed(text: str) -> None:
    with pytest.raises(CanonicalizationError):
        parse_json(text)


def test_unsafe_integer_and_invalid_surrogate_fail() -> None:
    with pytest.raises(CanonicalizationError):
        jcs_bytes({"unsafe": SAFE_INTEGER + 1})
    with pytest.raises(CanonicalizationError):
        jcs_bytes({"invalid": "\ud800"})


def test_partial_artifact_cannot_bypass_semantic_preconditions() -> None:
    with pytest.raises(ArtifactValidationError):
        canonical_hash(
            {"schema_version": "1.0.0", "design_spec_id": "ds_partial"},
            CanonicalProfile.DESIGN_SPEC,
        )


def test_object_order_whitespace_and_number_format_are_harmless() -> None:
    variants = [
        '{"b":1.0,"a":-0,"c":1e0}',
        '{ "c" : 1, "b" : 1, "a" : 0.0 }',
        '{"a":0,"b":1,"c":1}',
    ]
    parsed = [parse_json(text) for text in variants]
    assert all(isinstance(value, dict) for value in parsed)
    hashes = {
        canonical_hash(value, CanonicalProfile.DESIGN_SPEC)
        for value in parsed
        if isinstance(value, dict)
    }
    assert len(hashes) == 1


def test_locale_does_not_enter_canonical_bytes() -> None:
    before = locale.setlocale(locale.LC_NUMERIC)
    try:
        baseline = jcs_bytes({"number": 1.5})
        for candidate in ("C", "German_Germany.1252", "de_DE.UTF-8"):
            try:
                locale.setlocale(locale.LC_NUMERIC, candidate)
            except locale.Error:
                continue
            assert jcs_bytes({"number": 1.5}) == baseline
    finally:
        locale.setlocale(locale.LC_NUMERIC, before)


def test_design_sets_sort_but_solver_preference_remains_ordered(
    design_spec: dict[str, object],
) -> None:
    left = deepcopy(design_spec)
    right = deepcopy(design_spec)
    left["difficulty_constraints"]["allowed_stitch_types"] = [
        "DOUBLE_CROCHET",
        "SINGLE_CROCHET",
    ]
    right["difficulty_constraints"]["allowed_stitch_types"] = [
        "SINGLE_CROCHET",
        "DOUBLE_CROCHET",
    ]
    assert canonical_bytes(left, CanonicalProfile.DESIGN_SPEC) == canonical_bytes(
        right, CanonicalProfile.DESIGN_SPEC
    )
    left["solver_options"]["allowed_solver_families"] = ["ANALYTIC", "GEODESIC"]
    right["solver_options"]["allowed_solver_families"] = ["ANALYTIC", "GEODESIC"]
    left["solver_options"]["solver_family_preference"] = ["ANALYTIC", "GEODESIC"]
    right["solver_options"]["solver_family_preference"] = ["GEODESIC", "ANALYTIC"]
    assert canonical_bytes(left, CanonicalProfile.DESIGN_SPEC) != canonical_bytes(
        right, CanonicalProfile.DESIGN_SPEC
    )


def test_inline_material_uses_authoritative_recursive_projection(
    design_spec: dict[str, object], material_profile: dict[str, object]
) -> None:
    left = deepcopy(design_spec)
    right = deepcopy(design_spec)
    second = deepcopy(material_profile["calibration_responses"][0]["observations"][0])
    second["specimen_id"] = "specimen_fixture_002"
    material_profile["calibration_responses"][0]["observations"].append(second)
    reversed_material = deepcopy(material_profile)
    reversed_material["calibration_responses"][0]["observations"].reverse()
    left["material_profile"] = {"binding_type": "INLINE", "profile": material_profile}
    right["material_profile"] = {"binding_type": "INLINE", "profile": reversed_material}
    assert canonical_hash(left, CanonicalProfile.DESIGN_SPEC) == canonical_hash(
        right, CanonicalProfile.DESIGN_SPEC
    )


@given(st.dictionaries(st.text(min_size=1), st.integers(-1000, 1000), max_size=12))
def test_jcs_serialization_is_idempotent(value: dict[str, int]) -> None:
    encoded = jcs_bytes(value)
    reparsed = parse_json(encoded)
    assert jcs_bytes(reparsed) == encoded


@settings(deadline=None)
@given(permutation=st.permutations(["V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7", "V10"]))
def test_design_gate_set_projection_is_permutation_invariant(permutation: list[str]) -> None:
    from conftest import load_fixture

    design_spec = load_fixture("design-spec.analytic-sphere.valid.json")
    design_spec["material_profile"] = {
        "binding_type": "INLINE",
        "profile": load_fixture("material-profile.minimal.valid.json"),
    }
    design_spec["verification_requirements"]["required_gates"] = permutation
    projection = canonical_projection(design_spec, CanonicalProfile.DESIGN_SPEC)
    assert projection["verification_requirements"]["required_gates"] == [
        "V0",
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
        "V7",
        "V10",
    ]
