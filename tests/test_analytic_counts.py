"""Exhaustive tiny-domain oracle, independent from the production DP."""

from dataclasses import replace
from fractions import Fraction
from itertools import pairwise, product

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from crochet_ai.analytic_counts import (
    CountSearchBudget,
    CountSearchInput,
    CountSearchStatus,
    CountWindow,
    search_counts,
)


def _request(targets: tuple[Fraction, ...], windows: tuple[CountWindow, ...]) -> CountSearchInput:
    return CountSearchInput(
        targets, Fraction(1), windows, 5, 5, CountSearchBudget(512, 256, 256, 2_000_000)
    )


def _oracle(request: CountSearchInput) -> tuple[Fraction, Fraction, int, tuple[int, ...]] | None:
    feasible = []
    for counts in product(*(range(w.minimum, w.maximum + 1) for w in request.windows)):
        shaping = 0
        for before, after in pairwise(counts):
            # Enumerate arities rather than reproduce the solver's delta formula.
            operations = [
                (plain, inc, dec)
                for plain in range(before + 1)
                for inc in range(request.max_increases_per_course + 1)
                for dec in range(request.max_decreases_per_course + 1)
                if not inc * dec
                and plain + inc + 2 * dec == before
                and plain + 2 * inc + dec == after
            ]
            if not operations:
                break
            assert len(operations) == 1
            shaping += operations[0][1] + operations[0][2]
        else:
            errors = tuple(
                abs(n * request.stitch_pitch_mm - c)
                for n, c in zip(counts, request.circumference_mm, strict=True)
            )
            feasible.append(
                (max(errors), sum((e * e for e in errors), Fraction(0)), shaping, counts)
            )
    return min(feasible) if feasible else None


@given(
    st.lists(
        st.tuples(st.integers(0, 18), st.integers(1, 6), st.integers(0, 2)), min_size=1, max_size=4
    ),
    st.integers(1, 5),
    st.integers(0, 3),
)
@settings(max_examples=100, deadline=None)
def test_dp_matches_exhaustive_arity_oracle(
    rows: list[tuple[int, int, int]], pitch: int, cap: int
) -> None:
    request = _request(
        tuple(Fraction(q, 2) for q, _, _ in rows),
        tuple(CountWindow(lo, lo + width) for _, lo, width in rows),
    )
    request = replace(
        request,
        stitch_pitch_mm=Fraction(pitch, 2),
        max_increases_per_course=cap,
        max_decreases_per_course=cap,
    )
    expected = _oracle(request)
    result = search_counts(request)
    assert search_counts(request) == result
    if expected is None:
        assert result.status == CountSearchStatus.NO_FEASIBLE_CONSTRUCTION
        assert result.counts == () and result.objective is None
    else:
        assert result.status == CountSearchStatus.OPTIMAL_COUNT_PROPOSAL
        assert result.objective is not None
        assert (
            result.objective.max_residual_mm,
            result.objective.squared_residual_sum_mm2,
            result.objective.shaping_events,
            result.counts,
        ) == expected
        for index, t in enumerate(result.transitions):
            assert t.plain + t.increases + 2 * t.decreases == result.counts[index]
            assert t.plain + 2 * t.increases + t.decreases == result.counts[index + 1]
            assert not t.increases * t.decreases


def test_bottleneck_must_not_prune_additive_optimum() -> None:
    # Independent mathematical review produced this counterexample to single-pass pruning.
    request = _request(
        tuple(Fraction(q, 2) for q in (13, 39, 11, 26, 39)),
        tuple(CountWindow(a, b) for a, b in ((7, 11), (14, 16), (9, 11), (8, 8), (11, 11))),
    )
    result = search_counts(request)
    assert result.counts == (9, 14, 9, 8, 11)
    assert _oracle(request) == (Fraction(17, 2), Fraction(146), 14, result.counts)


@pytest.mark.parametrize(
    "field,limit",
    [
        ("max_courses", 1),
        ("max_count_values_per_course", 1),
        ("max_dp_states_per_course", 1),
        ("max_transition_evaluations", 1),
    ],
)
def test_budget_exhaustion_never_returns_partial_proposal(field: str, limit: int) -> None:
    request = _request((Fraction(3), Fraction(4)), (CountWindow(2, 3), CountWindow(3, 4)))
    request = replace(request, budget=replace(request.budget, **{field: limit}))
    result = search_counts(request)
    assert result.status == CountSearchStatus.SEARCH_BUDGET_EXHAUSTED
    assert not result.counts and not result.transitions and result.objective is None


def test_exact_budget_boundary_and_second_pass_exhaustion() -> None:
    request = _request((Fraction(2), Fraction(3)), (CountWindow(2, 2), CountWindow(3, 3)))
    exhausted = search_counts(
        replace(request, budget=replace(request.budget, max_transition_evaluations=1))
    )
    assert exhausted.completed_passes == 1
    assert exhausted.status == CountSearchStatus.SEARCH_BUDGET_EXHAUSTED
    complete = search_counts(
        replace(request, budget=replace(request.budget, max_transition_evaluations=2))
    )
    assert complete.counts == (2, 3)
    assert complete.transition_evaluations == 2


@pytest.mark.parametrize(
    "pitch", [Fraction(0), Fraction(-1), Fraction(1, 2**129), Fraction(2**257)]
)
def test_invalid_rationals_fail_before_search(pitch: Fraction) -> None:
    request = _request((Fraction(3),), (CountWindow(2, 4),))
    result = search_counts(replace(request, stitch_pitch_mm=pitch))
    assert result.status == CountSearchStatus.INVALID_SOLVER_INPUT
    assert result.transition_evaluations == 0


def test_scale_covariance_and_lexicographic_ties() -> None:
    request = _request((Fraction(7, 2), Fraction(9, 2)), (CountWindow(3, 4), CountWindow(4, 5)))
    result = search_counts(request)
    assert result.counts == (4, 4)  # Equal geometric cost; fewer shaping events wins.
    scale = Fraction(7, 3)
    scaled = search_counts(
        replace(
            request,
            circumference_mm=tuple(q * scale for q in request.circumference_mm),
            stitch_pitch_mm=request.stitch_pitch_mm * scale,
        )
    )
    assert scaled.counts == result.counts
    assert scaled.objective is not None and result.objective is not None
    assert scaled.objective.max_residual_mm == result.objective.max_residual_mm * scale
    assert (
        scaled.objective.squared_residual_sum_mm2
        == result.objective.squared_residual_sum_mm2 * scale**2
    )
    tie = search_counts(_request((Fraction(7, 2),), (CountWindow(3, 4),)))
    assert tie.counts == (3,)
