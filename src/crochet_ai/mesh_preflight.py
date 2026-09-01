"""Fail-closed V0 validation for canonical indexed triangle surfaces.

The implementation deliberately uses exact ``Fraction`` arithmetic for signs and
threshold comparisons. Input coordinates are binary64, therefore their exact
rational values are finite and unambiguous. Contact candidates use deterministic
sweep-and-prune broad phase; the required mesh vertex diameter remains O(V^2).
"""

from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeAlias, cast

from .canonical import CanonicalProfile, canonical_hash
from .diagnostics import Diagnostic, FailureCode, ValidationReport
from .schema import artifact_fingerprint, validate_schema

Point: TypeAlias = tuple[float, float, float]
RPoint: TypeAlias = tuple[Fraction, Fraction, Fraction]
Face: TypeAlias = tuple[int, int, int]
Edge: TypeAlias = tuple[int, int]

PROFILE_ID = "v0_num_mesh_binary64_v1"
PROFILE_VERSION = "1.0.0"
PROFILE_HASH = "6d93723875f28f31dd0c36a4b47d26bf5b22c43e5d863cc51980d6edd2af24fc"
PREDICATE_BACKEND = "fraction-exact-binary64/1.0.0"


class PreflightOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"


class ContactKind(StrEnum):
    NONE = "NONE"
    SHARED_VERTEX = "SHARED_VERTEX"
    SHARED_EDGE = "SHARED_EDGE"
    PROPER_INTERSECTION = "PROPER_INTERSECTION"
    VERTEX_FACE_TOUCH = "VERTEX_FACE_TOUCH"
    EDGE_EDGE_TOUCH = "EDGE_EDGE_TOUCH"
    COPLANAR_OVERLAP = "COPLANAR_OVERLAP"
    COINCIDENT_TRIANGLES = "COINCIDENT_TRIANGLES"
    NEAR_CONTACT = "NEAR_CONTACT"


@dataclass(frozen=True, slots=True)
class NumericalGeometryProfile:
    profile_id: str
    profile_version: str
    record_hash: str
    triangle_area2_max: Fraction
    coordinate_distance_max: Fraction
    near_contact_distance_max: Fraction
    volume6_min_exclusive: Fraction
    landmark_slack_max: Fraction


@dataclass(frozen=True, slots=True)
class MeshComponent:
    component_id: int
    vertex_ids: tuple[int, ...]
    face_ids: tuple[int, ...]
    edge_count: int
    boundary_loops: tuple[tuple[int, ...], ...]
    is_closed: bool
    is_manifold: bool
    is_orientable: bool
    is_consistently_oriented: bool
    outward_orientation: str | None
    normalized_volume6: float | None


@dataclass(frozen=True, slots=True)
class MeshPreflightResult:
    outcome: PreflightOutcome
    domain_profile_id: str | None
    numerical_profile_id: str | None
    numerical_profile_version: str | None
    numerical_profile_hash: str | None
    canonical_mesh_hash: str | None
    characteristic_scale_mm: float | None
    components: tuple[MeshComponent, ...]
    diagnostics: tuple[Diagnostic, ...]
    predicate_backend: str = PREDICATE_BACKEND
    normalization_events: tuple[str, ...] = ()
    evidence: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def accepted(self) -> bool:
        return self.outcome == PreflightOutcome.PASS


@dataclass(frozen=True, slots=True)
class _Mesh:
    vertices: tuple[Point, ...]
    faces: tuple[Face, ...]
    frame_id: str

    def as_json(self) -> dict[str, Any]:
        return {
            "representation_version": "INDEXED_TRIANGLE_MESH_V1",
            "coordinate_system": {
                "length_unit": "MILLIMETER",
                "handedness": "RIGHT_HANDED",
                "coordinate_frame_id": self.frame_id,
            },
            "vertices": [{"position_mm": list(point)} for point in self.vertices],
            "faces": [{"vertex_indices": list(face)} for face in self.faces],
        }


def _fraction(value: float) -> Fraction:
    return Fraction.from_float(value)


def _rpoint(point: Point) -> RPoint:
    return (_fraction(point[0]), _fraction(point[1]), _fraction(point[2]))


def _sub(a: RPoint, b: RPoint) -> RPoint:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: RPoint, b: RPoint) -> RPoint:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: RPoint, scalar: Fraction) -> RPoint:
    return (a[0] * scalar, a[1] * scalar, a[2] * scalar)


def _dot(a: RPoint, b: RPoint) -> Fraction:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: RPoint, b: RPoint) -> RPoint:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm2(a: RPoint) -> Fraction:
    return _dot(a, a)


def _edge(a: int, b: int) -> Edge:
    return (a, b) if a < b else (b, a)


def _directed_edges(face: Face) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    return ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))


def _triangle_area2(vertices: Sequence[Point], face: Face) -> Fraction:
    a, b, c = (_rpoint(vertices[index]) for index in face)
    return _norm2(_cross(_sub(b, a), _sub(c, a)))


def _point_on_triangle(point: RPoint, triangle: tuple[RPoint, RPoint, RPoint]) -> tuple[bool, bool]:
    """Return (inside including boundary, strictly interior) on the triangle plane."""
    a, b, c = triangle
    normal = _cross(_sub(b, a), _sub(c, a))
    if _dot(normal, _sub(point, a)) != 0:
        return False, False
    uu = _dot(_sub(b, a), _sub(b, a))
    uv = _dot(_sub(b, a), _sub(c, a))
    vv = _dot(_sub(c, a), _sub(c, a))
    wu = _dot(_sub(point, a), _sub(b, a))
    wv = _dot(_sub(point, a), _sub(c, a))
    determinant = uu * vv - uv * uv
    if determinant == 0:
        return False, False
    beta = (wu * vv - wv * uv) / determinant
    gamma = (wv * uu - wu * uv) / determinant
    alpha = 1 - beta - gamma
    inside = alpha >= 0 and beta >= 0 and gamma >= 0
    return inside, inside and alpha > 0 and beta > 0 and gamma > 0


