"""Independent bounded replay of explicit coordinate meridian numerics."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from typing import cast

from .analytic_coordinate_target import AnalyticCoordinateTarget
from .trace_verification_types import TraceReplayWork


class CoordinateReplayError(ValueError):
    """A supported coordinate sampler claim cannot be replayed safely."""


def _neighbor(value: float, upward: bool) -> float:
    bits = struct.unpack(">Q", struct.pack(">d", value))[0]
    if value == 0.0:
        bits = 1 if upward else (1 << 63) | 1
    elif (value > 0) == upward:
        bits += 1
    else:
        bits -= 1
    return cast(float, struct.unpack(">d", struct.pack(">Q", bits))[0])


def _float(value: Fraction, allowance: Fraction, name: str) -> float:
    try:
        result = float(value)
    except OverflowError as exc:
        raise CoordinateReplayError("coordinate." + name + "_conversion") from exc
    if not math.isfinite(result) or abs(Fraction(result) - value) > allowance:
        raise CoordinateReplayError("coordinate." + name + "_conversion")
    return result


@dataclass(frozen=True, slots=True)
class CoordinateSample:
    s_mm: float
    radius_mm: float
    axial_mm: float


@dataclass(frozen=True, slots=True)
class CoordinateMeridianReplay:
    target_sha256: str
    total: Fraction
    total_float: float
    error_bound: float
    allowance: Fraction
    coordinates: tuple[tuple[Fraction, Fraction], ...]
    lengths: tuple[Fraction, ...]
    prefix: tuple[Fraction, ...]

    @classmethod
    def build(
        cls,
        target: AnalyticCoordinateTarget,
        arc_tolerance_mm: float,
        roundoff_allowance_mm: float,
        max_arc_panels: int,
        work: TraceReplayWork,
        radius_zero_tolerance_mm: float = 0.0,
    ) -> CoordinateMeridianReplay:
        if (
            type(arc_tolerance_mm) not in (int, float)
            or not math.isfinite(arc_tolerance_mm)
            or type(roundoff_allowance_mm) not in (int, float)
            or not math.isfinite(roundoff_allowance_mm)
            or type(radius_zero_tolerance_mm) not in (int, float)
            or not math.isfinite(radius_zero_tolerance_mm)
            or radius_zero_tolerance_mm < 0
            or type(max_arc_panels) is not int
            or not 2 <= max_arc_panels <= 200_000
            or not 0 < roundoff_allowance_mm < arc_tolerance_mm
        ):
            raise CoordinateReplayError("coordinate.numerics")
        points = tuple((Fraction(r), Fraction(z)) for r, z in target.coordinates_mm)
        if any(radius <= Fraction(radius_zero_tolerance_mm) for radius, _ in points[1:-1]):
            raise CoordinateReplayError("coordinate.thin_neck")
        if len(points) - 1 > min(max_arc_panels, 128):
            raise CoordinateReplayError("coordinate.segment_budget")
        lengths: list[Fraction] = []
        errors: list[Fraction] = []
        for (r0, z0), (r1, z1) in pairwise(points):
            work.spend()
            dr, dz = r1 - r0, z1 - z0
            square = dr * dr + dz * dz
            if square <= 0:
                raise CoordinateReplayError("coordinate.zero_segment")
            try:
                estimate = math.hypot(float(dr), float(dz))
            except (OverflowError, ValueError):
                estimate = math.inf
            if not math.isfinite(estimate) or estimate <= 0:
                raise CoordinateReplayError("coordinate.sqrt_nonfinite")
            lo = hi = estimate
            for attempt in range(3):
                if not math.isfinite(lo) or not math.isfinite(hi):
                    raise CoordinateReplayError("coordinate.sqrt_bracket")
                lf, hf = Fraction(lo), Fraction(hi)
                if lf * lf <= square <= hf * hf:
                    break
                if attempt == 2:
                    raise CoordinateReplayError("coordinate.sqrt_bracket")
                if lf * lf > square:
                    lo = _neighbor(lo, False)
                if hf * hf < square:
                    hi = _neighbor(hi, True)
                if not math.isfinite(lo) or not math.isfinite(hi):
                    raise CoordinateReplayError("coordinate.sqrt_bracket")
            lf, hf = Fraction(lo), Fraction(hi)
            if not (math.isfinite(lo) and math.isfinite(hi) and lf * lf <= square <= hf * hf):
                raise CoordinateReplayError("coordinate.sqrt_bracket")
            lengths.append(Fraction(estimate))
            errors.append(max(Fraction(estimate) - lf, hf - Fraction(estimate)))
        total = sum(lengths, Fraction(0))
        error = sum(errors, Fraction(0))
        total_float = _float(total, Fraction(roundoff_allowance_mm), "length")
        if total_float <= 0 or abs(Fraction(total_float) - total) > Fraction(roundoff_allowance_mm):
            raise CoordinateReplayError("coordinate.length_conversion")
        if error > Fraction(arc_tolerance_mm) - Fraction(roundoff_allowance_mm):
            raise CoordinateReplayError("coordinate.arc_tolerance")
        prefix = [Fraction(0)]
        for length in lengths:
            prefix.append(prefix[-1] + length)
        bound = float(error)
        if Fraction(bound) < error:
            bound = _neighbor(bound, True)
        if not math.isfinite(bound):
            raise CoordinateReplayError("coordinate.error_bound")
        return cls(
            target.sha256,
            total,
            total_float,
            bound,
            Fraction(roundoff_allowance_mm),
            points,
            tuple(lengths),
            tuple(prefix),
        )

    def sample(self, fraction: Fraction, work: TraceReplayWork) -> CoordinateSample:
        if not isinstance(fraction, Fraction) or not 0 <= fraction <= 1:
            raise CoordinateReplayError("coordinate.fraction")
        desired = fraction * self.total
        if fraction == 0:
            radius, axial = self.coordinates[0]
        elif fraction == 1:
            radius, axial = self.coordinates[-1]
        else:
            for index, segment_end in enumerate(self.prefix[1:]):
                work.spend()
                if desired <= segment_end:
                    local = (desired - self.prefix[index]) / self.lengths[index]
                    (r0, z0), (r1, z1) = self.coordinates[index : index + 2]
                    radius = r0 + local * (r1 - r0)
                    axial = z0 + local * (z1 - z0)
                    break
            else:
                raise CoordinateReplayError("coordinate.sample_segment")
        if radius < 0:
            raise CoordinateReplayError("coordinate.negative_radius")
        return CoordinateSample(
            _float(desired, self.allowance, "s"),
            _float(radius, self.allowance, "radius"),
            _float(axial, self.allowance, "axial"),
        )
