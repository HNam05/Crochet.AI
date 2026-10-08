"""Independent bounded replay of analytic search evidence, never generation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from itertools import pairwise
from math import ceil, floor, isfinite, pi, sin
from typing import Any

from .analytic_claims import inspect_analytic_candidate_claims
from .analytic_coordinate_target import (
    PROFILE_ID as COORDINATE_PROFILE_ID,
)
from .analytic_coordinate_target import (
    admit_analytic_coordinate_target,
)
from .analytic_target import AnalyticTargetError
from .canonical import CanonicalProfile, canonical_hash, jcs_bytes, validate_ijson
from .coordinate_meridian_replay import CoordinateMeridianReplay, CoordinateReplayError
from .diagnostics import ArtifactValidationError
from .trace_count_replay import CountReplayBudget, replay_count_search
from .trace_phase_replay import PhaseReplayBudget, replay_phase_search
from .trace_verification_types import (
    TraceAuditInputError,
    TraceReplayBudgetExceeded,
    TraceReplayWork,
)
from .validation import SemanticValidator

AUDIT_DOMAIN = b"Crochet.AI\0ANALYTIC_TRACE_AUDIT_V1\0"
_TRACE_DOMAIN = b"Crochet.AI\0ANALYTIC_SEARCH_TRACE_V1\0"
_INTEGER_LIMITS = {
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
}
_NESTED_KEYS = {
    "numerics": {
        "arc_length_abs_tolerance_mm",
        "roundoff_allowance_mm",
        "max_arc_panels",
        "radius_zero_tolerance_mm",
    },
    "count_budget": {
        "max_courses",
        "max_count_values_per_course",
        "max_dp_states_per_course",
        "max_transition_evaluations",
    },
    "placement_budget": {
        "max_variants_per_transition",
        "max_transition_evaluations",
        "max_pair_evaluations",
    },
}


@dataclass(frozen=True, slots=True)
class AnalyticTraceAudit:
    status: str
    sha256: str
    canonical_bytes: bytes
    assertions: tuple[tuple[str, bool], ...]
    diagnostics: tuple[tuple[str, str], ...]
    missing_checks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return dict(json.loads(self.canonical_bytes))


def _object(value: object, keys: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise TraceAuditInputError(name + ".fields")
    return value


def _bounded(value: object) -> None:
    pending = [(value, 0)]
    visited = 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if visited > 100_000 or depth > 64:
            raise TraceAuditInputError("trace_audit.input_complexity")
        if isinstance(item, dict):
            if any(not isinstance(key, str) or len(key) > 128 for key in item):
                raise TraceAuditInputError("trace_audit.input_key")
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, str) and len(item) > 4096:
            raise TraceAuditInputError("trace_audit.input_string")
    validate_ijson(value)


def bound_analytic_search_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    """Bound direct pipeline inputs before their evidence-bundle digest exists."""
    evidence = _object(
        dict(value), {"run_config", "search_trace", "candidate_proposals"}, "search_evidence"
    )
    _bounded(evidence)
    return evidence


def _fraction(value: object) -> Fraction:
    if not isinstance(value, str) or re.fullmatch(r"-?[0-9]{1,78}/[1-9][0-9]{0,38}", value) is None:
        raise TraceAuditInputError("trace_audit.fraction")
    result = Fraction(value)
    if (
        value != _rational(result)
        or result.numerator.bit_length() > 256
        or result.denominator.bit_length() > 128
    ):
        raise TraceAuditInputError("trace_audit.fraction_bounds")
    return result


def _rational(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _configuration(value: object) -> tuple[dict[str, Any], dict[str, Any]]:
    keys = (
        set(_INTEGER_LIMITS)
        | set(_NESTED_KEYS)
        | {
            "parameter_profile_id",
            "tension_profile_id",
            "fabric_state",
            "minimum_shaping_separation_turns",
        }
    )
    config = dict(_object(value, keys, "run_config"))
    for name, (low, high) in _INTEGER_LIMITS.items():
        if type(config[name]) is not int or not low <= config[name] <= high:
            raise TraceAuditInputError("run_config." + name)
    for lower, upper in (
        ("min_courses", "max_courses"),
        ("min_count", "max_count"),
        ("initial_ring_min", "initial_ring_max"),
    ):
        if config[lower] > config[upper]:
            raise TraceAuditInputError("run_config.order")
    for name in ("parameter_profile_id", "tension_profile_id", "fabric_state"):
        if (
            not isinstance(config[name], str)
            or not config[name]
            or len(config[name]) > 128
            or not config[name].isascii()
        ):
            raise TraceAuditInputError("run_config." + name)
    if config["fabric_state"] not in {"RELAXED_UNSTUFFED", "BLOCKED_UNSTUFFED", "STUFFED"}:
        raise TraceAuditInputError("run_config.fabric_state")
    separation = _fraction(config["minimum_shaping_separation_turns"])
    if not 0 <= separation <= Fraction(1, 2):
        raise TraceAuditInputError("run_config.minimum_shaping_separation_turns")
    for name, fields in _NESTED_KEYS.items():
        config[name] = dict(_object(config[name], fields, "run_config." + name))
    CountReplayBudget(**config["count_budget"])
    PhaseReplayBudget(**config["placement_budget"])
    if any(
        config["placement_budget"][name] == 0
        for name in ("max_transition_evaluations", "max_pair_evaluations")
    ):
        raise TraceAuditInputError("run_config.placement_budget")
    numeric = config["numerics"]
    for name in (
        "arc_length_abs_tolerance_mm",
        "roundoff_allowance_mm",
        "radius_zero_tolerance_mm",
    ):
        if type(numeric[name]) not in {int, float} or not isfinite(numeric[name]):
            raise TraceAuditInputError("run_config.numerics")
    if not (
        0 < numeric["roundoff_allowance_mm"] < numeric["arc_length_abs_tolerance_mm"]
        and numeric["radius_zero_tolerance_mm"] >= 0
        and type(numeric["max_arc_panels"]) is int
        and 2 <= numeric["max_arc_panels"] <= 200_000
    ):
        raise TraceAuditInputError("run_config.numerics")
    flat = {name: item for name, item in config.items() if name not in _NESTED_KEYS}
    for name in _NESTED_KEYS:
        flat.update((name + "." + key, item) for key, item in config[name].items())
    return config, flat


def _radius(design: dict[str, Any]) -> float | None:
    target = design["target_geometry"]
    if design["project_type"] != "AMIGURUMI_3D" or target["geometry_type"] != "ANALYTIC_SHAPE":
        return None
    measurements = {
        row["measurement_id"]: float(row["value_mm"])
        for row in design["dimensions"]["measurements"]
    }
    params = {row["parameter"]: measurements[row["measurement_id"]] for row in target["parameters"]}
    if target["primitive"] == "SPHERE":
        return float(params["RADIUS"])
    if target["primitive"] == "ELLIPSOID" and params["EQUATORIAL_RADIUS"] == params["POLAR_RADIUS"]:
        return float(params["EQUATORIAL_RADIUS"])
    return None


def _compile_failure(
    design: dict[str, Any], counts: tuple[int, ...], max_stitches: int
) -> tuple[str, str] | None:
    if (
        design["domain_constraints"]["surface_mode"] != "CLOSED"
        or design["construction_constraints"]["intentional_openings"]
        or len(design["colors"]) != 1
    ):
        return "NOT_APPLICABLE", "compiler.closed_single_color_only"
    difficulty = design["difficulty_constraints"]
    shaping = {"INCREASE" for a, b in pairwise(counts) if b > a} | {
        "DECREASE" for a, b in pairwise(counts) if b < a
    }
    if (
        "SINGLE_CROCHET" not in difficulty["allowed_stitch_types"]
        or not {"MAGIC_RING", "CLOSE"} <= set(difficulty["allowed_construction_operations"])
        or not shaping <= set(difficulty["allowed_shaping"])
    ):
        return "NOT_APPLICABLE", "compiler.design_techniques"
    if counts[0] + sum(min(a, b) for a, b in pairwise(counts)) > max_stitches:
        return "SEARCH_BUDGET_EXHAUSTED", "compiler.stitches"
    return None


def inspect_analytic_search_trace(
    design: dict[str, Any],
    material: dict[str, Any],
    run_config: object,
    search_trace: object,
    candidate_proposals: object,
    *,
    validator: SemanticValidator,
    max_replay_work: int = 6_000_000,
) -> AnalyticTraceAudit:
    """Recompute evidence; PASS is restricted to this computational profile."""
    work = TraceReplayWork(max_replay_work)
    for value in (design, material, run_config, search_trace, candidate_proposals):
        _bounded(value)
    config, flat = _configuration(run_config)
    trace = _object(
        search_trace,
        {
            "profile",
            "version",
            "bindings",
            "source",
            "algorithms",
            "random_seed",
            "material_response",
            "budgets",
            "hypotheses",
            "terminal",
        },
        "search_trace",
    )
    records = trace["hypotheses"]
    if not isinstance(records, list) or len(records) > 512:
        raise TraceAuditInputError("search_trace.hypotheses")
    if not isinstance(candidate_proposals, list) or len(candidate_proposals) > 128:
        raise TraceAuditInputError("search_trace.candidate_proposals")
    for artifact, validate in (
        (design, validator.validate_design_spec),
        (material, validator.validate_material_profile),
    ):
        report = validate(artifact)
        if not report.ok:
            raise ArtifactValidationError(report)
    assertions: dict[str, bool] = {}
    diagnostics: list[tuple[str, str]] = []
    missing: list[str] = []
    coordinate_target = None
    meridian: CoordinateMeridianReplay | None = None
    coordinate_scope = False

    def check(name: str, actual: Any, expected: Any) -> None:
        ok = jcs_bytes(actual) == jcs_bytes(expected)
        assertions[name] = ok
        if not ok:
            diagnostics.append(("E_DETERMINISM", "trace_audit." + name))

    def finish() -> AnalyticTraceAudit:
        status = "FAIL" if diagnostics else "INDETERMINATE" if missing else "PASS"
        payload: dict[str, Any] = {
            "profile": "ANALYTIC_TRACE_AUDIT_V1",
            "status": status,
            "scope": (
                "Exact staged analytic coordinate-meridian search; computational evidence only"
                if coordinate_scope
                else "Exact staged analytic sphere search; computational evidence only"
            ),
            "source_authentication": "NOT_VERIFIED",
            "physical_status": "UNTESTED",
            "search_trace_sha256": sha256(_TRACE_DOMAIN + jcs_bytes(trace)).hexdigest(),
            "assertions": assertions,
            "diagnostics": [{"code": code, "reason": reason} for code, reason in diagnostics],
            "missing_checks": sorted(set(missing)),
            "budgets": {
                "max_replay_work": work.limit,
                "trace_course_slots": 8192,
                "max_proposals": 128,
            },
            "proof_work": work.consumed,
        }
        if coordinate_scope and coordinate_target is not None and meridian is not None:
            payload["coordinate_sampling"] = {
                "producer_policy": "EXPLICIT_COORDINATE_MERIDIAN_V1",
                "verifier_policy": "COORDINATE_MERIDIAN_REPLAY_V1",
                "target_sha256": coordinate_target.sha256,
                "segment_count": len(meridian.lengths),
                "total_length_mm": meridian.total_float,
                "total_length_rational_mm": _rational(meridian.total),
                "conservative_arc_error_bound_mm": meridian.error_bound,
                "arc_length_abs_tolerance_mm": config["numerics"]["arc_length_abs_tolerance_mm"],
                "roundoff_allowance_mm": config["numerics"]["roundoff_allowance_mm"],
                "sqrt_bracket_max_steps_per_side": 2,
            }
        encoded = jcs_bytes(payload)
        return AnalyticTraceAudit(
            status,
            sha256(AUDIT_DOMAIN + encoded).hexdigest(),
            encoded,
            tuple(sorted(assertions.items())),
            tuple(diagnostics),
            tuple(sorted(set(missing))),
        )

    check("profile", trace["profile"], "ANALYTIC_SEARCH_TRACE_V1")
    check("version", trace["version"], "ANALYTIC_SEARCH_TRACE_V1")
    check(
        "algorithms",
        trace["algorithms"],
        {
            "solver": "analytic-solver-1",
            "count": "analytic-count-dp-1",
            "phase": "analytic-phase-dp-1",
        },
    )
    check("random_seed", trace["random_seed"], None)
    check("budgets", trace["budgets"], {"trace_course_slots": 8192, **flat})
    design_hash = canonical_hash(design, CanonicalProfile.DESIGN_SPEC, validator=validator)
    material_hash = canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE, validator=validator)
    check(
        "bindings",
        trace["bindings"],
        {
            "design_spec_sha256": design_hash,
            "material_profile_sha256": material_hash,
            "target_sha256": sha256(
                b"Crochet.AI\0ANALYTIC_SEARCH_TARGET_V1\0" + jcs_bytes(design["target_geometry"])
            ).hexdigest(),
            "run_config_sha256": sha256(
                b"Crochet.AI\0ANALYTIC_SEARCH_RUN_CONFIG_V1\0"
                + jcs_bytes([[key, item] for key, item in sorted(flat.items())])
            ).hexdigest(),
        },
    )
    source = _object(
        trace["source"], {"software_commit", "source_snapshot_sha256"}, "search_trace.source"
    )
    for key, length in (("software_commit", "40,64"), ("source_snapshot_sha256", "64")):
        value = source[key]
        if (
            not isinstance(value, str)
            or re.fullmatch(f"[a-f0-9]{{{length}}}", value) is None
            or set(value) == {"0"}
        ):
            raise TraceAuditInputError("search_trace.source." + key)
    responses = [
        row
        for row in material["calibration_responses"]
        if row["measurement_conditions"]
        == {
            "canonical_stitch_type": "SINGLE_CROCHET",
            "course_mode": "CYCLIC",
            "tension_profile_id": config["tension_profile_id"],
            "fabric_state": config["fabric_state"],
        }
    ]
    if len(responses) != 1:
        raise TraceAuditInputError("trace_audit.material_response")
    response = responses[0]
    pitch = Fraction(float(response["effective_gauge"]["effective_stitch_pitch_mm"]))
    check(
        "material_response",
        trace["material_response"],
        {
            "response_id": response["response_id"],
            "stitch_pitch_mm": _rational(pitch),
            "course_pitch_mm": _rational(
                Fraction(float(response["effective_gauge"]["effective_course_pitch_mm"]))
            ),
        },
    )
    material_binding = design["material_profile"]
    expected_material_hash = (
        canonical_hash(
            material_binding["profile"], CanonicalProfile.MATERIAL_PROFILE, validator=validator
        )
        if material_binding["binding_type"] == "INLINE"
        else material_binding["sha256"]
    )
    check("design_material_binding", material_hash, expected_material_hash)
    check(
        "candidate_budget",
        config["max_emitted_candidates"] <= design["solver_options"]["max_candidate_evaluations"],
        True,
    )
    check(
        "fabric_loading",
        (design["domain_constraints"]["stuffing_level"] == "NONE")
        != (config["fabric_state"] == "STUFFED"),
        True,
    )
    radius = _radius(design)
    target_profile = design["target_geometry"].get("radial_profile", {})
    if (
        radius is None
        and design["target_geometry"].get("primitive") == "SURFACE_OF_REVOLUTION"
        and target_profile.get("canonicalization_profile") == COORDINATE_PROFILE_ID
    ):
        coordinate_scope = True
        try:
            coordinate_target = admit_analytic_coordinate_target(design, validator)
            meridian = CoordinateMeridianReplay.build(
                coordinate_target,
                config["numerics"]["arc_length_abs_tolerance_mm"],
                config["numerics"]["roundoff_allowance_mm"],
                config["numerics"]["max_arc_panels"],
                work,
                config["numerics"]["radius_zero_tolerance_mm"],
            )
            assertions["coordinate_sampler_policy"] = True
        except TraceReplayBudgetExceeded:
            missing.append("independent_replay_budget_exhausted")
            return finish()
        except AnalyticTargetError as exc:
            if exc.status == "NOT_APPLICABLE":
                missing.append("unsupported_coordinate_target_scope")
                return finish()
            diagnostics.append(("E_DETERMINISM", "trace_audit.coordinate_target." + exc.reason))
            return finish()
        except CoordinateReplayError as exc:
            if str(exc) == "coordinate.thin_neck":
                missing.append("unsupported_coordinate_thin_neck")
                return finish()
            diagnostics.append(("E_DETERMINISM", "trace_audit.coordinate_sampler." + str(exc)))
            return finish()
    elif radius is None:
        missing.append("unsupported_target_sampler")
        return finish()
    elif not isfinite(pi * radius):
        missing.append("nonfinite_sphere_sampling")
        return finish()
    proposals: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for index, proposal in enumerate(candidate_proposals):
        if not isinstance(proposal, dict):
            raise TraceAuditInputError("candidate_proposal.object")
        claims = inspect_analytic_candidate_claims(design, material, proposal, validator=validator)
        data = claims.to_dict()
        missing.extend(
            f"proposal_{index}:{item}"
            for item in claims.missing_checks
            if item.startswith("unsupported_parameter:")
        )
        check(
            f"proposal_{index}_raw_claims",
            claims.status != "FAIL"
            and dict(claims.assertions).get("closed_sc_source_schedule", False),
            True,
        )
        params = {row["name"]: row["value"] for row in proposal["provenance"]["solver_parameters"]}
        check(
            f"proposal_{index}_source",
            {
                "software_commit": proposal["provenance"]["software_commit"],
                "source_snapshot_sha256": params.get("source_snapshot_sha256"),
            },
            source,
        )
        check(
            f"proposal_{index}_run",
            {key[4:]: val for key, val in params.items() if key.startswith("run.")},
            flat,
        )
        check(
            f"proposal_{index}_native", any(key.startswith("prototype.") for key in params), False
        )
        if coordinate_scope:
            assert coordinate_target is not None and meridian is not None
            check(
                f"proposal_{index}_coordinate_parameters",
                {
                    key: params.get(key)
                    for key in (
                        "solver.coordinate_sampler_version",
                        "solver.coordinate_target_sha256",
                        "solver.coordinate_sqrt_bracket_max_steps",
                    )
                },
                {
                    "solver.coordinate_sampler_version": "EXPLICIT_COORDINATE_MERIDIAN_V1",
                    "solver.coordinate_target_sha256": coordinate_target.sha256,
                    "solver.coordinate_sqrt_bracket_max_steps": 2,
                },
            )
        schedule = data["schedule"]
        if not isinstance(schedule, dict):
            raise TraceAuditInputError("candidate_proposal.schedule")
        proposals.append((str(data["source_ir_sha256"]), schedule, params))
    completed = slots = count_used = phase_used = pairs_used = 0
    expected_records: list[dict[str, Any]] = []
    hashes: list[str] = []
    terminal_status, terminal_reason = "NO_FEASIBLE_CONSTRUCTION", "domain.complete"
    try:
        for courses in range(config["min_courses"], config["max_courses"] + 1):
            stopped = (
                "budget.course_hypotheses"
                if completed == config["max_course_hypotheses"]
                else "budget.emitted_candidates"
                if len(hashes) == config["max_emitted_candidates"]
                else "budget.trace_course_slots"
                if slots + courses > 8192
                else None
            )
            if stopped:
                terminal_status, terminal_reason = "SEARCH_BUDGET_EXHAUSTED", stopped
                break
            if len(expected_records) >= len(records):
                check("attempted_prefix", len(records), len(expected_records) + 1)
                return finish()
            actual = records[len(expected_records)]
            if not isinstance(actual, dict):
                raise TraceAuditInputError("search_trace.hypothesis.object")
            slots += courses
            rec: dict[str, Any] = {
                "course_count": courses,
                "samples": [],
                "circumference_mm": [],
                "count_windows": [],
                "stage": "count_windows",
                "completed": False,
                "outcome": "RUNNING",
            }
            expected_records.append(rec)
            circumferences = []
            windows = []
            if coordinate_scope:
                rec["stage"] = "sample"
                sample_rows = []
                numerical_failure = False
                for i in range(courses):
                    fraction = Fraction(2 * i + 1, 2 * courses)
                    assert meridian is not None
                    try:
                        sample = meridian.sample(fraction, work)
                    except TraceReplayBudgetExceeded:
                        missing.append("independent_replay_budget_exhausted")
                        return finish()
                    except CoordinateReplayError as exc:
                        reason = str(exc).removeprefix("coordinate.")
                        if reason not in {
                            "s_conversion",
                            "radius_conversion",
                            "axial_conversion",
                            "negative_radius",
                        }:
                            diagnostics.append(
                                ("E_DETERMINISM", "trace_audit.coordinate_sample." + str(exc))
                            )
                            return finish()
                        rec.update(
                            outcome="NUMERICAL_FAILURE",
                            terminal_status="NUMERICAL_FAILURE",
                            terminal_reason="meridian." + reason,
                        )
                        terminal_status, terminal_reason = (
                            "NUMERICAL_FAILURE",
                            "meridian." + reason,
                        )
                        missing.append("coordinate_sampling_numerical_failure")
                        numerical_failure = True
                        break
                    sample_rows.append(
                        {
                            "s_mm": _rational(Fraction(sample.s_mm)),
                            "radius_mm": _rational(Fraction(sample.radius_mm)),
                            "axial_mm": _rational(Fraction(sample.axial_mm)),
                        }
                    )
                if not numerical_failure:
                    rec["samples"] = sample_rows
                    rec["stage"] = "circumference"
                    sampled_circumferences = [
                        2 * pi * float(row_radius)
                        for row_radius in (Fraction(row["radius_mm"]) for row in sample_rows)
                    ]
                    if not all(isfinite(value) for value in sampled_circumferences):
                        rec.update(
                            stage="circumference",
                            outcome="NUMERICAL_FAILURE",
                            terminal_status="NUMERICAL_FAILURE",
                            terminal_reason="solver.circumference",
                        )
                        terminal_status, terminal_reason = (
                            "NUMERICAL_FAILURE",
                            "solver.circumference",
                        )
                        missing.append("coordinate_sampling_numerical_failure")
                        numerical_failure = True
                    else:
                        circumferences = [Fraction(value) for value in sampled_circumferences]
                        rec["stage"] = "count_windows"
                        rec["circumference_mm"] = [_rational(value) for value in circumferences]
                if numerical_failure:
                    break
            else:
                for i in range(courses):
                    fraction = Fraction(2 * i + 1, 2 * courses)
                    assert radius is not None
                    r = (
                        radius
                        if fraction == Fraction(1, 2)
                        else radius * sin(pi * float(min(fraction, 1 - fraction)))
                    )
                    rec["samples"].append(
                        {
                            "s_mm": _rational(Fraction(float(fraction) * (pi * radius))),
                            "radius_mm": _rational(Fraction(r)),
                        }
                    )
                    circumference = 2 * pi * r
                    if not isfinite(circumference):
                        missing.append("nonfinite_sphere_sampling")
                        return finish()
                    circumferences.append(Fraction(circumference))
                rec["circumference_mm"] = [_rational(value) for value in circumferences]
            for i, circumference_fraction in enumerate(circumferences):
                quotient = circumference_fraction / pitch
                low = max(config["min_count"], floor(quotient) - config["count_window_radius"])
                high = min(config["max_count"], ceil(quotient) + config["count_window_radius"])
                if i == 0:
                    low, high = (
                        max(low, config["initial_ring_min"]),
                        min(high, config["initial_ring_max"]),
                    )
                if i == courses - 1:
                    high = min(high, config["max_terminal_count"])
                rec["count_windows"].append(
                    {"course": i, "minimum": str(low), "maximum": str(high), "empty": low > high}
                )
                if low > high:
                    break
                windows.append((low, high))
            if len(windows) != courses:
                rec.update(completed=True, outcome="SKIPPED_EMPTY_WINDOW")
                completed += 1
                continue
            if count_used == config["count_budget"]["max_transition_evaluations"]:
                rec.update(
                    outcome="SEARCH_BUDGET_EXHAUSTED",
                    count_status="SEARCH_BUDGET_EXHAUSTED",
                    count_reason="budget.transitions",
                )
                terminal_status, terminal_reason = (
                    "SEARCH_BUDGET_EXHAUSTED",
                    "budget.count_transitions",
                )
                break
            rec["stage"] = "count_search"
            count_budget = {
                **config["count_budget"],
                "max_transition_evaluations": config["count_budget"]["max_transition_evaluations"]
                - count_used,
            }
            allowed = design["difficulty_constraints"]["allowed_shaping"]
            count = replay_count_search(
                tuple(circumferences),
                pitch,
                tuple(windows),
                config["max_increases_per_course"] if "INCREASE" in allowed else 0,
                config["max_decreases_per_course"] if "DECREASE" in allowed else 0,
                CountReplayBudget(**count_budget),
                work=work,
            )
            count_used += count.used_transition_evaluations
            result = count.to_dict()
            rec.update(result)
            status = count.count_status
            if status != "OPTIMAL_COUNT_PROPOSAL":
                rec["outcome"] = status
                if status == "NO_FEASIBLE_CONSTRUCTION":
                    rec["completed"] = True
                    completed += 1
                    continue
                terminal_status, terminal_reason = status, count.count_reason
                break
            counts = count.counts
            rec["stage"] = "placement"
            phase_budget = {
                **config["placement_budget"],
                "max_transition_evaluations": config["placement_budget"][
                    "max_transition_evaluations"
                ]
                - phase_used,
                "max_pair_evaluations": config["placement_budget"]["max_pair_evaluations"]
                - pairs_used,
            }
            phase = replay_phase_search(
                counts,
                _fraction(config["minimum_shaping_separation_turns"]),
                PhaseReplayBudget(**phase_budget),
                work=work,
            )
            phase_used += phase.used_transition_evaluations
            pairs_used += phase.used_pair_evaluations
            phase_data = phase.to_dict()
            if phase.status != "PASS":
                terminal_status, terminal_reason = phase.status, phase.reason
                rec.update(
                    outcome=phase.status, terminal_status=phase.status, terminal_reason=phase.reason
                )
                if phase_data["layers"]:
                    rec["phase"] = {"layers": phase_data["layers"]}
                break
            rec["phase"] = phase_data
            rec["stage"] = "compile"
            failure = _compile_failure(design, counts, config["max_stitches"])
            if failure:
                terminal_status, terminal_reason = failure
                rec.update(
                    outcome=terminal_status,
                    terminal_status=terminal_status,
                    terminal_reason=terminal_reason,
                )
                break
            proposal_index = len(hashes)
            declared = actual.get("proposal_ir_sha256")
            if not isinstance(declared, str) or re.fullmatch(r"[a-f0-9]{64}", declared) is None:
                check(f"hypothesis_{courses}_proposal_hash", declared, "required sha256")
                return finish()
            if proposal_index >= len(proposals):
                missing.append("original_proposal_artifacts")
                proposal_hash = declared
            else:
                proposal_hash, schedule, params = proposals[proposal_index]
                check(
                    f"proposal_{proposal_index}_schedule",
                    {"counts": schedule["counts"], "phases": schedule["phases"]},
                    {"counts": list(counts), "phases": phase_data["phases"]},
                )
                expected_params = {
                    "course_count": courses,
                    "count_transitions": count.used_transition_evaluations,
                    "placement_transitions": phase.used_transition_evaluations,
                    "placement_pairs": phase.used_pair_evaluations,
                    "arc_panels": (meridian is not None and len(meridian.lengths)) or 0,
                    "arc_error_bound_mm": meridian.error_bound if meridian is not None else 0.0,
                    "material_response_id": response["response_id"],
                }
                check(
                    f"proposal_{proposal_index}_work",
                    {key: params.get("solver." + key) for key in expected_params},
                    expected_params,
                )
            hashes.append(proposal_hash)
            rec.update(
                completed=True,
                stage="complete",
                outcome="COMPILED",
                proposal_ir_sha256=proposal_hash,
            )
            completed += 1
        else:
            terminal_status = "CANDIDATES_EMITTED" if hashes else "NO_FEASIBLE_CONSTRUCTION"
    except TraceReplayBudgetExceeded:
        missing.append("independent_replay_budget_exhausted")
        return finish()
    check("hypotheses", records, expected_records)
    if len(proposals) >= len(hashes):
        check("proposal_artifact_count", len(proposals), len(hashes))
    check(
        "terminal",
        trace["terminal"],
        {
            "status": terminal_status,
            "reason": terminal_reason,
            "completed_prefix_count": completed,
            "reserved_course_slots": slots,
            "proposal_ir_sha256": hashes,
            "work": {
                "count_transition_evaluations": count_used,
                "placement_transition_evaluations": phase_used,
                "placement_pair_evaluations": pairs_used,
            },
        },
    )
    return finish()
