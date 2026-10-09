"""Target-free exact triangle-surface contact hypothesis and path guard.

The stiffness is an uncalibrated HYPOTHESIS. Exact rational predicates treat
binary64 coordinates as their exact represented values. A path is accepted
only when every primitive pair has a conservative continuous-time proof.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from typing import TypeAlias

from .exact_triangle_relation import (
    TriangleRelationKind,
    triangle_relation,
)
from .forward_bending import MIN_AREA_VECTOR_MM2, MIN_EDGE_LENGTH_MM, MIN_TRIANGLE_QUALITY

PROFILE = "FORWARD_SURFACE_CONTACT_V1"
MAX_CONTACT_VERTICES = 2048
MAX_CONTACT_FACES = 4096
Point: TypeAlias = tuple[Fraction, Fraction, Fraction]
Vec3: TypeAlias = tuple[float, float, float]


class ContactError(ValueError):
    """Invalid contact input, unsupported topology, or exhausted work."""

    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


@dataclass(frozen=True, slots=True)
class ContactParameters:
    schema_version: int
    status: str
    provenance_id: str
    activation_distance_mm: float
    minimum_clearance_mm: float
    stiffness_n_per_mm: float
    max_pair_evaluations: int


@dataclass(frozen=True, slots=True)
class ContactSurface:
    vertices: tuple[Point, ...]
    faces: tuple[tuple[int, int, int], ...]
    topology_sha256: str


@dataclass(slots=True)
class ContactBudgetContext:
    """Mutable caller-owned counter reusable across evaluations/trials."""

    pair_evaluations: int = 0
    exact_distance_evaluations: int = 0
    path_pair_proofs: int = 0
    indeterminate_pair_proofs: int = 0
    broadphase_candidate_tests: int = 0
    exact_pair_tests: int = 0


@dataclass(frozen=True, slots=True)
class ContactEvaluation:
    energy_n_mm: float
    forces_n: tuple[tuple[int, Vec3], ...]
    pair_evaluations: int
    exact_distance_evaluations: int
    static_report: tuple[tuple[str, int | str], ...]


@dataclass(frozen=True, slots=True)
class ContactPathCertificate:
    status: str
    pair_evaluations: int
    path_pair_proofs: int
    indeterminate_pair_proofs: int
    reason: str


def admit_contact_parameters(value: object) -> ContactParameters:
    """Validate and freeze explicit HYPOTHESIS parameters, fail-closed."""
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "status",
        "provenance_id",
        "activation_distance_mm",
        "minimum_clearance_mm",
        "stiffness_n_per_mm",
        "max_pair_evaluations",
    }:
        raise ContactError("contact.parameters_invalid", "fields_must_match_v1")
    if (
        isinstance(value["schema_version"], bool)
        or not isinstance(value["schema_version"], int)
        or value["schema_version"] != 1
    ):
        raise ContactError("contact.parameters_invalid", "schema_version_unsupported")
    if value["status"] != "HYPOTHESIS":
        raise ContactError("contact.parameters_invalid", "status_must_be_hypothesis")
    provenance = value["provenance_id"]
    if not isinstance(provenance, str) or not provenance.strip():
        raise ContactError("contact.parameters_invalid", "provenance_id_invalid")
    activation = _positive_finite(value["activation_distance_mm"], "activation_distance")
    clearance = _positive_finite(value["minimum_clearance_mm"], "minimum_clearance")
    stiffness = _positive_finite(value["stiffness_n_per_mm"], "stiffness")
    if not activation > clearance:
        raise ContactError("contact.parameters_invalid", "activation_must_exceed_clearance")
    budget = value["max_pair_evaluations"]
    if isinstance(budget, bool) or not isinstance(budget, int) or not 0 < budget <= 2_000_000:
        raise ContactError("contact.parameters_invalid", "pair_budget_out_of_range")
    return ContactParameters(1, "HYPOTHESIS", provenance, activation, clearance, stiffness, budget)


def prepare_surface_contact(
    vertices: tuple[tuple[float, float, float], ...],
    faces: tuple[tuple[int, int, int], ...],
) -> ContactSurface:
    """Admit a closed, oriented, combinatorial two-manifold surface."""
    if not isinstance(vertices, tuple) or not vertices or not isinstance(faces, tuple) or not faces:
        raise ContactError("contact.surface_invalid", "vertices_and_faces_required")
    if len(vertices) > MAX_CONTACT_VERTICES or len(faces) > MAX_CONTACT_FACES:
        raise ContactError("contact.surface_invalid", "surface_size_limit_exceeded")
    exact_vertices = tuple(_exact_point(point) for point in vertices)
    if len(set(exact_vertices)) != len(exact_vertices):
        raise ContactError("contact.surface_invalid", "coincident_vertices")
    edges: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)
    incident: dict[int, list[int]] = defaultdict(list)
    normalized: list[tuple[int, int, int]] = []
    seen_faces: set[tuple[int, int, int]] = set()
    for face_index, face in enumerate(faces):
        if (
            not isinstance(face, tuple)
            or len(face) != 3
            or any(
                isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(vertices)
                for i in face
            )
            or len(set(face)) != 3
        ):
            raise ContactError("contact.surface_invalid", "face_indices_invalid")
        a, b, c = face
        sorted_face = sorted(face)
        unordered_face = (sorted_face[0], sorted_face[1], sorted_face[2])
        if unordered_face in seen_faces:
            raise ContactError("contact.surface_invalid", "duplicate_face")
        seen_faces.add(unordered_face)
        tri = (exact_vertices[a], exact_vertices[b], exact_vertices[c])
        _check_triangle(tri)
        normalized.append(face)
        for vertex in face:
            incident[vertex].append(face_index)
        for u, v in ((a, b), (b, c), (c, a)):
            edges[(min(u, v), max(u, v))].append((face_index, u, v))
    if set(incident) != set(range(len(vertices))):
        raise ContactError("contact.surface_invalid", "unreferenced_vertex")
    for uses in edges.values():
        if len(uses) != 2 or uses[0][1:] != (uses[1][2], uses[1][1]):
            raise ContactError("contact.surface_invalid", "not_closed_consistently_oriented")
    # Each vertex link must be one cycle, not a bow-tie fan.
    for vertex, face_ids in incident.items():
        link: dict[int, set[int]] = defaultdict(set)
        for fi in face_ids:
            others = [v for v in normalized[fi] if v != vertex]
            if len(others) != 2:
                raise ContactError("contact.surface_invalid", "vertex_link_invalid")
            link[others[0]].add(others[1])
            link[others[1]].add(others[0])
        if any(len(neighbors) != 2 for neighbors in link.values()) or not _connected(link):
            raise ContactError("contact.surface_invalid", "vertex_link_not_single_cycle")
    import hashlib

    body = repr((exact_vertices, tuple(normalized))).encode("ascii")
    return ContactSurface(exact_vertices, tuple(normalized), hashlib.sha256(body).hexdigest())


def evaluate_contact(
    surface: ContactSurface,
    points: tuple[tuple[float, float, float], ...],
    parameters: ContactParameters,
    budget_context: ContactBudgetContext,
) -> ContactEvaluation:
    """Evaluate capped-distance repulsion and negative-gradient vertex forces."""
    _validate_runtime(surface, points, parameters, budget_context)
    exact_points = tuple(_exact_point(point) for point in points)
    triangles: tuple[tuple[Point, Point, Point], ...] = tuple(
        (exact_points[face[0]], exact_points[face[1]], exact_points[face[2]])
        for face in surface.faces
    )
    if any(
        not _valid_triangle_guard(_cross(_sub(tri[1], tri[0]), _sub(tri[2], tri[0])), tri)
        for tri in triangles
    ):
        raise ContactError("contact.numerical_failure", "triangle_arithmetic_guard_failed")
    forces: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    energies: list[float] = []
    checked = 0
    pairs = _sweep_pairs(
        triangles,
        Fraction.from_float(parameters.activation_distance_mm),
        parameters,
        budget_context,
    )
    for first, second, yz_candidate in pairs:
        checked += 1
        if not yz_candidate:
            continue
        budget_context.exact_pair_tests += 1
        shared = tuple(sorted(set(surface.faces[first]) & set(surface.faces[second])))
        ta, tb = triangles[first], triangles[second]
        if shared:
            _validate_static_adjacency(ta, tb, surface.faces[first], surface.faces[second], shared)
            continue
        if triangle_relation(ta, tb).witnesses:
            raise ContactError("contact.unresolved_collision", "nonadjacent_triangles_intersect")
        best = _closest(ta, tb)
        budget_context.exact_distance_evaluations += 1
        distance_squared, qa, qb, wa, wb = best
        if distance_squared == 0:
            raise ContactError("contact.unresolved_collision", "nonadjacent_triangles_intersect")
        clearance_squared = Fraction.from_float(parameters.minimum_clearance_mm) ** 2
        activation_squared = Fraction.from_float(parameters.activation_distance_mm) ** 2
        if distance_squared < clearance_squared:
            raise ContactError("contact.unresolved_collision", "minimum_clearance_violated")
        if distance_squared >= activation_squared:
            continue
        distance = _sqrt_fraction_to_float(distance_squared, "distance")
        if distance <= 0.0:
            raise ContactError("contact.numerical_failure", "positive_distance_underflow")
        overlap = parameters.activation_distance_mm - distance
        energy = 0.5 * parameters.stiffness_n_per_mm * overlap * overlap
        if not math.isfinite(energy):
            raise ContactError("contact.numerical_failure", "pair_energy_not_finite")
        delta = tuple(_fraction_to_float(qa[i] - qb[i], "closest_point_delta") for i in range(3))
        scale = parameters.stiffness_n_per_mm * overlap / distance
        pair_force = tuple(scale * component for component in delta)
        for local, vertex in enumerate(surface.faces[first]):
            for axis in range(3):
                forces[vertex][axis] += float(wa[local]) * pair_force[axis]
        for local, vertex in enumerate(surface.faces[second]):
            for axis in range(3):
                forces[vertex][axis] -= float(wb[local]) * pair_force[axis]
        energies.append(energy)
    energy_sum = _finite_energy_sum(energies)
    rows = tuple(
        (index, (values[0], values[1], values[2])) for index, values in sorted(forces.items())
    )
    if not math.isfinite(energy_sum) or any(not math.isfinite(x) for _, row in rows for x in row):
        raise ContactError("contact.numerical_failure", "result_not_finite")
    return ContactEvaluation(
        energy_sum,
        rows,
        checked,
        budget_context.exact_distance_evaluations,
        (
            ("population_pairs", len(triangles) * (len(triangles) - 1) // 2),
            ("broadphase_candidate_tests", budget_context.broadphase_candidate_tests),
            ("exact_pair_tests", budget_context.exact_pair_tests),
            ("nonadjacent_distance_pairs", budget_context.exact_distance_evaluations),
            ("status", "EXPERIMENTAL_CONTACT_HYPOTHESIS"),
        ),
    )


def certify_contact_path(
    surface: ContactSurface,
    start: tuple[tuple[float, float, float], ...],
    end: tuple[tuple[float, float, float], ...],
    parameters: ContactParameters,
    budget_context: ContactBudgetContext,
) -> ContactPathCertificate:
    """Certify an entire linear vertex path; never infer safety from samples."""
    _validate_runtime(surface, start, parameters, budget_context)
    _validate_runtime(surface, end, parameters, budget_context)
    a = tuple(_exact_point(point) for point in start)
    b = tuple(_exact_point(point) for point in end)
    if not _all_triangles_quality_certified(surface, a, b):
        return _path_result("INDETERMINATE", budget_context, "triangle_quality_not_certified")
    start_triangles = tuple(_face_points(face, a) for face in surface.faces)
    end_triangles = tuple(_face_points(face, b) for face in surface.faces)
    swept_pairs = _sweep_pairs(
        tuple(t0 + t1 for t0, t1 in zip(start_triangles, end_triangles, strict=True)),
        Fraction.from_float(parameters.minimum_clearance_mm),
        parameters,
        budget_context,
    )
    try:
        for first, second, yz_candidate in swept_pairs:
            if not yz_candidate:
                continue
            budget_context.exact_pair_tests += 1
            shared = tuple(sorted(set(surface.faces[first]) & set(surface.faces[second])))
            ta0, tb0 = _face_points(surface.faces[first], a), _face_points(surface.faces[second], a)
            ta1, tb1 = _face_points(surface.faces[first], b), _face_points(surface.faces[second], b)
            try:
                if not shared:
                    start_distance = _closest(ta0, tb0)[0]
                    end_distance = _closest(ta1, tb1)[0]
                    budget_context.exact_distance_evaluations += 2
                    if (
                        triangle_relation(ta0, tb0).witnesses
                        or triangle_relation(ta1, tb1).witnesses
                    ):
                        return _path_result(
                            "UNRESOLVED_COLLISION", budget_context, "endpoint_intersection"
                        )
                    gap_squared = Fraction.from_float(parameters.minimum_clearance_mm) ** 2
                    if (
                        start_distance == 0
                        or end_distance == 0
                        or min(start_distance, end_distance) < gap_squared
                    ):
                        return _path_result(
                            "UNRESOLVED_COLLISION", budget_context, "endpoint_clearance_violated"
                        )
                    if not _nonadjacent_path_safe(
                        ta0,
                        tb0,
                        ta1,
                        tb1,
                        parameters.minimum_clearance_mm,
                        start_distance,
                    ):
                        return _path_result(
                            "INDETERMINATE", budget_context, "nonadjacent_path_unproved"
                        )
                elif len(shared) == 1:
                    _validate_path_adjacency(
                        ta0, tb0, ta1, tb1, surface.faces[first], surface.faces[second], shared
                    )
                    if not _vertex_adjacent_path_safe(
                        ta0, tb0, ta1, tb1, shared[0], surface.faces[first], surface.faces[second]
                    ):
                        return _path_result(
                            "INDETERMINATE", budget_context, "vertex_adjacent_path_unproved"
                        )
                elif len(shared) == 2:
                    _validate_path_adjacency(
                        ta0, tb0, ta1, tb1, surface.faces[first], surface.faces[second], shared
                    )
                    if not _edge_adjacent_path_safe(
                        ta0, tb0, ta1, tb1, shared, surface.faces[first], surface.faces[second]
                    ):
                        return _path_result(
                            "INDETERMINATE", budget_context, "edge_adjacent_path_unproved"
                        )
                else:
                    return _path_result("INDETERMINATE", budget_context, "invalid_shared_simplex")
            except ContactError as error:
                if error.code == "contact.unresolved_collision":
                    return _path_result("UNRESOLVED_COLLISION", budget_context, error.reason)
                return _path_result(
                    "INDETERMINATE", budget_context, "contact_path_predicate_failed"
                )
            except (ArithmeticError, OverflowError, ValueError):
                return _path_result(
                    "INDETERMINATE", budget_context, "exact_path_arithmetic_unresolved"
                )
            budget_context.path_pair_proofs += 1
    except ContactError as error:
        if error.code == "contact.budget_exhausted":
            return _path_result("BUDGET_EXHAUSTED", budget_context, "pair_budget_exhausted")
        raise
    return _path_result("SAFE", budget_context, "all_pair_paths_certified")


def _validate_runtime(
    surface: ContactSurface,
    points: tuple[tuple[float, float, float], ...],
    parameters: ContactParameters,
    context: ContactBudgetContext,
) -> None:
    if not isinstance(surface, ContactSurface) or not isinstance(parameters, ContactParameters):
        raise ContactError("contact.input_invalid", "surface_or_parameters_invalid")
    if not isinstance(context, ContactBudgetContext):
        raise ContactError("contact.input_invalid", "budget_context_invalid")
    _validate_budget_context(context)
    _validate_parameter_value(parameters)
    _validate_surface_value(surface)
    if not isinstance(points, tuple) or len(points) != len(surface.vertices):
        raise ContactError("contact.input_invalid", "coordinate_count_mismatch")
    for point in points:
        _exact_point(point)


def _validate_parameter_value(parameters: ContactParameters) -> None:
    if any(
        type(value) is not float
        for value in (
            parameters.activation_distance_mm,
            parameters.minimum_clearance_mm,
            parameters.stiffness_n_per_mm,
        )
    ):
        raise ContactError("contact.parameters_invalid", "parameters_not_canonical")
    admitted = admit_contact_parameters(
        {
            "schema_version": parameters.schema_version,
            "status": parameters.status,
            "provenance_id": parameters.provenance_id,
            "activation_distance_mm": parameters.activation_distance_mm,
            "minimum_clearance_mm": parameters.minimum_clearance_mm,
            "stiffness_n_per_mm": parameters.stiffness_n_per_mm,
            "max_pair_evaluations": parameters.max_pair_evaluations,
        }
    )
    if admitted != parameters:
        raise ContactError("contact.parameters_invalid", "parameters_not_canonical")


def _validate_budget_context(context: ContactBudgetContext) -> None:
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (
            context.pair_evaluations,
            context.exact_distance_evaluations,
            context.path_pair_proofs,
            context.indeterminate_pair_proofs,
            context.broadphase_candidate_tests,
            context.exact_pair_tests,
        )
    ):
        raise ContactError("contact.input_invalid", "budget_context_counters_invalid")


def _validate_surface_value(surface: ContactSurface) -> None:
    if not isinstance(surface.vertices, tuple) or not surface.vertices:
        raise ContactError("contact.surface_invalid", "vertices_invalid")
    if not isinstance(surface.faces, tuple) or not surface.faces:
        raise ContactError("contact.surface_invalid", "faces_invalid")
    if len(surface.vertices) > MAX_CONTACT_VERTICES or len(surface.faces) > MAX_CONTACT_FACES:
        raise ContactError("contact.surface_invalid", "surface_size_limit_exceeded")
    if any(
        not isinstance(point, tuple)
        or len(point) != 3
        or any(not isinstance(coordinate, Fraction) for coordinate in point)
        for point in surface.vertices
    ):
        raise ContactError("contact.surface_invalid", "exact_vertices_invalid")
    if len(set(surface.vertices)) != len(surface.vertices):
        raise ContactError("contact.surface_invalid", "coincident_vertices")
    edges: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)
    incident: dict[int, list[int]] = defaultdict(list)
    seen_faces: set[tuple[int, int, int]] = set()
    for face_index, face in enumerate(surface.faces):
        if (
            not isinstance(face, tuple)
            or len(face) != 3
            or any(
                isinstance(index, bool)
                or not isinstance(index, int)
                or not 0 <= index < len(surface.vertices)
                for index in face
            )
            or len(set(face)) != 3
        ):
            raise ContactError("contact.surface_invalid", "face_indices_invalid")
        sorted_face = sorted(face)
        unordered_face = (sorted_face[0], sorted_face[1], sorted_face[2])
        if unordered_face in seen_faces:
            raise ContactError("contact.surface_invalid", "duplicate_face")
        seen_faces.add(unordered_face)
        tri = (
            surface.vertices[face[0]],
            surface.vertices[face[1]],
            surface.vertices[face[2]],
        )
        _check_triangle(tri)
        for vertex in face:
            incident[vertex].append(face_index)
        for u, v in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edges[(min(u, v), max(u, v))].append((face_index, u, v))
    if set(incident) != set(range(len(surface.vertices))):
        raise ContactError("contact.surface_invalid", "unreferenced_vertex")
    if any(len(uses) != 2 or uses[0][1:] != (uses[1][2], uses[1][1]) for uses in edges.values()):
        raise ContactError("contact.surface_invalid", "not_closed_consistently_oriented")
    for vertex, face_ids in incident.items():
        link: dict[int, set[int]] = defaultdict(set)
        for face_index in face_ids:
            others = [index for index in surface.faces[face_index] if index != vertex]
            link[others[0]].add(others[1])
            link[others[1]].add(others[0])
        if any(len(neighbors) != 2 for neighbors in link.values()) or not _connected(link):
            raise ContactError("contact.surface_invalid", "vertex_link_not_single_cycle")
    import hashlib

    body = repr((surface.vertices, surface.faces)).encode("ascii")
    if hashlib.sha256(body).hexdigest() != surface.topology_sha256:
        raise ContactError("contact.surface_invalid", "topology_digest_mismatch")


def _positive_finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ContactError("contact.parameters_invalid", f"{name}_must_be_number")
    try:
        converted = float(value)
    except OverflowError as error:
        raise ContactError("contact.parameters_invalid", f"{name}_out_of_range") from error
    if not math.isfinite(converted) or converted <= 0:
        raise ContactError("contact.parameters_invalid", f"{name}_must_be_positive_finite")
    if isinstance(value, int) and int(converted) != value:
        raise ContactError("contact.parameters_invalid", f"{name}_not_binary64_representable")
    return converted


def _sqrt_fraction_to_float(value: Fraction, name: str) -> float:
    try:
        converted = math.sqrt(float(value))
    except OverflowError as error:
        raise ContactError("contact.numerical_failure", f"{name}_conversion_overflow") from error
    if not math.isfinite(converted):
        raise ContactError("contact.numerical_failure", f"{name}_not_finite")
    return converted


def _fraction_to_float(value: Fraction, name: str) -> float:
    try:
        converted = float(value)
    except OverflowError as error:
        raise ContactError("contact.numerical_failure", f"{name}_conversion_overflow") from error
    if not math.isfinite(converted):
        raise ContactError("contact.numerical_failure", f"{name}_not_finite")
    return converted


def _finite_energy_sum(energies: list[float]) -> float:
    try:
        total = math.fsum(energies)
    except (OverflowError, ValueError) as error:
        raise ContactError("contact.numerical_failure", "energy_sum_not_finite") from error
    if not math.isfinite(total):
        raise ContactError("contact.numerical_failure", "energy_sum_not_finite")
    return total


def _validate_path_adjacency(
    a0: tuple[Point, Point, Point],
    b0: tuple[Point, Point, Point],
    a1: tuple[Point, Point, Point],
    b1: tuple[Point, Point, Point],
    face_a: tuple[int, int, int],
    face_b: tuple[int, int, int],
    shared: tuple[int, ...],
) -> None:
    try:
        _validate_static_adjacency(a0, b0, face_a, face_b, shared)
        _validate_static_adjacency(a1, b1, face_a, face_b, shared)
    except ContactError as error:
        raise ContactError(
            "contact.unresolved_collision", "adjacent_endpoint_relation_invalid"
        ) from error


def _exact_point(point: object) -> Point:
    if not isinstance(point, tuple) or len(point) != 3:
        raise ContactError("contact.input_invalid", "point_requires_three_coordinates")
    converted: list[Fraction] = []
    for value in point:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ContactError("contact.input_invalid", "coordinate_must_be_finite")
        try:
            binary64 = float(value)
        except OverflowError as error:
            raise ContactError("contact.input_invalid", "coordinate_out_of_range") from error
        if not math.isfinite(binary64):
            raise ContactError("contact.input_invalid", "coordinate_must_be_finite")
        if isinstance(value, int) and int(binary64) != value:
            raise ContactError("contact.input_invalid", "coordinate_not_binary64_representable")
        converted.append(Fraction.from_float(binary64))
    return converted[0], converted[1], converted[2]


def _check_triangle(triangle: tuple[Point, Point, Point]) -> None:
    if _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0])) == _zero():
        raise ContactError("contact.surface_invalid", "degenerate_triangle")


def _connected(graph: dict[int, set[int]]) -> bool:
    if not graph:
        return False
    todo = [next(iter(graph))]
    seen: set[int] = set()
    while todo:
        item = todo.pop()
        if item in seen:
            continue
        seen.add(item)
        todo.extend(graph[item] - seen)
    return seen == set(graph)


def _consume_pair(parameters: ContactParameters, context: ContactBudgetContext) -> None:
    if context.pair_evaluations >= parameters.max_pair_evaluations:
        raise ContactError("contact.budget_exhausted", "pair_evaluation_budget_exhausted")
    context.pair_evaluations += 1


def _closest(
    a: tuple[Point, Point, Point], b: tuple[Point, Point, Point]
) -> tuple[Fraction, Point, Point, tuple[Fraction, ...], tuple[Fraction, ...]]:
    candidates: list[tuple[Fraction, Point, Point, tuple[Fraction, ...], tuple[Fraction, ...]]] = []
    for i, point in enumerate(a):
        q, weights = _point_triangle_weights(point, b)
        candidates.append((_norm2(_sub(point, q)), point, q, _unit_weights(i), weights))
    for i, point in enumerate(b):
        q, weights = _point_triangle_weights(point, a)
        candidates.append((_norm2(_sub(point, q)), q, point, weights, _unit_weights(i)))
    for i in range(3):
        for j in range(3):
            qa, qb, s, t = _segment_closest(a[i], a[(i + 1) % 3], b[j], b[(j + 1) % 3])
            wa = [Fraction(0)] * 3
            wb = [Fraction(0)] * 3
            wa[i], wa[(i + 1) % 3] = 1 - s, s
            wb[j], wb[(j + 1) % 3] = 1 - t, t
            candidates.append((_norm2(_sub(qa, qb)), qa, qb, tuple(wa), tuple(wb)))
    return min(candidates, key=lambda item: (item[0], item[1], item[2], item[3], item[4]))


def _point_triangle_weights(
    p: Point, tri: tuple[Point, Point, Point]
) -> tuple[Point, tuple[Fraction, Fraction, Fraction]]:
    a, b, c = tri
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(p, a)
    d00, d01, d11 = _dot(ab, ab), _dot(ab, ac), _dot(ac, ac)
    d20, d21 = _dot(ap, ab), _dot(ap, ac)
    den = d00 * d11 - d01 * d01
    v, w = (d11 * d20 - d01 * d21) / den, (d00 * d21 - d01 * d20) / den
    if v >= 0 and w >= 0 and v + w <= 1:
        weights = (1 - v - w, v, w)
        return _weighted(tri, weights), weights
    best = None
    for i in range(3):
        j = (i + 1) % 3
        delta = _sub(tri[j], tri[i])
        t = max(Fraction(0), min(Fraction(1), _dot(_sub(p, tri[i]), delta) / _dot(delta, delta)))
        weights_list = [Fraction(0)] * 3
        weights_list[i], weights_list[j] = 1 - t, t
        edge_weights: tuple[Fraction, Fraction, Fraction] = (
            weights_list[0],
            weights_list[1],
            weights_list[2],
        )
        q = _weighted(tri, edge_weights)
        item = (_norm2(_sub(p, q)), q, edge_weights)
        if best is None or item < best:
            best = item
    assert best is not None
    return best[1], best[2]


def _segment_closest(
    p: Point, p1: Point, q: Point, q1: Point
) -> tuple[Point, Point, Fraction, Fraction]:
    u, v, w = _sub(p1, p), _sub(q1, q), _sub(p, q)
    aa, bb, cc = _dot(u, u), _dot(u, v), _dot(v, v)
    dd, ee = _dot(u, w), _dot(v, w)
    det = aa * cc - bb * bb
    choices: list[tuple[Fraction, Fraction]] = []
    for s in (Fraction(0), Fraction(1)):
        t = max(Fraction(0), min(Fraction(1), (bb * s + ee) / cc))
        choices.append((s, t))
    for t in (Fraction(0), Fraction(1)):
        s = max(Fraction(0), min(Fraction(1), (bb * t - dd) / aa))
        choices.append((s, t))
    if det > 0:
        s, t = (bb * ee - cc * dd) / det, (aa * ee - bb * dd) / det
        if 0 <= s <= 1 and 0 <= t <= 1:
            choices.append((s, t))
    s, t = min(choices, key=lambda st: (_norm2(_sub(_add(p, u, st[0]), _add(q, v, st[1]))), st))
    return _add(p, u, s), _add(q, v, t), s, t


def _unit_weights(i: int) -> tuple[Fraction, Fraction, Fraction]:
    return tuple(Fraction(int(j == i)) for j in range(3))  # type: ignore[return-value]


def _validate_static_adjacency(
    a: tuple[Point, Point, Point],
    b: tuple[Point, Point, Point],
    fa: tuple[int, int, int],
    fb: tuple[int, int, int],
    shared: tuple[int, ...],
) -> None:
    relation = triangle_relation(a, b)
    if relation.kind is TriangleRelationKind.COPLANAR_AREA:
        raise ContactError("contact.unresolved_collision", "adjacent_coplanar_area_overlap")
    allowed = tuple(a[fa.index(index)] for index in shared)
    if any(not _in_simplex(witness, allowed) for witness in relation.witnesses):
        raise ContactError("contact.unresolved_collision", "adjacency_has_extra_intersection")


def _in_simplex(point: Point, simplex: tuple[Point, ...]) -> bool:
    if len(simplex) == 1:
        return point == simplex[0]
    direction = _sub(simplex[1], simplex[0])
    delta = _sub(point, simplex[0])
    axis = next((i for i, value in enumerate(direction) if value), None)
    if axis is None:
        return point == simplex[0]
    t = delta[axis] / direction[axis]
    return 0 <= t <= 1 and all(delta[i] == t * direction[i] for i in range(3))


def _nonadjacent_path_safe(
    a0: tuple[Point, Point, Point],
    b0: tuple[Point, Point, Point],
    a1: tuple[Point, Point, Point],
    b1: tuple[Point, Point, Point],
    gap: float,
    start_distance_squared: Fraction,
) -> bool:
    d2 = start_distance_squared
    if d2 <= 0:
        return False
    move_a = _sqrt_upper(max(_norm2(_sub(x1, x0)) for x0, x1 in zip(a0, a1, strict=True)))
    move_b = _sqrt_upper(max(_norm2(_sub(x1, x0)) for x0, x1 in zip(b0, b1, strict=True)))
    # Every point in a moving triangle moves by no more than the maximum vertex displacement.
    gap_fraction = Fraction.from_float(gap)
    distance_lower = _sqrt_lower(d2)
    return distance_lower > gap_fraction + move_a + move_b


def _sqrt_upper(value: Fraction) -> Fraction:
    if value < 0:
        raise ArithmeticError("negative square-root argument")
    if value == 0:
        return Fraction(0)
    guess = math.sqrt(float(value))
    if not math.isfinite(guess):
        raise ArithmeticError("square-root overflow")
    candidate = Fraction.from_float(guess)
    for _ in range(8):
        if candidate * candidate >= value:
            return candidate
        guess = math.nextafter(guess, math.inf)
        candidate = Fraction.from_float(guess)
    raise ArithmeticError("bounded outward square-root failed")


def _sqrt_lower(value: Fraction) -> Fraction:
    if value < 0:
        raise ArithmeticError("negative square-root argument")
    if value == 0:
        return Fraction(0)
    guess = math.sqrt(float(value))
    if not math.isfinite(guess):
        raise ArithmeticError("square-root overflow")
    candidate = Fraction.from_float(guess)
    for _ in range(8):
        if candidate * candidate <= value:
            return candidate
        guess = math.nextafter(guess, -math.inf)
        candidate = Fraction.from_float(guess)
    raise ArithmeticError("bounded inward square-root failed")


def _vertex_adjacent_path_safe(
    a0: tuple[Point, Point, Point],
    b0: tuple[Point, Point, Point],
    a1: tuple[Point, Point, Point],
    b1: tuple[Point, Point, Point],
    shared: int,
    fa: tuple[int, int, int],
    fb: tuple[int, int, int],
) -> bool:
    ia, ib = fa.index(shared), fb.index(shared)
    vectors = tuple(_sub(a0[i], a0[ia]) for i in range(3) if i != ia) + tuple(
        _sub(b0[i], b0[ib]) for i in range(3) if i != ib
    )
    axis = _convex_hull_nearest(vectors)
    if axis is None or axis == _zero():
        return False
    end_vectors = tuple(_sub(a1[i], a1[ia]) for i in range(3) if i != ia) + tuple(
        _sub(b1[i], b1[ib]) for i in range(3) if i != ib
    )
    return all(_dot(axis, v) > 0 for v in vectors) and all(_dot(axis, v) > 0 for v in end_vectors)


def _convex_hull_nearest(points: tuple[Point, ...]) -> Point | None:
    best: tuple[Fraction, Point] | None = None
    for size in range(1, len(points) + 1):
        for subset in combinations(points, size):
            origin_projection = _affine_projection_origin(subset)
            if origin_projection is None:
                continue
            q, weights = origin_projection
            if all(weight >= 0 for weight in weights):
                candidate = (_norm2(q), q)
                if best is None or candidate < best:
                    best = candidate
    return None if best is None else best[1]


def _affine_projection_origin(
    points: tuple[Point, ...],
) -> tuple[Point, tuple[Fraction, ...]] | None:
    base = points[0]
    dirs = tuple(_sub(point, base) for point in points[1:])
    n = len(dirs)
    if n == 0:
        return base, (Fraction(1),)
    gram = [[_dot(dirs[i], dirs[j]) for j in range(n)] for i in range(n)]
    rhs = [-_dot(dirs[i], base) for i in range(n)]
    solved = _solve(gram, rhs)
    if solved is None:
        return None
    weights = (1 - sum(solved, Fraction(0)), *solved)
    return _weighted(points, weights), weights


def _solve(matrix: list[list[Fraction]], rhs: list[Fraction]) -> tuple[Fraction, ...] | None:
    augmented = [[*row[:], rhs[i]] for i, row in enumerate(matrix)]
    n = len(rhs)
    for col in range(n):
        pivot = next((row for row in range(col, n) if augmented[row][col]), None)
        if pivot is None:
            return None
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        scale = augmented[col][col]
        augmented[col] = [value / scale for value in augmented[col]]
        for row in range(n):
            if row != col:
                factor = augmented[row][col]
                augmented[row] = [
                    augmented[row][j] - factor * augmented[col][j] for j in range(n + 1)
                ]
    return tuple(augmented[i][-1] for i in range(n))


def _edge_adjacent_path_safe(
    a0: tuple[Point, Point, Point],
    b0: tuple[Point, Point, Point],
    a1: tuple[Point, Point, Point],
    b1: tuple[Point, Point, Point],
    shared: tuple[int, ...],
    fa: tuple[int, int, int],
    fb: tuple[int, int, int],
) -> bool:
    shared = tuple(sorted(shared))
    ia, ja = (fa.index(index) for index in shared)
    ib, jb = (fb.index(index) for index in shared)
    oa = next(i for i in range(3) if i not in (ia, ja))
    ob = next(i for i in range(3) if i not in (ib, jb))
    # Opposite directed shared-edge uses are normalized to a,c; b,d are the off-edge vertices.
    a, c = a0[ia], a0[ja]
    a_end, c_end = a1[ia], a1[ja]
    b, b_end, d, d_end = a0[oa], a1[oa], b0[ob], b1[ob]
    orient = _linear_det_bernstein((a, b, c, d), (a_end, b_end, c_end, d_end))
    if all(value > 0 for value in orient) or all(value < 0 for value in orient):
        return True
    n1 = _cross_poly(_sub_poly((b, b_end), (a, a_end)), _sub_poly((c, c_end), (a, a_end)))
    n2 = _cross_poly(_sub_poly((c, c_end), (a, a_end)), _sub_poly((d, d_end), (a, a_end)))
    dot_poly = _dot_poly(n1, n2)
    bernstein = _power_to_bernstein(dot_poly, 4)
    return all(value > 0 for value in bernstein)


def _linear_det_bernstein(
    start: tuple[Point, Point, Point, Point], end: tuple[Point, Point, Point, Point]
) -> tuple[Fraction, ...]:
    a, b, c, d = start
    ae, be, ce, de = end
    poly = _dot_poly(
        _cross_poly(_sub_poly((b, be), (a, ae)), _sub_poly((c, ce), (a, ae))),
        _sub_poly((d, de), (a, ae)),
    )
    return _power_to_bernstein(poly, 3)


def _all_triangles_quality_certified(
    surface: ContactSurface, start: tuple[Point, ...], end: tuple[Point, ...]
) -> bool:
    for face in surface.faces:
        a, b, c = (start[index] for index in face)
        ae, be, ce = (end[index] for index in face)
        normal = _cross_poly(_sub_poly((b, be), (a, ae)), _sub_poly((c, ce), (a, ae)))
        initial = _cross(_sub(b, a), _sub(c, a))
        final = _cross(_sub(be, ae), _sub(ce, ae))
        edge_pairs = ((a, b, ae, be), (b, c, be, ce), (c, a, ce, ae))
        endpoint_edge_squared = max(_norm2(_sub(p0, q0)) for p0, q0, p1, q1 in edge_pairs)
        endpoint_edge_squared = max(
            endpoint_edge_squared, *(_norm2(_sub(p1, q1)) for p0, q0, p1, q1 in edge_pairs)
        )
        if not _valid_triangle_guard(initial, (a, b, c)) or not _valid_triangle_guard(
            final, (ae, be, ce)
        ):
            return False
        fixed_normal = tuple((coordinate,) for coordinate in initial)
        coefficients = _power_to_bernstein(_dot_poly(normal, fixed_normal), 2)
        lower = min(coefficients)
        initial_norm2 = _norm2(initial)
        if lower <= 0:
            return False
        if lower * lower <= Fraction.from_float(MIN_AREA_VECTOR_MM2) ** 2 * initial_norm2:
            return False
        quality_bound = (
            Fraction.from_float(MIN_TRIANGLE_QUALITY) ** 2
            * endpoint_edge_squared**2
            * initial_norm2
        )
        if lower * lower <= quality_bound:
            return False
    return True


def _valid_triangle_guard(normal: Point, triangle: tuple[Point, Point, Point]) -> bool:
    if _norm2(normal) <= Fraction.from_float(MIN_AREA_VECTOR_MM2) ** 2:
        return False
    max_edge_squared = max(_norm2(_sub(triangle[i], triangle[(i + 1) % 3])) for i in range(3))
    min_edge_squared = min(_norm2(_sub(triangle[i], triangle[(i + 1) % 3])) for i in range(3))
    if min_edge_squared <= Fraction.from_float(MIN_EDGE_LENGTH_MM) ** 2:
        return False
    return _norm2(normal) > Fraction.from_float(MIN_TRIANGLE_QUALITY) ** 2 * max_edge_squared**2


def _power_to_bernstein(power: tuple[Fraction, ...], degree: int) -> tuple[Fraction, ...]:
    padded = power + (Fraction(0),) * max(0, degree + 1 - len(power))
    return tuple(
        sum(
            (padded[i] * Fraction(math.comb(k, i), math.comb(degree, i)) for i in range(k + 1)),
            Fraction(0),
        )
        for k in range(degree + 1)
    )


def _cross_poly(
    first: tuple[tuple[Fraction, ...], ...], second: tuple[tuple[Fraction, ...], ...]
) -> tuple[tuple[Fraction, ...], ...]:
    return tuple(
        _sub_poly_scalar(_convolve(first[i], second[j]), _convolve(first[j], second[i]))
        for i, j in ((1, 2), (2, 0), (0, 1))
    )


def _dot_poly(
    first: tuple[tuple[Fraction, ...], ...], second: tuple[tuple[Fraction, ...], ...]
) -> tuple[Fraction, ...]:
    result: tuple[Fraction, ...] = (Fraction(0),)
    for a, b in zip(first, second, strict=True):
        result = _add_poly(result, _convolve(a, b))
    return result


def _sub_poly(
    first: tuple[Point, Point], second: tuple[Point, Point]
) -> tuple[tuple[Fraction, ...], ...]:
    return tuple((second[0][i] - first[0][i], second[1][i] - first[1][i]) for i in range(3))


def _convolve(first: tuple[Fraction, ...], second: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    result = [Fraction(0)] * (len(first) + len(second) - 1)
    for i, a in enumerate(first):
        for j, b in enumerate(second):
            result[i + j] += a * b
    return tuple(result)


def _add_poly(first: tuple[Fraction, ...], second: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    return tuple(
        (first[i] if i < len(first) else Fraction(0))
        + (second[i] if i < len(second) else Fraction(0))
        for i in range(max(len(first), len(second)))
    )


def _sub_poly_scalar(
    first: tuple[Fraction, ...], second: tuple[Fraction, ...]
) -> tuple[Fraction, ...]:
    return tuple(
        (first[i] if i < len(first) else Fraction(0))
        - (second[i] if i < len(second) else Fraction(0))
        for i in range(max(len(first), len(second)))
    )


def _face_points(
    face: tuple[int, int, int], points: tuple[Point, ...]
) -> tuple[Point, Point, Point]:
    return points[face[0]], points[face[1]], points[face[2]]


def _path_result(status: str, context: ContactBudgetContext, reason: str) -> ContactPathCertificate:
    if status == "INDETERMINATE":
        context.indeterminate_pair_proofs += 1
    return ContactPathCertificate(
        status,
        context.pair_evaluations,
        context.path_pair_proofs,
        context.indeterminate_pair_proofs,
        reason,
    )


def _sweep_pairs(
    triangles: tuple[tuple[Point, ...], ...],
    margin: Fraction,
    parameters: ContactParameters,
    context: ContactBudgetContext,
) -> Iterator[tuple[int, int, bool]]:
    """Exact x sweep; each active-set candidate is budget-accountable.

    A row may contain either one triangle or both endpoint triangles, making
    the latter a conservative swept AABB. Expanding both boxes by the declared
    distance only adds false-positive candidates.
    """
    boxes: list[
        tuple[tuple[Fraction, Fraction, Fraction], tuple[Fraction, Fraction, Fraction]]
    ] = []
    for tri in triangles:
        low = tuple(min(point[axis] for point in tri) - margin for axis in range(3))
        high = tuple(max(point[axis] for point in tri) + margin for axis in range(3))
        boxes.append(((low[0], low[1], low[2]), (high[0], high[1], high[2])))
    order = sorted(range(len(boxes)), key=lambda index: (boxes[index][0][0], index))
    active: list[int] = []
    for current in order:
        low, high = boxes[current]
        active = [index for index in active if boxes[index][1][0] >= low[0]]
        for previous in active:
            _consume_pair(parameters, context)
            context.broadphase_candidate_tests += 1
            other_low, other_high = boxes[previous]
            yz = all(
                other_low[axis] <= high[axis] and low[axis] <= other_high[axis] for axis in (1, 2)
            )
            yield min(previous, current), max(previous, current), yz
        active.append(current)


def _zero() -> Point:
    return Fraction(0), Fraction(0), Fraction(0)


def _sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _add(a: Point, b: Point, scale: Fraction) -> Point:
    return a[0] + scale * b[0], a[1] + scale * b[1], a[2] + scale * b[2]


def _cross(a: Point, b: Point) -> Point:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _dot(a: Point, b: Point) -> Fraction:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm2(a: Point) -> Fraction:
    return _dot(a, a)


def _weighted(points: tuple[Point, ...], weights: tuple[Fraction, ...]) -> Point:
    return tuple(
        sum((points[j][i] * weights[j] for j in range(len(points))), Fraction(0)) for i in range(3)
    )  # type: ignore[return-value]
