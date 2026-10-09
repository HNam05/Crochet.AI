"""Bounded graph-distance contour draft generation on closed genus-zero meshes.

This research draft uses edge-graph Dijkstra distances, not exact surface
geodesics. Target coordinates remain solver-private and never enter simulation.
"""

from __future__ import annotations

import heapq
import json
import math
from collections import defaultdict
from fractions import Fraction
from hashlib import sha256
from typing import Any, TypedDict, cast

from .analytic_compile import CompileProvenance, compile_closed_schedule
from .analytic_counts import (
    CountSearchBudget,
    CountSearchInput,
    CountSearchStatus,
    CountWindow,
    search_counts,
)
from .canonical import CanonicalProfile, canonical_hash, jcs_bytes
from .json_types import JSONValue
from .models import DesignSpec, MaterialProfile
from .solver_types import GenerationError
from .surface_topology import audit_surface_topology
from .v0_mesh_preflight import (
    V0MeshBudgets,
    V0MeshPreflightError,
    inspect_v0_closed_mesh_v2,
)
from .validation import SemanticValidator

PROFILE = "GEODESIC_DRAFT_SOLVER_V1"
_CONFIG_FIELDS = {
    "profile",
    "schema_version",
    "software_commit",
    "parameter_profile_id",
    "random_seed",
    "source_mesh_sha256",
    "start_pole_source_vertex_index",
    "end_pole_source_vertex_index",
    "tension_profile_id",
    "fabric_state",
    "count_window_radius",
    "max_increases_per_course",
    "max_decreases_per_course",
    "max_graph_edge_visits",
    "max_graph_heap_pops",
    "max_level_intervals",
    "max_contour_face_tests",
    "max_count_values_per_course",
    "max_dp_states_per_course",
    "max_transition_evaluations",
    "max_stitches",
    "v0_budgets",
}
_V0_BUDGET_FIELDS = {
    "max_bytes",
    "max_vertices",
    "max_faces",
    "max_vertex_pairs",
    "max_face_pairs",
    "max_distance_piece_pairs",
    "max_lambda_bits",
    "max_orientation_tests",
    "max_openings",
    "max_landmark_refs",
    "max_landmarks",
    "max_landmark_edge_tests",
}
_SAFE_INTEGER = 9_007_199_254_740_991
Vec3 = tuple[float, float, float]
Point = tuple[Fraction, Fraction, Fraction]
Edge = tuple[int, int]
JSONObject = dict[str, JSONValue]


class V0Budget(TypedDict):
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


class GeodesicConfig(TypedDict):
    profile: str
    schema_version: str
    software_commit: str
    parameter_profile_id: str
    random_seed: int
    source_mesh_sha256: str
    start_pole_source_vertex_index: int
    end_pole_source_vertex_index: int
    tension_profile_id: str
    fabric_state: str
    count_window_radius: int
    max_increases_per_course: int
    max_decreases_per_course: int
    max_graph_edge_visits: int
    max_graph_heap_pops: int
    max_level_intervals: int
    max_contour_face_tests: int
    max_count_values_per_course: int
    max_dp_states_per_course: int
    max_transition_evaluations: int
    max_stitches: int
    v0_budgets: V0Budget


class GeodesicSolverError(ValueError):
    """Invalid bounded geodesic draft input or numerical contour state."""

    def __init__(self, status: str, code: str, reason: str) -> None:
        self.status, self.code, self.reason = status, code, reason
        super().__init__(f"{status}/{code}: {reason}")


