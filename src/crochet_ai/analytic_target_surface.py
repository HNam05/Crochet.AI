"""Bounded target-side triangulation for admitted analytic revolution surfaces.

The emitted mesh is a deterministic discretization, never an ideal-surface or
V0 certificate. The analytic forward simulator is deliberately not imported.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from itertools import pairwise
from typing import TypeAlias, cast

import rfc8785

from .analytic_coordinate_target import AnalyticCoordinateTarget
from .analytic_target import AnalyticTarget, _transform, admit_analytic_target
from .canonical import CanonicalProfile, canonical_hash, jcs_bytes
from .json_types import JSONValue
from .surface_topology import audit_surface_topology
from .validation import SemanticValidator

PROFILE = "ANALYTIC_TARGET_SURFACE_V1"
POLICY_PROFILE = "ANALYTIC_TARGET_SURFACE_SAMPLING_V1"
MAX_VERTICES = 512
MAX_FACES = 1024
Vec3: TypeAlias = tuple[float, float, float]
MeridianPoint: TypeAlias = tuple[float, float]


class AnalyticTargetSurfaceError(ValueError):
    """Invalid policy or unrepresentable target surface discretization."""

    def __init__(self, code: str, reason: str) -> None:
        self.code, self.reason = code, reason
        super().__init__(f"{code}: {reason}")


@dataclass(frozen=True, slots=True)
class SamplingPolicy:
    target_kind: str
    schema_version: str
    azimuth_sectors: int
    ring_count: int | None
    linear_segment_subdivisions: int | None
    canonical_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class SampledTargetSurface:
    target_sha256: str
    design_spec_sha256: str
    design_spec_jcs_bytes: bytes
    design_spec_jcs_sha256: str
    source_profile_sha256: str | None
    sampling_policy: SamplingPolicy
    coordinate_frame_id: str
    vertices_mm: tuple[Vec3, ...]
    faces: tuple[tuple[int, int, int], ...]
    start_pole_vertex: int
    end_pole_vertex: int
    authored_knot_vertex_indices: tuple[int, ...]
    sampled_mesh_jcs_bytes: bytes
    sampled_mesh_sha256: str
    topology_sha256: str
    analytic_discretization_bound_mm: float
    approximation_algorithm: str
    sha256: str

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "profile": PROFILE,
            "status": "SAMPLED_DISCRETIZATION_ONLY",
            "comparison_eligible": True,
            "v0_certificate": "NOT_PROVIDED",
            "ideal_surface_certificate": "NOT_PROVIDED",
            "target_sha256": self.target_sha256,
            "design_spec_sha256": self.design_spec_sha256,
            "design_spec_jcs_sha256": self.design_spec_jcs_sha256,
            "source_profile_sha256": self.source_profile_sha256,
            "sampling_policy": _policy_dict(self.sampling_policy),
            "coordinate_frame_id": self.coordinate_frame_id,
            "vertices_mm": [list(point) for point in self.vertices_mm],
            "faces": [list(face) for face in self.faces],
            "poles": {
                "start_vertex_index": self.start_pole_vertex,
                "end_vertex_index": self.end_pole_vertex,
            },
            "authored_knot_vertex_indices": list(self.authored_knot_vertex_indices),
            "sampled_mesh_jcs_sha256": self.sampled_mesh_sha256,
            "sampled_mesh_jcs_bytes_hex": self.sampled_mesh_jcs_bytes.hex(),
            "topology_sha256": self.topology_sha256,
            "approximation": {
                "kind": "TRIANGULATED_ANALYTIC_SURFACE_APPROXIMATION",
                "coverage_bound_mm": self.analytic_discretization_bound_mm,
                "bound_algorithm": self.approximation_algorithm,
                "bound_scope": "exact-arithmetic parameterized surface to linear triangles",
                "binary64_rounding_included": False,
                "whole_ideal_surface_or_v0_certified": False,
            },
            "sha256": self.sha256,
        }


def admit_sampling_policy(
    value: object, target: AnalyticTarget | AnalyticCoordinateTarget
) -> SamplingPolicy:
    if not isinstance(value, dict):
        raise AnalyticTargetSurfaceError("E_SCHEMA", "sampling_policy.must_be_object")
    kind = "COORDINATE" if isinstance(target, AnalyticCoordinateTarget) else "ANALYTIC"
    base = {"profile", "schema_version", "azimuth_sectors"}
    expected = base | ({"linear_segment_subdivisions"} if kind == "COORDINATE" else {"ring_count"})
    if set(value) != expected:
        raise AnalyticTargetSurfaceError("E_SCHEMA", "sampling_policy.fields_invalid")
    if value["profile"] != POLICY_PROFILE or value["schema_version"] != "1.0.0":
        raise AnalyticTargetSurfaceError("E_INPUT", "sampling_policy.version_invalid")
    sectors = value["azimuth_sectors"]
    if type(sectors) is not int or not 4 <= sectors <= 64:
        raise AnalyticTargetSurfaceError("E_INPUT", "sampling_policy.azimuth_sectors_invalid")
    rings: int | None = None
    subdivisions: int | None = None
    if kind == "ANALYTIC":
        rings = value["ring_count"]
        if type(rings) is not int or not 2 <= rings <= 64:
            raise AnalyticTargetSurfaceError("E_INPUT", "sampling_policy.ring_count_invalid")
        intervals = rings
    else:
        subdivisions = value["linear_segment_subdivisions"]
        if type(subdivisions) is not int or not 1 <= subdivisions <= 8:
            raise AnalyticTargetSurfaceError("E_INPUT", "sampling_policy.subdivision_count_invalid")
        intervals = (len(cast(AnalyticCoordinateTarget, target).coordinates_mm) - 1) * subdivisions
    vertices, faces = 2 + max(0, intervals - 1) * sectors, 2 * sectors * max(0, intervals - 1)
    if vertices > MAX_VERTICES or faces > MAX_FACES:
        raise AnalyticTargetSurfaceError("E_BUDGET", "sampling_policy.mesh_budget_exceeded")
    normalized: dict[str, JSONValue] = {
        "profile": POLICY_PROFILE,
        "schema_version": "1.0.0",
        "azimuth_sectors": sectors,
    }
    if rings is not None:
        normalized["ring_count"] = rings
    if subdivisions is not None:
        normalized["linear_segment_subdivisions"] = subdivisions
    encoded = rfc8785.dumps(cast(JSONValue, normalized))
    digest = sha256(b"Crochet.AI\0" + POLICY_PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return SamplingPolicy(kind, "1.0.0", sectors, rings, subdivisions, encoded, digest)


def sample_analytic_target_surface(
    design_spec: dict[str, object],
    target: AnalyticTarget | AnalyticCoordinateTarget,
    parameters: object,
    *,
    validator: SemanticValidator,
) -> SampledTargetSurface:
    """Triangulate an admitted analytic target under an explicit strict policy."""
    if not isinstance(target, (AnalyticTarget, AnalyticCoordinateTarget)):
        raise AnalyticTargetSurfaceError("E_INPUT", "target.must_be_admitted_analytic_target")
    try:
        design_digest = canonical_hash(
            design_spec, CanonicalProfile.DESIGN_SPEC, validator=validator
        )
        admitted_again = admit_analytic_target(design_spec, validator)
    except (ValueError, KeyError, TypeError) as error:
        raise AnalyticTargetSurfaceError("E_INPUT", "design_spec.not_admitted") from error
    if design_digest != target.design_spec_sha256 or admitted_again != target:
        raise AnalyticTargetSurfaceError("E_BINDING", "target_design_binding_mismatch")
    design_bytes = rfc8785.dumps(cast(JSONValue, design_spec))
    design_bytes_sha = sha256(design_bytes).hexdigest()
    policy = admit_sampling_policy(parameters, target)
    sectors = policy.azimuth_sectors
    if isinstance(target, AnalyticTarget):
        meridian, _generated_rows = _analytic_meridian(target, cast(int, policy.ring_count))
        bound, algorithm = _analytic_bound(target, cast(int, policy.ring_count), sectors)
        source_profile = None
        authored: list[int] = []
        frame_id = _coordinate_frame_id(design_spec)
    else:
        meridian, authored = _coordinate_meridian(
            target, cast(int, policy.linear_segment_subdivisions)
        )
        bound, algorithm = _coordinate_bound(
            target, cast(int, policy.linear_segment_subdivisions), sectors
        )
        source_profile = target.profile_sha256
        frame_id = _coordinate_frame_id(design_spec)
    vertices, rings, poles = _make_vertices(target, meridian, sectors)
    if source_profile is not None:
        authored = [
            poles[0]
            if index == 0
            else poles[1]
            if index == len(meridian) - 1
            else 1 + (index - 1) * sectors
            for index in authored
        ]
    faces = _make_faces(rings, poles[0], poles[1], sectors)
    _orient_and_validate(vertices, faces)
    topology = audit_surface_topology(
        [f"v{index:04d}" for index in range(len(vertices))],
        [[f"v{index:04d}" for index in face] for face in faces],
        max_vertices=MAX_VERTICES,
        max_faces=MAX_FACES,
    )
    if topology.status != "PASS" or topology.betti_numbers != (1, 0, 1):
        raise AnalyticTargetSurfaceError("E_TOPOLOGY", "sampled_mesh_topology_invalid")
    mesh: dict[str, JSONValue] = {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER",
            "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": frame_id,
        },
        "vertices": [{"position_mm": list(point)} for point in vertices],
        "faces": [{"vertex_indices": list(face)} for face in faces],
    }
    mesh_bytes = rfc8785.dumps(cast(JSONValue, mesh))
    mesh_digest = sha256(mesh_bytes).hexdigest()
    design_digest = target.design_spec_sha256
    envelope: dict[str, JSONValue] = {
        "profile": PROFILE,
        "target_sha256": target.sha256,
        "design_spec_sha256": design_digest,
        "design_spec_jcs_sha256": design_bytes_sha,
        "source_profile_sha256": source_profile,
        "sampling_policy_sha256": policy.sha256,
        "coordinate_frame_id": frame_id,
        "sampled_mesh_sha256": mesh_digest,
        "topology_sha256": topology.sha256,
        "coverage_bound_mm": bound,
        "approximation_algorithm": algorithm,
        "poles": list(poles),
        "authored_knot_vertex_indices": list(authored),
    }
    artifact_digest = sha256(
        b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + jcs_bytes(envelope)
    ).hexdigest()
    return SampledTargetSurface(
        target.sha256,
        design_digest,
        design_bytes,
        design_bytes_sha,
        source_profile,
        policy,
        frame_id,
        tuple(vertices),
        tuple(faces),
        poles[0],
        poles[1],
        tuple(authored),
        mesh_bytes,
        mesh_digest,
        topology.sha256,
        bound,
        algorithm,
        artifact_digest,
    )


def _analytic_meridian(
    target: AnalyticTarget, intervals: int
) -> tuple[list[MeridianPoint], list[int]]:
    radius, polar = target.equatorial_radius_mm, target.polar_radius_mm
    points: list[MeridianPoint] = []
    for index in range(intervals + 1):
        if index == 0:
            points.append((0.0, -polar))
        elif index == intervals:
            points.append((0.0, polar))
        elif index * 2 == intervals:
            points.append((radius, 0.0))
        else:
            angle = -math.pi / 2 + math.pi * index / intervals
            points.append((radius * math.cos(angle), polar * math.sin(angle)))
    return points, list(range(intervals + 1))


def _coordinate_meridian(
    target: AnalyticCoordinateTarget, subdivisions: int
) -> tuple[list[MeridianPoint], list[int]]:
    knots = target.coordinates_mm
    points: list[MeridianPoint] = [knots[0]]
    authored = [0]
    for start, end in pairwise(knots):
        for part in range(1, subdivisions):
            fraction = Fraction(part, subdivisions)
            point = tuple(
                float(
                    Fraction.from_float(start[axis])
                    + fraction * (Fraction.from_float(end[axis]) - Fraction.from_float(start[axis]))
                )
                for axis in range(2)
            )
            if not all(math.isfinite(value) for value in point):
                raise AnalyticTargetSurfaceError("E_NUMERIC", "meridian_subdivision_non_finite")
            points.append(cast(MeridianPoint, point))
        points.append(end)
        authored.append(len(points) - 1)
    return points, authored


def _make_vertices(
    target: AnalyticTarget | AnalyticCoordinateTarget,
    meridian: list[MeridianPoint],
    sectors: int,
) -> tuple[list[Vec3], list[list[int]], tuple[int, int]]:
    origin, right, second, up = (
        target.origin_mm,
        target.right_axis,
        target.second_axis,
        target.up_axis,
    )
    if not all(math.isfinite(value) for value in origin):
        raise AnalyticTargetSurfaceError("E_NUMERIC", "origin_non_finite")
    vertices: list[Vec3] = []
    rings: list[list[int]] = []
    poles = (0, -1)
    vertices.append(_transform(origin, right, second, up, 0.0, 0.0, meridian[0][1]))
    for radius, axial in meridian[1:-1]:
        ring: list[int] = []
        for sector in range(sectors):
            cos_theta, sin_theta = _azimuth(sector, sectors)
            point = _transform(
                origin, right, second, up, radius * cos_theta, radius * sin_theta, axial
            )
            if not all(math.isfinite(value) for value in point):
                raise AnalyticTargetSurfaceError("E_NUMERIC", "sample_coordinate_non_finite")
            ring.append(len(vertices))
            vertices.append(point)
        rings.append(ring)
    vertices.append(_transform(origin, right, second, up, 0.0, 0.0, meridian[-1][1]))
    poles = (0, len(vertices) - 1)
    if len(set(vertices)) != len(vertices):
        raise AnalyticTargetSurfaceError("E_NUMERIC", "sample_vertices_collapse")
    expected_vertices = 2 + max(0, len(meridian) - 2) * sectors
    expected_faces = 2 * sectors * max(0, len(meridian) - 2)
    if expected_vertices > MAX_VERTICES or expected_faces > MAX_FACES:
        raise AnalyticTargetSurfaceError("E_BUDGET", "mesh_budget_exceeded")
    return vertices, rings, poles


def _make_faces(
    rings: list[list[int]], start: int, end: int, sectors: int
) -> list[tuple[int, int, int]]:
    if not rings:
        raise AnalyticTargetSurfaceError("E_INPUT", "mesh_requires_interior_rings")
    faces: list[tuple[int, int, int]] = []
    first = rings[0]
    for sector in range(sectors):
        following = (sector + 1) % sectors
        faces.append((start, first[following], first[sector]))
    for lower, upper in pairwise(rings):
        for sector in range(sectors):
            following = (sector + 1) % sectors
            faces.append((lower[sector], lower[following], upper[following]))
            faces.append((lower[sector], upper[following], upper[sector]))
    last = rings[-1]
    for sector in range(sectors):
        following = (sector + 1) % sectors
        faces.append((last[sector], last[following], end))
    if len(faces) > MAX_FACES:
        raise AnalyticTargetSurfaceError("E_BUDGET", "mesh_face_budget_exceeded")
    return faces


def _orient_and_validate(vertices: list[Vec3], faces: list[tuple[int, int, int]]) -> None:
    exact = [tuple(Fraction.from_float(value) for value in point) for point in vertices]
    volume6 = Fraction(0)
    for face in faces:
        a, b, c = (exact[index] for index in face)
        ab = tuple(b[i] - a[i] for i in range(3))
        ac = tuple(c[i] - a[i] for i in range(3))
        cross = (
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        )
        if cross[0] == 0 and cross[1] == 0 and cross[2] == 0:
            raise AnalyticTargetSurfaceError("E_NUMERIC", "sample_triangle_exactly_degenerate")
        volume6 += a[0] * cross[0] + a[1] * cross[1] + a[2] * cross[2]
    if volume6 == 0:
        raise AnalyticTargetSurfaceError("E_NUMERIC", "sample_signed_volume_zero")
    if volume6 < 0:
        faces[:] = [(face[0], face[2], face[1]) for face in faces]


def _azimuth(sector: int, sectors: int) -> tuple[float, float]:
    if sector == 0:
        return 1.0, 0.0
    if sectors % 4 == 0 and sector == sectors // 4:
        return 0.0, 1.0
    if sectors % 2 == 0 and sector == sectors // 2:
        return -1.0, 0.0
    if sectors % 4 == 0 and sector == 3 * sectors // 4:
        return 0.0, -1.0
    angle = 2 * math.pi * sector / sectors
    return math.cos(angle), math.sin(angle)


def _analytic_bound(target: AnalyticTarget, rings: int, sectors: int) -> tuple[float, str]:
    hessian_bound = target.equatorial_radius_mm + max(
        target.equatorial_radius_mm, target.polar_radius_mm
    )
    delta_lat = math.pi / rings
    delta_theta = 2 * math.pi / sectors
    h_squared = delta_lat * delta_lat + delta_theta * delta_theta
    bound = 0.5 * hessian_bound * h_squared
    if not math.isfinite(bound):
        raise AnalyticTargetSurfaceError("E_NUMERIC", "coverage_bound_non_finite")
    return bound, "ANALYTIC_PARAMETRIC_HESSIAN_BOUND_V1"


def _coordinate_bound(
    target: AnalyticCoordinateTarget, subdivisions: int, sectors: int
) -> tuple[float, str]:
    max_piece_length = 0.0
    for start, end in pairwise(target.coordinates_mm):
        length = math.hypot(end[0] - start[0], end[1] - start[1]) / subdivisions
        max_piece_length = max(max_piece_length, length)
    max_radius = max(radius for radius, _ in target.coordinates_mm)
    delta_theta = 2 * math.pi / sectors
    bound = max_piece_length * delta_theta + 0.5 * max_radius * delta_theta * delta_theta
    if not math.isfinite(bound):
        raise AnalyticTargetSurfaceError("E_NUMERIC", "coverage_bound_non_finite")
    return bound, "LINEAR_MERIDIAN_AZIMUTH_HESSIAN_BOUND_V1"


def _policy_dict(policy: SamplingPolicy) -> dict[str, JSONValue]:
    return cast(dict[str, JSONValue], json.loads(policy.canonical_bytes))


def _coordinate_frame_id(design_spec: dict[str, object]) -> str:
    target = cast(dict[str, object], design_spec["target_geometry"])
    frame = cast(dict[str, object], target["coordinate_frame"])
    return cast(str, frame["coordinate_frame_id"])
