"""Independent exact replay of the analytic count-search trace."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise

from crochet_ai.trace_verification_types import (
    TraceAuditInputError,
    TraceReplayBudgetExceeded,
    TraceReplayWork,
)


@dataclass(frozen=True, slots=True)
class CountReplayBudget:
    max_courses: int = 512
    max_count_values_per_course: int = 256
    max_dp_states_per_course: int = 256
    max_transition_evaluations: int = 2_000_000

    def __post_init__(self) -> None:
        values = (
            self.max_courses,
            self.max_count_values_per_course,
            self.max_dp_states_per_course,
            self.max_transition_evaluations,
        )
        limits = (512, 256, 256, 2_000_000)
        if any(
            type(value) is not int or not 1 <= value <= ceiling
            for value, ceiling in zip(values, limits, strict=True)
        ):
            raise TraceAuditInputError("trace_audit.count_budget")


@dataclass(frozen=True, slots=True)
class CountReplayResult:
    count_status: str
    count_reason: str
    count_completed_passes: int
    count_layers: tuple[dict[str, int | bool], ...]
    counts: tuple[int, ...]
    transitions: tuple[dict[str, int], ...]
    objective: dict[str, str | int] | None
    used_transition_evaluations: int

    def to_dict(self) -> dict[str, object]:
        return {
            "count_status": self.count_status,
            "count_reason": self.count_reason,
            "count_completed_passes": self.count_completed_passes,
            "count_layers": [dict(layer) for layer in self.count_layers],
            "counts": list(self.counts),
            "transitions": [dict(item) for item in self.transitions],
            "objective": None if self.objective is None else dict(self.objective),
        }


def _fraction_ok(value: object, positive: bool) -> bool:
    return (
        isinstance(value, Fraction)
        and (value > 0 if positive else value >= 0)
        and value.numerator.bit_length() <= 256
        and value.denominator.bit_length() <= 128
    )


def replay_count_search(
    circumferences: tuple[Fraction, ...],
    stitch_pitch: Fraction,
    windows: tuple[tuple[int, int], ...],
    max_increases: int,
    max_decreases: int,
    budget: CountReplayBudget,
    *,
    work: TraceReplayWork,
) -> CountReplayResult:
    """Replay both count passes without importing or invoking producer code."""
    if not isinstance(budget, CountReplayBudget):
        raise TraceAuditInputError("trace_audit.count_budget")
    if (
        not isinstance(work, TraceReplayWork)
        or not isinstance(circumferences, tuple)
        or not isinstance(windows, tuple)
    ):
        raise TraceAuditInputError("trace_audit.count_input_type")
    if not circumferences or len(circumferences) != len(windows) or len(circumferences) > 512:
        raise TraceAuditInputError("trace_audit.count_course_lengths")
    if not _fraction_ok(stitch_pitch, True) or any(
        not _fraction_ok(c, False) for c in circumferences
    ):
        raise TraceAuditInputError("trace_audit.count_fraction")
    if (
        type(max_increases) is not int
        or type(max_decreases) is not int
        or not 0 <= max_increases <= 100_000
        or not 0 <= max_decreases <= 100_000
    ):
        raise TraceAuditInputError("trace_audit.count_shape_limits")
    for window in windows:
        if not isinstance(window, tuple) or len(window) != 2:
            raise TraceAuditInputError("trace_audit.count_window")
        lo, hi = window
        if type(lo) is not int or type(hi) is not int or not 1 <= lo <= hi <= 100_000:
            raise TraceAuditInputError("trace_audit.count_window")

    used = passes = 0
    layers: list[dict[str, int | bool]] = []

    def result(
        status: str,
        reason: str,
        counts: tuple[int, ...] = (),
        transitions: tuple[dict[str, int], ...] = (),
        objective: dict[str, str | int] | None = None,
    ) -> CountReplayResult:
        return CountReplayResult(
            status, reason, passes, tuple(layers), counts, transitions, objective, used
        )

    def fail_budget(reason: str) -> CountReplayResult:
        return result("SEARCH_BUDGET_EXHAUSTED", reason)

    if len(windows) > budget.max_courses:
        return fail_budget("budget.courses")
    if any(hi - lo + 1 > budget.max_count_values_per_course for lo, hi in windows):
        return fail_budget("budget.count_values")

    def residual(i: int, n: int) -> Fraction:
        return abs(n * stitch_pitch - circumferences[i])

    def edge(a: int, b: int) -> dict[str, int] | None:
        inc, dec = max(b - a, 0), max(a - b, 0)
        plain = a - inc - 2 * dec
        if plain < 0 or inc > max_increases or dec > max_decreases:
            return None
        return {"plain": plain, "increases": inc, "decreases": dec}

    lo, hi = windows[0]
    bottleneck = {n: residual(0, n) for n in range(lo, hi + 1)}
    if len(bottleneck) > budget.max_dp_states_per_course:
        layers.append(
            {
                "pass": 1,
                "layer": 0,
                "retained_states": len(bottleneck),
                "transition_evaluations": 0,
                "completed": False,
            }
        )
        return fail_budget("budget.dp_states")
    layers.append(
        {
            "pass": 1,
            "layer": 0,
            "retained_states": len(bottleneck),
            "transition_evaluations": 0,
            "completed": True,
        }
    )
    for i in range(1, len(windows)):
        start = used
        next_values: dict[int, Fraction] = {}
        lo, hi = windows[i]
        for b in range(lo, hi + 1):
            for a in sorted(bottleneck):
                if used >= budget.max_transition_evaluations:
                    layers.append(
                        {
                            "pass": 1,
                            "layer": i,
                            "retained_states": len(next_values),
                            "transition_evaluations": used - start,
                            "completed": False,
                        }
                    )
                    return fail_budget("budget.transitions")
                try:
                    work.spend()
                except TraceReplayBudgetExceeded:
                    layers.append(
                        {
                            "pass": 1,
                            "layer": i,
                            "retained_states": len(next_values),
                            "transition_evaluations": used - start,
                            "completed": False,
                        }
                    )
                    raise
                used += 1
                if edge(a, b) is not None:
                    cost = max(bottleneck[a], residual(i, b))
                    if b not in next_values or cost < next_values[b]:
                        next_values[b] = cost
            if len(next_values) > budget.max_dp_states_per_course:
                layers.append(
                    {
                        "pass": 1,
                        "layer": i,
                        "retained_states": len(next_values),
                        "transition_evaluations": used - start,
                        "completed": False,
                    }
                )
                return fail_budget("budget.dp_states")
        layers.append(
            {
                "pass": 1,
                "layer": i,
                "retained_states": len(next_values),
                "transition_evaluations": used - start,
                "completed": True,
            }
        )
        if not next_values:
            return result("NO_FEASIBLE_CONSTRUCTION", "domain.no_reachable_path")
        bottleneck = next_values
    threshold = min(bottleneck.values())
    passes = 1

    lo, hi = windows[0]
    paths: dict[int, tuple[Fraction, int, tuple[int, ...]]] = {
        n: (residual(0, n) ** 2, 0, (n,)) for n in range(lo, hi + 1) if residual(0, n) <= threshold
    }
    layers.append(
        {
            "pass": 2,
            "layer": 0,
            "retained_states": len(paths),
            "transition_evaluations": 0,
            "completed": True,
        }
    )
    for i in range(1, len(windows)):
        start = used
        next_paths: dict[int, tuple[Fraction, int, tuple[int, ...]]] = {}
        lo, hi = windows[i]
        for b in range(lo, hi + 1):
            node = residual(i, b)
            if node > threshold:
                continue
            for a in sorted(paths):
                if used >= budget.max_transition_evaluations:
                    layers.append(
                        {
                            "pass": 2,
                            "layer": i,
                            "retained_states": len(next_paths),
                            "transition_evaluations": used - start,
                            "completed": False,
                        }
                    )
                    return fail_budget("budget.transitions")
                try:
                    work.spend()
                except TraceReplayBudgetExceeded:
                    layers.append(
                        {
                            "pass": 2,
                            "layer": i,
                            "retained_states": len(next_paths),
                            "transition_evaluations": used - start,
                            "completed": False,
                        }
                    )
                    raise
                used += 1
                trans = edge(a, b)
                if trans is not None:
                    prev = paths[a]
                    candidate = (
                        prev[0] + node**2,
                        prev[1] + trans["increases"] + trans["decreases"],
                        (*prev[2], b),
                    )
                    if b not in next_paths or candidate < next_paths[b]:
                        next_paths[b] = candidate
        paths = next_paths
        layers.append(
            {
                "pass": 2,
                "layer": i,
                "retained_states": len(paths),
                "transition_evaluations": used - start,
                "completed": True,
            }
        )
        if not paths:
            return result("NO_FEASIBLE_CONSTRUCTION", "domain.no_reachable_path")
    passes = 2
    cost, shaping, counts = min(paths.values())
    chosen: list[dict[str, int]] = []
    for before, after in pairwise(counts):
        transition = edge(before, after)
        if transition is None:
            raise AssertionError("replayed optimum contains an unreachable edge")
        chosen.append(transition)
    objective: dict[str, str | int] = {
        "maximum_residual_mm": f"{threshold.numerator}/{threshold.denominator}",
        "squared_residual_sum_mm2": f"{cost.numerator}/{cost.denominator}",
        "shaping_events": shaping,
    }
    return result(
        "OPTIMAL_COUNT_PROPOSAL",
        "domain.optimum",
        counts,
        tuple(chosen),
        objective,
    )