def _point_segment_distance2(point: RPoint, a: RPoint, b: RPoint) -> Fraction:
    direction = _sub(b, a)
    denominator = _norm2(direction)
    if denominator == 0:
        return _norm2(_sub(point, a))
    parameter = _dot(_sub(point, a), direction) / denominator
    parameter = max(Fraction(0), min(Fraction(1), parameter))
    return _norm2(_sub(point, _add(a, _mul(direction, parameter))))


def _segment_segment_distance2(a: RPoint, b: RPoint, c: RPoint, d: RPoint) -> Fraction:
    u, v, w = _sub(b, a), _sub(d, c), _sub(a, c)
    aa, bb, cc = _dot(u, u), _dot(u, v), _dot(v, v)
    dd, ee = _dot(u, w), _dot(v, w)
    denominator = aa * cc - bb * bb
    if denominator == 0:
        return min(
            _point_segment_distance2(a, c, d),
            _point_segment_distance2(b, c, d),
            _point_segment_distance2(c, a, b),
            _point_segment_distance2(d, a, b),
        )
    s = (bb * ee - cc * dd) / denominator
    t = (aa * ee - bb * dd) / denominator
    if s < 0 or s > 1 or t < 0 or t > 1:
        return min(
            _point_segment_distance2(a, c, d),
            _point_segment_distance2(b, c, d),
            _point_segment_distance2(c, a, b),
            _point_segment_distance2(d, a, b),
        )
    return _norm2(_sub(_add(a, _mul(u, s)), _add(c, _mul(v, t))))


def _point_triangle_distance2(point: RPoint, triangle: tuple[RPoint, RPoint, RPoint]) -> Fraction:
    a, b, c = triangle
    normal = _cross(_sub(b, a), _sub(c, a))
    normal2 = _norm2(normal)
    if normal2 != 0:
        projected = _sub(point, _mul(normal, _dot(_sub(point, a), normal) / normal2))
        inside, _ = _point_on_triangle(projected, triangle)
        if inside:
            return _norm2(_sub(point, projected))
    return min(
        _point_segment_distance2(point, a, b),
        _point_segment_distance2(point, b, c),
        _point_segment_distance2(point, c, a),
    )


def _triangle_distance2(
    first: tuple[RPoint, RPoint, RPoint], second: tuple[RPoint, RPoint, RPoint]
) -> Fraction:
    candidates = [_point_triangle_distance2(point, second) for point in first]
    candidates.extend(_point_triangle_distance2(point, first) for point in second)
    first_edges = ((first[0], first[1]), (first[1], first[2]), (first[2], first[0]))
    second_edges = ((second[0], second[1]), (second[1], second[2]), (second[2], second[0]))
    candidates.extend(
        _segment_segment_distance2(a, b, c, d) for a, b in first_edges for c, d in second_edges
    )
    return min(candidates)


def _within_landmark_threshold(
    distance2: Fraction,
    tolerance: Fraction,
    slack: Fraction,
    scale2: Fraction,
) -> bool:
    """Exactly decide d <= tolerance + slack * sqrt(scale2) without sqrt."""
    if distance2 <= tolerance * tolerance:
        return True
    if tolerance == 0:
        return distance2 <= slack * slack * scale2
    residual = distance2 - tolerance * tolerance - slack * slack * scale2
    if residual <= 0:
        return True
    return residual * residual <= 4 * tolerance * tolerance * slack * slack * scale2


def _axis_may_be_within(first_max: float, second_min: float, limit2: Fraction) -> bool:
    if first_max >= second_min:
        return True
    delta = _fraction(second_min) - _fraction(first_max)
    return delta * delta <= limit2


def _boxes_may_be_within(
    first: tuple[float, float, float, float, float, float, int],
    second: tuple[float, float, float, float, float, float, int],
    limit2: Fraction,
) -> bool:
    return (
        _axis_may_be_within(first[1], second[0], limit2)
        and _axis_may_be_within(second[1], first[0], limit2)
        and _axis_may_be_within(first[3], second[2], limit2)
        and _axis_may_be_within(second[3], first[2], limit2)
        and _axis_may_be_within(first[5], second[4], limit2)
        and _axis_may_be_within(second[5], first[4], limit2)
    )


def _projection_axis(normal: RPoint) -> int:
    return max(range(3), key=lambda index: abs(normal[index]))


def _p2(point: RPoint, axis: int) -> tuple[Fraction, Fraction]:
    values = [point[index] for index in range(3) if index != axis]
    return values[0], values[1]


def _orient2(
    a: tuple[Fraction, Fraction], b: tuple[Fraction, Fraction], c: tuple[Fraction, Fraction]
) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment2(
    point: tuple[Fraction, Fraction], a: tuple[Fraction, Fraction], b: tuple[Fraction, Fraction]
) -> bool:
    return (
        _orient2(a, b, point) == 0
        and min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= point[1] <= max(a[1], b[1])
    )


