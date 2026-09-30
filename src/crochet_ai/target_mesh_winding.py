"""Source-dependent, diagnostic-only whole-component winding proposal."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import cast

from .canonical import jcs_bytes
from .diagnostics import ArtifactValidationError
from .json_types import JSONValue
from .target_mesh_canonical_order import (
    MeshCanonicalOrderError,
    diagnose_indexed_triangle_mesh_canonical_order,
)
from .target_mesh_decode import MeshDecodeError, decode_indexed_triangle_mesh
from .target_mesh_exact_geometry import (
    MeshGeometryError,
    diagnose_indexed_triangle_mesh_exact_geometry,
)
from .target_mesh_pair_relations import (
    MeshPairRelationsError,
    diagnose_indexed_triangle_mesh_pair_relations,
)
from .target_mesh_topology import (
    TOPOLOGY_VERSION,
    MeshTopologyError,
    diagnose_indexed_triangle_mesh,
)
from .target_mesh_volume import (
    MeshVolumeError,
    diagnose_indexed_triangle_mesh_signed_six_volume,
)
from .v0_numeric_profile import (
    NumericalGeometryProfileError,
    V0NumericProfile,
    resolve_v0_numeric_profile,
)

WINDING_STATUS = "WINDING_PROPOSAL_DIAGNOSTIC_ONLY"
WINDING_VERSION = "1.0.0"
_HASH_DOMAIN = b"TARGET_MESH_WINDING_PROPOSAL_DIAGNOSTIC_V1\0"


class MeshWindingError(ValueError):
    """The source cannot safely support a winding proposal."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class WindingComponent:
    source_face_indices: tuple[int, ...]
    reference_vertex_index: int | None
    signed_six_volume_numerator_mm3: str | None
    signed_six_volume_denominator_mm3: str | None
    volume_status: str
    decision: str
    event: str


@dataclass(frozen=True, slots=True)
class WindingProposal:
    status: str
    algorithm_version: str
    source_sha256: str
    parser_name: str
    parser_version: str
    diagnostic_sha256: str
    media_type: str
    coordinate_frame_id: str
    numerical_profile_id: str
    numerical_profile_version: str
    numerical_profile_record_sha256: str
    topology_diagnostic_sha256: str
    ordering_diagnostic_sha256: str
    exact_geometry_diagnostic_sha256: str
    pair_relations_diagnostic_sha256: str
    volume_diagnostic_sha256: str | None
    max_bytes: int
    max_vertices: int
    max_faces: int
    max_vertex_pairs: int
    max_face_pairs: int
    required_vertex_pairs: int
    vertex_pair_work: int
    face_pair_work: int
    derived_vertices_mm: tuple[tuple[float, float, float], ...]
    proposed_faces: tuple[tuple[int, int, int], ...]
    source_to_proposed_vertex_indices: tuple[int, ...]
    proposed_to_source_vertex_indices: tuple[int, ...]
    source_to_proposed_face_indices: tuple[int, ...]
    proposed_to_source_face_indices: tuple[int, ...]
    components: tuple[WindingComponent, ...]
    unresolved_gates: tuple[str, ...]


