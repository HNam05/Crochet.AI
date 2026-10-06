"""Immutable target-side decoding and bounded sampling for analytic primitives."""

from __future__ import annotations

import math
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Any, cast

import rfc8785

from .canonical import CanonicalProfile, canonical_hash
from .json_types import JSONValue
from .validation import SemanticValidator

if TYPE_CHECKING:
    from .analytic_coordinate_target import AnalyticCoordinateTarget

VERSION = "ANALYTIC_TARGET_V1"
SAMPLING_ALGORITHM = "ANALYTIC_TARGET_LATITUDE_AZIMUTH_GRID_V1"
_HASH_DOMAIN = b"Crochet.AI\x00ANALYTIC_TARGET_V1\x00"
_SAMPLE_HASH_DOMAIN = b"Crochet.ANALYTIC_TARGET_SAMPLE_V1\x00"
MAX_RING_COUNT = 256
MAX_SECTOR_COUNT = 256
MAX_SAMPLE_POINTS = 65_536


class AnalyticTargetError(ValueError):
    """Fail-closed target admission or sampling error."""

    def __init__(self, reason: str, status: str = "INVALID_SOLVER_INPUT") -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


@dataclass(frozen=True, slots=True)
class SampledAnalyticTarget:
    """Deterministic point cloud, distinct from the ideal analytic surface."""

    target_sha256: str
    algorithm_id: str
    ring_count: int
    sector_count: int
    points_mm: tuple[tuple[float, float, float], ...]
    sha256: str


