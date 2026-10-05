"""Fail-closed V0 admission for supported mesh profiles under numeric v2."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from itertools import combinations
from typing import Any, cast

from .canonical import CanonicalProfile, canonical_hash, jcs_bytes
from .certified_orientation import (
    BACKEND as ORIENTATION_BACKEND,
)
from .certified_orientation import (
    VERSION as ORIENTATION_VERSION,
)
from .certified_orientation import (
    OrientationError,
    orientation2d,
    orientation3d,
)
from .exact_triangle_distance import triangle_distance_squared
from .exact_triangle_relation import ExactTriangleRelationError
from .json_types import JSONValue
from .models import DesignSpec, MaterialProfile
from .schema import validate_schema
from .target_mesh_adjacent_clearance import (
    MeshAdjacentClearanceError,
    diagnose_indexed_triangle_mesh_adjacent_clearance,
)
from .target_mesh_canonical_order import diagnose_indexed_triangle_mesh_canonical_order
from .target_mesh_decode import MESH_MEDIA_TYPE, decode_indexed_triangle_mesh
from .target_mesh_diameter import diagnose_indexed_triangle_mesh_diameter
from .target_mesh_exact_geometry import diagnose_indexed_triangle_mesh_exact_geometry
from .target_mesh_openings import TargetMeshOpeningError, diagnose_target_mesh_openings
from .target_mesh_pair_relations import diagnose_indexed_triangle_mesh_pair_relations
from .target_mesh_topology import diagnose_indexed_triangle_mesh
from .v0_adjacent_profile import PROFILE_ID, resolve_v0_adjacent_numeric_profile
from .validation import SemanticValidator

VERSION = "1.0.0"
_MESH_DOMAIN = b"Crochet.AI\0INDEXED_TRIANGLE_MESH_CANONICAL_JSON_V1\0"
_EVIDENCE_DOMAIN = b"V0_CLOSED_MESH_PREFLIGHT_V2\0"
_CLOSED_PROFILE = "V0_AMIGURUMI_CLOSED_SURFACE_V1"
_OPEN_PROFILE = "V0_AMIGURUMI_DECLARED_BOUNDARY_SURFACE_V1"
_GARMENT_PROFILE = "V0_GARMENT_DECLARED_BOUNDARY_SURFACE_V1"


class V0MeshPreflightError(ValueError):
    """A mandatory V0 predicate failed or cannot be established."""

    def __init__(self, reason: str, *, outcome: str = "FAIL", code: str = "E_INPUT") -> None:
        self.reason = reason
        self.outcome = outcome
        self.code = code
        super().__init__(f"{outcome}/{code}: {reason}")


@dataclass(frozen=True, slots=True)
class V0MeshBudgets:
    max_bytes: int
    max_vertices: int
    max_faces: int
    max_vertex_pairs: int
    max_face_pairs: int
    max_distance_piece_pairs: int
    max_lambda_bits: int
    max_orientation_tests: int
    max_openings: int
    max_landmark_refs: int
    max_landmarks: int
    max_landmark_edge_tests: int

    def validate(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise V0MeshPreflightError(f"budget.{name}_invalid", outcome="INDETERMINATE")


@dataclass(frozen=True, slots=True)
class V0MeshResult:
    outcome: str
    implementation_version: str
    design_spec_sha256: str
    material_profile_sha256: str
    source_sha256: str
    coordinate_frame_id: str
    domain_profile_id: str
    normalized_mesh_sha256: str
    normalized_mesh_jcs: str
    parser_name: str
    parser_version: str
    numerical_profile_id: str
    numerical_profile_version: str
    numerical_profile_sha256: str
    squared_diameter_numerator_mm2: str
    squared_diameter_denominator_mm2: str
    source_to_normalized_vertex_indices: tuple[int, ...]
    normalized_to_source_vertex_indices: tuple[int, ...]
    source_to_normalized_face_indices: tuple[int, ...]
    normalized_to_source_face_indices: tuple[int, ...]
    reversed_source_components: tuple[tuple[int, ...], ...]
    volume_reference_source_vertices: tuple[int, ...]
    open_source_components: tuple[tuple[int, ...], ...]
    normalization_events: tuple[tuple[str, str, str], ...]
    predicate_evidence: tuple[tuple[str, str], ...]
    threshold_evidence: tuple[tuple[str, str, str], ...]
    metric_evidence: tuple[tuple[str, str, str, str], ...]
    budgets: V0MeshBudgets
    predicate_backend: str
    predicate_backend_version: str
    certified_orientation_tests: int
    exact_orientation_fallbacks: int
    evidence_sha256: str


def _point(value: tuple[float, float, float]) -> tuple[Fraction, Fraction, Fraction]:
    return (Fraction.from_float(value[0]), Fraction.from_float(value[1]),
            Fraction.from_float(value[2]))


def _square_distance(
    left: tuple[Fraction, Fraction, Fraction],
    right: tuple[Fraction, Fraction, Fraction],
) -> Fraction:
    return sum(((left[i] - right[i]) ** 2 for i in range(3)), Fraction(0))


def _difference(
    left: tuple[Fraction, Fraction, Fraction],
    right: tuple[Fraction, Fraction, Fraction],
) -> tuple[Fraction, Fraction, Fraction]:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _cross_squared(
    a: tuple[Fraction, Fraction, Fraction],
    b: tuple[Fraction, Fraction, Fraction],
    c: tuple[Fraction, Fraction, Fraction],
) -> Fraction:
    u = tuple(b[i] - a[i] for i in range(3))
    v = tuple(c[i] - a[i] for i in range(3))
    cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
             u[0] * v[1] - u[1] * v[0])
    return sum((axis * axis for axis in cross), Fraction(0))


def _determinant(
    a: tuple[Fraction, Fraction, Fraction],
    b: tuple[Fraction, Fraction, Fraction],
    c: tuple[Fraction, Fraction, Fraction],
) -> Fraction:
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


def _sign(value: Fraction) -> int:
    return (value > 0) - (value < 0)


def _certify_relations(
    vertices: tuple[tuple[float, float, float], ...],
    faces: tuple[tuple[int, int, int], ...],
    relation_pairs: tuple[tuple[int, int, bool], ...],
) -> tuple[int, int]:
    """Cross-check every source vertex/plane and coplanar edge sign."""
    count = 0
    fallbacks = 0
    try:
        for first_index, second_index, coplanar in relation_pairs:
            plane_signs: list[int] = []
            for plane_index, point_index in ((first_index, second_index),
                                             (second_index, first_index)):
                plane_ids = faces[plane_index]
                for vertex_index in faces[point_index]:
                    a, b, c = (vertices[index] for index in plane_ids)
                    p = vertices[vertex_index]
                    result = orientation3d(a, b, c, p, max_exact_fallbacks=1)
                    qa, qb, qc, qp = (_point(item) for item in (a, b, c, p))
                    exact = _determinant(
                        _difference(qb, qa), _difference(qc, qa), _difference(qp, qa),
                    )
                    if result.sign != _sign(exact):
                        raise V0MeshPreflightError(
                            "geometry.orientation_backend_disagreement",
                            outcome="INDETERMINATE",
                        )
                    plane_signs.append(result.sign)
                    count += 1
                    fallbacks += result.exact_fallback_count
            if coplanar != all(sign == 0 for sign in plane_signs):
                raise V0MeshPreflightError(
                    "geometry.coplanarity_backend_disagreement",
                    outcome="INDETERMINATE",
                )
            if not coplanar:
                continue
            for plane_index, point_index in ((first_index, second_index),
                                             (second_index, first_index)):
                plane_ids = faces[plane_index]
                qa, qb, qc = (_point(vertices[index]) for index in plane_ids)
                u = _difference(qb, qa)
                v = _difference(qc, qa)
                normal = (u[1] * v[2] - u[2] * v[1],
                          u[2] * v[0] - u[0] * v[2],
                          u[0] * v[1] - u[1] * v[0])
                drop = max(range(3), key=lambda axis: abs(normal[axis]))
                axes = tuple(axis for axis in range(3) if axis != drop)
                for edge in range(3):
                    left = vertices[plane_ids[edge]]
                    right = vertices[plane_ids[(edge + 1) % 3]]
                    for vertex_index in faces[point_index]:
                        point = vertices[vertex_index]
                        result2 = orientation2d(
                            (left[axes[0]], left[axes[1]]),
                            (right[axes[0]], right[axes[1]]),
                            (point[axes[0]], point[axes[1]]),
                            max_exact_fallbacks=1,
                        )
                        lx = Fraction.from_float(left[axes[0]])
                        ly = Fraction.from_float(left[axes[1]])
                        rx = Fraction.from_float(right[axes[0]])
                        ry = Fraction.from_float(right[axes[1]])
                        px = Fraction.from_float(point[axes[0]])
                        py = Fraction.from_float(point[axes[1]])
                        exact2 = (rx - lx) * (py - ly) - (ry - ly) * (px - lx)
                        if result2.sign != _sign(exact2):
                            raise V0MeshPreflightError(
                                "geometry.orientation_backend_disagreement",
                                outcome="INDETERMINATE",
                            )
                        count += 1
                        fallbacks += result2.exact_fallback_count
    except OrientationError as error:
        raise V0MeshPreflightError(
            "geometry.orientation_backend_uncertified", outcome="INDETERMINATE"
        ) from error
    return count, fallbacks


def _mesh_value(frame_id: str, vertices: tuple[tuple[float, float, float], ...],
                faces: tuple[tuple[int, int, int], ...]) -> JSONValue:
    return {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {"length_unit": "MILLIMETER", "handedness": "RIGHT_HANDED",
                              "coordinate_frame_id": frame_id},
        "vertices": [{"position_mm": list(point)} for point in vertices],
        "faces": [{"vertex_indices": list(face)} for face in faces],
    }


def _mesh_hash(value: JSONValue) -> str:
    return sha256(_MESH_DOMAIN + jcs_bytes(value)).hexdigest()


def _component_closed(
    faces: tuple[tuple[int, int, int], ...], component: tuple[int, ...]
) -> bool:
    edge_count: dict[tuple[int, int], int] = {}
    for face_index in component:
        a, b, c = faces[face_index]
        for left, right in ((a, b), (b, c), (c, a)):
            edge = (min(left, right), max(left, right))
            edge_count[edge] = edge_count.get(edge, 0) + 1
    return all(count == 2 for count in edge_count.values())


def inspect_v0_mesh_v2(
    design_spec: DesignSpec,
    raw_bytes: bytes,
    *,
    material_profile: MaterialProfile | None,
    budgets: V0MeshBudgets,
) -> V0MeshResult:
    """Admit a complete V0 v2 mesh check; physical state is separate."""
    budgets.validate()
    if not isinstance(design_spec, DesignSpec) or not isinstance(raw_bytes, bytes):
        raise V0MeshPreflightError("input.model_or_bytes_invalid")
    design = cast(dict[str, Any], design_spec.to_dict())
    supplied: dict[str | tuple[str, int], dict[str, Any]] = {}
    if material_profile is not None:
        if not isinstance(material_profile, MaterialProfile):
            raise V0MeshPreflightError("input.material_model_invalid")
        material = cast(dict[str, Any], material_profile.to_dict())
        supplied[(material["profile_id"], material["revision"])] = material
    validator = SemanticValidator(material_profiles=supplied)
    if not validator.validate_design_spec(design).ok:
        raise V0MeshPreflightError("input.design_spec_invalid")
    binding = design["material_profile"]
    if binding["binding_type"] == "INLINE":
        resolved_material = binding["profile"]
    else:
        resolved_material = supplied.get((binding["profile_id"], binding["revision"]))
    if resolved_material is None:
        raise V0MeshPreflightError("input.material_profile_unresolved")
    material_hash = canonical_hash(resolved_material, CanonicalProfile.MATERIAL_PROFILE)
    target = design["target_geometry"]
    domain_profile = target["preflight_profile_id"]
    project = design["project_type"]
    if (design["schema_version"] != "1.1.0"
            or target["geometry_type"] != "MESH_3D"
            or target["preflight_numerical_profile_id"] != PROFILE_ID
            or (project, domain_profile) not in {
                ("AMIGURUMI_3D", _CLOSED_PROFILE),
                ("AMIGURUMI_3D", _OPEN_PROFILE),
                ("GARMENT", _GARMENT_PROFILE),
            }):
        raise V0MeshPreflightError("profile.unsupported", outcome="INDETERMINATE",
                                   code="E_UNSUPPORTED_FEATURE")
    artifact = target["artifact"]
    frame_id = target["coordinate_frame"]["coordinate_frame_id"]
    if (artifact["media_type"] != MESH_MEDIA_TYPE
            or artifact["sha256"] != sha256(raw_bytes).hexdigest()):
        raise V0MeshPreflightError("input.source_binding_invalid")
    expected = target["topology_expectation"]
    closed_target = domain_profile == _CLOSED_PROFILE
    if closed_target != (expected["boundary_policy"] == "FORBIDDEN"):
        raise V0MeshPreflightError("profile.boundary_expectation_invalid")
    if closed_target != (expected["expected_boundary_components"] == 0):
        raise V0MeshPreflightError("profile.boundary_expectation_invalid")
    profile = resolve_v0_adjacent_numeric_profile(PROFILE_ID)
    common = dict(media_type=MESH_MEDIA_TYPE, expected_coordinate_frame_id=frame_id,
                  max_bytes=budgets.max_bytes, max_vertices=budgets.max_vertices,
                  max_faces=budgets.max_faces)
    try:
        decoded = decode_indexed_triangle_mesh(raw_bytes, **common)
        topology = diagnose_indexed_triangle_mesh(raw_bytes, decoded, **common)
        exact = diagnose_indexed_triangle_mesh_exact_geometry(raw_bytes, decoded, **common)
        ordering = diagnose_indexed_triangle_mesh_canonical_order(raw_bytes, decoded, **common)
        diameter = diagnose_indexed_triangle_mesh_diameter(
            raw_bytes, decoded, **common, max_vertex_pairs_evaluated=budgets.max_vertex_pairs)
    except ValueError as error:
        raise V0MeshPreflightError(
            "input.mesh_diagnostic_unavailable", outcome="INDETERMINATE"
        ) from error
    if topology.issues or topology.orientable is not True:
        raise V0MeshPreflightError("geometry.topology_invalid")
    if (len(topology.component_face_indices) != expected["expected_connected_components"]
            or len(topology.boundary_loops) != expected["expected_boundary_components"]):
        raise V0MeshPreflightError("geometry.component_or_boundary_mismatch")
    if closed_target and topology.boundary_edge_count:
        raise V0MeshPreflightError("geometry.boundary_forbidden")
    if exact.coincident_vertex_groups or exact.zero_area_faces:
        raise V0MeshPreflightError("geometry.exact_degeneracy")
    diameter_squared = Fraction(int(diameter.squared_diameter_numerator_mm2),
                                int(diameter.squared_diameter_denominator_mm2))
    if diameter_squared <= 0:
        raise V0MeshPreflightError("geometry.zero_scale")
    positions = tuple(_point(point) for point in decoded.vertices_mm)
    coordinate_limit = (
        Fraction.from_float(profile.thresholds.coordinate_distance_normalized_max) ** 2
        * diameter_squared
    )
    area_limit = (
        Fraction.from_float(profile.thresholds.triangle_area2_normalized_max) ** 2
        * diameter_squared ** 2
    )
    vertex_distances = tuple(
        _square_distance(positions[a], positions[b])
        for a, b in combinations(range(len(positions)), 2)
    )
    if any(distance <= coordinate_limit for distance in vertex_distances):
        raise V0MeshPreflightError("geometry.coincident_vertex")
    face_areas_squared = tuple(
        _cross_squared(positions[face[0]], positions[face[1]], positions[face[2]])
        for face in decoded.faces
    )
    if any(area <= area_limit for area in face_areas_squared):
        raise V0MeshPreflightError("geometry.degenerate_face")
    try:
        relations = diagnose_indexed_triangle_mesh_pair_relations(
            raw_bytes, decoded, topology, **common,
            max_face_pairs_evaluated=budgets.max_face_pairs)
    except ValueError as error:
        raise V0MeshPreflightError(
            "geometry.relations_unavailable", outcome="INDETERMINATE"
        ) from error
    if any(relation.forbidden for relation in relations.relations):
        raise V0MeshPreflightError("geometry.intersection")
    required_face_pairs = {
        (a, b) for a, b in combinations(range(len(decoded.faces)), 2)
    }
    if (relations.face_pairs_evaluated != len(required_face_pairs)
            or len(relations.relations) != len(required_face_pairs)
            or {item.face_indices for item in relations.relations} != required_face_pairs):
        raise V0MeshPreflightError(
            "geometry.relations_incomplete", outcome="INDETERMINATE"
        )
    required_orientation_tests = 6 * len(relations.relations) + 18 * sum(
        relation.coplanar for relation in relations.relations
    )
    if required_orientation_tests > budgets.max_orientation_tests:
        raise V0MeshPreflightError(
            "geometry.orientation_budget_exhausted", outcome="INDETERMINATE"
        )
    certified_tests, exact_fallbacks = _certify_relations(
        decoded.vertices_mm, decoded.faces,
        tuple((item.face_indices[0], item.face_indices[1], item.coplanar)
              for item in relations.relations),
    )
    if certified_tests != required_orientation_tests:
        raise V0MeshPreflightError(
            "geometry.orientation_evidence_incomplete", outcome="INDETERMINATE"
        )
    clearance_limit = (
        Fraction.from_float(profile.thresholds.near_contact_distance_normalized_max) ** 2
        * diameter_squared
    )
    component_of = {
        face: component
        for component, faces in enumerate(topology.component_face_indices)
        for face in faces
    }
    nonadjacent_distances: list[Fraction] = []
    for relation in relations.relations:
        a, b = relation.face_indices
        if relation.shared_indexed_vertex_count:
            continue
        first_ids, second_ids = decoded.faces[a], decoded.faces[b]
        first = (positions[first_ids[0]], positions[first_ids[1]], positions[first_ids[2]])
        second = (positions[second_ids[0]], positions[second_ids[1]], positions[second_ids[2]])
        try:
            distance = triangle_distance_squared(first, second)
        except ExactTriangleRelationError as error:
            raise V0MeshPreflightError(
                "geometry.nonadjacent_distance_uncertified", outcome="INDETERMINATE"
            ) from error
        nonadjacent_distances.append(distance)
        if distance <= clearance_limit:
            code = "E_UNSUPPORTED_FEATURE" if component_of[a] != component_of[b] else "E_INPUT"
            raise V0MeshPreflightError("geometry.contact_unsupported", code=code)
    try:
        adjacent = diagnose_indexed_triangle_mesh_adjacent_clearance(
            raw_bytes, profile=profile, adjacent_exclusion_zone=target["adjacent_exclusion_zone"],
            **common, max_vertex_pairs=budgets.max_vertex_pairs,
            max_face_pairs=budgets.max_face_pairs,
            max_distance_piece_pairs=budgets.max_distance_piece_pairs,
            max_lambda_bits=budgets.max_lambda_bits)
    except MeshAdjacentClearanceError as error:
        raise V0MeshPreflightError("geometry.adjacent_clearance_unavailable",
                                   outcome="INDETERMINATE") from error
    expected_adjacent = {
        (a, b) for a, b in required_face_pairs
        if set(decoded.faces[a]).intersection(decoded.faces[b])
    }
    if (adjacent.required_face_pairs != len(required_face_pairs)
            or adjacent.adjacent_face_pair_count != len(expected_adjacent)
            or {item.source_face_indices for item in adjacent.pairs} != expected_adjacent):
        raise V0MeshPreflightError(
            "geometry.adjacent_evidence_incomplete", outcome="INDETERMINATE"
        )
    if adjacent.adjacent_face_pair_count != len(adjacent.pairs) or any(
        pair.normalized_threshold_state != "ABOVE_THRESHOLD" for pair in adjacent.pairs
    ):
        raise V0MeshPreflightError("geometry.adjacent_contact")
    reversed_components: list[tuple[int, ...]] = []
    reverse_faces: set[int] = set()
    volumes6: list[Fraction] = []
    reference_vertices: list[int] = []
    volume_limit = Fraction.from_float(profile.thresholds.volume6_normalized_min_exclusive)
    ordered_components = tuple(sorted(
        topology.component_face_indices,
        key=lambda component: min(
            ordering.source_to_derived_vertex_indices[vertex]
            for face_index in component for vertex in decoded.faces[face_index]
        ),
    ))
    open_components: list[tuple[int, ...]] = []
    for component in ordered_components:
        if not _component_closed(decoded.faces, component):
            open_components.append(component)
            continue
        vertex = min(
            (index for face_index in component for index in decoded.faces[face_index]),
            key=ordering.source_to_derived_vertex_indices.__getitem__,
        )
        reference_vertices.append(vertex)
        reference = positions[vertex]
        volume6 = Fraction(0)
        for face_index in sorted(
            component, key=ordering.source_to_derived_face_indices.__getitem__
        ):
            a, b, c = decoded.faces[face_index]
            pa, pb, pc = positions[a], positions[b], positions[c]
            va = (pa[0] - reference[0], pa[1] - reference[1], pa[2] - reference[2])
            vb = (pb[0] - reference[0], pb[1] - reference[1], pb[2] - reference[2])
            vc = (pc[0] - reference[0], pc[1] - reference[1], pc[2] - reference[2])
            volume6 += _determinant(va, vb, vc)
        if volume6 * volume6 <= volume_limit ** 2 * diameter_squared ** 3:
            raise V0MeshPreflightError("geometry.orientation_indeterminate",
                                       outcome="INDETERMINATE")
        volumes6.append(volume6)
        if volume6 < 0:
            reversed_components.append(component)
            reverse_faces.update(component)
    if domain_profile == _GARMENT_PROFILE and len(open_components) != len(ordered_components):
        raise V0MeshPreflightError("geometry.garment_closed_component")
    opening_hash: str | None = None
    boundary_hash: str | None = None
    if not closed_target:
        try:
            opening = diagnose_target_mesh_openings(
                design_spec, raw_bytes, material_profile=material_profile,
                max_bytes=budgets.max_bytes, max_vertices=budgets.max_vertices,
                max_faces=budgets.max_faces, max_openings=budgets.max_openings,
                max_landmark_refs=budgets.max_landmark_refs,
                max_landmarks=budgets.max_landmarks,
                max_vertex_pairs=budgets.max_vertex_pairs,
                max_landmark_edge_tests=budgets.max_landmark_edge_tests,
            )
        except TargetMeshOpeningError as error:
            raise V0MeshPreflightError(
                "geometry.opening_binding_unavailable", outcome="INDETERMINATE"
            ) from error
        if opening.classification != "UNIQUE":
            raise V0MeshPreflightError("geometry.opening_binding_failed")
        if (opening.source_sha256 != decoded.source_sha256
                or opening.design_spec_sha256 != canonical_hash(
                    design, CanonicalProfile.DESIGN_SPEC, validator=validator
                )
                or opening.profile_sha256 != material_hash
                or opening.numerical_profile_id != profile.profile_id
                or opening.numerical_profile_version != profile.profile_version
                or opening.numerical_profile_sha256 != profile.record_sha256
                or opening.ordering_diagnostic_sha256 != ordering.diagnostic_sha256
                or opening.boundary_loop_count != len(topology.boundary_loops)):
            raise V0MeshPreflightError(
                "geometry.opening_evidence_mismatch", outcome="INDETERMINATE"
            )
        opening_hash = opening.diagnostic_sha256
        boundary_hash = opening.boundary_diagnostic_sha256
    normalized_by_source: list[tuple[int, int, int]] = []
    for source_index, face in enumerate(decoded.faces):
        mapped = tuple(ordering.source_to_derived_vertex_indices[index] for index in face)
        if source_index in reverse_faces:
            mapped = (mapped[0], mapped[2], mapped[1])
        start = mapped.index(min(mapped))
        normalized_by_source.append((mapped[start], mapped[(start + 1) % 3],
                                     mapped[(start + 2) % 3]))
    face_sources = tuple(sorted(
        range(len(normalized_by_source)), key=normalized_by_source.__getitem__
    ))
    normalized_faces = tuple(normalized_by_source[index] for index in face_sources)
    source_to_faces = [0] * len(face_sources)
    for normalized_index, source_index in enumerate(face_sources):
        source_to_faces[source_index] = normalized_index
    ordered_mesh = _mesh_value(frame_id, ordering.derived_vertices_mm, ordering.derived_faces)
    normalized_mesh = _mesh_value(frame_id, ordering.derived_vertices_mm, normalized_faces)
    if not validate_schema("indexed_triangle_mesh", normalized_mesh).ok:
        raise V0MeshPreflightError("normalization.invalid_mesh", outcome="INDETERMINATE")
    ordering_hash = _mesh_hash(ordered_mesh)
    normalized_hash = _mesh_hash(normalized_mesh)
    decoded_hash = _mesh_hash(_mesh_value(frame_id, decoded.vertices_mm, decoded.faces))
    event_list = [
        ("SOURCE_DECODE_V1", decoded.source_sha256, decoded_hash),
        ("CANONICAL_ORDER_V1", decoded_hash, ordering_hash),
    ]
    if reversed_components:
        event_list.append(("WHOLE_COMPONENT_REVERSAL_V1", ordering_hash, normalized_hash))
    events = tuple(event_list)
    evidence_items = [
        ("topology", topology.diagnostic_sha256), ("exact_geometry", exact.diagnostic_sha256),
        ("ordering", ordering.diagnostic_sha256), ("diameter", diameter.diagnostic_sha256),
        ("pair_relations", relations.diagnostic_sha256),
        ("adjacent_clearance", adjacent.diagnostic_sha256),
    ]
    if opening_hash is not None:
        evidence_items.append(("opening_binding", opening_hash))
    if boundary_hash is not None:
        evidence_items.append(("directed_boundaries", boundary_hash))
    evidence = tuple(evidence_items)
    threshold_evidence = (
        ("triangle_area2_normalized_max",
         str(Fraction.from_float(profile.thresholds.triangle_area2_normalized_max)), "<="),
        ("coordinate_distance_normalized_max",
         str(Fraction.from_float(profile.thresholds.coordinate_distance_normalized_max)), "<="),
        ("near_contact_distance_normalized_max",
         str(Fraction.from_float(profile.thresholds.near_contact_distance_normalized_max)), "<="),
        ("volume6_normalized_min_exclusive",
         str(Fraction.from_float(profile.thresholds.volume6_normalized_min_exclusive)), ">"),
        ("landmark_numeric_slack_normalized_max",
         str(Fraction.from_float(profile.thresholds.landmark_numeric_slack_normalized_max)),
         "ADD_TO_DECLARED_TOLERANCE_NOT_APPLICABLE"),
    )
    adjacent_distances = tuple(
        Fraction(int(pair.squared_distance_numerator_mm2),
                 int(pair.squared_distance_denominator_mm2))
        for pair in adjacent.pairs
    )
    metric_values: list[tuple[str, Fraction, str]] = [
        ("squared_diameter", diameter_squared, "mm2"),
        ("minimum_squared_vertex_distance", min(vertex_distances), "mm2"),
        ("minimum_squared_doubled_face_area", min(face_areas_squared), "mm4"),
    ]
    if nonadjacent_distances:
        metric_values.append(("minimum_nonadjacent_squared_distance",
                              min(nonadjacent_distances), "mm2"))
    if adjacent_distances:
        metric_values.append(("minimum_adjacent_squared_residual",
                              min(adjacent_distances), "mm2"))
    metric_values.extend((f"component_{index}_signed_six_volume", value, "mm3")
                         for index, value in enumerate(volumes6))
    metric_evidence = tuple((name, str(value.numerator), str(value.denominator), unit)
                            for name, value, unit in metric_values)
    normalized_mesh_jcs = jcs_bytes(normalized_mesh).decode("utf-8")
    design_hash = canonical_hash(design, CanonicalProfile.DESIGN_SPEC, validator=validator)
    payload: JSONValue = {
        "implementation_version": VERSION, "outcome": "PASS",
        "design_spec_sha256": design_hash,
        "material_profile_sha256": material_hash,
        "source_sha256": decoded.source_sha256, "normalized_mesh_sha256": normalized_hash,
        "coordinate_frame_id": frame_id,
        "normalized_mesh_jcs": normalized_mesh_jcs,
        "parser": {"name": decoded.parser_name, "version": decoded.parser_version},
        "numerical_profile": {"id": profile.profile_id, "version": profile.profile_version,
                              "sha256": profile.record_sha256},
        "domain_profile_id": domain_profile,
        "squared_diameter_mm2": {"numerator": diameter.squared_diameter_numerator_mm2,
                                  "denominator": diameter.squared_diameter_denominator_mm2},
        "source_to_normalized_vertex_indices": list(ordering.source_to_derived_vertex_indices),
        "normalized_to_source_vertex_indices": list(ordering.derived_to_source_vertex_indices),
        "source_to_normalized_face_indices": cast(JSONValue, source_to_faces),
        "normalized_to_source_face_indices": list(face_sources),
        "reversed_source_components": [list(component) for component in reversed_components],
        "open_source_components": [list(component) for component in open_components],
        "volume_reference_source_vertices": cast(JSONValue, reference_vertices),
        "normalization_events": [list(event) for event in events],
        "predicate_evidence": [list(item) for item in evidence],
        "threshold_evidence": [list(item) for item in threshold_evidence],
        "metric_evidence": [list(item) for item in metric_evidence],
        "budgets": cast(JSONValue, {
            name: getattr(budgets, name) for name in budgets.__dataclass_fields__
        }),
        "predicate_backend": {"name": ORIENTATION_BACKEND, "version": ORIENTATION_VERSION,
                              "certified_tests": certified_tests,
                              "required_tests": required_orientation_tests,
                              "exact_fallbacks": exact_fallbacks,
                              "derived_comparisons": "EXACT_BINARY64_RATIONAL_V1"},
    }
    digest = sha256(_EVIDENCE_DOMAIN + jcs_bytes(payload)).hexdigest()
    return V0MeshResult(
        "PASS", VERSION, design_hash, material_hash, decoded.source_sha256,
        frame_id, domain_profile,
        normalized_hash, normalized_mesh_jcs, decoded.parser_name, decoded.parser_version,
        profile.profile_id, profile.profile_version, profile.record_sha256,
        diameter.squared_diameter_numerator_mm2, diameter.squared_diameter_denominator_mm2,
        ordering.source_to_derived_vertex_indices, ordering.derived_to_source_vertex_indices,
        tuple(source_to_faces), face_sources, tuple(reversed_components),
        tuple(reference_vertices), tuple(open_components), events, evidence,
        threshold_evidence, metric_evidence, budgets,
        ORIENTATION_BACKEND, ORIENTATION_VERSION,
        certified_tests, exact_fallbacks, digest)


def inspect_v0_closed_mesh_v2(
    design_spec: DesignSpec,
    raw_bytes: bytes,
    *,
    material_profile: MaterialProfile | None,
    budgets: V0MeshBudgets,
) -> V0MeshResult:
    """Compatibility entry point restricted to the closed amigurumi domain."""
    if not isinstance(design_spec, DesignSpec):
        raise V0MeshPreflightError("input.design_spec_model_invalid")
    target = cast(dict[str, Any], design_spec.to_dict()).get("target_geometry")
    if not isinstance(target, dict) or target.get("preflight_profile_id") != _CLOSED_PROFILE:
        raise V0MeshPreflightError(
            "profile.unsupported", outcome="INDETERMINATE", code="E_UNSUPPORTED_FEATURE"
        )
    return inspect_v0_mesh_v2(
        design_spec, raw_bytes, material_profile=material_profile, budgets=budgets
    )
