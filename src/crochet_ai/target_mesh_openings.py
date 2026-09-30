"""Diagnostic-only binding of declared target openings to mesh boundary loops."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast

from .canonical import CanonicalProfile, canonical_hash, jcs_bytes
from .diagnostics import ArtifactValidationError
from .json_types import JSONValue
from .models import DesignSpec, MaterialProfile
from .target_mesh_boundaries import (
    diagnose_indexed_triangle_mesh_boundaries,
)
from .target_mesh_canonical_order import diagnose_indexed_triangle_mesh_canonical_order
from .target_mesh_decode import (
    MESH_MEDIA_TYPE,
    decode_indexed_triangle_mesh,
)
from .target_mesh_landmarks import (
    BoundaryLandmark,
    diagnose_boundary_landmark_eligibility,
)
from .v0_numeric_profile import resolve_v0_numeric_profile
from .validation import SemanticValidator

STATUS = "OPENING_BINDING_DIAGNOSTIC_ONLY"
VERSION = "1.0.0"
_DOMAIN = b"TARGET_MESH_OPENING_BINDING_DIAGNOSTIC_V1\0"


class TargetMeshOpeningError(ValueError):
    """Input, contract, provenance, or bounded-work rejection."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class OpeningLoopBinding:
    opening_requirement_id: str
    purpose: str
    loop_index: int


@dataclass(frozen=True, slots=True)
class TargetMeshOpeningDiagnostic:
    status: str
    algorithm_version: str
    classification: str
    reason: str | None
    source_sha256: str
    design_spec_sha256: str
    profile_id: str
    profile_revision: int
    profile_sha256: str
    ordering_diagnostic_sha256: str
    boundary_diagnostic_sha256: str
    landmark_diagnostic_sha256: str
    boundary_loop_count: int
    expected_component_count: int
    bindings: tuple[OpeningLoopBinding, ...]
    landmark_classifications: tuple[tuple[str, str, tuple[int, ...]], ...]
    diagnostic_sha256: str


