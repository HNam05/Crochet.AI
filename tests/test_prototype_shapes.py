from __future__ import annotations

import subprocess
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

import pytest

from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.prototype_backend import LocalPrototype
from crochet_ai.prototype_input import PROTOTYPE_VERSION, assemble_request
from crochet_ai.prototype_shapes import (
    SHAPE_CATALOG,
    coordinate_profile,
    radial_profile,
    shape_label,
)
from crochet_ai.prototype_storage import PrototypeStore
from crochet_ai.schema import validate_schema

BASE_REQUEST = {
    "prototype_version": PROTOTYPE_VERSION,
    "shape": "sphere",
    "diameter_mm": 40,
    "height_mm": 40,
    "stitches_per_100mm": 25,
    "courses_per_100mm": 28,
    "hook_diameter_mm": 3,
    "yarn_label": "Testgarn",
    "color_hex": "#B88757",
    "uncertainty_percent": 10,
}


def _commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.parametrize(
    ("shape", "diameter", "height"),
    (
        ("cylinder", 40, 40), ("cone", 40, 40),
        ("capsule", 30, 50), ("pear", 40, 55),
    ),
)
def test_each_added_shape_builds_a_valid_deterministic_closed_candidate(
    tmp_path: Path, shape: str, diameter: float, height: float,
) -> None:
    request = {**BASE_REQUEST, "shape": shape, "diameter_mm": diameter, "height_mm": height}
    design, _, _ = assemble_request(request, software_commit=_commit(), working_tree_dirty=True)
    target = design["target_geometry"]
    profile = target["radial_profile"]
    payload = {key: value for key, value in profile.items() if key != "sha256"}
    assert validate_schema("design_spec", design).ok
    assert design["schema_version"] == "1.2.0"
    assert target["primitive"] == "SURFACE_OF_REVOLUTION"
    assert profile["sha256"] == canonical_hash(
        payload, CanonicalProfile.SURFACE_OF_REVOLUTION_COORDINATES
    )
    samples = profile["samples"]
    assert len(samples) <= 129
    assert samples[0]["axial_mm"] == 0 and samples[0]["radius_mm"] == 0
    assert samples[-1]["radius_mm"] == 0
    assert samples[-1]["axial_mm"] == height
    assert max(sample["radius_mm"] for sample in samples) == diameter / 2
    for index, sample in enumerate(samples):
        assert sample["sample_index"] == index
        assert set(sample) == {"sample_index", "radius_mm", "axial_mm"}
    again, _, _ = assemble_request(request, software_commit=_commit(), working_tree_dirty=True)
    assert again["target_geometry"] == target

    store = PrototypeStore(tmp_path / shape)
    try:
        generated = LocalPrototype(store, _commit()).generate(request)
    finally:
        store.close()
    assert generated["generation"]["status"] == "CANDIDATES_EMITTED"
    assert generated["semantic_validation"] == "PASS"
    assert generated["verification_state"] == "NOT_VERIFIED"
    ir = generated["crochet_ir"]
    assert len(ir["courses"]) > 0
    assert generated["round_trip_state"] == "PASS"
    assert ir["crochet_ir_id"] == "cir_analytic"
    assert generated["project_id"] == generated["source_crochet_ir_sha256"]
    stitches = {item["stitch_id"]: item for item in ir["stitches"]}
    events = {item["event_id"]: item for item in ir["construction_sequence"]}
    frontiers = {item["frontier_id"]: item for item in ir["frontiers"]}
    for course in ir["courses"]:
        incoming = frontiers[course["input_frontier_ids"][0]]["attachment_location_ids"]
        cursor = 0
        for event_id in course["member_event_ids"]:
            subject = events[event_id]["subject_ref"]
            stitch = stitches[subject["stitch_id"]]
            width = len(stitch["base_attachment_location_ids"])
            assert stitch["base_attachment_location_ids"] == [
                incoming[(cursor + offset) % len(incoming)] for offset in range(width)
            ]
            cursor += width