@dataclass(frozen=True, slots=True)
class AnalyticTarget:
    """Validated immutable description of an ideal sphere or ellipsoid."""

    primitive: str
    design_spec_sha256: str
    origin_mm: tuple[float, float, float]
    up_axis: tuple[int, int, int]
    right_axis: tuple[int, int, int]
    second_axis: tuple[int, int, int]
    equatorial_radius_mm: float
    polar_radius_mm: float
    component_count: int
    boundary_component_count: int
    genus: int
    betti_numbers: tuple[int, int, int]
    characteristic_length_mm: float
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-compatible metadata value."""
        return {
            "version": VERSION,
            "primitive": self.primitive,
            "design_spec_sha256": self.design_spec_sha256,
            "origin_mm": list(self.origin_mm),
            "frame_basis": {
                "right_axis": list(self.right_axis),
                "second_axis": list(self.second_axis),
                "up_axis": list(self.up_axis),
            },
            "equatorial_radius_mm": self.equatorial_radius_mm,
            "polar_radius_mm": self.polar_radius_mm,
            "ideal_topology": {
                "component_count": self.component_count,
                "boundary_component_count": self.boundary_component_count,
                "genus": self.genus,
                "betti_numbers": list(self.betti_numbers),
            },
            "characteristic_length_mm": self.characteristic_length_mm,
            "sha256": self.sha256,
        }

    def sample(self, *, ring_count: int, sector_count: int) -> SampledAnalyticTarget:
        """Produce a bounded latitude/azimuth grid without claiming surface certification."""
        _validate_budget(ring_count, sector_count)
        points: list[tuple[float, float, float]] = []
        local_points: list[tuple[float, float, float]] = []

        for ring in range(ring_count + 1):
            if ring == 0:
                latitude_cos, latitude_sin = 0.0, -1.0
            elif ring == ring_count:
                latitude_cos, latitude_sin = 0.0, 1.0
            elif ring * 2 == ring_count:
                latitude_cos, latitude_sin = 1.0, 0.0
            else:
                angle = -math.pi / 2.0 + math.pi * ring / ring_count
                latitude_cos, latitude_sin = math.cos(angle), math.sin(angle)

            azimuth_count = 1 if ring in (0, ring_count) else sector_count
            for sector in range(azimuth_count):
                if ring in (0, ring_count):
                    cos_azimuth, sin_azimuth = 1.0, 0.0
                elif sector_count % 4 == 0 and sector == sector_count // 4:
                    cos_azimuth, sin_azimuth = 0.0, 1.0
                elif sector_count % 2 == 0 and sector == sector_count // 2:
                    cos_azimuth, sin_azimuth = -1.0, 0.0
                elif sector_count % 4 == 0 and sector == 3 * sector_count // 4:
                    cos_azimuth, sin_azimuth = 0.0, -1.0
                else:
                    angle = 2.0 * math.pi * sector / sector_count
                    cos_azimuth, sin_azimuth = math.cos(angle), math.sin(angle)
                x = self.equatorial_radius_mm * latitude_cos * cos_azimuth
                y = self.equatorial_radius_mm * latitude_cos * sin_azimuth
                z = self.polar_radius_mm * latitude_sin
                local = (x, y, z)
                point = _transform(
                    self.origin_mm,
                    self.right_axis,
                    self.second_axis,
                    self.up_axis,
                    x,
                    y,
                    z,
                )
                if not all(math.isfinite(value) for value in (*local, *point)):
                    raise AnalyticTargetError("sample coordinate is non-finite")
                local_points.append(local)
                points.append(point)

        if len(set(local_points)) != len(local_points):
            raise AnalyticTargetError("binary64 sampling coordinates collapse to duplicates")
        if len(set(points)) != len(points):
            raise AnalyticTargetError("origin translation collapses distinct sampling coordinates")
        point_tuple = tuple(points)
        sample_payload = {
            "algorithm_id": SAMPLING_ALGORITHM,
            "target_sha256": self.sha256,
            "ring_count": ring_count,
            "sector_count": sector_count,
            "points_mm": [list(point) for point in point_tuple],
        }
        sample_hash = sha256(
            _SAMPLE_HASH_DOMAIN + rfc8785.dumps(cast(JSONValue, sample_payload))
        ).hexdigest()
        return SampledAnalyticTarget(
            self.sha256,
            SAMPLING_ALGORITHM,
            ring_count,
            sector_count,
            point_tuple,
            sample_hash,
        )


def admit_analytic_target(
    design: dict[str, Any], validator: SemanticValidator
) -> AnalyticTarget | AnalyticCoordinateTarget:
    """Semantically validate and decode a supported AMIGURUMI_3D primitive."""
    report = validator.validate_design_spec(design)
    if not report.ok:
        raise AnalyticTargetError("DesignSpec semantic validation failed")
    target = design["target_geometry"]
    if (
        target.get("primitive") == "SURFACE_OF_REVOLUTION"
        and target.get("radial_profile", {}).get("canonicalization_profile")
        == "SURFACE_OF_REVOLUTION_COORDINATE_PROFILE_CANONICAL_JSON_V1"
    ):
        from .analytic_coordinate_target import admit_analytic_coordinate_target

        return admit_analytic_coordinate_target(design, validator)
    if target["geometry_type"] != "ANALYTIC_SHAPE":
        raise AnalyticTargetError("target is not an analytic shape", "NOT_APPLICABLE")
    primitive = target["primitive"]
    if primitive in {"CYLINDER", "CONE", "SURFACE_OF_REVOLUTION"}:
        raise AnalyticTargetError(
            f"{primitive} target has unresolved interface or axial-sign semantics",
            "NOT_APPLICABLE",
        )
    if primitive not in {"SPHERE", "ELLIPSOID"} or design["project_type"] != "AMIGURUMI_3D":
        raise AnalyticTargetError(
            "target is outside ANALYTIC_TARGET_V1 applicability", "NOT_APPLICABLE"
        )
    if design["domain_constraints"]["surface_mode"] != "CLOSED" or any(
        opening["closure_expectation"] == "REMAIN_OPEN"
        for opening in design["construction_constraints"]["intentional_openings"]
    ):
        raise AnalyticTargetError(
            "closed analytic target conflicts with declared boundary intent", "NOT_APPLICABLE"
        )

    expected = {
        "SPHERE": ("RADIUS",),
        "ELLIPSOID": ("EQUATORIAL_RADIUS", "POLAR_RADIUS"),
    }[primitive]
    measurements = {
        item["measurement_id"]: item["value_mm"] for item in design["dimensions"]["measurements"]
    }
    parameter_measurements = {
        item["parameter"]: item["measurement_id"] for item in target["parameters"]
    }
    if set(parameter_measurements) != set(expected):
        raise AnalyticTargetError("analytic parameter set is incomplete or ambiguous")
    equatorial = float(measurements[parameter_measurements[expected[0]]])
    polar = equatorial if primitive == "SPHERE" else float(
        measurements[parameter_measurements[expected[1]]]
    )
    origin_values = tuple(float(value) for value in target["origin_mm"])
    origin: tuple[float, float, float] = (
        origin_values[0], origin_values[1], origin_values[2]
    )
    if not all(math.isfinite(value) for value in (*origin, equatorial, polar)):
        raise AnalyticTargetError("target contains a non-finite binary64 value")
    if equatorial <= 0 or polar <= 0:
        raise AnalyticTargetError("derived target radii must be positive")
    characteristic = 2.0 * max(equatorial, polar)
    if not math.isfinite(characteristic) or characteristic <= 0:
        raise AnalyticTargetError("derived characteristic length is outside binary64 range")

    up = _axis_vector(target["coordinate_frame"]["up_axis"])
    front = _axis_vector(target["coordinate_frame"]["front_axis"])
    right = _cross(up, front)
    if right == (0, 0, 0):
        raise AnalyticTargetError("coordinate frame axes do not determine a right axis")
    second = _cross(up, right)
    _validate_cardinal_coordinates(origin, right, second, up, equatorial, polar)
    design_digest = canonical_hash(design, CanonicalProfile.DESIGN_SPEC, validator=validator)
    payload = {
        "version": VERSION,
        "primitive": primitive,
        "design_spec_sha256": design_digest,
        "origin_mm": list(origin),
        "frame_basis": {
            "right_axis": list(right), "second_axis": list(second), "up_axis": list(up)
        },
        "equatorial_radius_mm": equatorial,
        "polar_radius_mm": polar,
        "ideal_topology": {
            "component_count": 1,
            "boundary_component_count": 0,
            "genus": 0,
            "betti_numbers": [1, 0, 1],
        },
        "characteristic_length_mm": characteristic,
    }
    digest = sha256(_HASH_DOMAIN + rfc8785.dumps(cast(JSONValue, payload))).hexdigest()
    return AnalyticTarget(
        primitive=primitive,
        design_spec_sha256=design_digest,
        origin_mm=origin,
        up_axis=up,
        right_axis=right,
        second_axis=second,
        equatorial_radius_mm=equatorial,
        polar_radius_mm=polar,
        component_count=1,
        boundary_component_count=0,
        genus=0,
        betti_numbers=(1, 0, 1),
        characteristic_length_mm=characteristic,
        sha256=digest,
    )


def _axis_vector(value: str) -> tuple[int, int, int]:
    sign = -1 if value.startswith("NEGATIVE_") else 1
    axis = value.removeprefix("POSITIVE_").removeprefix("NEGATIVE_")
    components = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}
    vector = components.get(axis)
    if vector is None:
        raise AnalyticTargetError("invalid signed coordinate axis")
    return (sign * vector[0], sign * vector[1], sign * vector[2])


def _cross(
    left: tuple[int, int, int], right: tuple[int, int, int]
) -> tuple[int, int, int]:
    result: tuple[int, int, int] = (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )
    return result


def _transform(
    origin: tuple[float, float, float],
    right: tuple[int, int, int],
    second: tuple[int, int, int],
    up: tuple[int, int, int],
    x: float,
    y: float,
    z: float,
) -> tuple[float, float, float]:
    return (
        origin[0] + right[0] * x + second[0] * y + up[0] * z,
        origin[1] + right[1] * x + second[1] * y + up[1] * z,
        origin[2] + right[2] * x + second[2] * y + up[2] * z,
    )


def _validate_cardinal_coordinates(
    origin: tuple[float, float, float],
    right: tuple[int, int, int],
    second: tuple[int, int, int],
    up: tuple[int, int, int],
    equatorial_radius: float,
    polar_radius: float,
) -> None:
    cardinal_points = (
        _transform(origin, right, second, up, equatorial_radius, 0.0, 0.0),
        _transform(origin, right, second, up, -equatorial_radius, 0.0, 0.0),
        _transform(origin, right, second, up, 0.0, equatorial_radius, 0.0),
        _transform(origin, right, second, up, 0.0, -equatorial_radius, 0.0),
        _transform(origin, right, second, up, 0.0, 0.0, polar_radius),
        _transform(origin, right, second, up, 0.0, 0.0, -polar_radius),
    )
    if not all(math.isfinite(coordinate) for point in cardinal_points for coordinate in point):
        raise AnalyticTargetError("target cardinal coordinates are outside binary64 range")
    if len(set(cardinal_points)) != len(cardinal_points) or origin in cardinal_points:
        raise AnalyticTargetError("target cardinal coordinates collapse in binary64")


def _validate_budget(ring_count: int, sector_count: int) -> None:
    if type(ring_count) is not int or not 2 <= ring_count <= MAX_RING_COUNT:
        raise AnalyticTargetError(f"ring_count must be an integer in [2, {MAX_RING_COUNT}]")
    if type(sector_count) is not int or not 4 <= sector_count <= MAX_SECTOR_COUNT:
        raise AnalyticTargetError(f"sector_count must be an integer in [4, {MAX_SECTOR_COUNT}]")
    point_count = 2 + (ring_count - 1) * sector_count
    if point_count > MAX_SAMPLE_POINTS:
        raise AnalyticTargetError(f"sampling grid exceeds {MAX_SAMPLE_POINTS} points")