def _segments_intersect2(
    a: tuple[Fraction, Fraction],
    b: tuple[Fraction, Fraction],
    c: tuple[Fraction, Fraction],
    d: tuple[Fraction, Fraction],
) -> tuple[bool, bool]:
    """Return (intersects, proper crossing)."""
    ab_c, ab_d = _orient2(a, b, c), _orient2(a, b, d)
    cd_a, cd_b = _orient2(c, d, a), _orient2(c, d, b)
    if ab_c == 0 and ab_d == 0 and cd_a == 0 and cd_b == 0:
        overlap_x = max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0]))
        overlap_y = max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1]))
        return overlap_x and overlap_y, False
    proper = (ab_c > 0) != (ab_d > 0) and (cd_a > 0) != (cd_b > 0)
    if proper:
        return True, True
    return any(
        (_on_segment2(c, a, b), _on_segment2(d, a, b), _on_segment2(a, c, d), _on_segment2(b, c, d))
    ), False


def _point_in_triangle2(
    point: tuple[Fraction, Fraction], triangle: tuple[tuple[Fraction, Fraction], ...]
) -> tuple[bool, bool]:
    signs = [_orient2(triangle[index], triangle[(index + 1) % 3], point) for index in range(3)]
    inside = all(sign >= 0 for sign in signs) or all(sign <= 0 for sign in signs)
    return inside, inside and all(sign != 0 for sign in signs)


def _coplanar_relation(
    first: tuple[RPoint, RPoint, RPoint], second: tuple[RPoint, RPoint, RPoint]
) -> ContactKind:
    axis = _projection_axis(_cross(_sub(first[1], first[0]), _sub(first[2], first[0])))
    one, two = (
        tuple(_p2(point, axis) for point in first),
        tuple(_p2(point, axis) for point in second),
    )
    if set(one) == set(two):
        return ContactKind.COINCIDENT_TRIANGLES
    for point in one:
        inside, strict = _point_in_triangle2(point, two)
        if inside:
            return ContactKind.COPLANAR_OVERLAP if strict else ContactKind.VERTEX_FACE_TOUCH
    for point in two:
        inside, strict = _point_in_triangle2(point, one)
        if inside:
            return ContactKind.COPLANAR_OVERLAP if strict else ContactKind.VERTEX_FACE_TOUCH
    saw_touch = False
    for index in range(3):
        for other in range(3):
            intersects, proper = _segments_intersect2(
                one[index], one[(index + 1) % 3], two[other], two[(other + 1) % 3]
            )
            if proper:
                return ContactKind.COPLANAR_OVERLAP
            saw_touch = saw_touch or intersects
    return ContactKind.EDGE_EDGE_TOUCH if saw_touch else ContactKind.NONE


def _segment_triangle_points(
    a: RPoint, b: RPoint, triangle: tuple[RPoint, RPoint, RPoint]
) -> set[RPoint]:
    normal = _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0]))
    da, db = _dot(normal, _sub(a, triangle[0])), _dot(normal, _sub(b, triangle[0]))
    points: set[RPoint] = set()
    if da == 0:
        inside, _ = _point_on_triangle(a, triangle)
        if inside:
            points.add(a)
    if db == 0:
        inside, _ = _point_on_triangle(b, triangle)
        if inside:
            points.add(b)
    if da * db < 0:
        point = _add(a, _mul(_sub(b, a), -da / (db - da)))
        inside, _ = _point_on_triangle(point, triangle)
        if inside:
            points.add(point)
    return points


def _triangle_relation(
    first: tuple[RPoint, RPoint, RPoint], second: tuple[RPoint, RPoint, RPoint], shared: int
) -> ContactKind:
    n1, n2 = (
        _cross(_sub(first[1], first[0]), _sub(first[2], first[0])),
        _cross(_sub(second[1], second[0]), _sub(second[2], second[0])),
    )
    coplanar = (
        _cross(n1, n2) == (Fraction(0), Fraction(0), Fraction(0))
        and _dot(n1, _sub(second[0], first[0])) == 0
    )
    if coplanar:
        relation = _coplanar_relation(first, second)
    else:
        points: set[RPoint] = set()
        for triangle, other in ((first, second), (second, first)):
            for index in range(3):
                points.update(
                    _segment_triangle_points(triangle[index], triangle[(index + 1) % 3], other)
                )
        if not points:
            relation = ContactKind.NONE
        else:
            interiors = [
                _point_on_triangle(point, first)[1] and _point_on_triangle(point, second)[1]
                for point in points
            ]
            relation = (
                ContactKind.PROPER_INTERSECTION if any(interiors) else ContactKind.EDGE_EDGE_TOUCH
            )
    if relation == ContactKind.NONE:
        return relation
    if shared == 2 and relation in {ContactKind.EDGE_EDGE_TOUCH, ContactKind.VERTEX_FACE_TOUCH}:
        return ContactKind.SHARED_EDGE
    if shared == 1 and relation in {ContactKind.EDGE_EDGE_TOUCH, ContactKind.VERTEX_FACE_TOUCH}:
        return ContactKind.SHARED_VERTEX
    return relation


class _Collector:
    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint
        self.items: list[Diagnostic] = []
        self.indeterminate = False

    def add(
        self,
        code: FailureCode,
        key: str,
        summary: str,
        *,
        refs: Iterable[str] = (),
        expected: object = None,
        observed: object = None,
        units: str | None = None,
        indeterminate: bool = False,
    ) -> None:
        self.indeterminate = self.indeterminate or indeterminate
        self.items.append(
            Diagnostic(
                code=code,
                gate="V0",
                message_key=key,
                summary=summary,
                artifact_hash=self.fingerprint,
                entity_refs=tuple(refs),
                expected=expected,
                observed=observed,
                units=units,
                tolerance_profile_id=PROFILE_ID,
            )
        )

    def report(self) -> ValidationReport:
        return ValidationReport.from_iterable(self.items)


