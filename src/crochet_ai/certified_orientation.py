"""Certified signs for orientation predicates on finite binary64 coordinates.

The interval filter assumes IEEE-754 binary64 operations are correctly rounded
to nearest and gradual underflow is enabled. ``sys.float_info.rounds`` records
the mode at interpreter startup; callers must not alter the IEEE environment
while using this backend. Runtime checks verify binary64 and exercise arithmetic
in the subnormal range. Overflow or a non-finite intermediate leaves the filter
unresolved and uses an exact rational determinant; it is never interpreted as
a sign.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal, TypeAlias

Point2: TypeAlias = tuple[float, float]
Point3: TypeAlias = tuple[float, float, float]
PredicatePath: TypeAlias = Literal["FILTER_CERTIFIED", "EXACT_FALLBACK"]
BACKEND = "crochet-ai-filtered-fraction-orientation"
VERSION = "1.0.0"


class OrientationError(ValueError):
    """Base class for rejected inputs or unsupported arithmetic environments."""


class ExactFallbackBudgetExceeded(OrientationError):
    """The interval filter was inconclusive and exact work was not authorized."""


@dataclass(frozen=True, slots=True)
class OrientationResult:
    """Count interval/exact determinant nodes, not individual endpoint operations.

    A complete filter uses 7 nodes in 2D or 23 in 3D; exact fallback adds the
    same number. Runtime admission probes are outside this fixed node count.
    """

    sign: Literal[-1, 0, 1]
    backend: str
    version: str
    path: PredicatePath
    operation_count: int
    exact_fallback_count: int


@dataclass(frozen=True, slots=True)
class _Interval:
    low: float
    high: float


class _UnresolvedArithmetic(Exception):
    pass


def _check_runtime() -> None:
    info = sys.float_info
    if (
        info.radix != 2
        or info.mant_dig != 53
        or info.max_exp != 1024
        or info.min_exp != -1021
        or info.rounds != 1
        or not _gradual_underflow_supported()
    ):
        raise OrientationError(
            "certified orientation requires binary64 round-to-nearest with subnormals"
        )


def _gradual_underflow_supported() -> bool:
    least_subnormal = math.nextafter(0.0, math.inf)
    return (
        least_subnormal > 0.0
        and sys.float_info.min * 0.5 != 0.0
        and least_subnormal * 1.0 == least_subnormal
    )


def _validate_budget(max_exact_fallbacks: int) -> None:
    if type(max_exact_fallbacks) is not int or max_exact_fallbacks < 0:
        raise OrientationError("max_exact_fallbacks must be a nonnegative integer")


def _validate_point(point: object, dimension: int, name: str) -> tuple[float, ...]:
    if type(point) is not tuple or len(point) != dimension:
        raise OrientationError(f"{name} must be a tuple of {dimension} finite floats")
    if any(type(value) is not float or not math.isfinite(value) for value in point):
        raise OrientationError(f"{name} must contain only finite floats")
    return point


def _outward(value: float, direction: float) -> float:
    if not math.isfinite(value):
        raise _UnresolvedArithmetic
    result = math.nextafter(value, direction)
    if not math.isfinite(result):
        raise _UnresolvedArithmetic
    return result


def _add(left: _Interval, right: _Interval) -> _Interval:
    return _Interval(
        _outward(left.low + right.low, -math.inf), _outward(left.high + right.high, math.inf)
    )


def _sub(left: _Interval, right: _Interval) -> _Interval:
    return _Interval(
        _outward(left.low - right.high, -math.inf), _outward(left.high - right.low, math.inf)
    )


def _mul(left: _Interval, right: _Interval) -> _Interval:
    products = (
        left.low * right.low,
        left.low * right.high,
        left.high * right.low,
        left.high * right.high,
    )
    if any(not math.isfinite(value) for value in products):
        raise _UnresolvedArithmetic
    return _Interval(
        _outward(min(products), -math.inf),
        _outward(max(products), math.inf),
    )


def _sign(interval: _Interval) -> Literal[-1, 0, 1] | None:
    if interval.low > 0.0:
        return 1
    if interval.high < 0.0:
        return -1
    return None


def _exact_difference(a: float, b: float) -> Fraction:
    return Fraction.from_float(a) - Fraction.from_float(b)


def _result(
    sign: Literal[-1, 0, 1], path: PredicatePath, operations: int, fallback_count: int
) -> OrientationResult:
    return OrientationResult(sign, BACKEND, VERSION, path, operations, fallback_count)


def _orientation(
    points: tuple[tuple[float, ...], ...], max_exact_fallbacks: int, dimension: int
) -> OrientationResult:
    _validate_budget(max_exact_fallbacks)
    _check_runtime()
    validated = tuple(
        _validate_point(point, dimension, f"point {index}") for index, point in enumerate(points)
    )
    operations = 0

    def add(left: _Interval, right: _Interval) -> _Interval:
        nonlocal operations
        operations += 1
        return _add(left, right)

    def sub(left: _Interval, right: _Interval) -> _Interval:
        nonlocal operations
        operations += 1
        return _sub(left, right)

    def mul(left: _Interval, right: _Interval) -> _Interval:
        nonlocal operations
        operations += 1
        return _mul(left, right)

    try:
        origin = validated[0]
        u = tuple(
            sub(_Interval(validated[1][i], validated[1][i]), _Interval(origin[i], origin[i]))
            for i in range(dimension)
        )
        v = tuple(
            sub(_Interval(validated[2][i], validated[2][i]), _Interval(origin[i], origin[i]))
            for i in range(dimension)
        )
        if dimension == 2:
            determinant = sub(mul(u[0], v[1]), mul(u[1], v[0]))
        else:
            w = tuple(
                sub(_Interval(validated[3][i], validated[3][i]), _Interval(origin[i], origin[i]))
                for i in range(3)
            )
            determinant = add(
                sub(
                    mul(u[0], sub(mul(v[1], w[2]), mul(v[2], w[1]))),
                    mul(u[1], sub(mul(v[0], w[2]), mul(v[2], w[0]))),
                ),
                mul(u[2], sub(mul(v[0], w[1]), mul(v[1], w[0]))),
            )
        filtered = _sign(determinant)
        if filtered is not None:
            return _result(filtered, "FILTER_CERTIFIED", operations, 0)
    except _UnresolvedArithmetic:
        pass

    if max_exact_fallbacks == 0:
        raise ExactFallbackBudgetExceeded(
            "orientation filter unresolved and exact fallback budget is zero"
        )
    exact_origin = validated[0]
    exact = tuple(
        tuple(
            _exact_difference(validated[index][axis], exact_origin[axis])
            for axis in range(dimension)
        )
        for index in range(1, dimension + 1)
    )
    if dimension == 2:
        determinant_exact = exact[0][0] * exact[1][1] - exact[0][1] * exact[1][0]
    else:
        u_exact, v_exact, w_exact = exact
        determinant_exact = (
            u_exact[0] * (v_exact[1] * w_exact[2] - v_exact[2] * w_exact[1])
            - u_exact[1] * (v_exact[0] * w_exact[2] - v_exact[2] * w_exact[0])
            + u_exact[2] * (v_exact[0] * w_exact[1] - v_exact[1] * w_exact[0])
        )
    if determinant_exact > 0:
        exact_sign: Literal[-1, 0, 1] = 1
    elif determinant_exact < 0:
        exact_sign = -1
    else:
        exact_sign = 0
    exact_operations = 7 if dimension == 2 else 23
    return _result(exact_sign, "EXACT_FALLBACK", operations + exact_operations, 1)


def orientation2d(
    a: Point2, b: Point2, c: Point2, *, max_exact_fallbacks: int
) -> OrientationResult:
    """Sign ``det(b-a, c-a)`` for three finite binary64 points."""
    return _orientation((a, b, c), max_exact_fallbacks, 2)


def orientation3d(
    a: Point3, b: Point3, c: Point3, d: Point3, *, max_exact_fallbacks: int
) -> OrientationResult:
    """Sign ``det(b-a, c-a, d-a)`` for four finite binary64 points."""
    return _orientation((a, b, c, d), max_exact_fallbacks, 3)
