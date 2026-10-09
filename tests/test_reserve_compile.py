from __future__ import annotations

from copy import deepcopy

import pytest
from conftest import resolved_artifacts

from crochet_ai.analytic_compile import CompileProvenance
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.reserve_compile import compile_reserve_schedule
from crochet_ai.validation import SemanticValidator


def inputs():
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("RESERVE")
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"].append("INCREASE")
    design["solver_options"]["allowed_solver_families"].append("FRONTIER")
    design["solver_options"]["random_seed"] = 17
    provenance = CompileProvenance(
        software_commit="a" * 40,
        source_snapshot_sha256="b" * 64,
        parameters=(("schedule_label", "test"),),
    )
    return design, material, provenance


def compile_case(initial=5, reserved=2, counts=(4, 4), phases=(1, 0)):
    design, material, provenance = inputs()
    return (
        compile_reserve_schedule(
            design,
            material,
            initial,
            reserved,
            counts,
            phases,
            provenance,
        ),
        design,
        material,
    )


def test_two_distinct_reserve_schedules_validate_and_are_deterministic():
    first, design, material = compile_case()
    second, _, _ = compile_case()
    third, _, _ = compile_case(initial=6, reserved=1, counts=(5,), phases=(2,))
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={
            material["profile_id"]: material,
            (material["profile_id"], material["revision"]): material,
        },
    )
    assert first == second
    assert first != third
    assert first["semantics_profile"] == "CROCHET_CORE_1.1.0"
    assert first["provenance"]["generator"]["solver_family"] == "FRONTIER"
    assert first["provenance"]["random_seed"] == 17
    assert validator.validate_crochet_ir(first).ok
    assert validator.validate_crochet_ir(third).ok
    assert [
        f["lifecycle_state"]
        for f in first["frontiers"]
        if f["frontier_id"] in first["components"][0]["terminal_frontier_ids"]
    ] == ["CLOSED", "CLOSED"]


def test_input_mutation_and_result_mutation_are_isolated():
    design, material, provenance = inputs()
    original_design_hash = canonical_hash(design, CanonicalProfile.DESIGN_SPEC)
    result = compile_reserve_schedule(design, material, 5, 2, (4,), (0,), provenance)
    assert canonical_hash(design, CanonicalProfile.DESIGN_SPEC) == original_design_hash
    design["colors"].clear()
    material["hook_diameter_mm"] += 0.25
    assert result["colors"]
    assert result["yarns"][0]["material_profile_ref"]["sha256"] != canonical_hash(
        material, CanonicalProfile.MATERIAL_PROFILE
    )
    result["stitches"].clear()
    assert not result["stitches"]


def test_budget_is_checked_before_emission():
    design, material, provenance = inputs()
    with pytest.raises(ValueError, match=r"SEARCH_BUDGET_EXHAUSTED:reserve.budget_preflight"):
        compile_reserve_schedule(
            design,
            material,
            5,
            2,
            (4, 4),
            (0, 0),
            provenance,
            max_events=5,
        )


@pytest.mark.parametrize("changed_input", ["design_binding", "material", "source"])
def test_changed_input_bindings_fail_closed(changed_input: str):
    design, material, provenance = inputs()
    if changed_input == "design_binding":
        design["material_profile"]["profile"]["hook_diameter_mm"] += 0.25
    elif changed_input == "material":
        material["hook_diameter_mm"] += 0.25
    else:
        provenance = CompileProvenance(
            software_commit=provenance.software_commit,
            source_snapshot_sha256="0" * 64,
            parameters=provenance.parameters,
        )
    with pytest.raises(ValueError):
        compile_reserve_schedule(design, material, 5, 2, (4,), (0,), provenance)


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "reserved_advance"])
def test_independent_validator_rejects_reservation_corruption(mutation: str):
    value, design, material = compile_case()
    changed = deepcopy(value)
    if mutation == "drop":
        transition = next(
            t for t in changed["frontier_transitions"] if t["transition_type"] == "RESERVE"
        )
        transition["reserved_attachment_location_ids"].pop()
    elif mutation == "duplicate":
        transition = next(
            t for t in changed["frontier_transitions"] if t["transition_type"] == "RESERVE"
        )
        transition["reserved_attachment_location_ids"].append(
            transition["reserved_attachment_location_ids"][0]
        )
    else:
        reserved = next(f for f in changed["frontiers"] if f["lifecycle_state"] == "RESERVED")
        advance = next(
            t for t in changed["frontier_transitions"] if t["transition_type"] == "ADVANCE"
        )
        advance["input_frontier_ids"] = [reserved["frontier_id"]]
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    assert not validator.validate_crochet_ir(changed).ok