def resolve_numerical_profile(profile_id: str) -> NumericalGeometryProfile:
    if profile_id != PROFILE_ID:
        raise ValueError("geometry.numeric_profile_unresolved")
    path = Path(__file__).resolve().parents[2] / "profiles" / "v0-mesh-numeric-profile-1.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("geometry.numeric_profile_unresolved") from error
    if not validate_schema("numerical_geometry_profile", value).ok:
        raise ValueError("geometry.numeric_profile_unresolved")
    digest = canonical_hash(value, CanonicalProfile.NUMERICAL_GEOMETRY_PROFILE)
    if digest != PROFILE_HASH or value["profile_version"] != PROFILE_VERSION:
        raise ValueError("geometry.numeric_profile_unresolved")
    thresholds = value["thresholds"]
    return NumericalGeometryProfile(
        profile_id,
        PROFILE_VERSION,
        digest,
        *(
            _fraction(thresholds[key]["value"])
            for key in (
                "triangle_area2_normalized_max",
                "coordinate_distance_normalized_max",
                "near_contact_distance_normalized_max",
                "volume6_normalized_min_exclusive",
                "landmark_numeric_slack_normalized_max",
            )
        ),
    )


class MeshPreflightValidator:
    """Independent V0 verifier; it does not mutate caller geometry or repair meshes."""

    def preflight(
        self, mesh_value: Mapping[str, Any], design_spec: Mapping[str, Any]
    ) -> MeshPreflightResult:
        fingerprint = artifact_fingerprint(mesh_value)
        collector = _Collector(fingerprint)
        target = design_spec.get("target_geometry")
        if not isinstance(target, Mapping) or target.get("geometry_type") != "MESH_3D":
            collector.add(
                FailureCode.UNSUPPORTED_FEATURE,
                "geometry.domain_not_mesh",
                "V0 accepts only a Mesh_3D DesignSpec target",
            )
            return self._result(collector, None, None, (), None, None)
        profile_id = cast(str, target.get("preflight_profile_id"))
        numeric_id = cast(str, target.get("preflight_numerical_profile_id"))
        try:
            numeric = resolve_numerical_profile(numeric_id)
        except ValueError:
            collector.add(
                FailureCode.INPUT,
                "geometry.numeric_profile_unresolved",
                "The declared numerical profile cannot be resolved or hash-verified",
                observed=numeric_id,
                indeterminate=True,
            )
            return self._result(collector, profile_id, None, (), None, None)
        schema = validate_schema("indexed_triangle_mesh", cast(Any, mesh_value))
        if not schema.ok:
            for diagnostic in schema.diagnostics:
                collector.add(
                    FailureCode.INPUT, "geometry.invalid_canonical_mesh", diagnostic.summary
                )
            return self._result(collector, profile_id, numeric, (), None, None)
        mesh = self._mesh(mesh_value)
        for face_index, face in enumerate(mesh.faces):
            if len(set(face)) != 3:
                collector.add(
                    FailureCode.INPUT,
                    "geometry.degenerate_face",
                    "Triangle repeats a vertex identity",
                    refs=(f"face:{face_index}",),
                )
            if any(vertex < 0 or vertex >= len(mesh.vertices) for vertex in face):
                collector.add(
                    FailureCode.INPUT,
                    "geometry.invalid_index",
                    "Triangle vertex index is out of range",
                    refs=(f"face:{face_index}",),
                )
        if collector.items:
            return self._result(collector, profile_id, numeric, (), None, None)
        if mesh.frame_id != target["coordinate_frame"]["coordinate_frame_id"]:
            collector.add(
                FailureCode.INPUT,
                "geometry.coordinate_frame_mismatch",
                "Mesh coordinate frame must equal the DesignSpec frame",
                expected=target["coordinate_frame"]["coordinate_frame_id"],
                observed=mesh.frame_id,
            )
        canonical, events = self._canonicalize(mesh)
        mesh_hash = canonical_hash(canonical.as_json(), CanonicalProfile.INDEXED_TRIANGLE_MESH)
        collector.fingerprint = mesh_hash
        components, scale2 = self._topology_and_geometry(canonical, numeric, collector)
        inverted = [
            component
            for component in components
            if component.is_closed and component.outward_orientation == "INVERTED"
        ]
        if inverted and not collector.items:
            canonical = self._reverse_closed_components(canonical, inverted)
            events = (*events, "reverse_reliably_inverted_closed_component_v1")
            mesh_hash = canonical_hash(canonical.as_json(), CanonicalProfile.INDEXED_TRIANGLE_MESH)
            collector.fingerprint = mesh_hash
            components, scale2 = self._topology_and_geometry(canonical, numeric, collector)
        self._validate_domain(
            canonical, design_spec, profile_id, numeric, components, scale2, collector
        )
        return self._result(collector, profile_id, numeric, components, scale2, mesh_hash, events)

    @staticmethod
    def _mesh(value: Mapping[str, Any]) -> _Mesh:
        vertices = tuple(
            tuple(cast(float, coordinate) for coordinate in item["position_mm"])
            for item in value["vertices"]
        )
        faces = tuple(
            tuple(cast(int, index) for index in item["vertex_indices"]) for item in value["faces"]
        )
        return _Mesh(
            cast(tuple[Point, ...], vertices),
            cast(tuple[Face, ...], faces),
            cast(str, value["coordinate_system"]["coordinate_frame_id"]),
        )

    @staticmethod
    def _canonicalize(mesh: _Mesh) -> tuple[_Mesh, tuple[str, ...]]:
        order = sorted(range(len(mesh.vertices)), key=lambda index: mesh.vertices[index])
        remap = {old: new for new, old in enumerate(order)}
        vertices = tuple(mesh.vertices[index] for index in order)
        faces = []
        for face in mesh.faces:
            mapped = tuple(remap[index] for index in face)
            pivot = mapped.index(min(mapped))
            faces.append(cast(Face, mapped[pivot:] + mapped[:pivot]))
        return _Mesh(vertices, tuple(sorted(faces)), mesh.frame_id), (
            "canonical_vertex_face_order_v1",
        )

    @staticmethod
    def _reverse_closed_components(mesh: _Mesh, components: Sequence[MeshComponent]) -> _Mesh:
        faces = list(mesh.faces)
        for component in components:
            for face_id in component.face_ids:
                a, b, c = faces[face_id]
                reversed_face = (a, c, b)
                pivot = reversed_face.index(min(reversed_face))
                faces[face_id] = cast(Face, reversed_face[pivot:] + reversed_face[:pivot])
        return _Mesh(mesh.vertices, tuple(sorted(faces)), mesh.frame_id)

    def _topology_and_geometry(
        self, mesh: _Mesh, profile: NumericalGeometryProfile, collector: _Collector
    ) -> tuple[tuple[MeshComponent, ...], Fraction | None]:
        if not mesh.vertices or not mesh.faces:
            collector.add(
                FailureCode.INPUT,
                "geometry.empty_mesh",
                "V0 mesh vertices and faces must both be non-empty",
            )
            return (), None
        for index, face in enumerate(mesh.faces):
            if len(set(face)) != 3:
                collector.add(
                    FailureCode.INPUT,
                    "geometry.degenerate_face",
                    "Triangle repeats a vertex identity",
                    refs=(f"face:{index}",),
                )
            if any(vertex < 0 or vertex >= len(mesh.vertices) for vertex in face):
                collector.add(
                    FailureCode.INPUT,
                    "geometry.invalid_index",
                    "Triangle vertex index is out of range",
                    refs=(f"face:{index}",),
                )
        if collector.items:
            return (), None
        positions: dict[Point, int] = {}
        for index, point in enumerate(mesh.vertices):
            if point in positions:
                collector.add(
                    FailureCode.INPUT,
                    "geometry.coincident_vertex",
                    "Distinct vertex identities have exactly equal coordinates",
                    refs=(f"vertex:{positions[point]}", f"vertex:{index}"),
                )
            positions[point] = index
        scale2 = max(
            (
                _norm2(_sub(_rpoint(a), _rpoint(b)))
                for index, a in enumerate(mesh.vertices)
                for b in mesh.vertices[index + 1 :]
            ),
            default=Fraction(0),
        )
        if scale2 == 0:
            collector.add(
                FailureCode.INPUT,
                "geometry.zero_characteristic_scale",
                "Mesh vertex diameter must be positive",
            )
            return (), None
        edge_faces: dict[Edge, list[tuple[int, tuple[int, int]]]] = defaultdict(list)
        referenced: set[int] = set()
        face_sets: dict[tuple[int, int, int], int] = {}
        for face_index, face in enumerate(mesh.faces):
            key = cast(tuple[int, int, int], tuple(sorted(face)))
            if key in face_sets:
                collector.add(
                    FailureCode.INPUT,
                    "geometry.duplicate_face",
                    "Duplicate or reversed-duplicate triangle identities are forbidden",
                    refs=(f"face:{face_sets[key]}", f"face:{face_index}"),
                )
            face_sets[key] = face_index
            referenced.update(face)
            for directed in _directed_edges(face):
                edge_faces[_edge(*directed)].append((face_index, directed))
            area2 = _triangle_area2(mesh.vertices, face)
            if (
                area2 == 0
                or area2
                <= profile.triangle_area2_max * profile.triangle_area2_max * scale2 * scale2
            ):
                collector.add(
                    FailureCode.INPUT,
                    "geometry.degenerate_face",
                    "Triangle area is zero or at/below the profile threshold",
                    refs=(f"face:{face_index}",),
                )
        for vertex in range(len(mesh.vertices)):
            if vertex not in referenced:
                collector.add(
                    FailureCode.INPUT,
                    "geometry.isolated_vertex",
                    "A vertex is not referenced by any face",
                    refs=(f"vertex:{vertex}",),
                )
        for face_index, face in enumerate(mesh.faces):
            if all(len(edge_faces[_edge(*directed)]) == 1 for directed in _directed_edges(face)):
                collector.add(
                    FailureCode.INPUT,
                    "geometry.isolated_face",
                    "A face shares no edge with any other face",
                    refs=(f"face:{face_index}",),
                )
        for edge, incidents in edge_faces.items():
            if len(incidents) > 2:
                collector.add(
                    FailureCode.INPUT,
                    "geometry.non_manifold",
                    "An edge has more than two incident faces",
                    refs=(f"edge:{edge[0]}:{edge[1]}",),
                )
        for first in range(len(mesh.vertices)):
            for second in range(first + 1, len(mesh.vertices)):
                distance2 = _norm2(
                    _sub(_rpoint(mesh.vertices[first]), _rpoint(mesh.vertices[second]))
                )
                if (
                    distance2 != 0
                    and distance2
                    <= profile.coordinate_distance_max * profile.coordinate_distance_max * scale2
                ):
                    collector.add(
                        FailureCode.INPUT,
                        "geometry.coincident_vertex",
                        "Distinct vertices are numerically coincident under the profile",
                        refs=(f"vertex:{first}", f"vertex:{second}"),
                    )
        components_faces = self._face_components(len(mesh.faces), edge_faces)
        components = self._components(
            mesh, edge_faces, components_faces, scale2, profile, collector
        )
        self._contacts(mesh, components_faces, scale2, profile, collector)
        return components, scale2

    @staticmethod
    def _face_components(
        face_count: int, edge_faces: Mapping[Edge, list[tuple[int, tuple[int, int]]]]
    ) -> tuple[tuple[int, ...], ...]:
        graph: dict[int, set[int]] = {index: set() for index in range(face_count)}
        for incidents in edge_faces.values():
            if len(incidents) == 2:
                a, b = incidents[0][0], incidents[1][0]
                graph[a].add(b)
                graph[b].add(a)
        seen: set[int] = set()
        components: list[tuple[int, ...]] = []
        for start in range(face_count):
            if start not in seen:
                queue = deque([start])
                seen.add(start)
                found: list[int] = []
                while queue:
                    current = queue.popleft()
                    found.append(current)
                    for neighbor in sorted(graph[current]):
                        if neighbor not in seen:
                            seen.add(neighbor)
                            queue.append(neighbor)
                components.append(tuple(sorted(found)))
        return tuple(components)

    def _components(
        self,
        mesh: _Mesh,
        edge_faces: Mapping[Edge, list[tuple[int, tuple[int, int]]]],
        groups: tuple[tuple[int, ...], ...],
        scale2: Fraction,
        profile: NumericalGeometryProfile,
        collector: _Collector,
    ) -> tuple[MeshComponent, ...]:
        result: list[MeshComponent] = []
        for component_id, faces in enumerate(groups):
            face_set = set(faces)
            edges = {
                edge: incidents
                for edge, incidents in edge_faces.items()
                if any(item[0] in face_set for item in incidents)
            }
            vertices = tuple(
                sorted({vertex for face_id in faces for vertex in mesh.faces[face_id]})
            )
            boundary = tuple(
                sorted(edge for edge, incidents in edges.items() if len(incidents) == 1)
            )
            loops, manifold = self._boundary_loops(boundary, component_id, collector)
            manifold = manifold and self._vertex_manifold(
                mesh, faces, vertices, boundary, component_id, collector
            )
            orientable, consistent = self._orientation(edges, component_id, collector)
            closed = not boundary
            volume: float | None = None
            outward: str | None = None
            if closed and orientable and consistent:
                volume6 = sum(
                    (
                        _dot(
                            _rpoint(mesh.vertices[a]),
                            _cross(_rpoint(mesh.vertices[b]), _rpoint(mesh.vertices[c])),
                        )
                        for a, b, c in (mesh.faces[index] for index in faces)
                    ),
                    Fraction(0),
                )
                normalized2 = volume6 * volume6 / (scale2 * scale2 * scale2)
                threshold2 = profile.volume6_min_exclusive * profile.volume6_min_exclusive
                if normalized2 <= threshold2:
                    collector.add(
                        FailureCode.INPUT,
                        "geometry.orientation_indeterminate",
                        "Closed-component signed volume is not reliable under the profile",
                        refs=(f"component:{component_id}",),
                        indeterminate=True,
                    )
                else:
                    outward = "OUTWARD" if volume6 > 0 else "INVERTED"
                    volume = math.copysign(math.sqrt(float(normalized2)), float(volume6))
            result.append(
                MeshComponent(
                    component_id,
                    vertices,
                    faces,
                    len(edges),
                    loops,
                    closed,
                    manifold,
                    orientable,
                    consistent,
                    outward,
                    volume,
                )
            )
        return tuple(result)

    @staticmethod
    def _boundary_loops(
        edges: tuple[Edge, ...], component_id: int, collector: _Collector
    ) -> tuple[tuple[tuple[int, ...], ...], bool]:
        if not edges:
            return (), True
        graph: dict[int, list[int]] = defaultdict(list)
        for a, b in edges:
            graph[a].append(b)
            graph[b].append(a)
        if any(len(neighbors) != 2 for neighbors in graph.values()):
            collector.add(
                FailureCode.INPUT,
                "geometry.non_manifold",
                "Boundary graph must consist only of simple cycles",
                refs=(f"component:{component_id}",),
            )
            return (), False
        loops: list[tuple[int, ...]] = []
        unseen = set(graph)
        while unseen:
            start = min(unseen)
            previous: int | None = None
            current = start
            loop: list[int] = []
            while current not in loop:
                loop.append(current)
                unseen.discard(current)
                choices = sorted(neighbor for neighbor in graph[current] if neighbor != previous)
                if not choices:
                    return (), False
                previous, current = current, choices[0]
            if current != start or len(loop) < 3:
                collector.add(
                    FailureCode.INPUT,
                    "geometry.non_manifold",
                    "Boundary component is not a simple loop",
                    refs=(f"component:{component_id}",),
                )
                return (), False
            loops.append(tuple(loop))
        return tuple(sorted(loops)), True

    @staticmethod
    def _vertex_manifold(
        mesh: _Mesh,
        faces: tuple[int, ...],
        vertices: tuple[int, ...],
        boundary: tuple[Edge, ...],
        component_id: int,
        collector: _Collector,
    ) -> bool:
        boundary_vertices = {vertex for edge in boundary for vertex in edge}
        valid = True
        for vertex in vertices:
            incident = [face_id for face_id in faces if vertex in mesh.faces[face_id]]
            neighbors: dict[int, set[int]] = defaultdict(set)
            for face_id in incident:
                others = [item for item in mesh.faces[face_id] if item != vertex]
                neighbors[others[0]].add(others[1])
                neighbors[others[1]].add(others[0])
            degrees = [len(value) for value in neighbors.values()]
            seen: set[int] = set()
            if neighbors:
                queue = deque([min(neighbors)])
                while queue:
                    current = queue.popleft()
                    if current in seen:
                        continue
                    seen.add(current)
                    queue.extend(neighbors[current] - seen)
            is_boundary = vertex in boundary_vertices
            expected = [1, 1] if is_boundary else []
            if len(seen) != len(neighbors) or sorted(degrees) != expected + [2] * (
                len(degrees) - len(expected)
            ):
                collector.add(
                    FailureCode.INPUT,
                    "geometry.non_manifold",
                    "Vertex link is not one cycle or one boundary path",
                    refs=(f"component:{component_id}", f"vertex:{vertex}"),
                )
                valid = False
        return valid

    @staticmethod
    def _orientation(
        edges: Mapping[Edge, list[tuple[int, tuple[int, int]]]],
        component_id: int,
        collector: _Collector,
    ) -> tuple[bool, bool]:
        graph: dict[int, list[tuple[int, int]]] = defaultdict(list)
        consistent = True
        for incidents in edges.values():
            if len(incidents) == 2:
                (a, direction_a), (b, direction_b) = incidents
                opposite = direction_a == (direction_b[1], direction_b[0])
                consistent = consistent and opposite
                graph[a].append((b, 0 if opposite else 1))
                graph[b].append((a, 0 if opposite else 1))
        assigned: dict[int, int] = {}
        orientable = True
        for start in sorted(graph):
            if start in assigned:
                continue
            assigned[start] = 0
            queue = deque([start])
            while queue:
                current = queue.popleft()
                for neighbor, flip in graph[current]:
                    wanted = assigned[current] ^ flip
                    if neighbor in assigned and assigned[neighbor] != wanted:
                        orientable = False
                    elif neighbor not in assigned:
                        assigned[neighbor] = wanted
                        queue.append(neighbor)
        if not orientable:
            collector.add(
                FailureCode.INPUT,
                "geometry.non_orientable",
                "Face adjacency orientation constraints contradict",
                refs=(f"component:{component_id}",),
            )
        if not consistent:
            collector.add(
                FailureCode.INPUT,
                "geometry.inconsistent_winding",
                "Interior edge uses are not consistently opposite",
                refs=(f"component:{component_id}",),
            )
        return orientable, consistent

    def _contacts(
        self,
        mesh: _Mesh,
        groups: tuple[tuple[int, ...], ...],
        scale2: Fraction,
        profile: NumericalGeometryProfile,
        collector: _Collector,
    ) -> None:
        component_of = {face: index for index, group in enumerate(groups) for face in group}
        # Sweep-and-prune candidates: exact AABB overlap catches intersections; the
        # conservative float radius only adds candidates for near-contact testing.
        contact_limit2 = (
            profile.near_contact_distance_max * profile.near_contact_distance_max * scale2
        )
        boxes = []
        for index, face in enumerate(mesh.faces):
            points = [mesh.vertices[item] for item in face]
            boxes.append(
                (
                    min(point[0] for point in points),
                    max(point[0] for point in points),
                    min(point[1] for point in points),
                    max(point[1] for point in points),
                    min(point[2] for point in points),
                    max(point[2] for point in points),
                    index,
                )
            )
        active: list[tuple[float, float, float, float, float, float, int]] = []
        for box in sorted(boxes):
            active = [
                item for item in active if _axis_may_be_within(item[1], box[0], contact_limit2)
            ]
            for other in active:
                if not _boxes_may_be_within(other, box, contact_limit2):
                    continue
                first, second = other[6], box[6]
                shared = len(set(mesh.faces[first]) & set(mesh.faces[second]))
                one = tuple(_rpoint(mesh.vertices[i]) for i in mesh.faces[first])
                two = tuple(_rpoint(mesh.vertices[i]) for i in mesh.faces[second])
                relation = _triangle_relation(
                    cast(tuple[RPoint, RPoint, RPoint], one),
                    cast(tuple[RPoint, RPoint, RPoint], two),
                    shared,
                )
                if relation in {ContactKind.SHARED_EDGE, ContactKind.SHARED_VERTEX}:
                    continue
                same_component = component_of[first] == component_of[second]
                code = (
                    FailureCode.INPUT
                    if same_component
                    or relation not in {ContactKind.VERTEX_FACE_TOUCH, ContactKind.EDGE_EDGE_TOUCH}
                    else FailureCode.UNSUPPORTED_FEATURE
                )
                if relation != ContactKind.NONE:
                    collector.add(
                        code,
                        "geometry.intersection"
                        if code == FailureCode.INPUT
                        else "geometry.contact_unsupported",
                        f"Forbidden triangle relation: {relation}",
                        refs=(f"face:{first}", f"face:{second}"),
                        observed=relation,
                    )
                else:
                    distance2 = _triangle_distance2(
                        cast(tuple[RPoint, RPoint, RPoint], one),
                        cast(tuple[RPoint, RPoint, RPoint], two),
                    )
                    if distance2 <= contact_limit2:
                        code = (
                            FailureCode.INPUT if same_component else FailureCode.UNSUPPORTED_FEATURE
                        )
                        collector.add(
                            code,
                            "geometry.intersection"
                            if code == FailureCode.INPUT
                            else "geometry.contact_unsupported",
                            "Disjoint triangles are within the profile near-contact distance",
                            refs=(f"face:{first}", f"face:{second}"),
                            units="MILLIMETER",
                        )
            active.append(box)

    def _validate_domain(
        self,
        mesh: _Mesh,
        design: Mapping[str, Any],
        profile_id: str,
        numeric: NumericalGeometryProfile,
        components: tuple[MeshComponent, ...],
        scale2: Fraction | None,
        collector: _Collector,
    ) -> None:
        target = cast(Mapping[str, Any], design["target_geometry"])
        expectation = cast(Mapping[str, Any], target["topology_expectation"])
        expected_components = cast(int, expectation["expected_connected_components"])
        expected_boundaries = cast(int, expectation["expected_boundary_components"])
        if len(components) != expected_components:
            collector.add(
                FailureCode.INPUT,
                "geometry.component_count_mismatch",
                "Component count differs from DesignSpec",
                expected=expected_components,
                observed=len(components),
            )
        boundaries = sum(len(component.boundary_loops) for component in components)
        if boundaries != expected_boundaries:
            collector.add(
                FailureCode.INPUT,
                "geometry.boundary_count_mismatch",
                "Boundary-loop count differs from DesignSpec",
                expected=expected_boundaries,
                observed=boundaries,
            )
        if profile_id == "V0_AMIGURUMI_CLOSED_SURFACE_V1" and any(
            not component.is_closed for component in components
        ):
            collector.add(
                FailureCode.INPUT,
                "geometry.unexpected_boundary",
                "Closed amigurumi requires every component to be closed",
            )
        if profile_id in {
            "V0_AMIGURUMI_DECLARED_BOUNDARY_SURFACE_V1",
            "V0_GARMENT_DECLARED_BOUNDARY_SURFACE_V1",
        }:
            if not components or boundaries == 0:
                collector.add(
                    FailureCode.INPUT,
                    "geometry.expected_boundary_missing",
                    "Declared-boundary profile requires at least one boundary loop",
                )
            self._assign_openings(mesh, design, components, numeric, scale2, collector)
        if profile_id not in {
            "V0_AMIGURUMI_CLOSED_SURFACE_V1",
            "V0_AMIGURUMI_DECLARED_BOUNDARY_SURFACE_V1",
            "V0_GARMENT_DECLARED_BOUNDARY_SURFACE_V1",
        }:
            collector.add(
                FailureCode.UNSUPPORTED_FEATURE,
                "geometry.domain_profile_unsupported",
                "Unknown V0 domain profile",
                observed=profile_id,
            )

    def _assign_openings(
        self,
        mesh: _Mesh,
        design: Mapping[str, Any],
        components: tuple[MeshComponent, ...],
        profile: NumericalGeometryProfile,
        scale2: Fraction | None,
        collector: _Collector,
    ) -> None:
        if scale2 is None:
            return
        loops = [
            (component.component_id, loop)
            for component in components
            for loop in component.boundary_loops
        ]
        landmarks = {item["landmark_id"]: item for item in design["landmarks"]}
        openings = [
            item
            for item in design["construction_constraints"]["intentional_openings"]
            if item["closure_expectation"] == "REMAIN_OPEN"
        ]
        assignments: dict[str, tuple[int, tuple[int, ...]]] = {}
        for opening in openings:
            candidates = set(range(len(loops)))
            for landmark_id in opening["boundary_landmark_ids"]:
                landmark = landmarks.get(landmark_id)
                if landmark is None:
                    continue
                raw_position = landmark["position_mm"]
                point = _rpoint(
                    (
                        cast(float, raw_position[0]),
                        cast(float, raw_position[1]),
                        cast(float, raw_position[2]),
                    )
                )
                threshold = _fraction(cast(float, landmark["tolerance_mm"]))
                eligible: set[int] = set()
                for index, (_, loop) in enumerate(loops):
                    distance2 = min(
                        _point_segment_distance2(
                            point,
                            _rpoint(mesh.vertices[loop[i]]),
                            _rpoint(mesh.vertices[loop[(i + 1) % len(loop)]]),
                        )
                        for i in range(len(loop))
                    )
                    if _within_landmark_threshold(
                        distance2,
                        threshold,
                        profile.landmark_slack_max,
                        scale2,
                    ):
                        eligible.add(index)
                candidates &= eligible
            if len(candidates) != 1:
                collector.add(
                    FailureCode.INPUT,
                    "geometry.landmark_boundary_ambiguous",
                    "Opening landmarks do not select exactly one boundary loop",
                    refs=(opening["opening_requirement_id"],),
                    observed=len(candidates),
                    indeterminate=len(candidates) > 1,
                )
            else:
                assignments[opening["opening_requirement_id"]] = loops[next(iter(candidates))]
        if len(assignments) != len(loops) or len(set(assignments.values())) != len(assignments):
            collector.add(
                FailureCode.INPUT,
                "geometry.landmark_boundary_ambiguous",
                "Every declared boundary loop must map one-to-one to a REMAIN_OPEN requirement",
                observed=len(assignments),
                expected=len(loops),
            )

    @staticmethod
    def _result(
        collector: _Collector,
        domain: str | None,
        profile: NumericalGeometryProfile | None,
        components: tuple[MeshComponent, ...],
        scale2: Fraction | None,
        mesh_hash: str | None,
        events: tuple[str, ...] = (),
    ) -> MeshPreflightResult:
        report = collector.report()
        outcome = (
            PreflightOutcome.INDETERMINATE
            if collector.indeterminate
            else (PreflightOutcome.PASS if report.ok else PreflightOutcome.FAIL)
        )
        scale = math.sqrt(float(scale2)) if scale2 is not None else None
        return MeshPreflightResult(
            outcome,
            domain,
            profile.profile_id if profile else None,
            profile.profile_version if profile else None,
            profile.record_hash if profile else None,
            mesh_hash,
            scale,
            components,
            report.diagnostics,
            normalization_events=events,
            evidence=MappingProxyType({"predicate_backend": PREDICATE_BACKEND}),
        )


def preflight_mesh(
    mesh_value: Mapping[str, Any], design_spec: Mapping[str, Any]
) -> MeshPreflightResult:
    """Convenience entry point for the V0 independent verification gate."""
    return MeshPreflightValidator().preflight(mesh_value, design_spec)
