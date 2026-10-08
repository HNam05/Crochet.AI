"""Independent, deliberately incomplete audit of analytic CrochetIR claims."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from typing import Any, cast

import rfc8785

from .analytic_coordinate_target import (
    PROFILE_ID as COORDINATE_PROFILE_ID,
)
from .analytic_coordinate_target import (
    admit_analytic_coordinate_target,
)
from .analytic_target import AnalyticTargetError
from .canonical import CanonicalProfile, canonical_hash, jcs_bytes, validate_ijson
from .coordinate_meridian_replay import CoordinateMeridianReplay, CoordinateReplayError
from .diagnostics import ArtifactValidationError, FailureCode
from .json_types import JSONValue
from .trace_verification_types import TraceReplayBudgetExceeded, TraceReplayWork
from .validation import SemanticValidator


class AnalyticClaimsInputError(ValueError):
    """Malformed or over-budget source, rejected before an audit report exists."""


@dataclass(frozen=True, slots=True)
class AnalyticClaimsReport:
    status: str
    sha256: str
    canonical_bytes: bytes
    _payload: bytes
    assertions: tuple[tuple[str, bool], ...]
    diagnostics: tuple[tuple[str, str], ...]
    missing_checks: tuple[str, ...]

    def to_dict(self) -> dict[str, JSONValue]:
        import json

        return cast(dict[str, JSONValue], json.loads(self._payload))


_TABLES = (
    "colors",
    "yarns",
    "attachment_locations",
    "stitches",
    "construction_operations",
    "courses",
    "frontiers",
    "branches",
    "components",
    "openings",
    "yarn_paths",
    "derivations",
    "construction_sequence",
    "frontier_transitions",
)
_RUN_CEILINGS: dict[str, tuple[int, int]] = {
    "min_courses": (1, 512),
    "max_courses": (1, 512),
    "max_course_hypotheses": (1, 512),
    "count_window_radius": (0, 127),
    "min_count": (1, 512),
    "max_count": (1, 512),
    "initial_ring_min": (2, 512),
    "initial_ring_max": (2, 512),
    "max_terminal_count": (1, 512),
    "max_increases_per_course": (0, 512),
    "max_decreases_per_course": (0, 512),
    "max_emitted_candidates": (1, 128),
    "max_stitches": (1, 10_000),
    "numerics.max_arc_panels": (2, 200_000),
    "count_budget.max_courses": (1, 512),
    "count_budget.max_count_values_per_course": (1, 256),
    "count_budget.max_dp_states_per_course": (1, 256),
    "count_budget.max_transition_evaluations": (1, 2_000_000),
    "placement_budget.max_variants_per_transition": (1, 512),
    "placement_budget.max_transition_evaluations": (1, 2_000_000),
    "placement_budget.max_pair_evaluations": (1, 2_000_000),
}
_STRING_RUNS = {"parameter_profile_id", "tension_profile_id", "fabric_state"}
_FLOAT_RUNS = {
    "numerics.arc_length_abs_tolerance_mm",
    "numerics.roundoff_allowance_mm",
}
_KNOWN_RUNS = (
    _RUN_CEILINGS.keys()
    | _STRING_RUNS
    | _FLOAT_RUNS
    | {
        "minimum_shaping_separation_turns",
        "numerics.radius_zero_tolerance_mm",
    }
)
_KNOWN_SOLVER = {
    "course_count",
    "count_transitions",
    "placement_transitions",
    "placement_pairs",
    "arc_panels",
    "arc_error_bound_mm",
    "material_response_id",
    "parameter_profile_id",
}
_COORDINATE_SOLVER = {
    "coordinate_sampler_version",
    "coordinate_target_sha256",
    "coordinate_sqrt_bracket_max_steps",
}
_KNOWN_PROTOTYPE = {"count_schedule", "final_phases", "phase_policy"}
_MISSING_TRACE = (
    "input_bound_search_trace",
    "independently_confirmed_search_work_and_completion",
    "count_window_admission",
    "deterministic_candidate_selection_and_tie_break",
    "global_phase_optimality",
    "physical_verification",
)


def _prebound(
    design: object,
    material: object,
    ir: object,
    max_events: int,
    max_courses: int,
    max_parameters: int,
) -> list[dict[str, Any]]:
    if (
        type(max_events) is not int
        or not 1 <= max_events <= 30_000
        or type(max_courses) is not int
        or not 1 <= max_courses <= 512
        or type(max_parameters) is not int
        or not 1 <= max_parameters <= 256
    ):
        raise AnalyticClaimsInputError(
            "resource limits must be positive integers within V1 ceilings"
        )
    if not all(isinstance(v, dict) for v in (design, material, ir)):
        raise AnalyticClaimsInputError("design, material and CrochetIR must be objects")
    source = cast(dict[str, Any], ir)
    for table in _TABLES:
        rows = source.get(table)
        if not isinstance(rows, list):
            raise AnalyticClaimsInputError(f"source table {table} must be an array")
        if len(rows) > 30_000:
            raise AnalyticClaimsInputError(f"{table}_resource_ceiling_exceeded")
    if len(source["construction_sequence"]) > max_events:
        raise AnalyticClaimsInputError("construction_sequence_budget_exceeded")
    if len(source["courses"]) > max_courses:
        raise AnalyticClaimsInputError("courses_budget_exceeded")
    if not isinstance(source.get("course_order"), list):
        raise AnalyticClaimsInputError("course_order_missing_or_malformed")
    if len(source["course_order"]) > max_courses:
        raise AnalyticClaimsInputError("course_order_budget_exceeded")
    if any(
        not isinstance(identifier, str) or len(identifier) > 128 or not identifier.isascii()
        for identifier in source["course_order"]
    ):
        raise AnalyticClaimsInputError("course_order_identifier_limits")
    provenance = source.get("provenance")
    if not isinstance(provenance, dict):
        raise AnalyticClaimsInputError("provenance must be an object")
    params = provenance.get("solver_parameters")
    if not isinstance(params, list) or len(params) > max_parameters:
        raise AnalyticClaimsInputError("solver_parameters_budget_exceeded_or_missing")
    for row in params:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise AnalyticClaimsInputError("malformed solver parameter")
        name, value = row["name"], row.get("value")
        if len(name) > 128 or not name.isascii() or (isinstance(value, str) and len(value) > 4096):
            raise AnalyticClaimsInputError("solver parameter exceeds string limits")
    # Bound all ID reference lists and identity-bearing strings before canonical hashing.
    pending: list[object] = [source]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if key.endswith("_ids") and isinstance(value, list):
                    if len(value) > 30_000:
                        raise AnalyticClaimsInputError(f"{key}_resource_ceiling_exceeded")
                    if any(
                        not isinstance(identifier, str)
                        or len(identifier) > 128
                        or not identifier.isascii()
                        for identifier in value
                    ):
                        raise AnalyticClaimsInputError(f"{key}_identifier_limits")
                if (
                    key.endswith("_id")
                    and isinstance(value, str)
                    and (len(value) > 128 or not value.isascii())
                ):
                    raise AnalyticClaimsInputError(f"{key}_identifier_limits")
                pending.append(value)
        elif isinstance(current, list):
            pending.extend(current)
    return params


def _code(reason: str) -> FailureCode:
    if "hash" in reason or "parameter" in reason or "provenance" in reason:
        return FailureCode.PROVENANCE
    if "count" in reason or "course" in reason or "stitch" in reason or "shap" in reason:
        return FailureCode.COUNT
    if "material" in reason or "profile" in reason:
        return FailureCode.REFERENCE
    if "scope" in reason or "unsupported" in reason:
        return FailureCode.UNSUPPORTED_FEATURE
    return FailureCode.DETERMINISM


def _analytic_closed_scope(design: dict[str, Any], ir: dict[str, Any]) -> bool:
    provenance = ir.get("provenance", {})
    if provenance.get("generator") != {
        "solver_family": "ANALYTIC",
        "name": "analytic-closed-sc",
        "version": "1",
    }:
        return False
    if not (
        design.get("project_type") == "AMIGURUMI_3D"
        and design.get("domain_constraints", {}).get("surface_mode") == "CLOSED"
        and not design.get("construction_constraints", {}).get("intentional_openings")
        and len(design.get("colors", [])) == 1
        and len(ir.get("components", [])) == 1
        and len(ir.get("branches", [])) == 1
        and len(ir.get("yarns", [])) == 1
        and len(ir.get("yarn_paths", [])) == 1
    ):
        return False
    courses = {course["course_id"]: course for course in ir["courses"]}
    if set(ir["course_order"]) != set(courses) or not courses:
        return False
    component_id = ir["components"][0]["component_id"]
    branch_id = ir["branches"][0]["branch_id"]
    if any(
        course.get("course_form") != "CYCLIC"
        or course.get("turn_mode") != "CONTINUOUS_SPIRAL"
        or course.get("work_direction") != "CLOCKWISE"
        or course.get("component_id") != component_id
        or course.get("branch_id") != branch_id
        for course in courses.values()
    ):
        return False
    if any(stitch.get("stitch_type") != "SINGLE_CROCHET" for stitch in ir["stitches"]):
        return False
    if any(stitch.get("yarn_id") != ir["yarns"][0]["yarn_id"] for stitch in ir["stitches"]):
        return False
    operations = {
        operation["operation_id"]: operation for operation in ir["construction_operations"]
    }
    event_subjects = [
        event["subject_ref"]
        for event in sorted(ir["construction_sequence"], key=lambda event: event["sequence_index"])
    ]
    if not event_subjects:
        return False
    if (
        event_subjects[0].get("entity_type") != "CONSTRUCTION_OPERATION"
        or event_subjects[0].get("operation_id") not in operations
        or operations[event_subjects[0]["operation_id"]].get("operation_type") != "MAGIC_RING"
        or event_subjects[-1].get("entity_type") != "CONSTRUCTION_OPERATION"
        or event_subjects[-1].get("operation_id") not in operations
        or operations[event_subjects[-1]["operation_id"]].get("operation_type") != "CLOSE"
    ):
        return False
    try:
        op_types = [
            operations[subject["operation_id"]]["operation_type"]
            for subject in event_subjects
            if subject["entity_type"] == "CONSTRUCTION_OPERATION"
        ]
    except KeyError:
        return False
    return op_types == ["MAGIC_RING", "CLOSE"] and {
        operation["operation_type"] for operation in operations.values()
    } == {"MAGIC_RING", "CLOSE"}


def inspect_analytic_candidate_claims(
    design: dict[str, Any],
    material: dict[str, Any],
    ir: dict[str, Any],
    *,
    validator: SemanticValidator,
    max_events: int = 30_000,
    max_courses: int = 512,
    max_parameters: int = 256,
) -> AnalyticClaimsReport:
    """Check exact source claims without calling any analytic generation code."""
    params = _prebound(design, material, ir, max_events, max_courses, max_parameters)
    for artifact, validate in (
        (design, validator.validate_design_spec),
        (material, validator.validate_material_profile),
        (ir, validator.validate_crochet_ir),
    ):
        report = validate(artifact)
        if not report.ok:
            raise ArtifactValidationError(report)
    # Resource and reference limits are checked before the canonical hash operations.
    for value in (design, material, ir):
        validate_ijson(value)
    input_hashes = {
        "design_spec_sha256": canonical_hash(
            design, CanonicalProfile.DESIGN_SPEC, validator=validator
        ),
        "material_profile_sha256": canonical_hash(
            material, CanonicalProfile.MATERIAL_PROFILE, validator=validator
        ),
        "source_ir_sha256": canonical_hash(ir, CanonicalProfile.CROCHET_IR, validator=validator),
    }
    assertions: dict[str, bool] = {}
    diagnostics: list[tuple[str, str]] = []
    missing = list(_MISSING_TRACE)

    def check(name: str, ok: bool, reason: str) -> None:
        assertions[name] = ok
        if not ok:
            diagnostics.append((str(_code(reason)), reason))

    scope_ok = _analytic_closed_scope(design, ir)
    if not scope_ok:
        operations = ir["construction_operations"]
        seams = sum(
            op.get("operation_type") == "JOIN" and op.get("join_method") == "SEWN"
            for op in operations
        )
        cuts = sum(op.get("operation_type") == "CUT_YARN" for op in operations)
        reattachments = sum(
            op.get("operation_type") == "ATTACH" and bool(op.get("input_frontier_ids"))
            for op in operations
        )
        constraints = design.get("construction_constraints", {})
        construction_ok = (
            seams <= constraints.get("maximum_sewn_seams", -1)
            and cuts <= constraints.get("maximum_yarn_cuts", -1)
            and reattachments <= constraints.get("maximum_reattachments", -1)
        )
        assertions = {"construction_limits": construction_ok}
        reasons = (
            []
            if construction_ok
            else [
                {
                    "code": str(_code("construction count exceeds DesignSpec limit")),
                    "reason": "construction count exceeds DesignSpec limit",
                }
            ]
        )
        missing = [*_MISSING_TRACE, "analytic_closed_sc_schedule_out_of_scope"]
        status = "NOT_APPLICABLE" if construction_ok else "FAIL"
        out_of_scope_payload: dict[str, JSONValue] = {
            "profile": "ANALYTIC_CANDIDATE_CLAIMS_V1",
            "status": status,
            **input_hashes,
            "assertions": cast(JSONValue, assertions),
            "diagnostics": cast(JSONValue, reasons),
            "missing_checks": cast(JSONValue, missing),
            "schedule": {
                "course_count": 0,
                "counts": [],
                "phases": [],
                "transitions": [],
                "count_totals": {"plain": 0, "increases": 0, "decreases": 0},
                "stitch_count": len(ir["stitches"]),
            },
            "construction": {
                "sewn_seams": seams,
                "yarn_cuts": cuts,
                "reattachments": reattachments,
            },
            "checked_parameters": {},
            "budgets": {
                "max_events": max_events,
                "max_courses": max_courses,
                "max_parameters": max_parameters,
            },
        }
        encoded = jcs_bytes(out_of_scope_payload)
        digest = sha256(b"Crochet.AI\0ANALYTIC_CANDIDATE_CLAIMS_V1\0" + encoded).hexdigest()
        diagnostic_tuples = tuple((row["code"], row["reason"]) for row in reasons)
        return AnalyticClaimsReport(
            status,
            digest,
            encoded,
            encoded,
            tuple(assertions.items()),
            diagnostic_tuples,
            tuple(missing),
        )
    provenance = ir["provenance"]
    names = [row["name"] for row in params]
    if scope_ok:
        check(
            "unique_parameter_names",
            len(set(names)) == len(names),
            "parameter names are duplicated",
        )
    parameter_hash = provenance.get("solver_parameters_sha256")
    if scope_ok:
        try:
            ordered_params = sorted(params, key=lambda row: row["name"])
            expected = sha256(
                b"Crochet.AI\0ANALYTIC_COMPILER_PARAMETERS_V1\0" + rfc8785.dumps(ordered_params)
            ).hexdigest()
        except (rfc8785.CanonicalizationError, TypeError, ValueError):
            expected = ""
        check(
            "parameter_digest",
            isinstance(parameter_hash, str) and parameter_hash == expected,
            "parameter hash does not match sorted ANALYTIC_COMPILER_PARAMETERS_V1 values",
        )
    values = {row["name"]: row["value"] for row in params if isinstance(row, dict)}
    coordinate_scope = (
        design.get("target_geometry", {}).get("primitive") == "SURFACE_OF_REVOLUTION"
        and design.get("target_geometry", {})
        .get("radial_profile", {})
        .get("canonicalization_profile")
        == COORDINATE_PROFILE_ID
    )
    if coordinate_scope:
        coordinate_names = (
            "solver.coordinate_sampler_version",
            "solver.coordinate_target_sha256",
            "solver.coordinate_sqrt_bracket_max_steps",
        )
        present = [name in values for name in coordinate_names]
        if any(present):
            valid_coordinate_claim = all(present)
            if valid_coordinate_claim:
                try:
                    target = admit_analytic_coordinate_target(design, validator)
                    arc_tolerance = values.get("run.numerics.arc_length_abs_tolerance_mm")
                    roundoff = values.get("run.numerics.roundoff_allowance_mm")
                    max_panels = values.get("run.numerics.max_arc_panels")
                    radius_zero = values.get("run.numerics.radius_zero_tolerance_mm")
                    if (
                        type(arc_tolerance) not in (int, float)
                        or type(roundoff) not in (int, float)
                        or type(max_panels) is not int
                        or type(radius_zero) not in (int, float)
                    ):
                        raise CoordinateReplayError("coordinate.run_numerics_missing")
                    replay = CoordinateMeridianReplay.build(
                        target,
                        cast(float, arc_tolerance),
                        cast(float, roundoff),
                        max_panels,
                        TraceReplayWork(1_000),
                        cast(float, radius_zero),
                    )
                    valid_coordinate_claim = (
                        values.get(coordinate_names[0]) == "EXPLICIT_COORDINATE_MERIDIAN_V1"
                        and values.get(coordinate_names[1]) == target.sha256
                        and type(values.get(coordinate_names[2])) is int
                        and values.get(coordinate_names[2]) == 2
                        and bool(replay.target_sha256)
                    )
                except (
                    AnalyticTargetError,
                    CoordinateReplayError,
                    TraceReplayBudgetExceeded,
                    TypeError,
                ):
                    valid_coordinate_claim = False
            else:
                valid_coordinate_claim = False
            check(
                "coordinate_sampler_parameters",
                valid_coordinate_claim,
                "coordinate sampler parameters do not bind to the admitted target and run numerics",
            )
        elif scope_ok:
            missing.append("coordinate_sampler_parameters")
    unknown = sorted(
        name
        for name in values
        if (name.startswith("run.") and name[4:] not in _KNOWN_RUNS)
        or (
            name.startswith("solver.")
            and name[7:] not in _KNOWN_SOLVER
            and not (coordinate_scope and name[7:] in _COORDINATE_SOLVER)
        )
        or (name.startswith("prototype.") and name[10:] not in _KNOWN_PROTOTYPE)
    )
    if scope_ok:
        missing.extend(f"unsupported_parameter:{name}" for name in unknown)
    bounds_ok = True
    for name, (low, high) in _RUN_CEILINGS.items():
        key = "run." + name
        if key in values and (type(values[key]) is not int or not low <= values[key] <= high):
            bounds_ok = False
    for name in _STRING_RUNS:
        if "run." + name in values and (
            not isinstance(values["run." + name], str) or not values["run." + name]
        ):
            bounds_ok = False
    for name in _FLOAT_RUNS:
        if "run." + name in values and (
            type(values["run." + name]) not in (int, float) or values["run." + name] <= 0
        ):
            bounds_ok = False
    for name in (
        "arc_length_abs_tolerance_mm",
        "roundoff_allowance_mm",
        "radius_zero_tolerance_mm",
    ):
        key = "run.numerics." + name
        if key in values and (type(values[key]) not in (int, float) or values[key] < 0):
            bounds_ok = False
    arc_tol = values.get("run.numerics.arc_length_abs_tolerance_mm")
    roundoff = values.get("run.numerics.roundoff_allowance_mm")
    if arc_tol is not None and roundoff is not None:
        if type(arc_tol) not in (int, float) or type(roundoff) not in (int, float):
            bounds_ok = False
        else:
            bounds_ok &= roundoff < arc_tol
    separation = values.get("run.minimum_shaping_separation_turns")
    if separation is not None:
        try:
            if not isinstance(separation, str):
                raise ValueError("fraction parameter must be text")
            fraction = Fraction(separation)
            bounds_ok &= (
                0 <= fraction <= Fraction(1, 2)
                and fraction.numerator.bit_length() <= 256
                and fraction.denominator.bit_length() <= 128
            )
        except (ValueError, ZeroDivisionError):
            bounds_ok = False
    if scope_ok:
        required_run = (
            set(_RUN_CEILINGS)
            | _STRING_RUNS
            | _FLOAT_RUNS
            | {"numerics.radius_zero_tolerance_mm", "minimum_shaping_separation_turns"}
        )
        missing.extend(
            f"run_parameter:{name}" for name in sorted(required_run) if "run." + name not in values
        )
        check("parameter_bounds", bounds_ok, "run parameter violates an implementation ceiling")
        option_profile = design.get("solver_options", {}).get("parameter_profile_id")
        claimed_profile = values.get("run.parameter_profile_id")
        if claimed_profile is None:
            missing.append("parameter_profile_binding")
        else:
            check(
                "parameter_profile_binding",
                claimed_profile == option_profile,
                "parameter profile does not bind to DesignSpec",
            )
        check(
            "analytic_family_authorized",
            "ANALYTIC" in design.get("solver_options", {}).get("allowed_solver_families", []),
            "analytic solver family is not authorized by DesignSpec",
        )

    operations = ir["construction_operations"]
    seams = sum(
        op.get("operation_type") == "JOIN" and op.get("join_method") == "SEWN" for op in operations
    )
    cuts = sum(op.get("operation_type") == "CUT_YARN" for op in operations)
    reattachments = sum(
        op.get("operation_type") == "ATTACH" and bool(op.get("input_frontier_ids"))
        for op in operations
    )
    limits = design.get("construction_constraints", {})
    construction_ok = (
        seams <= limits.get("maximum_sewn_seams", -1)
        and cuts <= limits.get("maximum_yarn_cuts", -1)
        and reattachments <= limits.get("maximum_reattachments", -1)
    )
    check("construction_limits", construction_ok, "construction count exceeds DesignSpec limit")

    # A hard construction violation survives unsupported schedule scope.
    schedule: dict[str, Any] = {
        "course_count": 0,
        "counts": [],
        "phases": [],
        "transitions": [],
        "count_totals": {"plain": 0, "increases": 0, "decreases": 0},
        "stitch_count": len(ir["stitches"]),
    }
    if scope_ok:
        try:
            event_by_id = {e["event_id"]: e for e in ir["construction_sequence"]}
            stitch_by_id = {s["stitch_id"]: s for s in ir["stitches"]}
            frontier_by_id = {f["frontier_id"]: f for f in ir["frontiers"]}
            course_by_id = {course["course_id"]: course for course in ir["courses"]}
            courses = [course_by_id[course_id] for course_id in ir["course_order"]]
            course_counts: list[int] = []
            phases: list[int] = []
            transition_rows: list[dict[str, int]] = []
            ring = next(op for op in operations if op["operation_type"] == "MAGIC_RING")
            initial = len(ring["attachment_location_ids"])
            previous = initial
            schedule_ok = True
            member_set: set[str] = set()
            for index, course in enumerate(courses):
                member_ids = course["member_event_ids"]
                if any(eid not in event_by_id for eid in member_ids):
                    schedule_ok = False
                    break
                member_set.update(member_ids)
                nodes = [
                    stitch_by_id[event_by_id[eid]["subject_ref"].get("stitch_id", "")]
                    for eid in member_ids
                ]
                if any(node["stitch_type"] != "SINGLE_CROCHET" for node in nodes):
                    schedule_ok = False
                    break
                input_ids = course["input_frontier_ids"]
                output_ids = course["output_frontier_ids"]
                before = frontier_by_id[input_ids[0]]["attachment_location_ids"]
                after = frontier_by_id[output_ids[0]]["attachment_location_ids"]
                phase = before.index(nodes[0]["base_attachment_location_ids"][0])
                cursor = phase
                top_order: list[str] = []
                plains = inc = dec = 0
                for node in nodes:
                    arity, top_arity = node["base_arity"], node["top_arity"]
                    expected_bases = [before[(cursor + j) % len(before)] for j in range(arity)]
                    if node["base_attachment_location_ids"] != expected_bases:
                        schedule_ok = False
                        break
                    if (arity, top_arity) == (1, 1):
                        plains += 1
                    elif (arity, top_arity) == (1, 2):
                        inc += 1
                    elif (arity, top_arity) == (2, 1):
                        dec += 1
                    else:
                        schedule_ok = False
                        break
                    top_order.extend(node["top_attachment_location_ids"])
                    cursor += arity
                if not schedule_ok or cursor != phase + len(before):
                    schedule_ok = False
                    break
                if len(after) != len(top_order) or (top_order and after[0] not in top_order):
                    schedule_ok = False
                    break
                offset = top_order.index(after[0]) if top_order else 0
                if after != top_order[offset:] + top_order[:offset]:
                    schedule_ok = False
                    break
                current = sum(node["top_arity"] for node in nodes)
                if index == 0 and (inc or dec or phase != 0 or current != initial):
                    schedule_ok = False
                    break
                if index and (
                    previous != len(before)
                    or previous != plains + inc + 2 * dec
                    or current != plains + 2 * inc + dec
                    or inc * dec != 0
                ):
                    schedule_ok = False
                    break
                if index:
                    transitions = inc + dec
                    transition_rows.append({"plain": plains, "increases": inc, "decreases": dec})
                    ops = len(nodes)
                    shaped_ordinals = [
                        i for i, node in enumerate(nodes) if node["shaping"] != "PLAIN"
                    ]
                    balanced = (
                        [
                            ((k * ops + transitions - 1) // transitions) - 1
                            for k in range(1, transitions + 1)
                        ]
                        if transitions
                        else []
                    )
                    if shaped_ordinals != balanced:
                        schedule_ok = False
                        break
                if index > 0:
                    phases.append(phase)
                course_counts.append(current)
                previous = current
            accounted = member_set | {
                e["event_id"]
                for e in ir["construction_sequence"]
                if event_by_id[e["event_id"]]["subject_ref"]["entity_type"]
                == "CONSTRUCTION_OPERATION"
            }
            if (
                accounted != set(event_by_id)
                or not courses
                or not any(op["operation_type"] == "CLOSE" for op in operations)
            ):
                schedule_ok = False
            # This profile allows only the ring anchor and terminal close.
            if {op["operation_type"] for op in operations} != {"MAGIC_RING", "CLOSE"}:
                schedule_ok = False
            schedule = {
                "course_count": len(courses),
                "counts": course_counts,
                "phases": phases,
                "transitions": transition_rows,
                "count_totals": {
                    "plain": sum(row["plain"] for row in transition_rows),
                    "increases": sum(row["increases"] for row in transition_rows),
                    "decreases": sum(row["decreases"] for row in transition_rows),
                },
                "stitch_count": len(ir["stitches"]),
            }
            check(
                "closed_sc_source_schedule",
                schedule_ok,
                "source schedule count, phase, order, shaping or closure claim is false",
            )
        except (KeyError, IndexError, ValueError, StopIteration, TypeError):
            check(
                "closed_sc_source_schedule", False, "source schedule is incomplete or inconsistent"
            )
    else:
        check(
            "analytic_closed_sc_scope",
            False,
            "source lies outside supported analytic closed SC scope",
        )

    # Selected material response must match the run's exact physical-semantic condition.
    tension, fabric = values.get("run.tension_profile_id"), values.get("run.fabric_state")
    matches = [
        r
        for r in material.get("calibration_responses", [])
        if r.get("measurement_conditions")
        == {
            "canonical_stitch_type": "SINGLE_CROCHET",
            "course_mode": "CYCLIC",
            "tension_profile_id": tension,
            "fabric_state": fabric,
        }
    ]
    response_id = values.get("solver.material_response_id")
    if tension is None:
        missing.append("run.tension_profile_id")
    if fabric is None:
        missing.append("run.fabric_state")
    if response_id is None:
        missing.append("solver.material_response_id")
    check(
        "selected_material_response",
        len(matches) == 1 and matches[0].get("response_id") == response_id,
        "selected material response does not uniquely match run conditions",
    ) if response_id is not None and tension is not None and fabric is not None else missing.append(
        "selected_material_response"
    )
    if fabric is None:
        missing.append("stuffing_condition")
    else:
        check(
            "stuffing_condition",
            (design.get("domain_constraints", {}).get("stuffing_level") == "NONE")
            != (fabric == "STUFFED"),
            "material fabric state conflicts with stuffing intent",
        )
    # Compare actual schedule against run bounds when supplied.
    observed = cast(list[int], schedule["counts"])
    run_bounds_ok = True
    observed_limit_names: set[str] = set()
    for parameter, observed_value in (
        ("max_courses", schedule["course_count"]),
        ("min_courses", schedule["course_count"]),
        ("min_count", min(observed, default=0)),
        ("max_count", max(observed, default=0)),
        ("initial_ring_min", observed[0] if observed else 0),
        ("initial_ring_max", observed[0] if observed else 0),
        ("max_terminal_count", observed[-1] if observed else 0),
        ("max_stitches", schedule["stitch_count"]),
    ):
        key = "run." + parameter
        if key in values:
            observed_limit_names.add(parameter)
            bound = values[key]
            if parameter in {"min_courses", "initial_ring_min"}:
                run_bounds_ok &= type(bound) is int and observed_value >= bound
            elif parameter in {
                "max_courses",
                "initial_ring_max",
                "max_terminal_count",
                "max_stitches",
            }:
                run_bounds_ok &= type(bound) is int and observed_value <= bound
            elif parameter == "min_count":
                run_bounds_ok &= type(bound) is int and min(observed, default=0) >= bound
            else:
                run_bounds_ok &= type(bound) is int and max(observed, default=0) <= bound
    transition_rows = cast(list[dict[str, int]], schedule["transitions"])
    for parameter, key in (
        ("max_increases_per_course", "increases"),
        ("max_decreases_per_course", "decreases"),
    ):
        bound = values.get("run." + parameter)
        if bound is not None:
            observed_limit_names.add(parameter)
            run_bounds_ok &= type(bound) is int and all(
                row[key] <= bound for row in transition_rows
            )
    low_courses, high_courses = values.get("run.min_courses"), values.get("run.max_courses")
    if low_courses is not None and high_courses is not None:
        observed_limit_names.update({"min_courses", "max_courses"})
        run_bounds_ok &= (
            type(low_courses) is int and type(high_courses) is int and low_courses <= high_courses
        )
    all_observed_bounds = {
        "max_courses",
        "min_courses",
        "min_count",
        "max_count",
        "initial_ring_min",
        "initial_ring_max",
        "max_terminal_count",
        "max_stitches",
        "max_increases_per_course",
        "max_decreases_per_course",
    }
    missing.extend(
        "run_bound:" + name for name in sorted(all_observed_bounds - observed_limit_names)
    )
    if observed_limit_names:
        check(
            "observed_run_bounds", run_bounds_ok, "observed schedule exceeds or misses run bounds"
        )
    claimed_course_count = values.get("solver.course_count")
    if claimed_course_count is None:
        missing.append("solver_course_count")
    elif not scope_ok:
        missing.append("solver_course_count_source_scope")
    else:
        check(
            "solver_course_count",
            type(claimed_course_count) is int and claimed_course_count == schedule["course_count"],
            "solver course-count claim disagrees with source schedule",
        )
    # Optional prototype claims: partial metadata is incomplete evidence, never inferred.
    proto = {
        name: values.get("prototype." + name)
        for name in ("count_schedule", "final_phases", "phase_policy")
    }
    for name, expected_value in (
        ("count_schedule", observed),
        ("final_phases", schedule["phases"]),
    ):
        recorded = proto[name]
        if recorded is None:
            missing.append("prototype." + name)
        else:
            try:
                parsed = (
                    [] if recorded == "" else [int(value) for value in str(recorded).split(",")]
                )
                check(
                    "prototype." + name,
                    parsed == expected_value,
                    "prototype " + name + " disagrees with the source schedule",
                )
            except ValueError:
                check("prototype." + name, False, "prototype " + name + " is malformed")
    policy = proto["phase_policy"]
    if policy is None:
        missing.append("prototype.phase_policy")
    elif policy != "FIXED_ZERO_CONTINUOUS_V1":
        missing.append("unsupported_prototype_phase_policy")
    else:
        check(
            "prototype_fixed_zero_phase_policy",
            all(phase == 0 for phase in cast(list[int], schedule["phases"])),
            "fixed-zero prototype phase policy conflicts with source phases",
        )
    budget = provenance.get("search_budget", {})
    if not isinstance(budget, dict) or not {"limit", "consumed", "exhausted"} <= budget.keys():
        missing.append("recorded_search_budget")
        budget_ok = True
    else:
        budget_ok = (
            type(budget.get("limit")) is int
            and type(budget.get("consumed")) is int
            and type(budget.get("exhausted")) is bool
            and 0 <= budget["consumed"] <= budget["limit"]
            and (not budget["exhausted"] or budget["consumed"] == budget["limit"])
            and budget["limit"]
            <= design.get("solver_options", {}).get("max_candidate_evaluations", 0)
        )
    if "recorded_search_budget" not in missing:
        check(
            "recorded_budget_well_formed",
            budget_ok,
            "recorded work counters exceed or contradict declared budget",
        )
    work_ok = True
    for counter, budget_name in (
        ("solver.count_transitions", "run.count_budget.max_transition_evaluations"),
        ("solver.placement_transitions", "run.placement_budget.max_transition_evaluations"),
        ("solver.placement_pairs", "run.placement_budget.max_pair_evaluations"),
        ("solver.arc_panels", "run.numerics.max_arc_panels"),
    ):
        observed_work, declared_limit = values.get(counter), values.get(budget_name)
        if observed_work is None or declared_limit is None:
            missing.append(f"work_counter:{counter}")
        elif (
            type(observed_work) is not int
            or observed_work < 0
            or type(declared_limit) is not int
            or observed_work > declared_limit
        ):
            work_ok = False
    check(
        "recorded_work_counters_within_declared_budgets",
        work_ok,
        "recorded work counter exceeds or contradicts its declared budget",
    )
    has_failure = (
        any(not value for name, value in assertions.items() if name != "analytic_closed_sc_scope")
        or not construction_ok
    )
    status = "FAIL" if has_failure else "NOT_APPLICABLE" if not scope_ok else "INDETERMINATE"
    payload: dict[str, JSONValue] = {
        "profile": "ANALYTIC_CANDIDATE_CLAIMS_V1",
        "status": status,
        **input_hashes,
        "assertions": cast(JSONValue, assertions),
        "diagnostics": [{"code": code, "reason": reason} for code, reason in diagnostics],
        "missing_checks": cast(JSONValue, sorted(set(missing))),
        "schedule": cast(JSONValue, schedule),
        "construction": {"sewn_seams": seams, "yarn_cuts": cuts, "reattachments": reattachments},
        "checked_parameters": cast(JSONValue, values),
        "budgets": {
            "max_events": max_events,
            "max_courses": max_courses,
            "max_parameters": max_parameters,
            "recorded_limit": budget.get("limit"),
            "recorded_consumed": budget.get("consumed"),
        },
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0ANALYTIC_CANDIDATE_CLAIMS_V1\0" + encoded).hexdigest()
    return AnalyticClaimsReport(
        status,
        digest,
        encoded,
        encoded,
        tuple(sorted(assertions.items())),
        tuple((str(c), r) for c, r in diagnostics),
        tuple(sorted(set(missing))),
    )
