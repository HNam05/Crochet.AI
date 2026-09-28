"""Bounded exact count proposals, not a geometry solver or verification gate.

The caller supplies course hypotheses and explicit integer search intervals.
Two passes avoid invalid lexicographic pruning of a bottleneck/additive cost.
See docs/ANALYTIC_COUNT_SEARCH.md for the scope, units and work budgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from itertools import pairwise


class CountSearchStatus(StrEnum):
    OPTIMAL_COUNT_PROPOSAL = "OPTIMAL_COUNT_PROPOSAL"
    INVALID_SOLVER_INPUT = "INVALID_SOLVER_INPUT"
    SEARCH_BUDGET_EXHAUSTED = "SEARCH_BUDGET_EXHAUSTED"
    NO_FEASIBLE_CONSTRUCTION = "NO_FEASIBLE_CONSTRUCTION"


@dataclass(frozen=True, slots=True)
class CountWindow:
    minimum: int
    maximum: int


@dataclass(frozen=True, slots=True)
class CountSearchBudget:
    max_courses: int
    max_count_values_per_course: int
    max_dp_states_per_course: int
    max_transition_evaluations: int


@dataclass(frozen=True, slots=True)
class CountSearchInput:
    circumference_mm: tuple[Fraction, ...]
    stitch_pitch_mm: Fraction
    windows: tuple[CountWindow, ...]
    max_increases_per_course: int
    max_decreases_per_course: int
    budget: CountSearchBudget


@dataclass(frozen=True, slots=True)
class CountTransition:
    plain: int
    increases: int
    decreases: int


@dataclass(frozen=True, slots=True)
class CountObjective:
    max_residual_mm: Fraction
    squared_residual_sum_mm2: Fraction
    shaping_events: int


@dataclass(frozen=True, slots=True)
class CountSearchResult:
    status: CountSearchStatus
    reason: str
    transition_evaluations: int
    completed_passes: int
    counts: tuple[int, ...] = ()
    transitions: tuple[CountTransition, ...] = ()
    objective: CountObjective | None = None
    algorithm_version: str = "analytic-count-dp-1"


def _integer(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _rational(value: object, *, positive: bool) -> bool:
    return (
        isinstance(value, Fraction)
        and (value > 0 if positive else value >= 0)
        and value.numerator.bit_length() <= 256
        and value.denominator.bit_length() <= 128
    )


def _input_error(request: CountSearchInput) -> str | None:
    if not isinstance(request, CountSearchInput) or not isinstance(
        request.budget, CountSearchBudget
    ):
        return "input.type"
    if not isinstance(request.windows, tuple) or not isinstance(request.circumference_mm, tuple):
        return "input.immutable_sequences_required"
    if not request.windows or len(request.windows) != len(request.circumference_mm):
        return "input.course_lengths"
    budget = request.budget
    if not (
        _integer(budget.max_courses, 1, 512)
        and _integer(budget.max_count_values_per_course, 1, 256)
        and _integer(budget.max_dp_states_per_course, 1, 256)
        and _integer(budget.max_transition_evaluations, 1, 2_000_000)
        and _integer(request.max_increases_per_course, 0, 100_000)
        and _integer(request.max_decreases_per_course, 0, 100_000)
    ):
        return "input.integer_limits"
    if not _rational(request.stitch_pitch_mm, positive=True):
        return "input.stitch_pitch"
    # Bound even invalid inputs before scanning their contents.
    if len(request.windows) > 512:
        return "input.implementation_course_limit"
    for circumference, window in zip(request.circumference_mm, request.windows, strict=True):
        if not _rational(circumference, positive=False):
            return "input.circumference"
        if not isinstance(window, CountWindow) or not (
            _integer(window.minimum, 1, 100_000)
            and _integer(window.maximum, window.minimum, 100_000)
        ):
            return "input.count_window"
    return None


def _transition(before: int, after: int, request: CountSearchInput) -> CountTransition | None:
    increases = max(after - before, 0)
    decreases = max(before - after, 0)
    plain = before - increases - 2 * decreases
    if (
        plain < 0
        or increases > request.max_increases_per_course
        or decreases > request.max_decreases_per_course
    ):
        return None
    return CountTransition(plain, increases, decreases)


def search_counts(request: CountSearchInput) -> CountSearchResult:
    """Find the global optimum in the declared count-only finite domain.

    No partial proposal escapes exhaustion. All counters are deterministic;
    each tested predecessor/successor pair costs one evaluation in either pass.
    """
    error = _input_error(request)
    if error is not None:
        return CountSearchResult(CountSearchStatus.INVALID_SOLVER_INPUT, error, 0, 0)
    budget = request.budget
    used = 0
    passes = 0

    def failure(status: CountSearchStatus, reason: str) -> CountSearchResult:
        return CountSearchResult(status, reason, used, passes)

    if len(request.windows) > budget.max_courses:
        return failure(CountSearchStatus.SEARCH_BUDGET_EXHAUSTED, "budget.courses")
    if any(w.maximum - w.minimum + 1 > budget.max_count_values_per_course for w in request.windows):
        return failure(CountSearchStatus.SEARCH_BUDGET_EXHAUSTED, "budget.count_values")

    def residual(layer: int, count: int) -> Fraction:
        return abs(count * request.stitch_pitch_mm - request.circumference_mm[layer])

    def values(layer: int) -> range:
        window = request.windows[layer]
        return range(window.minimum, window.maximum + 1)

    # Pass 1: bottleneck costs have the monotone recurrence min(max(prefix, node)).
    bottlenecks = {count: residual(0, count) for count in values(0)}
    if len(bottlenecks) > budget.max_dp_states_per_course:
        return failure(CountSearchStatus.SEARCH_BUDGET_EXHAUSTED, "budget.dp_states")
    for layer in range(1, len(request.windows)):
        next_bottlenecks: dict[int, Fraction] = {}
        for count in values(layer):
            node_cost = residual(layer, count)
            for before in sorted(bottlenecks):
                if used == budget.max_transition_evaluations:
                    return failure(CountSearchStatus.SEARCH_BUDGET_EXHAUSTED, "budget.transitions")
                used += 1
                if _transition(before, count, request) is None:
                    continue
                cost = max(bottlenecks[before], node_cost)
                if count not in next_bottlenecks or cost < next_bottlenecks[count]:
                    next_bottlenecks[count] = cost
            if len(next_bottlenecks) > budget.max_dp_states_per_course:
                return failure(CountSearchStatus.SEARCH_BUDGET_EXHAUSTED, "budget.dp_states")
        if not next_bottlenecks:
            return failure(CountSearchStatus.NO_FEASIBLE_CONSTRUCTION, "domain.no_reachable_path")
        bottlenecks = next_bottlenecks
    threshold = min(bottlenecks.values())
    passes = 1

    # Pass 2: within the optimal bottleneck, remaining costs are additive.
    paths: dict[int, tuple[Fraction, int, tuple[int, ...]]] = {
        count: (residual(0, count) ** 2, 0, (count,))
        for count in values(0)
        if residual(0, count) <= threshold
    }
    for layer in range(1, len(request.windows)):
        next_paths: dict[int, tuple[Fraction, int, tuple[int, ...]]] = {}
        for count in values(layer):
            node_cost = residual(layer, count)
            if node_cost > threshold:
                continue
            for before in sorted(paths):
                if used == budget.max_transition_evaluations:
                    return failure(CountSearchStatus.SEARCH_BUDGET_EXHAUSTED, "budget.transitions")
                used += 1
                transition = _transition(before, count, request)
                if transition is None:
                    continue
                previous = paths[before]
                candidate = (
                    previous[0] + node_cost**2,
                    previous[1] + transition.increases + transition.decreases,
                    (*previous[2], count),
                )
                if count not in next_paths or candidate < next_paths[count]:
                    next_paths[count] = candidate
        paths = next_paths
    cost_sum, shaping, counts = min(paths.values())
    transitions: list[CountTransition] = []
    for before, after in pairwise(counts):
        transition = _transition(before, after, request)
        # Proven by the two passes; no independent verification claim.
        assert transition is not None
        transitions.append(transition)
    return CountSearchResult(
        CountSearchStatus.OPTIMAL_COUNT_PROPOSAL,
        "domain.optimum",
        used,
        2,
        counts,
        tuple(transitions),
        CountObjective(threshold, cost_sum, shaping),
    )
