"""Exact, bounded admission of explicit-coordinate revolution targets."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from fractions import Fraction
from hashlib import sha256
from itertools import pairwise
from typing import Any, cast

import rfc8785

from .analytic_target import AnalyticTargetError, _axis_vector, _cross, _transform
from .canonical import CanonicalProfile, canonical_hash
from .json_types import JSONValue
from .validation import SemanticValidator

VERSION = "ANALYTIC_COORDINATE_TARGET_V1"
PROFILE_ID = "SURFACE_OF_REVOLUTION_COORDINATE_PROFILE_CANONICAL_JSON_V1"
MAX_KNOTS = 129
_HASH_DOMAIN = b"Crochet.AI\x00ANALYTIC_COORDINATE_TARGET_V1\x00"


@dataclass(frozen=True, slots=True)
class AnalyticCoordinateTarget:
    """Immutable ideal surface metadata for one explicit meridian polyline."""

    design_spec_sha256: str
    profile_sha256: str
    origin_mm: tuple[float, float, float]
    axis_direction: tuple[int, int, int]
    up_axis: tuple[int, int, int]
    right_axis: tuple[int, int, int]
    second_axis: tuple[int, int, int]
    coordinates_mm: tuple[tuple[float, float], ...]
    start_boundary: str
    end_boundary: str
    component_count: int
    boundary_component_count: int
    genus: int
    betti_numbers: tuple[int, int, int]
    characteristic_length_mm: float
    segment_pair_checks: int
    segment_pair_limit: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": VERSION,
            "design_spec_sha256": self.design_spec_sha256,
            "profile_sha256": self.profile_sha256,
            "origin_mm": list(self.origin_mm),
            "axis_direction": list(self.axis_direction),
            "frame_basis": {
                "right_axis": list(self.right_axis),
                "second_axis": list(self.second_axis),
                "up_axis": list(self.up_axis),
            },
            "coordinates_mm": [list(point) for point in self.coordinates_mm],
            "start_boundary": self.start_boundary,
            "end_boundary": self.end_boundary,
            "ideal_topology": {
                "component_count": self.component_count,
                "boundary_component_count": self.boundary_component_count,
                "genus": self.genus,
                "betti_numbers": list(self.betti_numbers),
            },
            "characteristic_length_mm": self.characteristic_length_mm,
            "admission": {
                "algorithm_id": VERSION,
                "segment_count": len(self.coordinates_mm) - 1,
                "segment_pair_checks": self.segment_pair_checks,
                "segment_pair_limit": self.segment_pair_limit,
                "finite_distinct_cardinal_witness_count": 2 + 4 * (len(self.coordinates_mm) - 2),
            },
            "sha256": self.sha256,
        }


def admit_analytic_coordinate_target(
    design: dict[str, Any], validator: SemanticValidator
) -> AnalyticCoordinateTarget:
    report = validator.validate_design_spec(design)
    if not report.ok:
        raise AnalyticTargetError("DesignSpec semantic validation failed")
    target = design["target_geometry"]
    profile = target.get("radial_profile", {})
    if (
        design["project_type"] != "AMIGURUMI_3D"
        or target["geometry_type"] != "ANALYTIC_SHAPE"
        or target["primitive"] != "SURFACE_OF_REVOLUTION"
        or design["domain_constraints"]["surface_mode"] != "CLOSED"
        or profile.get("canonicalization_profile") != PROFILE_ID
    ):
        raise AnalyticTargetError(
            "target is outside ANALYTIC_COORDINATE_TARGET_V1 scope", "NOT_APPLICABLE"
        )
    if any(
        item["closure_expectation"] == "REMAIN_OPEN"
        for item in design["construction_constraints"]["intentional_openings"]
    ):
        raise AnalyticTargetError(
            "closed target conflicts with declared boundary intent", "NOT_APPLICABLE"
        )
    if (
        profile["start_boundary"]["boundary_type"] != "CLOSED_POLE"
        or profile["end_boundary"]["boundary_type"] != "CLOSED_POLE"
    ):
        raise AnalyticTargetError(
            "coordinate target requires two CLOSED_POLE boundaries", "NOT_APPLICABLE"
        )

    axis = tuple(float(value) for value in target["axis_direction"])
    up = _axis_vector(target["coordinate_frame"]["up_axis"])
    axis_tuple = cast(tuple[float, float, float], axis)
    if axis_tuple != tuple(float(value) for value in up):
        raise AnalyticTargetError(
            "target axis must exactly match the signed cardinal frame up axis", "NOT_APPLICABLE"
        )

    samples = profile["samples"]
    points = tuple((float(sample["radius_mm"]), float(sample["axial_mm"])) for sample in samples)
    if not 3 <= len(points) <= MAX_KNOTS:
        raise AnalyticTargetError("coordinate knot count is outside [3, 129]")
    if points[0][0] != 0 or points[-1][0] != 0 or points[0][1] == points[-1][1]:
        raise AnalyticTargetError(
            "closed coordinate profile requires distinct zero-radius endpoint poles"
        )
    if any(radius <= 0 for radius, _ in points[1:-1]):
        raise AnalyticTargetError("coordinate profile interior radius must be positive")
    exact_points = tuple((Fraction(radius), Fraction(axial)) for radius, axial in points)
    if any(a == b for a, b in pairwise(exact_points)):
        raise AnalyticTargetError("coordinate profile contains a zero-length segment")
    checks = 0
    pair_limit = (len(points) - 1) * (len(points) - 2) // 2
    for seg_left in range(len(points) - 1):
        for seg_right in range(seg_left + 1, len(points) - 1):
            checks += 1
            a, b = exact_points[seg_left], exact_points[seg_left + 1]
            c, d = exact_points[seg_right], exact_points[seg_right + 1]
            if seg_right == seg_left + 1:
                if _orient(a, b, d) == 0:
                    # At shared knot b, strict opposite directions mean continuation.
                    va = (a[0] - b[0], a[1] - b[1])
                    vd = (d[0] - b[0], d[1] - b[1])
                    if va[0] * vd[0] + va[1] * vd[1] >= 0:
                        raise AnalyticTargetError(
                            "adjacent coordinate segments overlap by backtracking"
                        )
                continue
            if _segments_intersect(a, b, c, d):
                raise AnalyticTargetError("nonadjacent coordinate segments intersect or touch")

    axial_values = [point[1] for point in points]
    extent = max(axial_values) - min(axial_values)
    if not math.isfinite(extent) or extent <= 0:
        raise AnalyticTargetError("coordinate profile axial extent is not finite and positive")
    measurement_by_id = {
        item["measurement_id"]: float(item["value_mm"])
        for item in design["dimensions"]["measurements"]
    }
    length_parameter = next(
        item for item in target["parameters"] if item["parameter"] == "AXIAL_LENGTH"
    )
    if measurement_by_id[length_parameter["measurement_id"]] != extent:
        raise AnalyticTargetError("AXIAL_LENGTH does not equal coordinate profile axial extent")

    origin_values = tuple(float(value) for value in target["origin_mm"])
    origin = cast(tuple[float, float, float], origin_values)
    front = _axis_vector(target["coordinate_frame"]["front_axis"])
    right = _cross(up, front)
    second = _cross(up, right)
    witness_points: list[tuple[float, float, float]] = [
        _transform(origin, right, second, up, 0.0, 0.0, axial)
        for radius, axial in (points[0], points[-1])
    ]
    for radius, axial in points[1:-1]:
        witness_points.extend(
            _transform(origin, right, second, up, sx * radius, sy * radius, axial)
            for sx, sy in ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0))
        )
    if not all(math.isfinite(value) for point in witness_points for value in point):
        raise AnalyticTargetError("pole or cardinal-knot witness coordinate is non-finite")
    if len(set(witness_points)) != len(witness_points):
        raise AnalyticTargetError("pole or cardinal-knot witness positions collapse in binary64")
    max_radius = max(radius for radius, _ in points)
    characteristic = max(2.0 * max_radius, extent)
    if not math.isfinite(characteristic) or characteristic <= 0:
        raise AnalyticTargetError(
            "coordinate target characteristic length is outside binary64 range"
        )

    design_digest = canonical_hash(design, CanonicalProfile.DESIGN_SPEC, validator=validator)
    profile_payload = dict(profile)
    profile_payload.pop("sha256")
    profile_digest = canonical_hash(
        profile_payload, CanonicalProfile.SURFACE_OF_REVOLUTION_COORDINATES
    )
    admitted = AnalyticCoordinateTarget(
        design_digest,
        profile_digest,
        origin,
        up,
        up,
        right,
        second,
        points,
        "CLOSED_POLE",
        "CLOSED_POLE",
        1,
        0,
        0,
        (1, 0, 1),
        characteristic,
        checks,
        pair_limit,
        "",
    )
    metadata = admitted.to_dict()
    metadata.pop("sha256")
    digest = sha256(_HASH_DOMAIN + rfc8785.dumps(cast(JSONValue, metadata))).hexdigest()
    return replace(admitted, sha256=digest)


def _orient(
    a: tuple[Fraction, Fraction], b: tuple[Fraction, Fraction], c: tuple[Fraction, Fraction]
) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(
    a: tuple[Fraction, Fraction], b: tuple[Fraction, Fraction], p: tuple[Fraction, Fraction]
) -> bool:
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def _segments_intersect(
    a: tuple[Fraction, Fraction],
    b: tuple[Fraction, Fraction],
    c: tuple[Fraction, Fraction],
    d: tuple[Fraction, Fraction],
) -> bool:
    o1, o2, o3, o4 = _orient(a, b, c), _orient(a, b, d), _orient(c, d, a), _orient(c, d, b)
    if (o1 > 0 > o2 or o2 > 0 > o1) and (o3 > 0 > o4 or o4 > 0 > o3):
        return True
    return (
        (o1 == 0 and _on_segment(a, b, c))
        or (o2 == 0 and _on_segment(a, b, d))
        or (o3 == 0 and _on_segment(c, d, a))
        or (o4 == 0 and _on_segment(c, d, b))
    )