def generate_geodesic_draft(
    design_value: JSONObject,
    material_value: JSONObject,
    source_mesh_jcs_bytes: bytes,
    config_value: object,
    *,
    provenance: CompileProvenance,
) -> dict[str, JSONValue]:
    """Emit one complete closed-SC draft or a structured fail-closed outcome.

    Pole indices name vertices in the exact source mesh bytes. They are mapped
    only through the independently admitted V0 source-to-normalized map.
    """
    try:
        config = _admit_config(config_value, source_mesh_jcs_bytes)
        if not isinstance(provenance, CompileProvenance):
            raise GeodesicSolverError(
                "INVALID_SOLVER_INPUT", "PROVENANCE", "compile_provenance_invalid"
            )
        provenance.validate()
        if provenance.software_commit != config["software_commit"]:
            raise GeodesicSolverError(
                "INVALID_SOLVER_INPUT", "PROVENANCE", "software_commit_mismatch"
            )
        if len(source_mesh_jcs_bytes) > config["v0_budgets"]["max_bytes"]:
            raise GeodesicSolverError("SEARCH_BUDGET_EXHAUSTED", "MESH", "source_mesh_byte_budget")
        design = DesignSpec.from_dict(design_value)
        material = MaterialProfile.from_dict(material_value)
        solver_options = cast(JSONObject, design_value["solver_options"])
        allowed_families = cast(list[JSONValue], solver_options["allowed_solver_families"])
        if "GEODESIC" not in allowed_families:
            raise GeodesicSolverError(
                "NOT_APPLICABLE", "DESIGN_SPEC", "geodesic_solver_family_not_allowed"
            )
        if type(solver_options["max_candidate_evaluations"]) is not int or int(
            solver_options["max_candidate_evaluations"]
        ) < 1:
            raise GeodesicSolverError(
                "INVALID_SOLVER_INPUT", "DESIGN_SPEC", "candidate_evaluation_budget_invalid"
            )
        if solver_options["parameter_profile_id"] != config["parameter_profile_id"]:
            raise GeodesicSolverError(
                "INVALID_SOLVER_INPUT", "DESIGN_SPEC", "parameter_profile_mismatch"
            )
        if solver_options["random_seed"] != config["random_seed"]:
            raise GeodesicSolverError(
                "INVALID_SOLVER_INPUT", "DESIGN_SPEC", "random_seed_mismatch"
            )
        if config["random_seed"] > 4_294_967_295:
            raise GeodesicSolverError("INVALID_SOLVER_INPUT", "CONFIG", "random_seed_invalid")
        source_mesh = json.loads(source_mesh_jcs_bytes)
        source_vertices = source_mesh.get("vertices") if isinstance(source_mesh, dict) else None
        if not isinstance(source_vertices, list):
            raise GeodesicSolverError("INVALID_SOLVER_INPUT", "MESH", "source_vertices_missing")
        start_source = config["start_pole_source_vertex_index"]
        end_source = config["end_pole_source_vertex_index"]
        if start_source >= len(source_vertices) or end_source >= len(source_vertices):
            raise GeodesicSolverError(
                "INVALID_SOLVER_INPUT", "ANCHOR", "source_anchor_out_of_range"
            )
        if start_source == end_source:
            raise GeodesicSolverError("INVALID_SOLVER_INPUT", "ANCHOR", "pole_anchors_not_distinct")
        source_sha = sha256(source_mesh_jcs_bytes).hexdigest()
        v0 = inspect_v0_closed_mesh_v2(
            design,
            source_mesh_jcs_bytes,
            material_profile=material,
            budgets=V0MeshBudgets(**config["v0_budgets"]),
        )
        if v0.outcome != "PASS":
            raise GeodesicSolverError("NOT_APPLICABLE", "V0", "source_mesh_not_V0_admitted")
        design_digest = canonical_hash(
            design_value,
            CanonicalProfile.DESIGN_SPEC,
            validator=_semantic_validator(design_value, material_value),
        )
        if v0.source_sha256 != source_sha or v0.design_spec_sha256 != design_digest:
            raise GeodesicSolverError("INVALID_SOLVER_INPUT", "BINDING", "V0_binding_mismatch")
        mesh = cast(JSONObject, json.loads(v0.normalized_mesh_jcs))
        mesh_vertices = cast(list[JSONObject], mesh["vertices"])
        mesh_faces = cast(list[JSONObject], mesh["faces"])
        vertices = tuple(
            cast(Vec3, tuple(float(value) for value in cast(list[float], row["position_mm"])))
            for row in mesh_vertices
        )
        faces = cast(
            tuple[tuple[int, int, int], ...],
            tuple(
                tuple(int(index) for index in cast(list[int], row["vertex_indices"]))
                for row in mesh_faces
            ),
        )
        _require_closed_sphere_topology(vertices, faces)
        source_start = config["start_pole_source_vertex_index"]
        source_end = config["end_pole_source_vertex_index"]
        if source_start >= len(v0.source_to_normalized_vertex_indices) or source_end >= len(
            v0.source_to_normalized_vertex_indices
        ):
            raise GeodesicSolverError(
                "INVALID_SOLVER_INPUT", "ANCHOR", "source_anchor_out_of_range"
            )
        start = v0.source_to_normalized_vertex_indices[source_start]
        end = v0.source_to_normalized_vertex_indices[source_end]
        if start == end:
            raise GeodesicSolverError("INVALID_SOLVER_INPUT", "ANCHOR", "pole_anchors_not_distinct")
        material_digest = canonical_hash(material_value, CanonicalProfile.MATERIAL_PROFILE)
        response = _resolve_material_response(material_value, config)
        gauge = cast(JSONObject, response["effective_gauge"])
        stitch_pitch = Fraction(float(cast(float, gauge["effective_stitch_pitch_mm"])))
        course_pitch = Fraction(float(cast(float, gauge["effective_course_pitch_mm"])))
        if stitch_pitch <= 0 or course_pitch <= 0:
            raise GeodesicSolverError("INVALID_SOLVER_INPUT", "MATERIAL", "material_pitch_invalid")
        adjacency, edge_visits = _build_graph(
            vertices, faces, config["max_graph_edge_visits"]
        )
        distances, heap_pops, relaxations = _dijkstra(
            vertices,
            adjacency,
            start,
            config["max_graph_heap_pops"],
            config["max_graph_edge_visits"] - edge_visits,
        )
        if any(value is None for value in distances):
            raise GeodesicSolverError("NOT_APPLICABLE", "GRAPH", "source_mesh_disconnected")
        end_distance = cast(Fraction, distances[end])
        if end_distance <= 0 or any(
            cast(Fraction, distance) >= end_distance
            for index, distance in enumerate(distances)
            if index != end
        ):
            raise GeodesicSolverError(
                "NOT_APPLICABLE", "ANCHOR", "end_anchor_not_unique_graph_farthest"
            )
        intervals = _nearest_positive_integer(end_distance / course_pitch)
        if intervals < 2 or intervals > config["max_level_intervals"]:
            raise GeodesicSolverError("SEARCH_BUDGET_EXHAUSTED", "LEVELS", "level_interval_budget")
        levels = tuple(end_distance * Fraction(index, intervals) for index in range(1, intervals))
        contour_face_tests = 0
        contour_lengths: list[Fraction] = []
        for level in levels:
            length, used = _extract_one_closed_contour(
                vertices,
                faces,
                cast(list[Fraction], distances),
                level,
                config["max_contour_face_tests"] - contour_face_tests,
            )
            contour_face_tests += used
            contour_lengths.append(length)
        count_request = _count_request(contour_lengths, stitch_pitch, config)
        count_result = search_counts(count_request)
        if count_result.status != CountSearchStatus.OPTIMAL_COUNT_PROPOSAL:
            status = (
                "SEARCH_BUDGET_EXHAUSTED"
                if count_result.status == CountSearchStatus.SEARCH_BUDGET_EXHAUSTED
                else "NO_FEASIBLE_CONSTRUCTION"
            )
            raise GeodesicSolverError(status, "COUNT", count_result.reason)
        parameters = (
            *(
                (f"geodesic_{name}", cast(str | int | float | bool, value))
                for name, value in sorted(config.items())
                if name not in {"v0_budgets", "software_commit"}
            ),
            ("geodesic_design_parameter_profile_id", solver_options["parameter_profile_id"]),
            ("geodesic_design_random_seed", solver_options["random_seed"]),
            (
                "geodesic_design_max_candidate_evaluations",
                solver_options["max_candidate_evaluations"],
            ),
        )
        if {name for name, _ in provenance.parameters} & {name for name, _ in parameters}:
            raise GeodesicSolverError(
                "INVALID_SOLVER_INPUT", "PROVENANCE", "provenance_parameter_name_collision"
            )
        compile_provenance = CompileProvenance(
            provenance.software_commit,
            provenance.source_snapshot_sha256,
            provenance.parameters + parameters,
        )
        candidate = compile_closed_schedule(
            design_value,
            material_value,
            count_result.counts,
            (0,) * max(0, len(count_result.counts) - 1),
            compile_provenance,
            max_stitches=config["max_stitches"],
            generation_profile="GEODESIC_CLOSED_SC_V1",
        )
        validator = _semantic_validator(design_value, material_value)
        semantic = validator.validate_crochet_ir(candidate)
        if not semantic.ok:
            raise GeodesicSolverError(
                "NUMERICAL_FAILURE", "IR", "compiled_ir_semantic_validation_failed"
            )
        report: dict[str, JSONValue] = {
            "profile": PROFILE,
            "status": "CANDIDATES_EMITTED",
            "reason": "one_complete_closed_sc_draft_compiled",
            "verification_state": "NOT_VERIFIED",
            "physical_status": "UNTESTED",
            "comparison_eligible": False,
            "method": "EDGE_GRAPH_DIJKSTRA_PL_CONTOURS_V1",
            "geodesic_claim": "GRAPH_DISTANCE_APPROXIMATION_NOT_EXACT_SURFACE_GEODESIC",
            "design_spec_sha256": design_digest,
            "material_profile_sha256": material_digest,
            "source_mesh_sha256": source_sha,
            "implementation_source_snapshot_sha256": provenance.source_snapshot_sha256,
            "v0_evidence_sha256": v0.evidence_sha256,
            "normalized_mesh_sha256": v0.normalized_mesh_sha256,
            "source_start_pole_vertex_index": source_start,
            "source_end_pole_vertex_index": source_end,
            "normalized_start_pole_vertex_index": start,
            "normalized_end_pole_vertex_index": end,
            "distance_interval_count": intervals,
            "realized_course_pitch_mm": float(end_distance / intervals),
            "declared_course_pitch_mm": float(course_pitch),
            "course_pitch_residual_mm": float(abs(end_distance / intervals - course_pitch)),
            "contour_lengths_mm": [float(length) for length in contour_lengths],
            "contour_count": len(contour_lengths),
            "count_proposal": {
                "status": str(count_result.status),
                "algorithm_version": count_result.algorithm_version,
                "counts": list(count_result.counts),
                "transitions": [
                    {"plain": item.plain, "increases": item.increases, "decreases": item.decreases}
                    for item in count_result.transitions
                ],
                "max_contour_residual_mm": float(count_result.objective.max_residual_mm)
                if count_result.objective
                else None,
                "squared_contour_residual_sum_mm2": float(
                    count_result.objective.squared_residual_sum_mm2
                )
                if count_result.objective
                else None,
                "transition_evaluations": count_result.transition_evaluations,
                "completed_passes": count_result.completed_passes,
            },
            "work": {
                "graph_edge_build_visits": edge_visits,
                "dijkstra_heap_pops": heap_pops,
                "dijkstra_relaxation_attempts": relaxations,
                "contour_face_tests": contour_face_tests,
                "count_transition_evaluations": count_result.transition_evaluations,
                "compile_attempts": 1,
                "v0_budget": cast(JSONObject, dict(config["v0_budgets"])),
                "solver_budget": {
                    name: cast(JSONValue, value)
                    for name, value in config.items()
                    if name.startswith("max_")
                },
            },
            "candidate_crochet_ir": candidate,
            "limitations": [
                "target_mesh_guides_solver_only",
                "graph_distance_is_not_exact_surface_geodesic",
                "no_branching_or_open_boundary_support",
                "independent_verification_required",
            ],
        }
        report["sha256"] = sha256(
            b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + jcs_bytes(report)
        ).hexdigest()
        return report
    except GeodesicSolverError as error:
        return _failure(error.status, error.code, error.reason)
    except GenerationError as error:
        return _failure(str(error.status), "COMPILER", error.reason)
    except V0MeshPreflightError as error:
        return _failure("NOT_APPLICABLE", "V0", error.reason)
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        return _failure("INVALID_SOLVER_INPUT", "INPUT", str(error))


