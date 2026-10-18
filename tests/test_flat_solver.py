"""Independent small-oracle tests for the bounded FLAT SC rows producer."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from hashlib import sha256

import pytest
import rfc8785
from conftest import load_fixture

from crochet_ai.analytic_compile import CompileProvenance
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.flat_solver import FlatRowsRunConfig, generate_flat_rows
from crochet_ai.solver_types import GenerationError, GenerationStatus
from crochet_ai.validation import SemanticValidator


def _inputs(
    width: int = 8,
    height: int = 7,
    *,
    width_tolerance: int = 0,
    height_tolerance: int = 0,
    repeat_policy: str = "NONE",
) -> tuple[dict, dict, bytes, FlatRowsRunConfig, CompileProvenance]:
    material = load_fixture("material-profile.minimal.valid.json")
    material["calibration_responses"][0]["measurement_conditions"]["course_mode"] = "LINEAR"
    design = load_fixture("design-spec.analytic-sphere.valid.json")
    design["design_spec_id"] = "ds_fixture_flat_rows"
    design["project_type"] = "FLAT"
    design["dimensions"]["measurements"] = [
        {
            "measurement_id": "dim_flat_width",
            "semantic": "OVERALL_WIDTH",
            "label": "Target width",
            "value_mm": width,
            "tolerance_mm": width_tolerance,
        },
        {
            "measurement_id": "dim_flat_height",
            "semantic": "OVERALL_HEIGHT",
            "label": "Target height",
            "value_mm": height,
            "tolerance_mm": height_tolerance,
        },
    ]
    record = {
        "profile": "FLAT_RECTANGLE_TARGET_V1",
        "version": "1",
        "coordinate_frame_id": "frame_flat_target",
        "width_measurement_id": "dim_flat_width",
        "height_measurement_id": "dim_flat_height",
    }
    target_bytes = json.dumps(record, separators=(",", ":"), sort_keys=True).encode()
    design["target_geometry"] = {
        "geometry_type": "PLANAR_REGION",
        "artifact": {
            "artifact_id": "asset_flat_rectangle",
            "uri": "artifact:flat-rectangle",
            "sha256": sha256(target_bytes).hexdigest(),
            "media_type": "application/json",
        },
        "coordinate_frame": {
            "coordinate_frame_id": "frame_flat_target",
            "handedness": "RIGHT_HANDED",
            "length_unit": "MILLIMETER",
            "up_axis": "POSITIVE_Y",
            "front_axis": "POSITIVE_Z",
        },
    }
    design["material_profile"] = {"binding_type": "INLINE", "profile": deepcopy(material)}
    design["difficulty_constraints"]["allowed_stitch_types"] = ["CHAIN", "SINGLE_CROCHET"]
    design["difficulty_constraints"]["allowed_shaping"] = []
    design["difficulty_constraints"]["allowed_construction_operations"] = ["ATTACH", "CLOSE"]
    design["solver_options"].update(
        allowed_solver_families=["FLAT"],
        solver_family_preference=["FLAT"],
        max_candidate_evaluations=64,
        parameter_profile_id="solver_params_flat_rows_test",
    )
    design["domain_constraints"] = {
        "domain": "FLAT",
        "work_structure": "ROWS",
        "repeat_policy": repeat_policy,
    }
    config = FlatRowsRunConfig(
        parameter_profile_id="solver_params_flat_rows_test",
        tension_profile_id="tension_fixture_default",
        fabric_state="RELAXED_UNSTUFFED",
        random_seed=0,
        max_columns=4,
        max_rows=4,
        max_candidate_evaluations=16,
        max_events=100,
        max_attachment_locations=100,
        max_memberships=10_000,
    )
    provenance = CompileProvenance(
        software_commit="a" * 40,
        source_snapshot_sha256="b" * 64,
        parameters=(("test_case", "flat-rectangle"),),
    )
    return design, material, target_bytes, config, provenance


def _run(inputs: tuple[dict, dict, bytes, FlatRowsRunConfig, CompileProvenance]) -> dict:
    return generate_flat_rows(*inputs)


def _count_id_list_memberships(candidate: dict) -> int:
    """Count entries in ID arrays covered by the producer's work cap."""
    fields = {
        "attachment_location_ids",
        "member_event_ids",
        "input_frontier_ids",
        "output_frontier_ids",
        "course_order",
        "course_ids",
        "entry_frontier_ids",
        "terminal_frontier_ids",
        "branch_ids",
        "initial_frontier_ids",
        "created_attachment_location_ids",
        "retired_attachment_location_ids",
        "base_attachment_location_ids",
        "top_attachment_location_ids",
        "event_ids",
        "frontier_transition_ids",
        "input_artifacts",
        "subject_refs",
        "segments",
    }

    def visit(value: object) -> int:
        if isinstance(value, dict):
            return sum(
                (len(item) if key in fields and isinstance(item, list) else 0) + visit(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return sum(visit(item) for item in value)
        return 0

    return visit(candidate)


@pytest.mark.parametrize(
    ("width", "height", "columns", "rows"),
    [(8, 7, 2, 2), (12, 10, 3, 3)],
)
def test_emits_semantically_valid_complete_rectangle(
    width: int, height: int, columns: int, rows: int
) -> None:
    inputs = _inputs(width, height, height_tolerance=1)
    result = _run(inputs)
    candidate = result["candidate"]
    assert result["status"] == GenerationStatus.CANDIDATES_EMITTED.value
    assert result["selected_counts"] == {"columns": columns, "rows": rows}
    assert result["search"]["complete"] is True
    assert len(candidate["stitches"]) == columns * (rows + 1)
    assert len(candidate["courses"]) == rows + 1
    assert [course["work_direction"] for course in candidate["courses"]] == [
        "FORWARD",
        *["REVERSE" if row % 2 else "FORWARD" for row in range(1, rows + 1)],
    ]
    assert candidate["construction_operations"][0]["operation_type"] == "ATTACH"
    assert candidate["construction_operations"][-1]["operation_type"] == "CLOSE"
    assert candidate["attachment_locations"][0]["location_type"] == "FABRIC_ATTACHMENT_POINT"
    assert all(
        stitch["stitch_type"] == "SINGLE_CROCHET"
        for stitch in candidate["stitches"]
        if stitch["course_id"] != "course_000000"
    )
    frontiers = {item["frontier_id"]: item for item in candidate["frontiers"]}
    stitches = {item["stitch_id"]: item for item in candidate["stitches"]}
    events = {item["event_id"]: item for item in candidate["construction_sequence"]}
    for row in range(1, rows + 1):
        course = candidate["courses"][row]
        live_loops = frontiers[course["input_frontier_ids"][0]]["attachment_location_ids"][1:]
        oriented_bases = list(reversed(live_loops)) if row % 2 else live_loops
        observed_bases = [
            stitches[events[event_id]["subject_ref"]["stitch_id"]]["base_attachment_location_ids"][
                0
            ]
            for event_id in course["member_event_ids"]
        ]
        assert observed_bases == oriented_bases
    assert result["candidate_resources"] == {
        "events": len(candidate["construction_sequence"]),
        "attachment_locations": len(candidate["attachment_locations"]),
        "reference_list_memberships": _count_id_list_memberships(candidate),
    }
    validator = SemanticValidator(
        design_specs={inputs[0]["design_spec_id"]: inputs[0]},
        material_profiles={
            inputs[1]["profile_id"]: inputs[1],
            (inputs[1]["profile_id"], inputs[1]["revision"]): inputs[1],
        },
    )
    assert validator.validate_crochet_ir(candidate).ok
    parameters = {
        item["name"]: item["value"] for item in candidate["provenance"]["solver_parameters"]
    }
    parameter_bytes = rfc8785.dumps(candidate["provenance"]["solver_parameters"])
    assert (
        candidate["provenance"]["solver_parameters_sha256"]
        == sha256(b"Crochet.AI\x00FLAT_SC_ROWS_PARAMETERS_V1\x00" + parameter_bytes).hexdigest()
    )
    assert parameters["flat.run.max_columns"] == inputs[3].max_columns
    assert parameters["flat.run.max_candidate_evaluations"] == inputs[3].max_candidate_evaluations
    assert parameters["source_snapshot_sha256"] == inputs[4].source_snapshot_sha256
    assert parameters["flat.anchor_model"] == "UNBOUND_EXTERNAL_FABRIC_POINT_V1"
    assert result["candidate_sha256"] == canonical_hash(
        candidate, CanonicalProfile.CROCHET_IR, validator=validator
    )


def test_search_matches_independent_exhaustive_tiny_pair_oracle() -> None:
    inputs = _inputs(width=10, height=7, width_tolerance=2, height_tolerance=1)
    result = _run(inputs)
    # Independent exhaustive oracle: fixture pitches are 4 mm horizontally and
    # 3.5 mm vertically, represented as exact binary64 ratios by the producer.
    pitch_w, pitch_h = Fraction(4), Fraction(7, 2)
    fitting = [
        (columns, rows)
        for columns in range(1, 5)
        for rows in range(1, 5)
        if abs(columns * pitch_w - 10) <= 2 and abs(rows * pitch_h - 7) <= 1
    ]
    expected = min(
        fitting,
        key=lambda pair: (
            abs(pair[0] * pitch_w - 10),
            abs(pair[1] * pitch_h - 7),
            pair[0] + pair[0] * pair[1],
            pair[1] + 1,
            pair[1],
            pair[0],
        ),
    )
    assert result["selected_counts"] == {"columns": expected[0], "rows": expected[1]}
    assert result["search"]["geometrically_feasible_pairs"] == len(fitting)
    assert result["search"]["candidate_evaluations"] == 16


def test_exhaustion_is_not_reported_as_infeasible_and_candidate_is_prefix_best() -> None:
    inputs = list(_inputs(width=8, height=7))
    inputs[3] = replace(inputs[3], max_candidate_evaluations=6)
    result = _run(tuple(inputs))
    assert result["status"] == GenerationStatus.SEARCH_BUDGET_EXHAUSTED.value
    assert result["candidate"] is not None
    assert result["selected_counts"] == {"columns": 2, "rows": 2}
    assert result["search"]["complete"] is False


def test_raw_target_hash_frame_and_closed_keys_are_fail_closed() -> None:
    design, material, raw, config, provenance = _inputs()
    with pytest.raises(GenerationError, match=r"target\.design_binding"):
        generate_flat_rows(design, material, raw + b" ", config, provenance)
    record = json.loads(raw)
    record["uri"] = "file:///outside"
    invalid = json.dumps(record).encode()
    design["target_geometry"]["artifact"]["sha256"] = sha256(invalid).hexdigest()
    with pytest.raises(GenerationError, match=r"target\.closed_record"):
        generate_flat_rows(design, material, invalid, config, provenance)


def test_invalid_native_identity_and_reference_material_mutation_fail_closed() -> None:
    design, material, raw, config, provenance = _inputs()
    malformed = deepcopy(design)
    malformed["design_spec_id"] = []
    with pytest.raises(GenerationError, match=r"input\.identity_native_types"):
        generate_flat_rows(malformed, material, raw, config, provenance)
    referenced = deepcopy(design)
    referenced["material_profile"] = {
        "binding_type": "REFERENCE",
        "profile_id": material["profile_id"],
        "revision": material["revision"],
        "sha256": canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE),
    }
    material_mutated = deepcopy(material)
    material_mutated["yarn"]["description"] = "schema-valid changed yarn description"
    with pytest.raises(GenerationError):
        generate_flat_rows(referenced, material_mutated, raw, config, provenance)


def test_openings_and_invalid_provenance_types_fail_closed() -> None:
    design, material, raw, config, provenance = _inputs()
    design["construction_constraints"]["intentional_openings"] = [
        {
            "opening_requirement_id": "opening_req_demo",
            "purpose": "OTHER",
            "boundary_landmark_ids": [],
            "closure_expectation": "REMAIN_OPEN",
        }
    ]
    with pytest.raises(GenerationError, match=r"design\.openings_unsupported"):
        generate_flat_rows(design, material, raw, config, provenance)
    design, material, raw, config, provenance = _inputs()
    invalid_provenance = replace(provenance, software_commit=[])  # type: ignore[arg-type]
    with pytest.raises(GenerationError, match=r"provenance\.native_types"):
        generate_flat_rows(design, material, raw, config, invalid_provenance)
    invalid_parameters = replace(provenance, parameters=[("bad", "shape")])  # type: ignore[arg-type]
    with pytest.raises(GenerationError, match=r"provenance\.native_types"):
        generate_flat_rows(design, material, raw, config, invalid_parameters)


def test_config_caps_and_dimension_bindings_are_enforced() -> None:
    design, material, raw, config, provenance = _inputs()
    too_many = FlatRowsRunConfig(
        parameter_profile_id=config.parameter_profile_id,
        tension_profile_id=config.tension_profile_id,
        fabric_state=config.fabric_state,
        random_seed=config.random_seed,
        max_columns=513,
        max_rows=4,
        max_candidate_evaluations=16,
        max_events=100,
        max_attachment_locations=100,
        max_memberships=10_000,
    )
    with pytest.raises(GenerationError, match=r"config\.max_columns"):
        generate_flat_rows(design, material, raw, too_many, provenance)
    invalid = _inputs()
    invalid[0]["domain_constraints"]["work_structure"] = "GRID"
    with pytest.raises(GenerationError, match=r"design\.flat_scope"):
        _run(invalid)


def test_foundation_chain_must_be_allowed_by_design_spec() -> None:
    design, material, raw, config, provenance = _inputs()
    design["difficulty_constraints"]["allowed_stitch_types"] = ["SINGLE_CROCHET"]
    with pytest.raises(GenerationError, match=r"design\.foundation_or_sc_disallowed"):
        generate_flat_rows(design, material, raw, config, provenance)


def test_output_resource_caps_are_checked_before_ir_construction() -> None:
    inputs = list(_inputs())
    inputs[3] = replace(inputs[3], max_events=7)
    result = _run(tuple(inputs))
    assert result["status"] == GenerationStatus.NO_FEASIBLE_CONSTRUCTION.value
    assert result["candidate"] is None
    assert result["search"]["geometrically_feasible_pairs"] == 1
    assert result["reason"] == "budget.candidate_structure_limits"


def test_inputs_are_not_mutated_and_output_is_deterministic() -> None:
    inputs = _inputs(12, 10, height_tolerance=1, repeat_policy="FIT_WITHIN_DIMENSION_TOLERANCE")
    before = deepcopy(inputs[:2])
    first = _run(inputs)
    second = _run(inputs)
    assert inputs[:2] == tuple(before)
    assert first == second


@pytest.mark.parametrize("emits_candidate", [False, True])
def test_exact_ratio_reports_stay_in_ijson_for_decimal_gauge(emits_candidate: bool) -> None:
    design, material, raw, config, provenance = _inputs()
    material["calibration_responses"][0]["effective_gauge"]["effective_stitch_pitch_mm"] = 0.1
    observation = material["calibration_responses"][0]["observations"][0]
    observation["stitch_span_length_mm"] = 0.1 * observation["stitch_span_count"]
    design["material_profile"]["profile"] = deepcopy(material)
    if emits_candidate:
        design["dimensions"]["measurements"][0].update(value_mm=0.21, tolerance_mm=0.02)
    result = generate_flat_rows(design, material, raw, config, provenance)
    ratio = result["pitch_mm_binary64_ratios"]["stitch"]
    assert ratio == [str(value) for value in (0.1).as_integer_ratio()]
    assert int(ratio[1]) > 2**53 - 1
    assert (result["candidate"] is not None) == emits_candidate
    if emits_candidate:
        residual = abs(2 * Fraction(0.1) - Fraction(0.21))
        assert result["dimension_residuals_mm"]["width"] == [
            str(residual.numerator),
            str(residual.denominator),
        ]
    assert rfc8785.dumps(result)
