"""Bounded exact-prefix sampler for admitted explicit meridian coordinates."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from math import hypot, inf, isfinite, nextafter

from .analytic_coordinate_target import AnalyticCoordinateTarget
from .analytic_geometry import MeridianNumerics, MeridianPoint
from .solver_types import GenerationError, GenerationStatus


@dataclass(frozen=True, slots=True)
class CoordinateAnalyticMeridian:
    """A piecewise-linear meridian parameterized by bounded approximate arc length."""

    length_mm: float
    radius_mm: float
    start_kind: str
    end_kind: str
    exact_arithmetic_arc_error_bound_mm: float
    roundoff_allowance_mm: float
    arc_panels: int
    target_sha256: str
    _prefix: tuple[Fraction, ...]
    _arc_lengths: tuple[Fraction, ...]
    _coordinates: tuple[tuple[Fraction, Fraction], ...]

    @classmethod
    def from_target(
        cls, target: AnalyticCoordinateTarget, numerics: MeridianNumerics
    ) -> CoordinateAnalyticMeridian:
        numerics.validate()
        segment_count = len(target.coordinates_mm) - 1
        if segment_count > numerics.max_arc_panels:
            raise GenerationError(GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "meridian.arc_panels")

        coordinates = tuple(
            (Fraction(radius), Fraction(axial)) for radius, axial in target.coordinates_mm
        )
        arcs: list[Fraction] = []
        errors: list[Fraction] = []
        for (r0, z0), (r1, z1) in pairwise(coordinates):
            dr, dz = r1 - r0, z1 - z0
            q = dr * dr + dz * dz
            if q <= 0:
                raise GenerationError(
                    GenerationStatus.INVALID_SOLVER_INPUT, "meridian.zero_segment"
                )
            try:
                approximation = hypot(float(dr), float(dz))
            except (OverflowError, ValueError):
                approximation = float("inf")
            if not isfinite(approximation) or approximation <= 0:
                raise GenerationError(GenerationStatus.NUMERICAL_FAILURE, "meridian.sqrt_nonfinite")
            arc, lower, upper = _sqrt_bracket(q, approximation)
            arcs.append(arc)
            errors.append(max(arc - lower, upper - arc))

        exact_total = sum(arcs, Fraction(0))
        exact_error = sum(errors, Fraction(0))
        try:
            float_total = float(exact_total)
        except OverflowError as exc:
            raise GenerationError(
                GenerationStatus.NUMERICAL_FAILURE, "meridian.length_overflow"
            ) from exc
        if not isfinite(float_total) or float_total <= 0:
            raise GenerationError(GenerationStatus.NUMERICAL_FAILURE, "meridian.length_nonfinite")
        roundoff = abs(Fraction(float_total) - exact_total)
        allowance = Fraction(numerics.roundoff_allowance_mm)
        tolerance = Fraction(numerics.arc_length_abs_tolerance_mm)
        if roundoff > allowance or exact_error > tolerance - allowance:
            raise GenerationError(GenerationStatus.NUMERICAL_FAILURE, "meridian.arc_tolerance")

        prefix = [Fraction(0)]
        for arc in arcs:
            prefix.append(prefix[-1] + arc)
        bound_float = float(exact_error)
        if Fraction(bound_float) < exact_error:
            bound_float = nextafter(bound_float, inf)
        if not isfinite(bound_float):
            raise GenerationError(
                GenerationStatus.NUMERICAL_FAILURE, "meridian.error_bound_overflow"
            )
        return cls(
            float_total,
            max(float(radius) for radius, _ in coordinates),
            target.start_boundary,
            target.end_boundary,
            bound_float,
            numerics.roundoff_allowance_mm,
            segment_count,
            target.sha256,
            tuple(prefix),
            tuple(arcs),
            coordinates,
        )

    def sample(self, fraction: Fraction) -> MeridianPoint:
        if not isinstance(fraction, Fraction) or not 0 <= fraction <= 1:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "meridian.fraction")
        total = self._prefix[-1]
        desired_s = fraction * total
        if fraction == 0:
            radius, axial = self._coordinates[0]
        elif fraction == 1:
            radius, axial = self._coordinates[-1]
        else:
            index = min(bisect_right(self._prefix, desired_s) - 1, len(self._arc_lengths) - 1)
            local = (desired_s - self._prefix[index]) / self._arc_lengths[index]
            r0, z0 = self._coordinates[index]
            r1, z1 = self._coordinates[index + 1]
            radius = r0 + local * (r1 - r0)
            axial = z0 + local * (z1 - z0)
        s_mm = _checked_float(desired_s, self.roundoff_allowance_mm, "s")
        radius_mm = _checked_float(radius, self.roundoff_allowance_mm, "radius")
        axial_mm = _checked_float(axial, self.roundoff_allowance_mm, "axial")
        if radius_mm < 0:
            raise GenerationError(GenerationStatus.NUMERICAL_FAILURE, "meridian.negative_radius")
        return MeridianPoint(s_mm, radius_mm, axial_mm)


def _sqrt_bracket(
    square: Fraction, approximation: float
) -> tuple[Fraction, Fraction, Fraction]:
    """Return approximation and an exact-square-verified two-ULP enclosure."""
    lower = upper = approximation
    for attempt in range(3):
        lower_fraction, upper_fraction = Fraction(lower), Fraction(upper)
        if lower_fraction * lower_fraction <= square <= upper_fraction * upper_fraction:
            return Fraction(approximation), lower_fraction, upper_fraction
        if attempt == 2:
            break
        if lower_fraction * lower_fraction > square:
            lower = nextafter(lower, 0.0)
        if upper_fraction * upper_fraction < square:
            upper = nextafter(upper, inf)
        if not isfinite(lower) or not isfinite(upper) or lower < 0:
            break
    raise GenerationError(GenerationStatus.NUMERICAL_FAILURE, "meridian.sqrt_bracket")


def _checked_float(value: Fraction, allowance: float, coordinate: str) -> float:
    try:
        converted = float(value)
    except OverflowError as exc:
        raise GenerationError(
            GenerationStatus.NUMERICAL_FAILURE, f"meridian.{coordinate}_conversion"
        ) from exc
    if (
        not isfinite(converted)
        or abs(Fraction(converted) - value) > Fraction(allowance)
    ):
        raise GenerationError(
            GenerationStatus.NUMERICAL_FAILURE, f"meridian.{coordinate}_conversion"
        )
    return converted