def _failure(status: str, code: str, reason: str) -> dict[str, JSONValue]:
    result: dict[str, JSONValue] = {
        "profile": PROFILE,
        "status": status,
        "reason_code": code,
        "reason": reason,
        "verification_state": "NOT_VERIFIED",
        "physical_status": "UNTESTED",
        "comparison_eligible": False,
        "candidate_crochet_ir": None,
    }
    result["sha256"] = sha256(
        b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + jcs_bytes(result)
    ).hexdigest()
    return result


def _admit_config(value: object, mesh_bytes: bytes) -> GeodesicConfig:
    if not isinstance(value, dict) or set(value) != _CONFIG_FIELDS:
        raise GeodesicSolverError("INVALID_SOLVER_INPUT", "CONFIG", "config_fields_invalid")
    if value["profile"] != PROFILE or value["schema_version"] != "1.0.0":
        raise GeodesicSolverError("INVALID_SOLVER_INPUT", "CONFIG", "config_version_invalid")
    digest = sha256(mesh_bytes).hexdigest()
    if value["source_mesh_sha256"] != digest:
        raise GeodesicSolverError("INVALID_SOLVER_INPUT", "BINDING", "source_mesh_hash_mismatch")
    commit = value["software_commit"]
    if (
        not isinstance(commit, str)
        or len(commit) not in (40, 64)
        or any(c not in "0123456789abcdef" for c in commit)
    ):
        raise GeodesicSolverError("INVALID_SOLVER_INPUT", "CONFIG", "software_commit_invalid")
    for name in ("tension_profile_id", "fabric_state"):
        if not isinstance(value[name], str) or not value[name]:
            raise GeodesicSolverError("INVALID_SOLVER_INPUT", "CONFIG", f"{name}_invalid")
    if not isinstance(value["parameter_profile_id"], str) or not value["parameter_profile_id"]:
        raise GeodesicSolverError("INVALID_SOLVER_INPUT", "CONFIG", "parameter_profile_id_invalid")
    integer_bounds = {
        "start_pole_source_vertex_index": (0, _SAFE_INTEGER),
        "end_pole_source_vertex_index": (0, _SAFE_INTEGER),
        "random_seed": (0, 4_294_967_295),
        "count_window_radius": (0, 32),
        "max_increases_per_course": (0, 512),
        "max_decreases_per_course": (0, 512),
        "max_graph_edge_visits": (1, 2_000_000),
        "max_graph_heap_pops": (1, 1_000_000),
        "max_level_intervals": (2, 512),
        "max_contour_face_tests": (1, 2_000_000),
        "max_count_values_per_course": (1, 256),
        "max_dp_states_per_course": (1, 256),
        "max_transition_evaluations": (1, 2_000_000),
        "max_stitches": (1, 10_000),
    }
    config = dict(value)
    for name, (minimum, maximum) in integer_bounds.items():
        number = value[name]
        if type(number) is not int or not minimum <= number <= maximum:
            raise GeodesicSolverError("INVALID_SOLVER_INPUT", "CONFIG", f"{name}_invalid")
    raw_v0 = value["v0_budgets"]
    if not isinstance(raw_v0, dict) or set(raw_v0) != _V0_BUDGET_FIELDS:
        raise GeodesicSolverError("INVALID_SOLVER_INPUT", "CONFIG", "v0_budget_fields_invalid")
    for name, number in raw_v0.items():
        if type(number) is not int or number <= 0 or number > _SAFE_INTEGER:
            raise GeodesicSolverError("INVALID_SOLVER_INPUT", "CONFIG", f"v0_{name}_invalid")
    return cast(GeodesicConfig, config)