def _positive_budget(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MeshWindingError(f"winding.{name}_invalid")


def _cyclic_min(face: tuple[int, int, int]) -> tuple[int, int, int]:
    least = face.index(min(face))
    return (face[least], face[(least + 1) % 3], face[(least + 2) % 3])


def propose_indexed_triangle_mesh_winding(
    raw_bytes: bytes,
    *,
    media_type: str,
    expected_coordinate_frame_id: str,
    profile: V0NumericProfile,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
    max_vertex_pairs: int,
    max_face_pairs: int,
) -> WindingProposal:
    """Recompute all evidence and return a non-mutating whole-component proposal.

    Pair work is bounded by n(n-1)/2 face relations and vertex-diameter work by
    v(v-1)/2 exact pairs. Both aggregate bounds are checked before those stages.
    This diagnostic makes no V0, canonical identity, or physical-validity claim.
    """
    for name, value in (("max_bytes", max_bytes), ("max_vertices", max_vertices),
                        ("max_faces", max_faces), ("max_vertex_pairs", max_vertex_pairs),
                        ("max_face_pairs", max_face_pairs)):
        _positive_budget(name, value)
    if type(profile) is not V0NumericProfile:
        raise MeshWindingError("winding.profile_invalid")
    try:
        if resolve_v0_numeric_profile(profile.profile_id) != profile:
            raise MeshWindingError("winding.profile_mismatch")
    except NumericalGeometryProfileError as error:
        raise MeshWindingError("winding.profile_unresolved") from error
    try:
        decoded = decode_indexed_triangle_mesh(
            raw_bytes, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
        topology = diagnose_indexed_triangle_mesh(
            raw_bytes, decoded, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
        if topology.issues or topology.orientable is not True:
            raise MeshWindingError("winding.topology_invalid")
        geometry = diagnose_indexed_triangle_mesh_exact_geometry(
            raw_bytes, decoded, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
        if geometry.coincident_vertex_groups or geometry.zero_area_faces:
            raise MeshWindingError("winding.geometry_degenerate_or_coincident")
        ordering = diagnose_indexed_triangle_mesh_canonical_order(
            raw_bytes, decoded, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
    except MeshWindingError:
        raise
    except (MeshDecodeError, ArtifactValidationError, MeshTopologyError,
            MeshGeometryError, MeshCanonicalOrderError) as error:
        raise MeshWindingError("winding.source_or_index_topology_invalid") from error

    face_count = len(decoded.faces)
    required_face_pairs = face_count * (face_count - 1) // 2
    if required_face_pairs > max_face_pairs:
        raise MeshWindingError("winding.face_pair_budget_exhausted")

    boundary_counts: list[int] = []
    for component_faces in topology.component_face_indices:
        edge_counts: dict[tuple[int, int], int] = {}
        for face_index in component_faces:
            a, b, c = decoded.faces[face_index]
            for left, right in ((a, b), (b, c), (c, a)):
                edge = (min(left, right), max(left, right))
                edge_counts[edge] = edge_counts.get(edge, 0) + 1
        boundary_counts.append(sum(count == 1 for count in edge_counts.values()))
    has_open = any(count > 0 for count in boundary_counts)
    has_closed = any(count == 0 for count in boundary_counts)
    if has_open and has_closed:
        raise MeshWindingError("winding.mixed_open_closed_volume_unsupported")
    all_closed = has_closed
    vertex_count = len(decoded.vertices_mm)
    required_vertex_pairs = vertex_count * (vertex_count - 1) // 2
    if all_closed and required_vertex_pairs > max_vertex_pairs:
        raise MeshWindingError("winding.vertex_pair_budget_exhausted")

    try:
        relations = diagnose_indexed_triangle_mesh_pair_relations(
            raw_bytes, decoded, topology, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
            max_face_pairs_evaluated=max_face_pairs,
        )
    except MeshPairRelationsError as error:
        raise MeshWindingError("winding.face_relations_invalid") from error
    expected_pairs = {(left, right) for left in range(len(decoded.faces))
                      for right in range(left + 1, len(decoded.faces))}
    if (relations.face_pairs_evaluated != len(expected_pairs)
            or len(relations.relations) != len(expected_pairs)
            or {item.face_indices for item in relations.relations} != expected_pairs):
        raise MeshWindingError("winding.face_relations_incomplete")
    if any(relation.forbidden for relation in relations.relations):
        raise MeshWindingError("winding.forbidden_original_face_contact")

    volume = None
    vertex_pair_work = 0
    if all_closed:
        try:
            volume = diagnose_indexed_triangle_mesh_signed_six_volume(
                raw_bytes, decoded, topology, profile,
                media_type=media_type,
                expected_coordinate_frame_id=expected_coordinate_frame_id,
                max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
                max_vertex_pairs_evaluated=max_vertex_pairs,
            )
        except MeshVolumeError as error:
            raise MeshWindingError("winding.volume_unreliable_or_invalid") from error
        if (len(volume.components) != len(topology.component_face_indices)
                or {item.face_indices for item in volume.components}
                != set(topology.component_face_indices)):
            raise MeshWindingError("winding.volume_components_incomplete")
        vertex_pair_work = volume.vertex_pairs_evaluated
        if any(component.status != "ALGEBRAIC_SIGN_STABLE" for component in volume.components):
            raise MeshWindingError("winding.orientation_indeterminate")

    flips: set[int] = set()
    source_component_map: list[WindingComponent] = []
    volume_by_faces = {item.face_indices: item for item in volume.components} if volume else {}
    for source_faces in topology.component_face_indices:
        closed = all_closed
        diagnostic = volume_by_faces.get(source_faces)
        event = "OPEN_ORIENTATION_NOT_NORMALIZED" if not closed else "KEEP"
        if diagnostic is not None:
            if diagnostic.decision == (
                "ALGEBRAIC_NEGATIVE_SIGN_POTENTIAL_WHOLE_COMPONENT_REVERSAL_ONLY"
            ):
                event = "WHOLE_COMPONENT_REVERSAL"
                flips.update(source_faces)
            elif diagnostic.decision != "ALGEBRAIC_POSITIVE_SIGN_NO_OUTWARD_CLAIM":
                raise MeshWindingError("winding.orientation_indeterminate")
        source_component_map.append(WindingComponent(
            source_face_indices=source_faces,
            reference_vertex_index=diagnostic.reference_vertex_index if diagnostic else None,
            signed_six_volume_numerator_mm3=(
                diagnostic.signed_six_volume_numerator_mm3 if diagnostic else None
            ),
            signed_six_volume_denominator_mm3=(
                diagnostic.signed_six_volume_denominator_mm3 if diagnostic else None
            ),
            volume_status=diagnostic.status if diagnostic else "OPEN_NOT_EVALUATED",
            decision=diagnostic.decision if diagnostic else "NO_REVERSAL",
            event=event,
        ))

    # Build the final order after reversal; source-face mapping follows each source face.
    proposed_by_source: list[tuple[int, int, int]] = []
    for face_index, face in enumerate(decoded.faces):
        mapped = (
            ordering.source_to_derived_vertex_indices[face[0]],
            ordering.source_to_derived_vertex_indices[face[1]],
            ordering.source_to_derived_vertex_indices[face[2]],
        )
        if face_index in flips:
            mapped = (mapped[0], mapped[2], mapped[1])
        proposed_by_source.append(_cyclic_min(mapped))
    ordered_sources = tuple(sorted(range(face_count), key=lambda i: proposed_by_source[i]))
    source_to_face = [0] * face_count
    for proposed_index, source_index in enumerate(ordered_sources):
        source_to_face[source_index] = proposed_index
    unresolved = (
        "robust_backend_certification_gap",
        "v0_threshold_admission_not_performed",
        "V0_profile_acceptance_and_normalization_record",
        "canonical_mesh_identity",
        "physical_validation",
    )
    payload: JSONValue = {
        "status": WINDING_STATUS, "algorithm_version": WINDING_VERSION,
        "source_sha256": decoded.source_sha256, "media_type": media_type,
        "parser_name": decoded.parser_name, "parser_version": decoded.parser_version,
        "coordinate_frame_id": expected_coordinate_frame_id,
        "profile": {"id": profile.profile_id, "version": profile.profile_version,
                    "record_sha256": profile.record_sha256},
        "versions": {"topology": TOPOLOGY_VERSION,
                     "ordering": ordering.algorithm_version,
                     "exact_geometry": geometry.algorithm_version,
                     "pair_relations": relations.algorithm_version,
                     "volume": volume.algorithm_version if volume else None},
        "topology": topology.diagnostic_sha256, "ordering": ordering.diagnostic_sha256,
        "geometry": geometry.diagnostic_sha256, "relations": relations.diagnostic_sha256,
        "volume": volume.diagnostic_sha256 if volume else None,
        "budgets": {"max_bytes": max_bytes, "max_vertices": max_vertices,
                    "max_faces": max_faces, "max_vertex_pairs": max_vertex_pairs,
                    "max_face_pairs": max_face_pairs,
                    "required_vertex_pairs": required_vertex_pairs,
                    "vertex_pair_work": vertex_pair_work,
                    "face_pair_work": required_face_pairs},
        "vertices": [list(point) for point in ordering.derived_vertices_mm],
        "faces": [list(proposed_by_source[index]) for index in ordered_sources],
        "source_to_proposed_vertex_indices": list(ordering.source_to_derived_vertex_indices),
        "proposed_to_source_vertex_indices": list(ordering.derived_to_source_vertex_indices),
        "source_to_proposed_face_indices": cast(JSONValue, source_to_face),
        "proposed_to_source_face_indices": list(ordered_sources),
        "components": [{"source_face_indices": list(item.source_face_indices),
                        "reference_vertex_index": item.reference_vertex_index,
                        "signed_six_volume_numerator_mm3": item.signed_six_volume_numerator_mm3,
                        "signed_six_volume_denominator_mm3": item.signed_six_volume_denominator_mm3,
                        "volume_status": item.volume_status, "decision": item.decision,
                        "event": item.event} for item in source_component_map],
        "unresolved_gates": list(unresolved),
    }
    return WindingProposal(
        status=WINDING_STATUS, algorithm_version=WINDING_VERSION,
        source_sha256=decoded.source_sha256,
        diagnostic_sha256=sha256(_HASH_DOMAIN + jcs_bytes(payload)).hexdigest(),
        parser_name=decoded.parser_name, parser_version=decoded.parser_version,
        media_type=media_type, coordinate_frame_id=expected_coordinate_frame_id,
        numerical_profile_id=profile.profile_id, numerical_profile_version=profile.profile_version,
        numerical_profile_record_sha256=profile.record_sha256,
        topology_diagnostic_sha256=topology.diagnostic_sha256,
        ordering_diagnostic_sha256=ordering.diagnostic_sha256,
        exact_geometry_diagnostic_sha256=geometry.diagnostic_sha256,
        pair_relations_diagnostic_sha256=relations.diagnostic_sha256,
        volume_diagnostic_sha256=volume.diagnostic_sha256 if volume else None,
        max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        max_vertex_pairs=max_vertex_pairs, max_face_pairs=max_face_pairs,
        required_vertex_pairs=required_vertex_pairs,
        vertex_pair_work=vertex_pair_work, face_pair_work=required_face_pairs,
        derived_vertices_mm=ordering.derived_vertices_mm,
        proposed_faces=tuple(proposed_by_source[index] for index in ordered_sources),
        source_to_proposed_vertex_indices=ordering.source_to_derived_vertex_indices,
        proposed_to_source_vertex_indices=ordering.derived_to_source_vertex_indices,
        source_to_proposed_face_indices=tuple(source_to_face),
        proposed_to_source_face_indices=ordered_sources,
        components=tuple(source_component_map), unresolved_gates=unresolved,
    )
