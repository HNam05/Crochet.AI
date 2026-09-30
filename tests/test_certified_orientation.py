from __future__ import annotations

from fractions import Fraction
from itertools import permutations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from crochet_ai import certified_orientation
from crochet_ai.certified_orientation import (
    ExactFallbackBudgetExceeded,
    OrientationError,
    orientation2d,
    orientation3d,
)


def _oracle2(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> int:
    ax, ay = map(Fraction.from_float, a)
    bx, by = map(Fraction.from_float, b)
    cx, cy = map(Fraction.from_float, c)
    # Homogeneous shoelace expansion, unlike the production translated determinant.
    det = ax * by + bx * cy + cx * ay - ay * bx - by * cx - cy * ax
    return (det > 0) - (det < 0)


def _oracle3(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
    d: tuple[float, float, float],
) -> int:
    matrix = [
        [Fraction(1)] + [Fraction.from_float(point[axis]) for axis in range(3)]
        for point in (a, b, c, d)
    ]
    det = Fraction(0)
    for order in permutations(range(4)):
        inversions = sum(order[i] > order[j] for i in range(4) for j in range(i + 1, 4))
        term = Fraction(1)
        for row, column in enumerate(order):
            term *= matrix[row][column]
        det += -term if inversions % 2 else term
    return (det > 0) - (det < 0)


def test_hand_computed_determinants_and_filter_path() -> None:
    result2 = orientation2d((0.0, 0.0), (2.0, 0.0), (0.0, 3.0), max_exact_fallbacks=1)
    assert result2.sign == 1
    assert result2.path == "FILTER_CERTIFIED"
    assert result2.exact_fallback_count == 0
    assert result2.operation_count > 0
    assert (
        orientation3d(
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            max_exact_fallbacks=1,
        ).sign
        == 1
    )


_finite = st.floats(allow_nan=False, allow_infinity=False, width=64)
_point2 = st.tuples(_finite, _finite)
_point3 = st.tuples(_finite, _finite, _finite)


@settings(max_examples=250, deadline=None, derandomize=True)
@given(a=_point2, b=_point2, c=_point2)
def test_exact_oracle_binary64_2d(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float],
) -> None:
    """Finite binary64 sign equals rational oracle; Hypothesis shrinks/replays failures."""
    actual = orientation2d(a, b, c, max_exact_fallbacks=1)
    assert actual.sign == _oracle2(a, b, c)
    assert orientation2d(b, a, c, max_exact_fallbacks=1).sign == -actual.sign


@settings(max_examples=250, deadline=None, derandomize=True)
@given(a=_point3, b=_point3, c=_point3, d=_point3)
def test_exact_oracle_binary64_3d(
    a: tuple[float, float, float], b: tuple[float, float, float],
    c: tuple[float, float, float], d: tuple[float, float, float],
) -> None:
    """Sign matches independent homogeneous Leibniz oracle; failures shrink/replay."""
    actual = orientation3d(a, b, c, d, max_exact_fallbacks=1)
    assert actual.sign == _oracle3(a, b, c, d)
    assert orientation3d(b, a, c, d, max_exact_fallbacks=1).sign == -actual.sign


@pytest.mark.parametrize(
    ("a", "b", "c"),
    [
        ((0.0, 0.0), (1.0, 1.0), (2.0, 2.0)),
        ((0.0, 0.0), (1.0, 0.0), (1.0, float.fromhex("0x0.0000000000001p-1022"))),
        ((0.0, 0.0), (1e308, 0.0), (0.0, 1e308)),
    ],
)
def test_degenerate_subnormal_and_overflow_use_exact_fallback(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
) -> None:
    result = orientation2d(a, b, c, max_exact_fallbacks=1)
    assert result.sign == _oracle2(a, b, c)
    assert result.path == "EXACT_FALLBACK"
    assert result.exact_fallback_count == 1


def test_budget_exhaustion_fails_closed() -> None:
    with pytest.raises(ExactFallbackBudgetExceeded):
        orientation2d((0.0, 0.0), (1.0, 1.0), (2.0, 2.0), max_exact_fallbacks=0)


def test_runtime_rejects_arithmetic_without_gradual_underflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(certified_orientation, "_gradual_underflow_supported", lambda: False)
    with pytest.raises(OrientationError):
        orientation2d((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), max_exact_fallbacks=1)


@pytest.mark.parametrize("budget", [-1, True, 1.0])
def test_invalid_budget_rejected(budget: object) -> None:
    with pytest.raises(OrientationError):
        orientation2d((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), max_exact_fallbacks=budget)


@pytest.mark.parametrize(
    "points",
    [
        ((False, 0.0), (1.0, 0.0), (0.0, 1.0)),
        ((float("nan"), 0.0), (1.0, 0.0), (0.0, 1.0)),
        ((float("inf"), 0.0), (1.0, 0.0), (0.0, 1.0)),
        ([0.0, 0.0], (1.0, 0.0), (0.0, 1.0)),
        ((0.0, 0.0, 0.0), (1.0, 0.0), (0.0, 1.0)),
    ],
)
def test_invalid_coordinates_rejected(points: tuple[object, object, object]) -> None:
    with pytest.raises(OrientationError):
        orientation2d(*points, max_exact_fallbacks=1)


def test_permutation_antisymmetry() -> None:
    a, b, c = (0.25, -2.0), (4.0, 1.0), (-3.0, 5.0)
    assert (
        orientation2d(a, b, c, max_exact_fallbacks=1).sign
        == -orientation2d(b, a, c, max_exact_fallbacks=1).sign
    )
    a3, b3, c3, d3 = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    assert (
        orientation3d(a3, b3, c3, d3, max_exact_fallbacks=1).sign
        == -orientation3d(b3, a3, c3, d3, max_exact_fallbacks=1).sign
    )