def test_exact_small_budget_accounts_for_ring_anchors_and_every_snapshot():
    design, material, provenance = inputs()
    result = compile_reserve_schedule(
        design,
        material,
        5,
        2,
        (4,),
        (0,),
        provenance,
        max_events=12,
        max_attachment_locations=14,
        max_frontier_location_references=45,
    )
    assert len(result["construction_sequence"]) == 12
    assert len(result["attachment_locations"]) == 14
    # Six initial snapshots of five locations, the partition's five locations,
    # then three successive active snapshots of 3, 3, and 4 locations.
    assert sum(len(f["attachment_location_ids"]) for f in result["frontiers"]) == 45
    for name, limit in (
        ("max_events", 11),
        ("max_attachment_locations", 13),
        ("max_frontier_location_references", 44),
    ):
        with pytest.raises(ValueError, match="SEARCH_BUDGET_EXHAUSTED"):
            compile_reserve_schedule(
                design, material, 5, 2, (4,), (0,), provenance, **{name: limit}
            )


@pytest.mark.parametrize("field", ["design_spec_id", "profile_id", "revision"])
def test_unhashable_identity_is_a_structured_rejection(field):
    design, material, provenance = inputs()
    (design if field == "design_spec_id" else material)[field] = []
    with pytest.raises(ValueError):
        compile_reserve_schedule(design, material, 5, 2, (4,), (0,), provenance)


def test_design_must_admit_frontier_family_and_parameters_cannot_be_overwritten():
    design, material, provenance = inputs()
    design["solver_options"]["allowed_solver_families"].remove("FRONTIER")
    with pytest.raises(ValueError, match=r"NOT_APPLICABLE:reserve\.solver_family"):
        compile_reserve_schedule(design, material, 5, 2, (4,), (0,), provenance)
    design["solver_options"]["allowed_solver_families"].append("FRONTIER")
    collision = CompileProvenance("a" * 40, "b" * 64, (("initial_count", 42),))
    with pytest.raises(ValueError, match=r"reserve\.parameter_collision"):
        compile_reserve_schedule(design, material, 5, 2, (4,), (0,), collision)


def test_snapshot_budget_rejects_large_live_tables_before_initial_lowering(monkeypatch):
    design, material, provenance = inputs()

    def forbidden_lowering(*args, **kwargs):
        pytest.fail("initial lowering must not start after a failed snapshot budget")

    monkeypatch.setattr("crochet_ai.reserve_compile.compile_closed_schedule", forbidden_lowering)
    with pytest.raises(ValueError, match=r"reserve\.frontier_reference_budget"):
        compile_reserve_schedule(design, material, 512, 1, (511,), (0,), provenance)


def test_reference_material_and_decrease_preserve_the_exact_reserved_locations():
    design, material, provenance = inputs()
    design["difficulty_constraints"]["allowed_shaping"].append("DECREASE")
    design["material_profile"] = {
        "binding_type": "REFERENCE",
        "profile_id": material["profile_id"],
        "revision": material["revision"],
        "sha256": canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE),
    }
    result = compile_reserve_schedule(design, material, 6, 2, (3, 4), (3, 1), provenance)
    frontiers = {f["frontier_id"]: f for f in result["frontiers"]}
    reserved = frontiers["frontier_reserved"]["attachment_location_ids"]
    closing = next(
        op for op in result["construction_operations"] if op["operation_id"] == "op_close_reserved"
    )
    transition = next(
        t
        for t in result["frontier_transitions"]
        if t["caused_by_subject_ref"].get("operation_id") == closing["operation_id"]
    )
    assert transition["retired_attachment_location_ids"] == reserved
    assert any(st["shaping"] == "DECREASE" for st in result["stitches"])
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    assert validator.validate_crochet_ir(result).ok