def diagnose_target_mesh_openings(
    design_spec: DesignSpec,
    raw_bytes: bytes,
    *,
    material_profile: MaterialProfile | None = None,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
    max_openings: int,
    max_landmark_refs: int,
    max_landmarks: int,
    max_vertex_pairs: int,
    max_landmark_edge_tests: int,
) -> TargetMeshOpeningDiagnostic:
    """Bind every retained opening to one unique target loop, without a V0 pass claim."""
    if not isinstance(design_spec, DesignSpec):
        raise TargetMeshOpeningError("openings.design_spec_model_required")
    if not isinstance(raw_bytes, bytes):
        raise TargetMeshOpeningError("openings.source_bytes_required")
    value = cast(dict[str, Any], design_spec.to_dict())
    supplied_profiles: dict[str | tuple[str, int], dict[str, Any]] = {}
    if material_profile is not None:
        if not isinstance(material_profile, MaterialProfile):
            raise TargetMeshOpeningError("openings.material_profile_model_invalid")
        profile_value = cast(dict[str, Any], material_profile.to_dict())
        supplied_profiles[(profile_value["profile_id"], profile_value["revision"])] = profile_value
    validator = SemanticValidator(material_profiles=supplied_profiles)
    report = validator.validate_design_spec(value)
    if not report.ok:
        raise TargetMeshOpeningError("openings.design_spec_semantically_invalid")

    target = value["target_geometry"]
    if target.get("geometry_type") != "MESH_3D":
        raise TargetMeshOpeningError("openings.mesh_target_required")
    artifact = target["artifact"]
    if artifact["media_type"] != MESH_MEDIA_TYPE:
        raise TargetMeshOpeningError("openings.asset_media_type_mismatch")
    source_hash = sha256(raw_bytes).hexdigest()
    if artifact["sha256"] != source_hash:
        raise TargetMeshOpeningError("openings.asset_sha256_mismatch")
    frame_id = target["coordinate_frame"]["coordinate_frame_id"]

    openings = value["construction_constraints"]["intentional_openings"]
    remain_open = sorted(
        (opening for opening in openings if opening["closure_expectation"] == "REMAIN_OPEN"),
        key=lambda opening: opening["opening_requirement_id"],
    )
    limits = (
        ("max_bytes", max_bytes), ("max_vertices", max_vertices),
        ("max_faces", max_faces), ("max_openings", max_openings),
        ("max_landmark_refs", max_landmark_refs), ("max_landmarks", max_landmarks),
        ("max_vertex_pairs", max_vertex_pairs),
        ("max_landmark_edge_tests", max_landmark_edge_tests),
    )
    for name, budget in limits:
        if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
            raise TargetMeshOpeningError(f"openings.{name}_invalid")
    if len(openings) > max_openings:
        raise TargetMeshOpeningError("openings.opening_budget_exhausted")
    ref_count = sum(len(opening["boundary_landmark_ids"]) for opening in remain_open)
    if ref_count > max_landmark_refs:
        raise TargetMeshOpeningError("openings.landmark_ref_budget_exhausted")
    if any(not opening["boundary_landmark_ids"] for opening in remain_open):
        raise TargetMeshOpeningError("openings.remain_open_landmarks_required")

    binding = value["material_profile"]
    if binding["binding_type"] == "INLINE":
        resolved_profile = binding["profile"]
    else:
        resolved_profile = supplied_profiles.get((binding["profile_id"], binding["revision"]))
        if resolved_profile is None:
            raise TargetMeshOpeningError("openings.material_profile_unresolved")
        if (resolved_profile["profile_id"] != binding["profile_id"]
                or resolved_profile["revision"] != binding["revision"]):
            raise TargetMeshOpeningError("openings.material_profile_binding_mismatch")

    design_hash = canonical_hash(value, CanonicalProfile.DESIGN_SPEC, validator=validator)
    profile_hash = canonical_hash(resolved_profile, CanonicalProfile.MATERIAL_PROFILE)
    if material_profile is not None and canonical_hash(
        material_profile.to_dict(), CanonicalProfile.MATERIAL_PROFILE,
    ) != profile_hash:
        raise TargetMeshOpeningError("openings.supplied_material_profile_mismatch")
    try:
        decoded = decode_indexed_triangle_mesh(
            raw_bytes, media_type=artifact["media_type"],
            expected_coordinate_frame_id=frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
        ordering = diagnose_indexed_triangle_mesh_canonical_order(
            raw_bytes, decoded, media_type=artifact["media_type"],
            expected_coordinate_frame_id=frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
        boundaries = diagnose_indexed_triangle_mesh_boundaries(
            raw_bytes, decoded, ordering, media_type=artifact["media_type"],
            expected_coordinate_frame_id=frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
    except (ValueError, ArtifactValidationError) as error:
        raise TargetMeshOpeningError("openings.mesh_diagnostic_invalid") from error

    expected_components = target["topology_expectation"]["expected_connected_components"]
    expected_loops = target["topology_expectation"]["expected_boundary_components"]
    if len(boundaries.components) != expected_components:
        raise TargetMeshOpeningError("openings.component_count_mismatch")
    if len(boundaries.boundary_loops) != expected_loops:
        raise TargetMeshOpeningError("openings.boundary_count_mismatch")
    if len(boundaries.boundary_loops) != len(remain_open):
        raise TargetMeshOpeningError("openings.remain_open_count_mismatch")

    referenced_ids = sorted({
        landmark_id for opening in remain_open
        for landmark_id in opening["boundary_landmark_ids"]
    })
    if len(referenced_ids) > max_landmarks:
        raise TargetMeshOpeningError("openings.landmark_budget_exhausted")
    landmark_values = {item["landmark_id"]: item for item in value["landmarks"]}
    landmarks = tuple(BoundaryLandmark(
        landmark_id=identifier,
        target_frame_id=landmark_values[identifier]["coordinate_frame_id"],
        position_mm=(float(landmark_values[identifier]["position_mm"][0]),
                     float(landmark_values[identifier]["position_mm"][1]),
                     float(landmark_values[identifier]["position_mm"][2])),
        tolerance_mm=float(landmark_values[identifier]["tolerance_mm"]),
    ) for identifier in referenced_ids)
    numeric_profile = resolve_v0_numeric_profile(target["preflight_numerical_profile_id"])
    try:
        landmark_report = diagnose_boundary_landmark_eligibility(
            raw_bytes, decoded, ordering, boundaries, landmarks,
            profile=numeric_profile, media_type=artifact["media_type"],
            expected_coordinate_frame_id=frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
            max_landmarks=max_landmarks, max_vertex_pairs=max_vertex_pairs,
            max_landmark_edge_tests=max_landmark_edge_tests,
        )
    except ValueError as error:
        raise TargetMeshOpeningError("openings.landmark_diagnostic_invalid") from error

    eligibility = {result.landmark_id: result for result in landmark_report.results}
    assignments: list[tuple[str, tuple[int, ...]]] = []
    reason: str | None = None
    classification = "UNIQUE"
    for opening in remain_open:
        candidate_loop_set: set[int] | None = None
        for landmark_id in sorted(opening["boundary_landmark_ids"]):
            result = eligibility[landmark_id]
            if result.classification == "AMBIGUOUS":
                classification, reason = "AMBIGUOUS", "openings.landmark_ambiguous"
                break
            if result.classification == "UNMATCHED":
                classification, reason = "UNMATCHED", "openings.landmark_unmatched"
                break
            current = set(result.candidate_loop_indices)
            candidate_loop_set = (
                current if candidate_loop_set is None else candidate_loop_set & current
            )
        if reason is not None:
            break
        if not candidate_loop_set:
            classification, reason = "UNMATCHED", "openings.landmark_refs_split"
            break
        assignments.append((
            opening["opening_requirement_id"], tuple(sorted(candidate_loop_set)),
        ))
    loop_owners: dict[int, list[str]] = {}
    if reason is None:
        for opening_id, candidate_loops in assignments:
            if len(candidate_loops) != 1:
                classification, reason = "AMBIGUOUS", "openings.opening_loop_ambiguous"
                break
            loop_owners.setdefault(candidate_loops[0], []).append(opening_id)
    if reason is None and any(len(owners) != 1 for owners in loop_owners.values()):
        classification, reason = "AMBIGUOUS", "openings.shared_loop"
    if reason is None and set(loop_owners) != set(range(len(boundaries.boundary_loops))):
        classification, reason = "UNMATCHED", "openings.uncovered_loop"
    bindings: tuple[OpeningLoopBinding, ...] = ()
    if reason is None:
        opening_map = {opening["opening_requirement_id"]: opening for opening in remain_open}
        bindings = tuple(sorted((
            OpeningLoopBinding(opening_id, opening_map[opening_id]["purpose"], loop_index)
            for loop_index, owners in loop_owners.items()
            for opening_id in owners
        ), key=lambda item: item.opening_requirement_id))

    landmark_classes = tuple((
        result.landmark_id, result.classification, result.candidate_loop_indices
    ) for result in landmark_report.results)
    evidence: JSONValue = {
        "status": STATUS, "algorithm_version": VERSION,
        "classification": classification, "reason": reason,
        "source_sha256": source_hash, "design_spec_sha256": design_hash,
        "material_profile": {"id": resolved_profile["profile_id"],
                             "revision": resolved_profile["revision"],
                             "sha256": profile_hash},
        "ordering_sha256": ordering.diagnostic_sha256,
        "boundary_sha256": boundaries.diagnostic_sha256,
        "landmark_sha256": landmark_report.diagnostic_sha256,
        "bindings": [{"opening_requirement_id": item.opening_requirement_id,
                      "purpose": item.purpose, "loop_index": item.loop_index}
                     for item in bindings],
        "landmarks": [{"id": i, "classification": c, "candidate_loops": list(ls)}
                      for i, c, ls in landmark_classes],
        "counts": {"boundary_loops": len(boundaries.boundary_loops),
                   "components": len(boundaries.components),
                   "expected_components": expected_components},
        "budgets": {name: budget for name, budget in limits},
    }
    digest = sha256(_DOMAIN + jcs_bytes(evidence)).hexdigest()
    return TargetMeshOpeningDiagnostic(
        STATUS, VERSION, classification, reason, source_hash, design_hash,
        resolved_profile["profile_id"], resolved_profile["revision"], profile_hash,
        ordering.diagnostic_sha256, boundaries.diagnostic_sha256,
        landmark_report.diagnostic_sha256, len(boundaries.boundary_loops),
        expected_components, bindings, landmark_classes, digest,
    )