def _semantic_validator(design: JSONObject, material: JSONObject) -> SemanticValidator:
    return SemanticValidator(
        material_profiles={cast(str, material["profile_id"]): cast(dict[str, Any], material)},
        design_specs={cast(str, design["design_spec_id"]): cast(dict[str, Any], design)},
    )


def _resolve_material_response(material: JSONObject, config: GeodesicConfig) -> JSONObject:
    rows = cast(list[JSONObject], material["calibration_responses"])
    matches = [
        row
        for row in rows
        if row["measurement_conditions"]
        == {
            "canonical_stitch_type": "SINGLE_CROCHET",
            "course_mode": "CYCLIC",
            "tension_profile_id": config["tension_profile_id"],
            "fabric_state": config["fabric_state"],
        }
    ]
    if len(matches) != 1:
        raise GeodesicSolverError(
            "INVALID_SOLVER_INPUT", "MATERIAL", "material_response_not_unique"
        )
    return matches[0]


def _require_closed_sphere_topology(
    vertices: tuple[Vec3, ...], faces: tuple[tuple[int, int, int], ...]
) -> None:
    audit = audit_surface_topology(
        [f"v{index:06d}" for index in range(len(vertices))],
        [[f"v{index:06d}" for index in face] for face in faces],
        max_vertices=len(vertices),
        max_faces=len(faces),
    )
    if audit.status != "PASS" or audit.betti_numbers != (1, 0, 1):
        raise GeodesicSolverError("NOT_APPLICABLE", "TOPOLOGY", "mesh_must_be_closed_genus_zero")


