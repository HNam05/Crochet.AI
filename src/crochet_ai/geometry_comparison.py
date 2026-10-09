"""Deterministic, diagnostic-only comparison of two IndexedTriangleMeshV1 surfaces.

This profile intentionally cannot establish calibrated V7 or physical acceptance.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from itertools import combinations
from math import acos, atan2, degrees, isfinite, pi, sqrt
from typing import NoReturn, TypeAlias

from .canonical import SAFE_INTEGER, CanonicalizationError, jcs_bytes
from .diagnostics import ArtifactValidationError
from .exact_triangle_distance import _point_triangle as _exact_point_triangle
from .json_types import JSONValue
from .target_mesh_decode import (
    MESH_MEDIA_TYPE,
    DecodedIndexedTriangleMesh,
    MeshDecodeError,
    decode_indexed_triangle_mesh,
)

PROFILE = "GEOMETRY_COMPARISON_DIAGNOSTIC_V1"
_MAX_VERTICES, _MAX_FACES, _MAX_DISTANCE_QUERIES, _MAX_RASTER_TESTS = 512, 1024, 200_000, 2_000_000
_MAX_BROADPHASE_TESTS = 2_000_000
Point: TypeAlias = tuple[float, float, float]
Triangle: TypeAlias = tuple[Point, Point, Point]
Face: TypeAlias = tuple[int, int, int]
Barycentric: TypeAlias = tuple[float, float, float]
RationalPoint: TypeAlias = tuple[Fraction, Fraction]
SectionSegment: TypeAlias = tuple[RationalPoint, RationalPoint]
ExactPoint: TypeAlias = tuple[Fraction, Fraction, Fraction]
ExactTriangle: TypeAlias = tuple[ExactPoint, ExactPoint, ExactPoint]


@dataclass(frozen=True, slots=True)
class _Threshold:
    value: float
    unit: str
    owner: str
    rationale: str
    validation_path: str


@dataclass(frozen=True, slots=True)
class _Landmark:
    name: str
    predicted_vertex_index: int
    target: Point


@dataclass(frozen=True, slots=True)
class _Policy:
    raw: JSONValue
    coordinate_frame_id: str
    characteristic_length_mm: float
    max_vertices: int
    max_faces: int
    max_distance_queries: int
    max_raster_tests: int
    samples_per_face: int
    robust_percentile: float
    raster_resolution: int
    section_planes_z_mm: tuple[float, ...]
    landmarks: tuple[_Landmark, ...]
    hard_thresholds: dict[str, _Threshold]


class GeometryComparisonError(ValueError):
    """Malformed comparison input or exhausted declared deterministic budget."""

    def __init__(self, code: str, reason: str) -> None:
        self.code, self.reason = code, reason
        super().__init__(f"{code}: {reason}")


def _fail(code: str, reason: str) -> NoReturn:
    raise GeometryComparisonError(code, reason)


def _finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and type(value) in (int, float)
        and (not isinstance(value, int) or abs(value) <= SAFE_INTEGER)
        and isfinite(value)
    )


def _number(value: object) -> float:
    if isinstance(value, (int, float)) and _finite(value):
        return float(value)
    _fail("E_SCHEMA", "finite_number_required_after_validation")


def _integer(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    _fail("E_SCHEMA", "integer_required_after_validation")


def _text(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value
    _fail("E_SCHEMA", "text_required_after_validation")


def _metric_float(value: JSONValue) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            _fail("E_SCHEMA", "json.non_finite_number")
        return value
    if isinstance(value, list):
        return [_json_value(child) for child in value]
    if isinstance(value, Mapping):
        result: dict[str, JSONValue] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                _fail("E_SCHEMA", "json.object_key_not_string")
            result[key] = _json_value(child)
        return result
    _fail("E_SCHEMA", "json.value_unsupported")


def _mesh(value: object, frame: str) -> DecodedIndexedTriangleMesh:
    try:
        raw = jcs_bytes(_json_value(value))
        return decode_indexed_triangle_mesh(
            raw,
            media_type=MESH_MEDIA_TYPE,
            expected_coordinate_frame_id=frame,
            max_bytes=2_000_000,
            max_vertices=_MAX_VERTICES,
            max_faces=_MAX_FACES,
        )
    except (
        ArtifactValidationError,
        CanonicalizationError,
        MeshDecodeError,
        TypeError,
        ValueError,
    ) as error:
        _fail("E_INPUT", f"mesh.invalid:{error}")


def _policy(raw: object) -> _Policy:
    if not isinstance(raw, Mapping):
        _fail("E_SCHEMA", "policy.object_required")
    p: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            _fail("E_SCHEMA", "policy.member_name_not_string")
        p[key] = value
    required = {
        "policy_version",
        "profile_id",
        "provenance_status",
        "coordinate_frame_id",
        "initial_alignment",
        "characteristic_length_mm",
        "characteristic_length_owner",
        "characteristic_length_rationale",
        "max_vertices",
        "max_faces",
        "max_distance_queries",
        "max_raster_tests",
        "samples_per_face",
        "robust_percentile",
        "raster_resolution",
        "section_planes_z_mm",
        "landmarks",
        "hard_thresholds",
    }
    if set(p) != required:
        _fail("E_SCHEMA", "policy.members_missing_or_extra")
    if p["policy_version"] != "GEOMETRY_COMPARISON_POLICY_V1" or p["profile_id"] != PROFILE:
        _fail("E_UNSUPPORTED_FEATURE", "policy.version_or_profile_unsupported")
    if p["provenance_status"] != "HYPOTHESIS" or p["initial_alignment"] != "IDENTITY_V1":
        _fail("E_UNSUPPORTED_FEATURE", "policy.provenance_or_alignment_unsupported")
    if not isinstance(p["coordinate_frame_id"], str) or not p["coordinate_frame_id"]:
        _fail("E_SCHEMA", "policy.coordinate_frame_required")
    characteristic_length = _number(p["characteristic_length_mm"])
    if characteristic_length <= 0:
        _fail("E_SCHEMA", "policy.characteristic_length_invalid")
    for key in ("characteristic_length_owner", "characteristic_length_rationale"):
        owner_or_rationale = p[key]
        if not isinstance(owner_or_rationale, str) or not owner_or_rationale.strip():
            _fail("E_SCHEMA", f"policy.{key}_required")
    bounds = {
        "max_vertices": (1, _MAX_VERTICES),
        "max_faces": (1, _MAX_FACES),
        "max_distance_queries": (1, _MAX_DISTANCE_QUERIES),
        "max_raster_tests": (1, _MAX_RASTER_TESTS),
        "samples_per_face": (1, 16),
        "raster_resolution": (4, 64),
    }
    for key, (low, high) in bounds.items():
        v = p[key]
        if isinstance(v, bool) or not isinstance(v, int) or not low <= v <= high:
            _fail("E_SCHEMA", f"policy.{key}_out_of_range")
    robust_percentile = _number(p["robust_percentile"])
    if not 0 < robust_percentile <= 100:
        _fail("E_SCHEMA", "policy.robust_percentile_invalid")
    planes = p["section_planes_z_mm"]
    if not isinstance(planes, list) or len(planes) > 16 or any(not _finite(z) for z in planes):
        _fail("E_SCHEMA", "policy.section_planes_invalid")
    if len(set(planes)) != len(planes):
        _fail("E_SCHEMA", "policy.section_planes_duplicate")
    landmarks = p["landmarks"]
    if not isinstance(landmarks, list) or len(landmarks) > 32:
        _fail("E_SCHEMA", "policy.landmarks_invalid")
    names: set[str] = set()
    for item in landmarks:
        if not isinstance(item, Mapping) or set(item) != {
            "name",
            "predicted_vertex_index",
            "target_xyz_mm",
        }:
            _fail("E_SCHEMA", "policy.landmark_shape_invalid")
        name = item["name"]
        if not isinstance(name, str) or not name or name in names:
            _fail("E_SCHEMA", "policy.landmark_name_invalid")
        names.add(name)
        vertex_index = item["predicted_vertex_index"]
        if type(vertex_index) is not int or not 0 <= vertex_index < _MAX_VERTICES:
            _fail("E_SCHEMA", "policy.landmark_vertex_index_invalid")
        target_xyz = item["target_xyz_mm"]
        if (
            not isinstance(target_xyz, list)
            or len(target_xyz) != 3
            or any(not _finite(x) for x in target_xyz)
        ):
            _fail("E_SCHEMA", "policy.landmark_coordinate_invalid")
    thresholds = p["hard_thresholds"]
    if not isinstance(thresholds, Mapping):
        _fail("E_SCHEMA", "policy.thresholds_required")
    if not thresholds:
        _fail("E_SCHEMA", "policy.hard_threshold_required")
    supported_thresholds = {
        "symmetric_chamfer_normalized",
        "robust_hausdorff_normalized",
        "silhouette_iou_min",
        "topology_match",
        "normal_mean_degrees",
        "normal_p95_degrees",
        "section_error_normalized",
        "curvature_error_normalized",
        "relative_volume_error",
        "landmark_max_normalized",
    }
    for key, item in thresholds.items():
        if key not in supported_thresholds:
            _fail("E_UNSUPPORTED_FEATURE", f"policy.threshold.{key}_unsupported")
        if not isinstance(item, Mapping) or set(item) != {
            "value",
            "unit",
            "owner",
            "rationale",
            "validation_path",
        }:
            _fail("E_SCHEMA", f"policy.threshold.{key}_shape_invalid")
        threshold_value = _number(item["value"])
        invalid_threshold_value = (
            threshold_value != 0
            if key == "topology_match"
            else threshold_value < 0
            if key == "landmark_max_normalized"
            else threshold_value <= 0
        )
        if invalid_threshold_value or any(
            not isinstance(item[k], str) or not str(item[k]).strip()
            for k in ("unit", "owner", "rationale", "validation_path")
        ):
            _fail("E_SCHEMA", f"policy.threshold.{key}_invalid")
        expected_unit = "degree" if key in {"normal_mean_degrees", "normal_p95_degrees"} else "1"
        if item["unit"] != expected_unit:
            _fail("E_SCHEMA", f"policy.threshold.{key}_unit_invalid")
        if key == "silhouette_iou_min" and threshold_value > 1:
            _fail("E_SCHEMA", "policy.threshold.silhouette_iou_min_above_one")
    normalized = _json_value(p)
    thresholds = {
        key: _Threshold(
            _number(cast_mapping(item)["value"]),
            _text(cast_mapping(item)["unit"]),
            _text(cast_mapping(item)["owner"]),
            _text(cast_mapping(item)["rationale"]),
            _text(cast_mapping(item)["validation_path"]),
        )
        for key, item in thresholds.items()
    }
    landmark_values = tuple(
        _Landmark(
            str(cast_mapping(item)["name"]),
            _integer(cast_mapping(item)["predicted_vertex_index"]),
            _point3(cast_mapping(item)["target_xyz_mm"]),
        )
        for item in landmarks
    )
    return _Policy(
        normalized,
        _text(p["coordinate_frame_id"]),
        characteristic_length,
        _integer(p["max_vertices"]),
        _integer(p["max_faces"]),
        _integer(p["max_distance_queries"]),
        _integer(p["max_raster_tests"]),
        _integer(p["samples_per_face"]),
        robust_percentile,
        _integer(p["raster_resolution"]),
        tuple(_number(z) for z in planes),
        landmark_values,
        thresholds,
    )


def cast_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail("E_SCHEMA", "object_required_after_validation")
    return value


def _point3(value: object) -> Point:
    if not isinstance(value, list) or len(value) != 3 or any(not _finite(item) for item in value):
        _fail("E_SCHEMA", "point3_required_after_validation")
    return (_number(value[0]), _number(value[1]), _number(value[2]))


def _cross(a: Point, b: Point) -> Point:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Point, b: Point) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _face_data(mesh: DecodedIndexedTriangleMesh) -> tuple[list[Triangle], list[float], list[Point]]:
    tris: list[Triangle] = []
    areas: list[float] = []
    normals: list[Point] = []
    for face in mesh.faces:
        a, b, c = (mesh.vertices_mm[i] for i in face)
        n = _cross(_sub(b, a), _sub(c, a))
        twice = sqrt(_dot(n, n))
        if not isfinite(twice) or twice == 0:
            _fail("E_INPUT", "mesh.degenerate_triangle")
        tris.append((a, b, c))
        areas.append(twice / 2)
        normals.append((n[0] / twice, n[1] / twice, n[2] / twice))
    if not tris:
        _fail("E_INPUT", "mesh.empty_surface")
    return tris, areas, normals


def _samples(
    tris: list[Triangle], areas: list[float], n: int
) -> tuple[list[Point], list[float], list[int], list[Barycentric]]:
    # Deterministic Hammersley sequence mapped uniformly into triangle area.
    out: list[Point] = []
    weights: list[float] = []
    face_indices: list[int] = []
    barycentrics: list[Barycentric] = []
    for face_index, (tri, area) in enumerate(zip(tris, areas, strict=True)):
        for sample_index in range(n):
            radial = sqrt((sample_index + 0.5) / n)
            offset = _radical_inverse_base2(sample_index + 1)
            u, v, w = 1 - radial, radial * (1 - offset), radial * offset
            out.append(
                (
                    u * tri[0][0] + v * tri[1][0] + w * tri[2][0],
                    u * tri[0][1] + v * tri[1][1] + w * tri[2][1],
                    u * tri[0][2] + v * tri[1][2] + w * tri[2][2],
                )
            )
            weights.append(area / n)
            face_indices.append(face_index)
            barycentrics.append((u, v, w))
    return out, weights, face_indices, barycentrics


def _radical_inverse_base2(value: int) -> float:
    result = 0.0
    factor = 0.5
    remaining = value
    while remaining:
        result += (remaining & 1) * factor
        remaining >>= 1
        factor *= 0.5
    return result


def _nearest(
    samples: list[Point], tris: list[Triangle], budget: int, broadphase_budget: int
) -> tuple[list[float], list[int], int, int]:
    broadphase_needed = len(samples) * len(tris)
    if broadphase_needed > broadphase_budget:
        _fail("E_SEARCH_BUDGET", "distance_broadphase_budget_exhausted_before_work")
    distances: list[float] = []
    indices: list[int] = []
    exact_triangles: list[ExactTriangle] = [
        (_fraction_point(triangle[0]), _fraction_point(triangle[1]), _fraction_point(triangle[2]))
        for triangle in tris
    ]
    bounds = [
        tuple(
            (min(vertex[axis] for vertex in tri), max(vertex[axis] for vertex in tri))
            for axis in range(3)
        )
        for tri in exact_triangles
    ]
    queries = 0
    for point in samples:
        exact_point = _fraction_point(point)
        lower_bounds: list[tuple[Fraction, int]] = []
        for index, box in enumerate(bounds):
            squared_lower_bound = Fraction(0)
            for axis, (minimum, maximum) in enumerate(box):
                delta = (
                    minimum - exact_point[axis]
                    if exact_point[axis] < minimum
                    else (
                        exact_point[axis] - maximum if exact_point[axis] > maximum else Fraction(0)
                    )
                )
                squared_lower_bound += delta * delta
            lower_bounds.append((squared_lower_bound, index))
        lower_bounds.sort()
        best_squared: Fraction | None = None
        best_index = -1
        for lower_bound, index in lower_bounds:
            if best_squared is not None and (
                lower_bound > best_squared or (lower_bound == best_squared and index > best_index)
            ):
                break
            if queries >= budget:
                _fail("E_SEARCH_BUDGET", "distance_queries_budget_exhausted_before_work")
            candidate = _exact_point_triangle(exact_point, exact_triangles[index])
            queries += 1
            if best_squared is None or candidate < best_squared:
                best_squared, best_index = candidate, index
        if best_squared is None:
            _fail("E_INTERNAL", "distance_search_found_no_candidate")
        distances.append(sqrt(best_squared))
        indices.append(best_index)
    return distances, indices, queries, broadphase_needed


def _fraction_point(point: Point) -> ExactPoint:
    return Fraction(point[0]), Fraction(point[1]), Fraction(point[2])


def _vertex_gaussian_curvature(
    mesh: DecodedIndexedTriangleMesh,
    areas: list[float],
    topology: dict[str, int | bool],
) -> list[float] | None:
    if topology["boundary_edges"] != 0:
        return None
    angle_sums = [0.0] * len(mesh.vertices_mm)
    dual_areas = [0.0] * len(mesh.vertices_mm)
    for face, area in zip(mesh.faces, areas, strict=True):
        points = [mesh.vertices_mm[index] for index in face]
        for corner, vertex_index in enumerate(face):
            first = _sub(points[(corner + 1) % 3], points[corner])
            second = _sub(points[(corner + 2) % 3], points[corner])
            angle = atan2(
                sqrt(_dot(_cross(first, second), _cross(first, second))), _dot(first, second)
            )
            angle_sums[vertex_index] += angle
            dual_areas[vertex_index] += area / 3
    if any(area <= 0 or not isfinite(area) for area in dual_areas):
        _fail("E_INPUT", "curvature.invalid_barycentric_dual_area")
    values = [(2 * pi - angle) / area for angle, area in zip(angle_sums, dual_areas, strict=True)]
    if any(not isfinite(value) for value in values):
        _fail("E_INPUT", "curvature.non_finite_vertex_value")
    return values


def _closest_barycentric(point: Point, triangle: Triangle) -> Barycentric:
    a, b, c = triangle
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(point, a)
    d00, d01, d11 = _dot(ab, ab), _dot(ab, ac), _dot(ac, ac)
    d20, d21 = _dot(ap, ab), _dot(ap, ac)
    denominator = d00 * d11 - d01 * d01
    if denominator <= 0:
        _fail("E_INPUT", "curvature.correspondence_triangle_degenerate")
    v = (d11 * d20 - d01 * d21) / denominator
    w = (d00 * d21 - d01 * d20) / denominator
    if v >= 0 and w >= 0 and v + w <= 1:
        return (1 - v - w, v, w)
    best_distance = float("inf")
    best: Barycentric | None = None
    for start, end, weights in (
        (a, b, (0, 1)),
        (b, c, (1, 2)),
        (c, a, (2, 0)),
    ):
        direction = _sub(end, start)
        t = max(0.0, min(1.0, _dot(_sub(point, start), direction) / _dot(direction, direction)))
        projection: Point = (
            start[0] + t * direction[0],
            start[1] + t * direction[1],
            start[2] + t * direction[2],
        )
        delta = _sub(point, projection)
        squared_distance = _dot(delta, delta)
        if squared_distance < best_distance:
            barycentric = [0.0, 0.0, 0.0]
            barycentric[weights[0]] = 1 - t
            barycentric[weights[1]] = t
            best_distance = squared_distance
            best = (barycentric[0], barycentric[1], barycentric[2])
    if best is None:
        _fail("E_INTERNAL", "curvature.closest_triangle_projection_missing")
    return best


def _interpolate_vertex_value(values: list[float], face: Face, barycentric: Barycentric) -> float:
    return sum(values[face[index]] * barycentric[index] for index in range(3))


def _curvature_comparison(
    predicted_values: list[float] | None,
    target_values: list[float] | None,
    predicted_samples: list[Point],
    target_samples: list[Point],
    predicted_faces: list[int],
    target_faces: list[int],
    predicted_barycentrics: list[Barycentric],
    target_barycentrics: list[Barycentric],
    nearest_target_faces: list[int],
    nearest_predicted_faces: list[int],
    predicted_mesh_faces: tuple[Face, ...],
    target_mesh_faces: tuple[Face, ...],
    predicted_triangles: list[Triangle],
    target_triangles: list[Triangle],
    predicted_weights: list[float],
    target_weights: list[float],
    characteristic_length_mm: float,
) -> dict[str, JSONValue]:
    if predicted_values is None or target_values is None:
        return {
            "status": "INDETERMINATE",
            "reason": "closed_manifold_surface_required_for_vertex_angle_defect",
            "curvature_units": "mm^-2",
        }
    predicted_curvature = [
        _interpolate_vertex_value(predicted_values, predicted_mesh_faces[face], barycentric)
        for face, barycentric in zip(predicted_faces, predicted_barycentrics, strict=True)
    ]
    target_curvature = [
        _interpolate_vertex_value(
            target_values,
            target_mesh_faces[target_face],
            _closest_barycentric(point, target_triangles[target_face]),
        )
        for point, target_face in zip(predicted_samples, nearest_target_faces, strict=True)
    ]
    target_sample_curvature = [
        _interpolate_vertex_value(target_values, target_mesh_faces[face], barycentric)
        for face, barycentric in zip(target_faces, target_barycentrics, strict=True)
    ]
    predicted_at_target = [
        _interpolate_vertex_value(
            predicted_values,
            predicted_mesh_faces[predicted_face],
            _closest_barycentric(point, predicted_triangles[predicted_face]),
        )
        for point, predicted_face in zip(target_samples, nearest_predicted_faces, strict=True)
    ]
    errors = [
        abs(source - target)
        for source, target in zip(predicted_curvature, target_curvature, strict=True)
    ]
    reverse_errors = [
        abs(target - predicted)
        for target, predicted in zip(target_sample_curvature, predicted_at_target, strict=True)
    ]
    mean = (
        _weighted_mean(errors, predicted_weights) + _weighted_mean(reverse_errors, target_weights)
    ) / 2
    p95 = max(
        _weighted_percentile(errors, predicted_weights, 95),
        _weighted_percentile(reverse_errors, target_weights, 95),
    )
    maximum = max(errors + reverse_errors)
    scale_squared = characteristic_length_mm**2
    return {
        "status": "COMPUTED",
        "algorithm": "ANGLE_DEFECT_BARYCENTRIC_DUAL_AREA_V1",
        "vertex_curvature_units": "mm^-2",
        "error_units": "mm^-2",
        "area_weighted_mean_absolute_error": mean,
        "area_weighted_p95_absolute_error": p95,
        "maximum_absolute_error": maximum,
        "area_weighted_mean_absolute_error_normalized": mean * scale_squared,
        "area_weighted_p95_absolute_error_normalized": p95 * scale_squared,
        "maximum_absolute_error_normalized": maximum * scale_squared,
        "normalization_length_mm": characteristic_length_mm,
        "correspondence": (
            "EXACT_POINT_TRIANGLE_DISTANCE_THEN_FACE_INDEX_TIE_BREAK_BARYCENTRIC_PROJECTION_V1"
        ),
        "sampling_rule": "FACE_LOCAL_AREA_UNIFORM_HAMMERSLEY_BARYCENTRIC_V1",
        "resolution_limit": "vertex_angle_defect_is_mesh_resolution_and_triangulation_dependent",
    }


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    return sum(v * w for v, w in zip(values, weights, strict=True)) / sum(weights)


def _weighted_percentile(values: list[float], weights: list[float], q: float) -> float:
    pairs = sorted(zip(values, weights, strict=True))
    threshold = sum(weights) * q / 100
    acc = 0.0
    for value, weight in pairs:
        acc += weight
        if acc >= threshold:
            return value
    return pairs[-1][0]


def _topology(mesh: DecodedIndexedTriangleMesh) -> dict[str, int | bool]:
    edges: defaultdict[tuple[int, int], list[int]] = defaultdict(list)
    vfaces: defaultdict[int, set[int]] = defaultdict(set)
    for fi, face in enumerate(mesh.faces):
        for v in face:
            vfaces[v].add(fi)
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edges[(min(a, b), max(a, b))].append(fi)
    if len(vfaces) != len(mesh.vertices_mm):
        _fail("E_INPUT", "mesh.unreferenced_vertex")
    boundary_vertex_degrees: dict[int, int] = defaultdict(int)
    for (first, second), incident in edges.items():
        if len(incident) == 1:
            boundary_vertex_degrees[first] += 1
            boundary_vertex_degrees[second] += 1
    for vertex, incident_faces in vfaces.items():
        link: dict[int, set[int]] = defaultdict(set)
        for face_index in incident_faces:
            others = [index for index in mesh.faces[face_index] if index != vertex]
            link[others[0]].add(others[1])
            link[others[1]].add(others[0])
        link_components = _graph_component_count(link)
        degrees = [len(neighbors) for neighbors in link.values()]
        boundary_degree = boundary_vertex_degrees.get(vertex, 0)
        valid_cycle = (
            boundary_degree == 0 and bool(degrees) and all(degree == 2 for degree in degrees)
        )
        valid_path = (
            boundary_degree == 2
            and degrees.count(1) == 2
            and all(degree in (1, 2) for degree in degrees)
        )
        if link_components != 1 or not (valid_cycle or valid_path):
            _fail("E_INPUT", "mesh.nonmanifold_vertex_link")
    if any(len(fs) > 2 for fs in edges.values()) or any(not fs for fs in vfaces.values()):
        _fail("E_INPUT", "mesh.nonmanifold_or_isolated")
    graph: list[set[int]] = [set() for _ in mesh.faces]
    for fs in edges.values():
        if len(fs) == 2:
            graph[fs[0]].add(fs[1])
            graph[fs[1]].add(fs[0])
    if any(not neighbors for neighbors in graph):
        _fail("E_INPUT", "mesh.isolated_face")
    seen = set()
    comps = 0
    for start in range(len(graph)):
        if start in seen:
            continue
        comps += 1
        seen.add(start)
        q = deque([start])
        while q:
            for nxt in graph[q.popleft()]:
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
    boundary = sum(1 for fs in edges.values() if len(fs) == 1)
    chi = len(vfaces) - len(edges) + len(mesh.faces)
    closed_components = sum(
        1
        for component in _face_components(graph)
        if not any(
            len(incidents) == 1 and incidents[0] in component for incidents in edges.values()
        )
    )
    orientable = _orientable(mesh.faces, edges)
    b2 = closed_components if orientable else 0
    b0 = comps
    b1 = b0 + b2 - chi
    if b1 < 0:
        _fail("E_INPUT", "mesh.invalid_euler_betti_relation")
    return {
        "components": comps,
        "boundary_edges": boundary,
        "euler_characteristic": chi,
        "betti_0": b0,
        "betti_1": b1,
        "betti_2": b2,
        "orientable": orientable,
        "vertices": len(vfaces),
        "edges": len(edges),
        "faces": len(mesh.faces),
    }


def _face_components(graph: list[set[int]]) -> list[set[int]]:
    components: list[set[int]] = []
    seen: set[int] = set()
    for start in range(len(graph)):
        if start in seen:
            continue
        component = {start}
        seen.add(start)
        queue = deque([start])
        while queue:
            for neighbor in graph[queue.popleft()]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return components


def _graph_component_count(graph: dict[int, set[int]]) -> int:
    seen: set[int] = set()
    count = 0
    for start in graph:
        if start in seen:
            continue
        count += 1
        seen.add(start)
        queue = deque([start])
        while queue:
            for neighbor in graph[queue.popleft()]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
    return count


def _orientable(faces: tuple[Face, ...], edge_faces: dict[tuple[int, int], list[int]]) -> bool:
    constraints: list[list[tuple[int, int]]] = [[] for _ in faces]
    for edge, incident in edge_faces.items():
        if len(incident) != 2:
            continue
        first, second = incident
        first_direction = _directed_edge(faces[first], edge)
        second_direction = _directed_edge(faces[second], edge)
        flip_parity = int(first_direction == second_direction)
        constraints[first].append((second, flip_parity))
        constraints[second].append((first, flip_parity))
    assigned: dict[int, int] = {}
    for start in range(len(faces)):
        if start in assigned:
            continue
        assigned[start] = 0
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for neighbor, parity in constraints[current]:
                expected = assigned[current] ^ parity
                if neighbor in assigned and assigned[neighbor] != expected:
                    return False
                if neighbor not in assigned:
                    assigned[neighbor] = expected
                    queue.append(neighbor)
    return True


def _directed_edge(face: Face, edge: tuple[int, int]) -> tuple[int, int]:
    for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
        if tuple(sorted((start, end))) == edge:
            return (start, end)
    _fail("E_INTERNAL", "topology.edge_incidence_mismatch")


def _silhouette_plan(
    mesh: DecodedIndexedTriangleMesh,
    bounding_meshes: tuple[DecodedIndexedTriangleMesh, ...],
    resolution: int,
) -> tuple[
    list[tuple[int, int, float, float, float, float, list[tuple[Face, int, int, int, int]]]], int
]:
    axes = ((0, 1), (0, 2), (1, 2))
    plans = []
    bound_vertices = tuple(
        vertex for bound_mesh in bounding_meshes for vertex in bound_mesh.vertices_mm
    )
    vertices = mesh.vertices_mm
    for x, y in axes:
        xmin, xmax = min(v[x] for v in bound_vertices), max(v[x] for v in bound_vertices)
        ymin, ymax = min(v[y] for v in bound_vertices), max(v[y] for v in bound_vertices)
        sx = (xmax - xmin) / resolution or 1.0
        sy = (ymax - ymin) / resolution or 1.0
        face_cells = []
        for face in mesh.faces:
            pts = [vertices[i] for i in face]
            lo_x = max(0, int((min(p[x] for p in pts) - xmin) / sx))
            hi_x = min(resolution - 1, int((max(p[x] for p in pts) - xmin) / sx))
            lo_y = max(0, int((min(p[y] for p in pts) - ymin) / sy))
            hi_y = min(resolution - 1, int((max(p[y] for p in pts) - ymin) / sy))
            face_cells.append((face, lo_x, hi_x, lo_y, hi_y))
        plans.append((x, y, xmin, ymin, sx, sy, face_cells))
    required = sum(
        max(0, hi_x - lo_x + 1) * max(0, hi_y - lo_y + 1)
        for _, _, _, _, _, _, faces in plans
        for _, lo_x, hi_x, lo_y, hi_y in faces
    )
    return plans, required


def _rasterize_silhouette(
    mesh: DecodedIndexedTriangleMesh,
    plans: list[tuple[int, int, float, float, float, float, list[tuple[Face, int, int, int, int]]]],
) -> dict[str, set[tuple[int, int]]]:
    out: dict[str, set[tuple[int, int]]] = {}
    vertices = mesh.vertices_mm
    for axis, plan in enumerate(plans):
        x, y, xmin, ymin, sx, sy, face_cells = plan
        covered = set()
        for face, lo_x, hi_x, lo_y, hi_y in face_cells:
            pts = [vertices[i] for i in face]
            # Conservative fixed cell-center coverage by projected triangle.
            a, b, c = ((p[x], p[y]) for p in pts)
            den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if den == 0:
                continue
            for ix in range(lo_x, hi_x + 1):
                for iy in range(lo_y, hi_y + 1):
                    px = xmin + (ix + 0.5) * sx
                    py = ymin + (iy + 0.5) * sy
                    u = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / den
                    v = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / den
                    if u >= 0 and v >= 0 and u + v <= 1:
                        covered.add((ix, iy))
        out["XYZ"[axis]] = covered
    return out


def _section(mesh: DecodedIndexedTriangleMesh, z: float) -> tuple[list[SectionSegment], str]:
    plane = Fraction(z)
    segments: set[SectionSegment] = set()
    for face in mesh.faces:
        tri = [tuple(Fraction(value) for value in mesh.vertices_mm[i]) for i in face]
        if any(vertex[2] == plane for vertex in tri):
            return [], "INDETERMINATE"
        hits: set[RationalPoint] = set()
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            if (a[2] < plane < b[2]) or (b[2] < plane < a[2]):
                t = (plane - a[2]) / (b[2] - a[2])
                hits.add((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        if len(hits) == 2:
            first, second = sorted(hits)
            segments.add((first, second))
    if not segments:
        return [], "EMPTY"
    adjacency: dict[RationalPoint, list[RationalPoint]] = defaultdict(list)
    for first, second in segments:
        adjacency[first].append(second)
        adjacency[second].append(first)
    if any(len(neighbors) != 2 for neighbors in adjacency.values()):
        return sorted(segments), "INDETERMINATE"
    visited: set[RationalPoint] = set()
    loops = 0
    for start in sorted(adjacency):
        if start in visited:
            continue
        loops += 1
        stack: list[RationalPoint] = [start]
        visited.add(start)
        while stack:
            for following in adjacency[stack.pop()]:
                if following not in visited:
                    visited.add(following)
                    stack.append(following)
    return sorted(segments), "CLOSED_SINGLE_LOOP" if loops == 1 else "INDETERMINATE"


def _section_area(segments: list[SectionSegment]) -> float:
    adjacency: dict[RationalPoint, list[RationalPoint]] = defaultdict(list)
    for first, second in segments:
        adjacency[first].append(second)
        adjacency[second].append(first)
    start = min(adjacency)
    path = [start]
    previous: RationalPoint | None = None
    current = start
    while True:
        choices = sorted(point for point in adjacency[current] if point != previous)
        following = choices[0]
        if following == start:
            break
        path.append(following)
        previous, current = current, following
    twice = sum(
        path[index][0] * path[(index + 1) % len(path)][1]
        - path[index][1] * path[(index + 1) % len(path)][0]
        for index in range(len(path))
    )
    return float(abs(twice)) / 2


def _point_segment_distance(point: Point, segment: SectionSegment) -> float:
    first_r, second_r = segment
    first: Point = (float(first_r[0]), float(first_r[1]), 0.0)
    second: Point = (float(second_r[0]), float(second_r[1]), 0.0)
    direction = _sub(second, first)
    denominator = _dot(direction, direction)
    if denominator <= 0:
        _fail("E_INPUT", "section.zero_length_segment_after_binary64_conversion")
    t = max(0.0, min(1.0, _dot(_sub(point, first), direction) / denominator))
    projection: Point = (
        first[0] + t * direction[0],
        first[1] + t * direction[1],
        first[2] + t * direction[2],
    )
    return sqrt(_dot(_sub(point, projection), _sub(point, projection)))


def _section_samples(segments: list[SectionSegment]) -> tuple[list[Point], list[float]]:
    points: list[Point] = []
    weights: list[float] = []
    for first_r, second_r in segments:
        first = (float(first_r[0]), float(first_r[1]), 0.0)
        second = (float(second_r[0]), float(second_r[1]), 0.0)
        middle: Point = (
            (first[0] + second[0]) / 2,
            (first[1] + second[1]) / 2,
            (first[2] + second[2]) / 2,
        )
        length = sqrt(_dot(_sub(second, first), _sub(second, first)))
        if length <= 0:
            _fail("E_INPUT", "section.zero_length_segment_after_binary64_conversion")
        points.extend((first, middle, second))
        weights.extend((length / 3, length / 3, length / 3))
    return points, weights


def _section_metric(
    predicted: list[SectionSegment],
    predicted_state: str,
    target: list[SectionSegment],
    target_state: str,
    characteristic_length: float,
    budget: int,
    predicted_area_applicable: bool,
    target_area_applicable: bool,
) -> tuple[dict[str, JSONValue], int]:
    if predicted_state == "INDETERMINATE" or target_state == "INDETERMINATE":
        return {"status": "INDETERMINATE", "error_normalized": None}, 0
    if predicted_state == target_state == "EMPTY":
        return {"status": "NOT_APPLICABLE", "error_normalized": None}, 0
    if predicted_state == "EMPTY" or target_state == "EMPTY":
        return {"status": "FAIL", "error_normalized": 1.0}, 0
    if predicted_state != "CLOSED_SINGLE_LOOP" or target_state != "CLOSED_SINGLE_LOOP":
        return {"status": "INDETERMINATE", "error_normalized": None}, 0
    if predicted_area_applicable != target_area_applicable:
        return {
            "status": "INDETERMINATE",
            "error_normalized": None,
            "reason": "section_area_comparison_requires_both_surfaces_genus_zero",
        }, 0
    predicted_points, predicted_weights = _section_samples(predicted)
    target_points, target_weights = _section_samples(target)
    queries = len(predicted_points) * len(target) + len(target_points) * len(predicted)
    if queries > budget:
        _fail("E_SEARCH_BUDGET", "section_distance_queries_budget_exhausted_before_work")
    forward = [
        min(_point_segment_distance(point, segment) for segment in target)
        for point in predicted_points
    ]
    reverse = [
        min(_point_segment_distance(point, segment) for segment in predicted)
        for point in target_points
    ]
    mean = (
        _weighted_mean(forward, predicted_weights) + _weighted_mean(reverse, target_weights)
    ) / (2 * characteristic_length)
    percentile = (
        max(
            _weighted_percentile(forward, predicted_weights, 95),
            _weighted_percentile(reverse, target_weights, 95),
        )
        / characteristic_length
    )
    area_predicted = _section_area(predicted) if predicted_area_applicable else None
    area_target = _section_area(target) if target_area_applicable else None
    area_error = (
        abs(area_predicted - area_target) / max(area_target, characteristic_length**2 * 1e-12)
        if area_predicted is not None and area_target is not None
        else None
    )
    error = max(mean, percentile, area_error if area_error is not None else 0.0)
    return {
        "status": "COMPUTED",
        "error_normalized": error,
        "mean_contour_distance_normalized": mean,
        "sampled_hausdorff_p95_normalized": percentile,
        "predicted_area_mm2": area_predicted,
        "target_area_mm2": area_target,
        "relative_area_error": area_error,
        "area_status": "COMPUTED" if area_error is not None else "INDETERMINATE_TOPOLOGY",
        "samples_per_segment": 3,
        "sampling_rule": "SEGMENT_ENDPOINTS_AND_MIDPOINT_LENGTH_WEIGHTED_V1",
        "sampling_coverage_bound_mm": max(
            _section_segment_length(segment) for segment in predicted + target
        )
        / 4,
    }, queries


def _section_segment_length(segment: SectionSegment) -> float:
    first, second = segment
    dx = float(second[0] - first[0])
    dy = float(second[1] - first[1])
    return sqrt(dx * dx + dy * dy)


def _compare_geometry(
    predicted_mesh: object, target_mesh: object, policy: object
) -> dict[str, JSONValue]:
    """Compare explicit-frame meshes; return a canonical-hashed hypothesis diagnostic."""
    p = _policy(policy)
    frame = p.coordinate_frame_id
    predicted = _mesh(predicted_mesh, frame)
    target = _mesh(target_mesh, frame)
    for landmark in p.landmarks:
        if landmark.predicted_vertex_index >= len(predicted.vertices_mm):
            _fail("E_REFERENCE", "landmark.predicted_vertex_index_out_of_mesh_bounds")
    for mesh in (predicted, target):
        if len(mesh.vertices_mm) > p.max_vertices:
            _fail("E_SEARCH_BUDGET", "vertex_budget_exhausted_before_work")
        if len(mesh.faces) > p.max_faces:
            _fail("E_SEARCH_BUDGET", "face_budget_exhausted_before_work")
    pt, pa, pn = _face_data(predicted)
    tt, ta, tn = _face_data(target)
    ps, pw, p_face_ids, p_barycentrics = _samples(pt, pa, p.samples_per_face)
    ts, tw, t_face_ids, t_barycentrics = _samples(tt, ta, p.samples_per_face)
    required_broadphase_tests = len(ps) * len(tt) + len(ts) * len(pt)
    if required_broadphase_tests > _MAX_BROADPHASE_TESTS:
        _fail("E_SEARCH_BUDGET", "distance_broadphase_budget_exhausted_before_work")
    predicted_silhouette_plan, predicted_raster_tests = _silhouette_plan(
        predicted, (predicted, target), p.raster_resolution
    )
    target_silhouette_plan, target_raster_tests = _silhouette_plan(
        target, (predicted, target), p.raster_resolution
    )
    if predicted_raster_tests + target_raster_tests > p.max_raster_tests:
        _fail("E_SEARCH_BUDGET", "raster_tests_budget_exhausted_before_work")
    dpt, nearest_target_face_ids, c1, b1 = _nearest(
        ps, tt, p.max_distance_queries, _MAX_BROADPHASE_TESTS
    )
    dtt, nearest_predicted_face_ids, c2, b2 = _nearest(
        ts,
        pt,
        p.max_distance_queries - c1,
        _MAX_BROADPHASE_TESTS - b1,
    )
    length = p.characteristic_length_mm
    chamfer = (_weighted_mean(dpt, pw) + _weighted_mean(dtt, tw)) / (2 * length)
    percentile = max(
        _weighted_percentile(dpt, pw, p.robust_percentile),
        _weighted_percentile(dtt, tw, p.robust_percentile),
    )
    haus = percentile / length
    p_normal_errors = [
        degrees(acos(max(-1.0, min(1.0, _dot(pn[p_face], tn[t_face])))))
        for p_face, t_face in zip(p_face_ids, nearest_target_face_ids, strict=True)
    ]
    t_normal_errors = [
        degrees(acos(max(-1.0, min(1.0, _dot(tn[t_face], pn[p_face])))))
        for t_face, p_face in zip(t_face_ids, nearest_predicted_face_ids, strict=True)
    ]
    normal_mean = (_weighted_mean(p_normal_errors, pw) + _weighted_mean(t_normal_errors, tw)) / 2
    normal_p95 = max(
        _weighted_percentile(p_normal_errors, pw, 95),
        _weighted_percentile(t_normal_errors, tw, 95),
    )
    pred_top = _topology(predicted)
    target_top = _topology(target)
    predicted_curvature = _vertex_gaussian_curvature(predicted, pa, pred_top)
    target_curvature = _vertex_gaussian_curvature(target, ta, target_top)
    curvature = _curvature_comparison(
        predicted_curvature,
        target_curvature,
        ps,
        ts,
        p_face_ids,
        t_face_ids,
        p_barycentrics,
        t_barycentrics,
        nearest_target_face_ids,
        nearest_predicted_face_ids,
        predicted.faces,
        target.faces,
        pt,
        tt,
        pw,
        tw,
        length,
    )
    pred_vol = _volume(predicted, pt)
    target_vol = _volume(target, tt)
    vol_metric = (
        None
        if pred_vol is None or target_vol is None or target_vol == 0
        else abs(pred_vol - target_vol) / abs(target_vol)
    )
    volume_status = (
        "NOT_APPLICABLE"
        if pred_vol is None or target_vol is None
        else "INDETERMINATE"
        if target_vol == 0
        else "COMPUTED"
    )
    views_p = _rasterize_silhouette(predicted, predicted_silhouette_plan)
    views_t = _rasterize_silhouette(target, target_silhouette_plan)
    r1, r2 = predicted_raster_tests, target_raster_tests
    silhouettes: dict[str, float | None] = {}
    for axis in "XYZ":
        union = views_p[axis] | views_t[axis]
        silhouettes[axis] = len(views_p[axis] & views_t[axis]) / len(union) if union else None
    defined_silhouettes = [value for value in silhouettes.values() if value is not None]
    sections: list[JSONValue] = []
    section_error_values: list[float] = []
    section_queries = 0
    section_unknown = False
    section_topology_mismatch = False
    for z in p.section_planes_z_mm:
        predicted_segments, predicted_state = _section(predicted, z)
        target_segments, target_state = _section(target, z)
        result, queries = _section_metric(
            predicted_segments,
            predicted_state,
            target_segments,
            target_state,
            length,
            p.max_distance_queries - c1 - c2 - section_queries,
            pred_top["boundary_edges"] == 0
            and pred_top["components"] == 1
            and pred_top["euler_characteristic"] == 2
            and pred_top["orientable"] is True,
            target_top["boundary_edges"] == 0
            and target_top["components"] == 1
            and target_top["euler_characteristic"] == 2
            and target_top["orientable"] is True,
        )
        section_queries += queries
        if result["status"] == "COMPUTED":
            section_error_values.append(_number(result["error_normalized"]))
        elif result["status"] == "FAIL":
            section_error_values.append(1.0)
            section_topology_mismatch = True
        elif result["status"] == "INDETERMINATE":
            section_unknown = True
        sections.append(
            {
                "z_mm": z,
                "predicted_state": predicted_state,
                "target_state": target_state,
                "predicted_segment_count": len(predicted_segments),
                "target_segment_count": len(target_segments),
                "distance_queries": queries,
                **result,
            }
        )
    landmark_metrics: list[dict[str, JSONValue]] = [
        {
            "name": lm.name,
            "predicted_vertex_index": lm.predicted_vertex_index,
            "predicted_xyz_mm": list(predicted.vertices_mm[lm.predicted_vertex_index]),
            "target_xyz_mm": list(lm.target),
            "distance_mm": sqrt(
                sum(
                    (
                        predicted.vertices_mm[lm.predicted_vertex_index][i] - lm.target[i]
                    ) ** 2
                    for i in range(3)
                )
            ),
            "normalized": sqrt(
                sum(
                    (
                        predicted.vertices_mm[lm.predicted_vertex_index][i] - lm.target[i]
                    ) ** 2
                    for i in range(3)
                )
            ) / length,
        }
        for lm in p.landmarks
    ]
    landmark_status = "COMPUTED" if landmark_metrics else "NO_REQUIRED_LANDMARKS"
    landmark_max_normalized = max(
        (_number(item["normalized"]) for item in landmark_metrics), default=0.0
    )
    silhouette_metrics: dict[str, JSONValue] = dict(silhouettes)
    landmark_json: list[JSONValue] = list(landmark_metrics)
    predicted_topology: dict[str, JSONValue] = {key: value for key, value in pred_top.items()}
    target_topology: dict[str, JSONValue] = {key: value for key, value in target_top.items()}
    metrics: dict[str, JSONValue] = {
        "symmetric_chamfer_normalized": chamfer,
        "robust_hausdorff_normalized": haus,
        "robust_percentile": p.robust_percentile,
        "silhouette_iou_by_view": silhouette_metrics,
        "silhouette_iou_min": min(defined_silhouettes) if len(defined_silhouettes) == 3 else None,
        "silhouette_iou_mean": sum(defined_silhouettes) / 3
        if len(defined_silhouettes) == 3
        else None,
        "surface_normal_mean_degrees": normal_mean,
        "surface_normal_p95_degrees": normal_p95,
        "surface_normal_max_degrees": max(p_normal_errors + t_normal_errors),
        "cross_sections": sections,
        "section_topology_mismatch": section_topology_mismatch,
        "section_error_normalized": (
            1.0
            if 1.0 in section_error_values
            else None
            if section_unknown
            else max(section_error_values, default=None)
        ),
        "relative_volume_error": vol_metric,
        "volume_status": volume_status,
        "landmarks": landmark_json,
        "landmark_status": landmark_status,
        "landmark_max_normalized": landmark_max_normalized,
        "curvature_diagnostics": curvature,
        "curvature_error_normalized": curvature.get("area_weighted_p95_absolute_error_normalized"),
        "topology": {
            "predicted": predicted_topology,
            "target": target_topology,
            "matches": pred_top == target_top,
        },
    }
    evaluations: dict[str, JSONValue] = {}
    for name, threshold in p.hard_thresholds.items():
        value = _metric_value(name, metrics)
        evaluations[name] = {
            "value": value,
            "threshold": threshold.value,
            "operator": ">=" if name == "silhouette_iou_min" else "<=",
            "unit": threshold.unit,
            "owner": threshold.owner,
            "rationale": threshold.rationale,
            "validation_path": threshold.validation_path,
            "status": "FAIL"
            if name == "section_error_normalized" and section_topology_mismatch
            else "INDETERMINATE"
            if value is None
            else (
                "PASS"
                if (
                    value >= threshold.value
                    if name == "silhouette_iou_min"
                    else value <= threshold.value
                )
                else "FAIL"
            ),
        }
    outcomes = [str(v["status"]) for v in evaluations.values() if isinstance(v, dict)]
    failed: list[JSONValue] = [
        k for k, v in evaluations.items() if isinstance(v, dict) and v["status"] == "FAIL"
    ]
    limitations: list[JSONValue] = [
        "sampled surface distances do not certify continuous Hausdorff distance",
        "Gaussian curvature uses discrete angle defect over barycentric dual area",
        "curvature values depend on mesh resolution",
        "section area is reported only for one closed genus-zero contour",
        "diagnostic thresholds are hypotheses",
    ]
    payload: dict[str, JSONValue] = {
        "implementation_version": "geometry-comparison/1.0.0",
        "profile_id": PROFILE,
        "status": "HYPOTHESIS",
        "outcome": "FAIL" if failed else "INDETERMINATE" if "INDETERMINATE" in outcomes else "PASS",
        "verification_claim": "NOT_VERIFIED",
        "physical_status": "UNTESTED",
        "alignment": "IDENTITY_V1",
        "policy": p.raw,
        "policy_sha256": sha256(jcs_bytes(p.raw)).hexdigest(),
        "predicted_mesh_sha256": predicted.source_sha256,
        "target_mesh_sha256": target.source_sha256,
        "metrics": metrics,
        "threshold_evaluations": evaluations,
        "hard_failures": failed,
        "sampling": {
            "rule": "FACE_LOCAL_AREA_UNIFORM_HAMMERSLEY_BARYCENTRIC_V1",
            "samples_per_face": p.samples_per_face,
            "sample_count_predicted": len(ps),
            "sample_count_target": len(ts),
            "max_triangle_edge_mm": max(_edge_length(t) for t in pt + tt),
            "coverage_bound_mm": max(_edge_length(t) for t in pt + tt),
        },
        "work": {
            "distance_queries": c1 + c2 + section_queries,
            "distance_broadphase_tests": b1 + b2,
            "max_distance_broadphase_tests": _MAX_BROADPHASE_TESTS,
            "section_edge_intersection_tests": 3
            * len(p.section_planes_z_mm)
            * (len(predicted.faces) + len(target.faces)),
            "raster_tests": r1 + r2,
            "max_distance_queries": p.max_distance_queries,
            "max_raster_tests": p.max_raster_tests,
        },
        "limitations": limitations,
    }
    payload["sha256"] = sha256(
        b"GEOMETRY_COMPARISON_DIAGNOSTIC_V1\0" + jcs_bytes(payload)
    ).hexdigest()
    return payload


def _metric_value(name: str, metrics: dict[str, JSONValue]) -> float | None:
    if name == "silhouette_iou_min":
        return _metric_float(metrics.get(name))
    if name in metrics and isinstance(metrics[name], (int, float)):
        return _metric_float(metrics[name])
    if name == "topology_match":
        topology = metrics.get("topology")
        return 0.0 if isinstance(topology, dict) and topology.get("matches") is True else 1.0
    if name == "normal_mean_degrees":
        normal_value = metrics.get("surface_normal_mean_degrees")
        return _metric_float(normal_value) if normal_value is not None else None
    if name == "normal_p95_degrees":
        normal_value = metrics.get("surface_normal_p95_degrees")
        return _metric_float(normal_value) if normal_value is not None else None
    if name == "section_error_normalized":
        section_value = metrics.get("section_error_normalized")
        return _metric_float(section_value) if section_value is not None else None
    if name == "curvature_error_normalized":
        curvature = metrics.get("curvature_diagnostics")
        if isinstance(curvature, dict):
            return _metric_float(curvature.get("area_weighted_p95_absolute_error_normalized"))
        return None
    if name == "landmark_max_normalized":
        value = metrics.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        landmarks = metrics.get("landmarks")
        values: list[float] = []
        if isinstance(landmarks, list):
            for item in landmarks:
                if isinstance(item, dict):
                    value = _metric_float(item.get("normalized"))
                    if value is not None:
                        values.append(value)
        return max(values, default=0.0)
    return None


def _edge_length(tri: Triangle) -> float:
    return max(sqrt(_dot(_sub(a, b), _sub(a, b))) for a, b in combinations(tri, 2))


def _volume(mesh: DecodedIndexedTriangleMesh, triangles: list[Triangle]) -> float | None:
    top = _topology(mesh)
    if top["boundary_edges"]:
        return None
    # Supplied winding must be consistent on every interior edge.
    uses = defaultdict(list)
    for f in mesh.faces:
        for edge_start, edge_end in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            uses[tuple(sorted((edge_start, edge_end)))].append((edge_start, edge_end))
    if any(len(u) != 2 or u[0] == u[1] for u in uses.values()):
        return None
    total = 0.0
    for a, b, c in triangles:
        total += _dot(a, _cross(b, c)) / 6
    return total


def compare_geometry(
    predicted_mesh: object, target_mesh: object, policy: object
) -> dict[str, JSONValue]:
    """Compare admitted finite surfaces, returning typed failures for undefined arithmetic."""
    try:
        return _compare_geometry(predicted_mesh, target_mesh, policy)
    except (OverflowError, ZeroDivisionError, CanonicalizationError) as error:
        raise GeometryComparisonError("E_INPUT", "comparison.arithmetic_undefined") from error
