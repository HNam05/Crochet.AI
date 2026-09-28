from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256

import pytest
from conftest import make_closed_ir, make_split_join_ir, resolved_artifacts, resolved_validator
from ring_fixtures import make_multi_ring_ir

from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.diagnostics import ArtifactValidationError
from crochet_ai.physical_projection import (
    PhysicalProjectionError,
    PhysicalSemanticProjection,
)
from crochet_ai.validation import SemanticValidator


def project(value):
    _, material = resolved_artifacts()
    return PhysicalSemanticProjection(value, material, validator=resolved_validator())


@pytest.mark.parametrize("factory", [make_closed_ir, make_multi_ring_ir])
def test_projection_preserves_construction_and_is_immutable(factory) -> None:
    value = factory()
    projection = project(value)
    physical = projection.to_dict()
    assert len(physical["stitches"]) == len(value["stitches"])
    assert physical["course_order"] == value["course_order"]
    assert (
        projection.sha256
        == sha256(
            b"Crochet.AI\0FORWARD_PHYSICAL_SEMANTICS_V1\0" + projection.canonical_bytes
        ).hexdigest()
    )
    for prohibited in ("design_spec_ref", "derivations", "provenance", "colors", "color_id"):
        assert f'"{prohibited}"'.encode() not in projection.canonical_bytes
    physical["stitches"].clear()
    value["stitches"].clear()
    assert projection.to_dict()["stitches"]
    with pytest.raises(FrozenInstanceError):
        projection.sha256 = "changed"


@pytest.mark.parametrize("mutation", ["target", "seed", "generator", "derivation", "color"])
def test_excluded_source_changes_cannot_influence_physical_bytes(mutation: str) -> None:
    source = make_multi_ring_ir()
    original = project(source)
    value = deepcopy(source)
    if mutation == "target":
        value["provenance"]["input_artifacts"] = [
            {
                "artifact_id": "asset_changed",
                "artifact_role": "TARGET_GEOMETRY",
                "sha256": "f" * 64,
            }
        ]
    elif mutation == "seed":
        value["provenance"]["random_seed"] = 123
    elif mutation == "generator":
        value["provenance"]["generator"]["name"] = "unrelated-solver"
        value["provenance"]["solver_parameters"] = [{"name": "target_seed", "value": 99}]
        value["provenance"]["solver_parameters_sha256"] = "e" * 64
    elif mutation == "derivation":
        for row in value["derivations"]:
            row["parameter_sha256"] = "d" * 64
    else:
        value["colors"][0]["srgb_hex"] = "#FF0000"
        value["colors"][0]["label"] = "Different appearance"
    assert project(value).canonical_bytes == original.canonical_bytes


def test_design_identity_does_not_enter_projection() -> None:
    value = make_multi_ring_ir()
    original = project(value)
    design, material = resolved_artifacts()
    design["design_spec_id"] = "ds_other_target"
    design["dimensions"]["measurements"][0]["value_mm"] = 900
    value["design_spec_ref"] = {
        "design_spec_id": design["design_spec_id"],
        "sha256": canonical_hash(design, CanonicalProfile.DESIGN_SPEC),
    }
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    changed = PhysicalSemanticProjection(value, material, validator=validator)
    assert changed.canonical_bytes == original.canonical_bytes


def test_table_order_is_not_physical_order() -> None:
    value = make_multi_ring_ir()
    original = project(value)
    for table in value.values():
        if isinstance(table, list) and table and isinstance(table[0], dict):
            table.reverse()
    assert project(value).canonical_bytes == original.canonical_bytes
    assert project(make_multi_ring_ir(4)).sha256 != original.sha256


def test_corrupt_and_unsupported_construction_never_project() -> None:
    value = make_multi_ring_ir()
    value["stitches"][0]["base_attachment_location_ids"] = ["loc_missing"]
    with pytest.raises(ArtifactValidationError):
        project(value)
    with pytest.raises(PhysicalProjectionError, match="unsupported_construction"):
        project(make_split_join_ir())


def test_different_material_and_target_injection_fail() -> None:
    value = make_multi_ring_ir()
    _, material = resolved_artifacts()
    material["yarn"]["description"] = "Different content identity"
    with pytest.raises(PhysicalProjectionError, match="material_binding"):
        PhysicalSemanticProjection(value, material, validator=resolved_validator())
    with pytest.raises(TypeError):
        PhysicalSemanticProjection(value, material, validator=resolved_validator(), target_mesh={})
    value["stitches"][0]["target_position"] = [1, 2, 3]
    with pytest.raises(ArtifactValidationError):
        project(value)