def _build_graph(
    vertices: tuple[Vec3, ...], faces: tuple[tuple[int, int, int], ...], limit: int
) -> tuple[dict[int, dict[int, Fraction]], int]:
    edges: set[Edge] = set()
    visits = 0
    for a, b, c in faces:
        for left, right in ((a, b), (b, c), (c, a)):
            if visits >= limit:
                raise GeodesicSolverError(
                    "SEARCH_BUDGET_EXHAUSTED", "GRAPH", "graph_edge_build_budget"
                )
            visits += 1
            edges.add((min(left, right), max(left, right)))
    adjacency: dict[int, dict[int, Fraction]] = {index: {} for index in range(len(vertices))}
    for left, right in sorted(edges):
        length = math.hypot(*(vertices[left][axis] - vertices[right][axis] for axis in range(3)))
        if not math.isfinite(length) or length <= 0:
            raise GeodesicSolverError("NUMERICAL_FAILURE", "GRAPH", "edge_length_invalid")
        weight = Fraction.from_float(length)
        adjacency[left][right] = weight
        adjacency[right][left] = weight
    return adjacency, visits


def _dijkstra(
    vertices: tuple[Vec3, ...],
    adjacency: dict[int, dict[int, Fraction]],
    start: int,
    max_pops: int,
    max_relaxations: int,
) -> tuple[list[Fraction | None], int, int]:
    if not 0 <= start < len(vertices):
        raise GeodesicSolverError("INVALID_SOLVER_INPUT", "ANCHOR", "start_anchor_out_of_range")
    distances: list[Fraction | None] = [None] * len(vertices)
    distances[start] = Fraction(0)
    queue: list[tuple[Fraction, int]] = [(Fraction(0), start)]
    pops = relaxations = 0
    while queue:
        if pops >= max_pops:
            raise GeodesicSolverError("SEARCH_BUDGET_EXHAUSTED", "DIJKSTRA", "heap_pop_budget")
        distance, vertex = heapq.heappop(queue)
        pops += 1
        if distances[vertex] != distance:
            continue
        for neighbor, weight in sorted(adjacency[vertex].items()):
            if relaxations >= max_relaxations:
                raise GeodesicSolverError(
                    "SEARCH_BUDGET_EXHAUSTED", "DIJKSTRA", "relaxation_budget"
                )
            relaxations += 1
            candidate = distance + weight
            prior = distances[neighbor]
            if prior is None or candidate < prior:
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    return distances, pops, relaxations