def test_versioned_catalog_and_capsule_constraints_and_scale() -> None:
    assert {item["id"] for item in SHAPE_CATALOG} == {
        "sphere", "ellipsoid", "cylinder", "cone", "capsule", "pear",
    }
    assert shape_label("capsule") == "Kapsel"
    with pytest.raises(ValueError, match=r"request\.shape"):
        shape_label("torus")
    with pytest.raises(ValueError, match=r"request\.capsule_height"):
        radial_profile("capsule", 40, 39)

    coordinate, provenance = coordinate_profile("cylinder", 40, 40)
    assert coordinate["canonicalization_profile"] == (
        CanonicalProfile.SURFACE_OF_REVOLUTION_COORDINATES.value
    )
    assert provenance["profile_design_id"] == "prototype_cylinder_coordinate_silhouette_v1"
    # The historical radial_profile writer remains callable with its old contract.
    legacy, _ = radial_profile("cylinder", 40, 40)
    assert legacy["canonicalization_profile"] == CanonicalProfile.SURFACE_OF_REVOLUTION.value
    assert set(legacy["samples"][0]) == {"sample_index", "s_mm", "radius_mm"}

    base, _ = radial_profile("pear", 40, 55)
    scaled, _ = radial_profile("pear", 80, 110)
    assert len(base["samples"]) == len(scaled["samples"]) == 129
    for small, large in zip(base["samples"], scaled["samples"], strict=True):
        assert large["radius_mm"] == pytest.approx(2 * small["radius_mm"], rel=1e-14)
        assert large["s_mm"] == pytest.approx(2 * small["s_mm"], rel=1e-14)
    # At equal distances below and above the midplane, the pear's lower belly is wider.
    assert base["samples"][32]["radius_mm"] > base["samples"][96]["radius_mm"]


def test_capsule_preserves_the_straight_middle_and_join_only_deduplicates() -> None:
    long_capsule, _ = radial_profile("capsule", 30.0, 50.0)
    long_samples = long_capsule["samples"]
    lower_equator, upper_equator = long_samples[32], long_samples[33]
    assert lower_equator["radius_mm"] == upper_equator["radius_mm"] == 15.0
    assert upper_equator["s_mm"] - lower_equator["s_mm"] == pytest.approx(20.0, abs=1e-12)

    round_capsule, _ = radial_profile("capsule", 30.0, 30.0)
    assert len(round_capsule["samples"]) == 65
    assert round_capsule["samples"][32]["radius_mm"] == 15.0
    assert round_capsule["samples"][33]["radius_mm"] < 15.0


def test_decimal_dimensions_keep_exact_disk_caps_and_arc_slope_invariants() -> None:
    for shape, diameter, height in (
        ("cylinder", 41.7, 28.9),
        ("cone", 37.3, 51.7),
        ("capsule", 33.3, 51.7),
        ("pear", 42.7, 58.3),
    ):
        profile, _ = radial_profile(shape, diameter, height)
        samples = profile["samples"]
        for previous, current in pairwise(samples):
            ds = Fraction(current["s_mm"]) - Fraction(previous["s_mm"])
            dr = Fraction(current["radius_mm"]) - Fraction(previous["radius_mm"])
            assert ds > 0 and abs(dr) <= ds
    cylinder, _ = radial_profile("cylinder", 41.7, 28.9)
    disk_edge = cylinder["samples"][1]
    assert Fraction(disk_edge["s_mm"]) == Fraction(disk_edge["radius_mm"])


def test_profile_resolution_records_meaning_without_claiming_an_error_bound() -> None:
    profile, provenance = radial_profile("cylinder", 40, 40)
    assert provenance["profile_design_id"] == "prototype_cylinder_silhouette_v1"
    assert provenance["profile_resolution_sample_count"] == len(profile["samples"]) == 4
    assert "not a certified Hausdorff error bound" in provenance["profile_resolution_error_meaning"]
    assert profile["start_boundary"] == profile["end_boundary"] == {"boundary_type": "CLOSED_POLE"}
