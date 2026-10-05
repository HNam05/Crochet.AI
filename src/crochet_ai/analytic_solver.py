"""Executable closed-pole analytic proposals with explicit, bounded run configuration.

No returned candidate has passed independent physical/geometry verification.
Generation and verification outcomes must remain separate at the API boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from fractions import Fraction
from hashlib import sha256
from math import ceil, floor, isfinite, pi
from typing import Any

import rfc8785

from .analytic_compile import CompileProvenance, compile_closed_schedule
from .analytic_counts import (
    CountLayerTrace,
    CountSearchBudget,
    CountSearchInput,
    CountSearchResult,
    CountSearchStatus,
    CountWindow,
    search_counts,
)
from .analytic_geometry import MeridianNumerics, MeridianPoint, decode_meridian
from .analytic_placement import (
    PlacementBudget,
    PlacementLayerTrace,
    PlacementResult,
    choose_phases,
)
from .analytic_trace import AnalyticSearchTrace
from .canonical import CanonicalProfile, canonical_hash, jcs_bytes
from .diagnostics import ArtifactValidationError
from .models import CrochetIR
from .solver_types import GenerationError, GenerationStatus
from .validation import SemanticValidator


@dataclass(frozen=True, slots=True)
class AnalyticRunConfig:
    parameter_profile_id: str
    tension_profile_id: str
    fabric_state: str
    numerics: MeridianNumerics
    count_budget: CountSearchBudget
    placement_budget: PlacementBudget
    min_courses: int
    max_courses: int
    max_course_hypotheses: int
    count_window_radius: int
    min_count: int
    max_count: int
    initial_ring_min: int
    initial_ring_max: int
    max_terminal_count: int
    max_increases_per_course: int
    max_decreases_per_course: int
    minimum_shaping_separation_turns: Fraction
    max_emitted_candidates: int
    max_stitches: int

    def validate(self) -> None:
        self.numerics.validate()
        integer_bounds = {
            "min_courses": (1, 512),
            "max_courses": (self.min_courses, 512),
            "max_course_hypotheses": (1, 512),
            "count_window_radius": (0, 127),
            "min_count": (1, 512),
            "max_count": (self.min_count, 512),
            "initial_ring_min": (2, 512),
            "initial_ring_max": (self.initial_ring_min, 512),
            "max_terminal_count": (1, 512),
            "max_increases_per_course": (0, 512),
            "max_decreases_per_course": (0, 512),
            "max_emitted_candidates": (1, 128),
            "max_stitches": (1, 10_000),
        }
        for name, (low, high) in integer_bounds.items():
            value = getattr(self, name)
            if type(value) is not int or type(low) is not int or not low <= value <= high:
                raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, f"config.{name}")
        if self.fabric_state not in {"RELAXED_UNSTUFFED", "BLOCKED_UNSTUFFED", "STUFFED"}:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "config.fabric_state")
        if not self.parameter_profile_id or not self.tension_profile_id:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "config.profile_identity")
        for limit in (
            self.placement_budget.max_transition_evaluations,
            self.placement_budget.max_pair_evaluations,
        ):
            if type(limit) is not int or limit < 1:
                raise GenerationError(
                    GenerationStatus.INVALID_SOLVER_INPUT, "config.placement_budget"
                )
        # Validate placement budgets even when there are no shaping transitions.
        choose_phases((2,), self.minimum_shaping_separation_turns, self.placement_budget)
        check = search_counts(
            CountSearchInput(
                (Fraction(2),),
                Fraction(1),
                (CountWindow(2, 2),),
                self.max_increases_per_course,
                self.max_decreases_per_course,
                self.count_budget,
            )
        )
        if check.status == CountSearchStatus.INVALID_SOLVER_INPUT:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, check.reason)


@dataclass(frozen=True, slots=True)
class AnalyticCandidate:
    crochet_ir: CrochetIR
    count_search: CountSearchResult
    placement: PlacementResult
    samples: tuple[MeridianPoint, ...]
    course_spacing_residual_mm: float
    material_response_id: str


@dataclass(frozen=True, slots=True)
class AnalyticGenerationResult:
    status: GenerationStatus
    reason: str
    candidates: tuple[AnalyticCandidate, ...]
    completed_course_hypotheses: int
    count_transition_evaluations: int
    placement_transition_evaluations: int
    placement_pair_evaluations: int
    search_trace: AnalyticSearchTrace | None = None


def _parameters(config: AnalyticRunConfig) -> tuple[tuple[str, str | int | float | bool], ...]:
    result: list[tuple[str, str | int | float | bool]] = []
    for field in fields(config):
        value = getattr(config, field.name)
        if field.name in {"numerics", "count_budget", "placement_budget"}:
            result.extend(
                (f"{field.name}.{nested.name}", getattr(value, nested.name))
                for nested in fields(value)
            )
        elif isinstance(value, Fraction):
            result.append((field.name, f"{value.numerator}/{value.denominator}"))
        else:
            result.append((field.name, value))
    return tuple(result)


def _rational(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _count_layer(layer: CountLayerTrace) -> dict[str, Any]:
    return {
        "pass": layer.pass_index,
        "layer": layer.layer_index,
        "retained_states": layer.retained_state_count,
        "transition_evaluations": layer.transition_evaluations,
        "completed": layer.completed,
    }


def _placement_layer(layer: PlacementLayerTrace) -> dict[str, Any]:
    return {
        "transition": layer.transition_index,
        "variants": layer.variant_count,
        "input_states": layer.input_state_count,
        "output_states": layer.output_state_count,
        "transition_evaluations": layer.transition_evaluations,
        "pair_evaluations": layer.pair_evaluations,
        "completed": layer.completed,
    }


def generate_analytic(
    design: dict[str, Any],
    material: dict[str, Any],
    config: AnalyticRunConfig,
    provenance: CompileProvenance,
) -> AnalyticGenerationResult:
    """Generate complete unverified candidates; preserve partial batch on exhaustion."""
    candidates: list[AnalyticCandidate] = []
    completed = count_used = placement_used = pairs_used = 0
    trace_base: dict[str, Any] | None = None
    hypothesis_records: list[dict[str, Any]] = []
    proposal_hashes: list[str] = []
    reserved_course_slots = 0

    def result(status: GenerationStatus, reason: str) -> AnalyticGenerationResult:
        search_trace = None
        if trace_base is not None:
            payload = {
                **trace_base,
                "hypotheses": hypothesis_records,
                "terminal": {
                    "status": status.value,
                    "reason": reason,
                    "completed_prefix_count": completed,
                    "reserved_course_slots": reserved_course_slots,
                    "proposal_ir_sha256": proposal_hashes,
                    "work": {
                        "count_transition_evaluations": count_used,
                        "placement_transition_evaluations": placement_used,
                        "placement_pair_evaluations": pairs_used,
                    },
                },
            }
            search_trace = AnalyticSearchTrace(payload)
        return AnalyticGenerationResult(
            status,
            reason,
            tuple(candidates),
            completed,
            count_used,
            placement_used,
            pairs_used,
            search_trace,
        )

    try:
        provenance.validate()
        config.validate()
        validator = SemanticValidator(
            material_profiles={material.get("profile_id", ""): material},
            design_specs={design.get("design_spec_id", ""): design},
        )
        for report in (
            validator.validate_material_profile(material),
            validator.validate_design_spec(design),
        ):
            if not report.ok:
                raise ArtifactValidationError(report)
        if config.parameter_profile_id != design["solver_options"]["parameter_profile_id"]:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "solver.parameter_profile")
        if "ANALYTIC" not in design["solver_options"]["allowed_solver_families"]:
            raise GenerationError(GenerationStatus.NOT_APPLICABLE, "solver.family_disallowed")
        if config.max_emitted_candidates > design["solver_options"]["max_candidate_evaluations"]:
            raise GenerationError(
                GenerationStatus.INVALID_SOLVER_INPUT, "solver.design_candidate_budget"
            )
        bound = design["material_profile"]
        binding_hash = (
            canonical_hash(bound["profile"], CanonicalProfile.MATERIAL_PROFILE)
            if bound["binding_type"] == "INLINE"
            else bound["sha256"]
        )
        if canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE) != binding_hash:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "solver.material_binding")
        if design["project_type"] != "AMIGURUMI_3D":
            raise GenerationError(GenerationStatus.NOT_APPLICABLE, "solver.domain")
        if (design["domain_constraints"]["stuffing_level"] == "NONE") == (
            config.fabric_state == "STUFFED"
        ):
            raise GenerationError(GenerationStatus.NOT_APPLICABLE, "solver.fabric_loading_mismatch")
        responses = [
            r
            for r in material["calibration_responses"]
            if r["measurement_conditions"]
            == {
                "canonical_stitch_type": "SINGLE_CROCHET",
                "course_mode": "CYCLIC",
                "tension_profile_id": config.tension_profile_id,
                "fabric_state": config.fabric_state,
            }
        ]
        if len(responses) != 1:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "solver.material_response")
        response = responses[0]
        gauge = response["effective_gauge"]
        stitch_pitch = Fraction(float(gauge["effective_stitch_pitch_mm"]))
        course_pitch = float(gauge["effective_course_pitch_mm"])
        meridian = decode_meridian(design, config.numerics, validator=validator)
        if (meridian.start_kind, meridian.end_kind) != ("CLOSED_POLE", "CLOSED_POLE"):
            raise GenerationError(GenerationStatus.NOT_APPLICABLE, "solver.closed_poles_only")
        if any(name.startswith(("solver.", "run.")) for name, _ in provenance.parameters):
            raise GenerationError(
                GenerationStatus.INVALID_SOLVER_INPUT, "solver.reserved_provenance_parameter"
            )
        recorded = replace(
            provenance,
            parameters=provenance.parameters
            + tuple((f"run.{k}", v) for k, v in _parameters(config)),
        )
        target_payload = design["target_geometry"]
        run_payload = [[name, value] for name, value in sorted(_parameters(config))]
        trace_base = {
            "profile": "ANALYTIC_SEARCH_TRACE_V1",
            "version": "ANALYTIC_SEARCH_TRACE_V1",
            "bindings": {
                "design_spec_sha256": canonical_hash(
                    design, CanonicalProfile.DESIGN_SPEC, validator=validator
                ),
                "material_profile_sha256": canonical_hash(
                    material, CanonicalProfile.MATERIAL_PROFILE, validator=validator
                ),
                "target_sha256": sha256(
                    b"Crochet.AI\x00ANALYTIC_SEARCH_TARGET_V1\x00" + jcs_bytes(target_payload)
                ).hexdigest(),
                "run_config_sha256": sha256(
                    b"Crochet.AI\x00ANALYTIC_SEARCH_RUN_CONFIG_V1\x00" + rfc8785.dumps(run_payload)
                ).hexdigest(),
            },
            "source": {
                "source_snapshot_sha256": provenance.source_snapshot_sha256,
                "software_commit": provenance.software_commit,
            },
            "algorithms": {
                "solver": "analytic-solver-1",
                "count": "analytic-count-dp-1",
                "phase": "analytic-phase-dp-1",
            },
            "random_seed": None,
            "material_response": {
                "response_id": response["response_id"],
                "stitch_pitch_mm": _rational(stitch_pitch),
                "course_pitch_mm": _rational(Fraction(course_pitch)),
            },
            "budgets": {
                "trace_course_slots": 8192,
                **dict((str(k), v) for k, v in sorted(_parameters(config))),
            },
        }
        # Enumerate the complete explicit course-count domain in ascending order.
        for course_count in range(config.min_courses, config.max_courses + 1):
            if completed == config.max_course_hypotheses:
                return result(GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "budget.course_hypotheses")
            if len(candidates) == config.max_emitted_candidates:
                return result(GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "budget.emitted_candidates")
            if reserved_course_slots + course_count > 8192:
                return result(GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "budget.trace_course_slots")
            reserved_course_slots += course_count
            record: dict[str, Any] = {
                "course_count": course_count,
                "samples": [],
                "circumference_mm": [],
                "count_windows": [],
                "stage": "sample",
                "completed": False,
                "outcome": "RUNNING",
            }
            hypothesis_records.append(record)
            samples = tuple(
                meridian.sample(Fraction(2 * i + 1, 2 * course_count)) for i in range(course_count)
            )
            if not all(isfinite(point.s_mm) and isfinite(point.radius_mm) for point in samples):
                raise GenerationError(GenerationStatus.NUMERICAL_FAILURE, "solver.sample")
            record["samples"] = [
                {
                    "s_mm": _rational(Fraction(p.s_mm)),
                    "radius_mm": _rational(Fraction(p.radius_mm)),
                }
                for p in samples
            ]
            record["stage"] = "circumference"
            circumferences = tuple(2 * pi * p.radius_mm for p in samples)
            if not all(isfinite(c) for c in circumferences):
                raise GenerationError(GenerationStatus.NUMERICAL_FAILURE, "solver.circumference")
            record["circumference_mm"] = [_rational(Fraction(value)) for value in circumferences]
            windows = []
            window_records = []
            record["stage"] = "count_windows"
            for i, circumference in enumerate(circumferences):
                q = Fraction(circumference) / stitch_pitch
                low = max(config.min_count, floor(q) - config.count_window_radius)
                high = min(config.max_count, ceil(q) + config.count_window_radius)
                if i == 0:
                    low, high = (
                        max(low, config.initial_ring_min),
                        min(high, config.initial_ring_max),
                    )
                if i == course_count - 1:
                    high = min(high, config.max_terminal_count)
                window_records.append(
                    {
                        "course": i,
                        "minimum": str(low),
                        "maximum": str(high),
                        "empty": low > high,
                    }
                )
                if low > high:
                    break
                windows.append(CountWindow(low, high))
            record["count_windows"] = window_records
            if len(windows) != course_count:
                record.update(completed=True, outcome="SKIPPED_EMPTY_WINDOW")
                completed += 1
                continue
            if count_used == config.count_budget.max_transition_evaluations:
                record.update(
                    outcome="SEARCH_BUDGET_EXHAUSTED",
                    count_status="SEARCH_BUDGET_EXHAUSTED",
                    count_reason="budget.transitions",
                )
                return result(GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "budget.count_transitions")
            count_budget = replace(
                config.count_budget,
                max_transition_evaluations=config.count_budget.max_transition_evaluations
                - count_used,
            )
            record["stage"] = "count_search"
            search = search_counts(
                CountSearchInput(
                    tuple(Fraction(c) for c in circumferences),
                    stitch_pitch,
                    tuple(windows),
                    config.max_increases_per_course
                    if "INCREASE" in design["difficulty_constraints"]["allowed_shaping"]
                    else 0,
                    config.max_decreases_per_course
                    if "DECREASE" in design["difficulty_constraints"]["allowed_shaping"]
                    else 0,
                    count_budget,
                )
            )
            count_used += search.transition_evaluations
            record.update(
                {
                    "count_status": search.status.value,
                    "count_reason": search.reason,
                    "count_completed_passes": search.completed_passes,
                    "count_layers": [_count_layer(layer) for layer in search.layer_trace],
                    "counts": list(search.counts),
                    "transitions": [
                        {"plain": t.plain, "increases": t.increases, "decreases": t.decreases}
                        for t in search.transitions
                    ],
                    "objective": None
                    if search.objective is None
                    else {
                        "maximum_residual_mm": _rational(search.objective.max_residual_mm),
                        "squared_residual_sum_mm2": _rational(
                            search.objective.squared_residual_sum_mm2
                        ),
                        "shaping_events": search.objective.shaping_events,
                    },
                }
            )
            if search.status in {
                CountSearchStatus.INVALID_SOLVER_INPUT,
                CountSearchStatus.SEARCH_BUDGET_EXHAUSTED,
            }:
                record.update(outcome=search.status.value)
                return result(GenerationStatus(search.status.value), search.reason)
            if search.status == CountSearchStatus.NO_FEASIBLE_CONSTRUCTION:
                record.update(completed=True, outcome=search.status.value)
                completed += 1
                continue
            placement_budget = replace(
                config.placement_budget,
                max_transition_evaluations=config.placement_budget.max_transition_evaluations
                - placement_used,
                max_pair_evaluations=config.placement_budget.max_pair_evaluations - pairs_used,
            )
            record["stage"] = "placement"
            placement = choose_phases(
                search.counts, config.minimum_shaping_separation_turns, placement_budget
            )
            placement_used += placement.transition_evaluations
            pairs_used += placement.pair_evaluations
            record["phase"] = {
                "layers": [_placement_layer(layer) for layer in placement.layer_trace],
                "phases": list(placement.phases),
                "stacking_pairs": placement.stacking_pairs,
                "proximity_penalty_turns": _rational(placement.proximity_penalty_turns),
            }
            candidate_provenance = replace(
                recorded,
                parameters=(
                    *recorded.parameters,
                    ("solver.course_count", course_count),
                    ("solver.count_transitions", search.transition_evaluations),
                    ("solver.placement_transitions", placement.transition_evaluations),
                    ("solver.placement_pairs", placement.pair_evaluations),
                    ("solver.arc_panels", meridian.arc_panels),
                    ("solver.arc_error_bound_mm", meridian.exact_arithmetic_arc_error_bound_mm),
                    ("solver.material_response_id", response["response_id"]),
                ),
            )
            record["stage"] = "compile"
            value = compile_closed_schedule(
                design,
                material,
                search.counts,
                placement.phases,
                candidate_provenance,
                max_stitches=config.max_stitches,
            )
            candidates.append(
                AnalyticCandidate(
                    CrochetIR.from_dict(value),
                    search,
                    placement,
                    samples,
                    meridian.length_mm / course_count - course_pitch,
                    response["response_id"],
                )
            )
            proposal_hash = canonical_hash(value, CanonicalProfile.CROCHET_IR, validator=validator)
            proposal_hashes.append(proposal_hash)
            record.update(
                completed=True,
                stage="complete",
                outcome="COMPILED",
                proposal_ir_sha256=proposal_hash,
            )
            completed += 1
    except GenerationError as error:
        placement_used += error.work.get("placement_transitions", 0)
        pairs_used += error.work.get("placement_pairs", 0)
        if hypothesis_records and not hypothesis_records[-1]["completed"]:
            record = hypothesis_records[-1]
            record.update(
                outcome=error.status.value,
                terminal_reason=error.reason,
                terminal_status=error.status.value,
            )
            phase_trace = error.trace
            if phase_trace:
                record["phase"] = {"layers": [_placement_layer(layer) for layer in phase_trace]}
        return result(error.status, error.reason)
    return result(
        GenerationStatus.CANDIDATES_EMITTED
        if candidates
        else GenerationStatus.NO_FEASIBLE_CONSTRUCTION,
        "domain.complete",
    )