def _nearest_positive_integer(value: Fraction) -> int:
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + int(2 * remainder > value.denominator)


def _extract_one_closed_contour(
    vertices: tuple[Vec3, ...],
    faces: tuple[tuple[int, int, int], ...],
    distances: list[Fraction],
    level: Fraction,
    budget: int,
) -> tuple[Fraction, int]:
    if any(distance == level for distance in distances):
        raise GeodesicSolverError("NUMERICAL_FAILURE", "CONTOUR", "level_passes_through_vertex")
    graph: dict[Edge, set[Edge]] = defaultdict(set)
    tests = 0
    for face in faces:
        if tests >= budget:
            raise GeodesicSolverError("SEARCH_BUDGET_EXHAUSTED", "CONTOUR", "face_scan_budget")
        tests += 1
        crossings: list[Edge] = []
        for left, right in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            dl, dr = distances[left], distances[right]
            if (dl < level < dr) or (dr < level < dl):
                crossings.append((min(left, right), max(left, right)))
        if len(crossings) not in (0, 2):
            raise GeodesicSolverError(
                "NUMERICAL_FAILURE", "CONTOUR", "nonregular_face_intersection"
            )
        if len(crossings) == 2:
            first_edge, second_edge = sorted(crossings)
            graph[first_edge].add(second_edge)
            graph[second_edge].add(first_edge)
    if not graph or any(len(neighbors) != 2 for neighbors in graph.values()):
        raise GeodesicSolverError("NUMERICAL_FAILURE", "CONTOUR", "contour_not_one_regular_cycle")
    unseen = set(graph)
    components = 0
    while unseen:
        components += 1
        start = min(unseen)
        unseen.remove(start)
        pending = [start]
        while pending:
            current = pending.pop()
            for neighbor in graph[current]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    pending.append(neighbor)
    if components != 1:
        raise GeodesicSolverError("NUMERICAL_FAILURE", "CONTOUR", "contour_component_count_not_one")
    crossing_points: dict[Edge, Point] = {}
    for edge_key in graph:
        edge_start, edge_end = edge_key
        dl, dr = distances[edge_start], distances[edge_end]
        fraction = (level - dl) / (dr - dl)
        start_point = tuple(Fraction.from_float(value) for value in vertices[edge_start])
        end_point = tuple(Fraction.from_float(value) for value in vertices[edge_end])
        crossing_points[edge_key] = cast(
            Point,
            tuple(
                start_point[axis] + fraction * (end_point[axis] - start_point[axis])
                for axis in range(3)
            ),
        )
    lengths: list[Fraction] = []
    for left_key, neighbors in graph.items():
        for right_key in neighbors:
            if left_key < right_key:
                delta = tuple(
                    crossing_points[left_key][axis] - crossing_points[right_key][axis]
                    for axis in range(3)
                )
                squared = sum((value * value for value in delta), Fraction(0))
                length = math.sqrt(float(squared))
                if not math.isfinite(length) or length <= 0:
                    raise GeodesicSolverError(
                        "NUMERICAL_FAILURE", "CONTOUR", "contour_segment_length_invalid"
                    )
                lengths.append(Fraction.from_float(length))
    perimeter = sum(lengths, Fraction(0))
    if perimeter <= 0:
        raise GeodesicSolverError("NUMERICAL_FAILURE", "CONTOUR", "contour_length_invalid")
    return perimeter, tests


def _count_request(
    lengths: list[Fraction], stitch_pitch: Fraction, config: GeodesicConfig
) -> CountSearchInput:
    if not lengths:
        raise GeodesicSolverError("NO_FEASIBLE_CONSTRUCTION", "COUNT", "no_regular_course_contours")
    radius = config["count_window_radius"]
    windows: list[CountWindow] = []
    for length in lengths:
        nominal = _nearest_positive_integer(length / stitch_pitch)
        minimum = max(2, nominal - radius)
        maximum = min(512, nominal + radius)
        if maximum < minimum:
            raise GeodesicSolverError(
                "NO_FEASIBLE_CONSTRUCTION", "COUNT", "contour_count_window_empty"
            )
        windows.append(CountWindow(minimum, maximum))
    budget = CountSearchBudget(
        max_courses=min(512, len(lengths)),
        max_count_values_per_course=config["max_count_values_per_course"],
        max_dp_states_per_course=config["max_dp_states_per_course"],
        max_transition_evaluations=config["max_transition_evaluations"],
    )
    return CountSearchInput(
        tuple(lengths),
        stitch_pitch,
        tuple(windows),
        config["max_increases_per_course"],
        config["max_decreases_per_course"],
        budget,
    )
