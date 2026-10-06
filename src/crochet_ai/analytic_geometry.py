"""Target-side meridional sampling; never used as independent forward geometry."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction
from math import ceil, cos, hypot, isfinite, pi, sin
from typing import TYPE_CHECKING, Any

from .diagnostics import ArtifactValidationError
from .solver_types import GenerationError, GenerationStatus
from .validation import SemanticValidator

if TYPE_CHECKING:
    from .analytic_coordinate_meridian import CoordinateAnalyticMeridian


@dataclass(frozen=True, slots=True)
class MeridianNumerics:
    arc_length_abs_tolerance_mm: float
    roundoff_allowance_mm: float
    max_arc_panels: int
    radius_zero_tolerance_mm: float

    def validate(self) -> None:
        if not (
            type(self.arc_length_abs_tolerance_mm) in {int, float}
            and type(self.roundoff_allowance_mm) in {int, float}
            and isfinite(self.arc_length_abs_tolerance_mm)
            and isfinite(self.roundoff_allowance_mm)
            and 0 < self.roundoff_allowance_mm < self.arc_length_abs_tolerance_mm
            and type(self.max_arc_panels) is int
            and 2 <= self.max_arc_panels <= 200_000
            and type(self.radius_zero_tolerance_mm) in {int, float}
            and isfinite(self.radius_zero_tolerance_mm)
            and self.radius_zero_tolerance_mm >= 0
        ):
            raise GenerationError(
                GenerationStatus.INVALID_SOLVER_INPUT, "meridian.numerical_profile"
            )


@dataclass(frozen=True, slots=True)
class MeridianPoint:
    s_mm: float
    radius_mm: float
    axial_mm: float | None = None


@dataclass(frozen=True, slots=True)
class AnalyticMeridian:
    primitive: str
    length_mm: float
    radius_mm: float
    polar_radius_mm: float
    start_kind: str
    end_kind: str
    # Solver-only approximation diagnostics, not certified metric bounds.
    exact_arithmetic_arc_error_bound_mm: float
    roundoff_allowance_mm: float
    arc_panels: int
    prefix_mm: tuple[float, ...] = ()
    profile_s_mm: tuple[float, ...] = ()
    profile_r_mm: tuple[float, ...] = ()

    def sample(self, fraction: Fraction) -> MeridianPoint:
        if not isinstance(fraction, Fraction) or not 0 <= fraction <= 1:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "meridian.fraction")
        u = float(fraction)
        s = u * self.length_mm
        if self.primitive in {"SPHERE", "ELLIPSOID"}:
            if fraction in {0, 1}:
                return MeridianPoint(s, 0.0)
            if fraction == Fraction(1, 2):
                return MeridianPoint(s, self.radius_mm)
            half_fraction = float(min(fraction, 1 - fraction))
            if not self.prefix_mm:
                theta = pi * half_fraction
            else:
                arc = half_fraction * self.length_mm
                index = min(bisect_right(self.prefix_mm, arc) - 1, len(self.prefix_mm) - 2)
                width = self.prefix_mm[index + 1] - self.prefix_mm[index]
                interpolation = (arc - self.prefix_mm[index]) / width
                if not 0 <= interpolation <= 1:
                    raise GenerationError(
                        GenerationStatus.NUMERICAL_FAILURE, "meridian.inverse_range"
                    )
                theta = (index + interpolation) * (pi / 2 / (len(self.prefix_mm) - 1))
            radius = self.radius_mm * sin(theta)
        elif self.primitive == "CYLINDER":
            radius = self.radius_mm
        elif self.primitive == "CONE":
            radius = self.radius_mm * float(1 - fraction)
        else:
            if fraction == 1:
                radius = self.profile_r_mm[-1]
            else:
                index = min(bisect_right(self.profile_s_mm, s) - 1, len(self.profile_s_mm) - 2)
                weight = (s - self.profile_s_mm[index]) / (
                    self.profile_s_mm[index + 1] - self.profile_s_mm[index]
                )
                radius = (1 - weight) * self.profile_r_mm[index] + weight * self.profile_r_mm[
                    index + 1
                ]
        if not isfinite(s) or not isfinite(radius) or radius < 0:
            raise GenerationError(GenerationStatus.NUMERICAL_FAILURE, "meridian.nonfinite_sample")
        return MeridianPoint(s, radius)


def decode_meridian(
    design: dict[str, Any], numerics: MeridianNumerics, *, validator: SemanticValidator
) -> AnalyticMeridian | CoordinateAnalyticMeridian:
    numerics.validate()
    report = validator.validate_design_spec(design)
    if not report.ok:
        raise ArtifactValidationError(report)
    target = design["target_geometry"]
    if design["project_type"] != "AMIGURUMI_3D" or target["geometry_type"] != "ANALYTIC_SHAPE":
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "meridian.analytic_amigurumi_only")
    measurements = {
        m["measurement_id"]: float(m["value_mm"]) for m in design["dimensions"]["measurements"]
    }
    parameters = {p["parameter"]: measurements[p["measurement_id"]] for p in target["parameters"]}
    primitive = target["primitive"]
    if (
        primitive == "SURFACE_OF_REVOLUTION"
        and target.get("radial_profile", {}).get("canonicalization_profile")
        == "SURFACE_OF_REVOLUTION_COORDINATE_PROFILE_CANONICAL_JSON_V1"
    ):
        profile = target["radial_profile"]
        segment_count = len(profile["samples"]) - 1
        if segment_count > numerics.max_arc_panels:
            raise GenerationError(GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "meridian.arc_panels")
        from .analytic_coordinate_meridian import CoordinateAnalyticMeridian
        from .analytic_coordinate_target import admit_analytic_coordinate_target
        from .analytic_target import AnalyticTargetError

        try:
            admitted = admit_analytic_coordinate_target(design, validator)
        except AnalyticTargetError as error:
            status = (
                GenerationStatus.NOT_APPLICABLE
                if error.status == "NOT_APPLICABLE"
                else GenerationStatus.INVALID_SOLVER_INPUT
            )
            raise GenerationError(status, "meridian.coordinate_target_admission") from error
        if any(
            radius <= numerics.radius_zero_tolerance_mm
            for radius, _ in admitted.coordinates_mm[1:-1]
        ):
            raise GenerationError(GenerationStatus.NOT_APPLICABLE, "meridian.interior_thin_neck")
        return CoordinateAnalyticMeridian.from_target(admitted, numerics)
    prefix: tuple[float, ...] = ()
    profile_s: tuple[float, ...] = ()
    profile_r: tuple[float, ...] = ()
    bound = 0.0
    panels = 0
    polar = 0.0
    start, end = "CONSTRUCTION_INTERFACE", "CONSTRUCTION_INTERFACE"
    if primitive == "SPHERE":
        radius = parameters["RADIUS"]
        length = pi * radius
        start = end = "CLOSED_POLE"
    elif primitive == "CYLINDER":
        radius, length = parameters["RADIUS"], parameters["AXIAL_LENGTH"]
    elif primitive == "CONE":
        radius = parameters["BASE_RADIUS"]
        length = hypot(radius, parameters["AXIAL_LENGTH"])
        end = "CLOSED_POLE"
    elif primitive == "ELLIPSOID":
        radius, polar = parameters["EQUATORIAL_RADIUS"], parameters["POLAR_RADIUS"]
        start = end = "CLOSED_POLE"
        if radius == polar:
            length = pi * radius
        else:
            # Speed is monotone on each quarter ellipse. Endpoint rectangles
            # bound the integral in exact arithmetic; no false Simpson certificate.
            variation = pi * abs(radius - polar)
            allowance = numerics.arc_length_abs_tolerance_mm - numerics.roundoff_allowance_mm
            maximum = numerics.max_arc_panels // 2
            if not isfinite(variation) or variation / maximum > allowance:
                raise GenerationError(
                    GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "meridian.arc_panels"
                )
            n = max(1, ceil(variation / allowance))
            panels = 2 * n
            h = pi / 2 / n
            cumulative = [0.0]
            previous_speed = radius
            for i in range(1, n + 1):
                theta = i * h
                speed = polar if i == n else hypot(radius * cos(theta), polar * sin(theta))
                next_arc = cumulative[-1] + (previous_speed / 2 + speed / 2) * h
                if not isfinite(next_arc) or next_arc <= cumulative[-1]:
                    raise GenerationError(
                        GenerationStatus.NUMERICAL_FAILURE, "meridian.arc_conditioning", i
                    )
                cumulative.append(next_arc)
                previous_speed = speed
            prefix = tuple(cumulative)
            length = 2 * prefix[-1]
            bound = variation / n
    else:
        profile = target["radial_profile"]
        profile_s = tuple(float(p["s_mm"]) for p in profile["samples"])
        profile_r = tuple(float(p["radius_mm"]) for p in profile["samples"])
        if len(profile_s) > numerics.max_arc_panels + 1:
            raise GenerationError(
                GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "meridian.profile_samples"
            )
        for i in range(1, len(profile_s)):
            # Compare the represented values exactly: no clamping impossible slopes.
            ds = Fraction(profile_s[i]) - Fraction(profile_s[i - 1])
            dr = Fraction(profile_r[i]) - Fraction(profile_r[i - 1])
            if abs(dr) > ds:
                raise GenerationError(
                    GenerationStatus.INVALID_SOLVER_INPUT, "meridian.impossible_arc_slope"
                )
        radius, length = max(profile_r), profile_s[-1]
        if radius <= numerics.radius_zero_tolerance_mm or any(
            r <= numerics.radius_zero_tolerance_mm for r in profile_r[1:-1]
        ):
            raise GenerationError(GenerationStatus.NOT_APPLICABLE, "meridian.interior_pole")
        start, end = (
            profile["start_boundary"]["boundary_type"],
            profile["end_boundary"]["boundary_type"],
        )
        if (start == "CLOSED_POLE" and profile_r[0] > numerics.radius_zero_tolerance_mm) or (
            end == "CLOSED_POLE" and profile_r[-1] > numerics.radius_zero_tolerance_mm
        ):
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "meridian.nonzero_pole")
    if not isfinite(length) or length <= 0:
        raise GenerationError(GenerationStatus.NUMERICAL_FAILURE, "meridian.length")
    return AnalyticMeridian(
        primitive,
        length,
        radius,
        polar,
        start,
        end,
        bound,
        numerics.roundoff_allowance_mm,
        panels,
        prefix,
        profile_s,
        profile_r,
    )
