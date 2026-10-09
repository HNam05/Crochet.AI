"""Experimental target-free shear and bending terms for closed triangle shells.

Uniform rest values and stiffnesses are hypotheses, not calibrated material data.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import cast

from .canonical import SAFE_INTEGER, jcs_bytes
from .forward_bending import (
    ANGLE_BRANCH_TOLERANCE_RAD,
    MIN_EDGE_LENGTH_MM,
    ForwardBendingError,
    _dihedral,
    _dihedral_gradient,
    _length,
    _sub_float,
)
from .json_types import JSONValue
from .surface_topology import SurfaceTopologyInputError, audit_surface_topology

PROFILE = "FORWARD_CLOSED_SHELL_TERMS_V1"
TERMS_PROFILE = "FORWARD_CLOSED_SHELL_TERMS_CANONICAL_V1"
MAX_VERTICES, MAX_FACES, MAX_HINGES = 2048, 4096, 8192
Vec3 = tuple[float, float, float]


class ShellTermsError(ValueError):
    """Invalid, unsupported, or numerically undefined shell term input."""

    def __init__(self, code: str, reason: str) -> None:
        self.code, self.reason = code, reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ShellParameters:
    schema_version: str
    status: str
    provenance_id: str
    rest_corner_angle_rad: float
    shear_stiffness_n_mm: float
    rest_dihedral_rad: float
    bending_stiffness_n_mm: float
    canonical_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class ShellCornerTerm:
    face: tuple[str, str, str]
    center: str
    first: str
    second: str
    rest_cosine: float
    stiffness_n_mm: float


@dataclass(frozen=True, slots=True)
class ShellHingeTerm:
    vertices: tuple[str, str, str, str]
    rest_dihedral_rad: float
    stiffness_n_mm: float


@dataclass(frozen=True, slots=True)
class ShellTerms:
    status: str
    vertices: tuple[str, ...]
    faces: tuple[tuple[str, str, str], ...]
    parameters: ShellParameters
    parameters_sha256: str
    corners: tuple[ShellCornerTerm, ...]
    hinges: tuple[ShellHingeTerm, ...]
    canonical_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class ShellEvaluation:
    shear_n_mm: float
    bending_n_mm: float
    total_n_mm: float
    forces_n: tuple[tuple[str, Vec3], ...]
    maxforce_n: float


def admit_shell_parameters(value: object) -> ShellParameters:
    required = {
        "schema_version",
        "status",
        "provenance_id",
        "rest_corner_angle_rad",
        "shear_stiffness_n_mm",
        "rest_dihedral_rad",
        "bending_stiffness_n_mm",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ShellTermsError("E_SCHEMA", "parameters.schema_invalid")
    if value["schema_version"] != "1.0.0" or value["status"] != "HYPOTHESIS":
        raise ShellTermsError("E_SCHEMA", "parameters.version_or_status_invalid")
    provenance = value["provenance_id"]
    if not isinstance(provenance, str) or not provenance.strip():
        raise ShellTermsError("E_INPUT", "parameters.provenance_invalid")
    corner = _finite(value["rest_corner_angle_rad"], "parameters.rest_corner_angle_invalid")
    shear = _finite(value["shear_stiffness_n_mm"], "parameters.shear_stiffness_invalid")
    dihedral = _finite(value["rest_dihedral_rad"], "parameters.rest_dihedral_invalid")
    bending = _finite(value["bending_stiffness_n_mm"], "parameters.bending_stiffness_invalid")
    if not 0 < corner < math.pi:
        raise ShellTermsError("E_INPUT", "parameters.rest_corner_angle_invalid")
    if shear <= 0:
        raise ShellTermsError("E_INPUT", "parameters.shear_stiffness_invalid")
    if not -math.pi <= dihedral <= math.pi:
        raise ShellTermsError("E_INPUT", "parameters.rest_dihedral_invalid")
    if bending <= 0:
        raise ShellTermsError("E_INPUT", "parameters.bending_stiffness_invalid")
    payload: dict[str, JSONValue] = {
        "profile": PROFILE,
        "schema_version": "1.0.0",
        "status": "HYPOTHESIS",
        "provenance_id": provenance,
        "rest_corner_angle_rad": corner,
        "rest_corner_angle_unit": "rad",
        "shear_stiffness_n_mm": shear,
        "shear_stiffness_unit": "N*mm",
        "rest_dihedral_rad": dihedral,
        "rest_dihedral_unit": "rad",
        "bending_stiffness_n_mm": bending,
        "bending_stiffness_unit": "N*mm",
    }
    encoded = jcs_bytes(payload)
    return ShellParameters(
        "1.0.0",
        "HYPOTHESIS",
        provenance,
        corner,
        shear,
        dihedral,
        bending,
        encoded,
        _hash(PROFILE, encoded),
    )


def prepare_shell_terms(
    vertices: tuple[str, ...], faces: tuple[tuple[str, str, str], ...], parameters: ShellParameters
) -> ShellTerms:
    """Create a corner term for every face corner and one hinge per shared edge."""
    _validate_parameters(parameters)
    if not isinstance(vertices, tuple) or not 0 < len(vertices) <= MAX_VERTICES:
        raise ShellTermsError("E_INPUT", "vertices.budget_or_type_invalid")
    if not isinstance(faces, tuple) or not 0 < len(faces) <= MAX_FACES:
        raise ShellTermsError("E_INPUT", "faces.budget_or_type_invalid")
    if any(not isinstance(v, str) or not v or not v.isascii() or len(v) > 128 for v in vertices):
        raise ShellTermsError("E_INPUT", "vertices.identifier_invalid")
    if len(set(vertices)) != len(vertices):
        raise ShellTermsError("E_INPUT", "vertices.identifier_duplicate")
    if any(
        not isinstance(face, tuple) or len(face) != 3 or any(not isinstance(v, str) for v in face)
        for face in faces
    ):
        raise ShellTermsError("E_INPUT", "faces.triangle_invalid")
    ordered_vertices, ordered_faces = tuple(sorted(vertices)), tuple(sorted(faces))
    if len(set(ordered_faces)) != len(ordered_faces):
        raise ShellTermsError("E_INPUT", "faces.duplicate")
    try:
        audit = audit_surface_topology(
            list(ordered_vertices),
            [list(f) for f in ordered_faces],
            max_vertices=MAX_VERTICES,
            max_faces=MAX_FACES,
        )
    except SurfaceTopologyInputError as error:
        raise ShellTermsError("E_TOPOLOGY", str(error)) from error
    if audit.status != "PASS":
        raise ShellTermsError(
            "E_TOPOLOGY", "surface.topology_audit_failed:" + ",".join(audit.diagnostics)
        )
    rest_cos = math.cos(parameters.rest_corner_angle_rad)
    corners = tuple(
        ShellCornerTerm(face, center, first, second, rest_cos, parameters.shear_stiffness_n_mm)
        for face in ordered_faces
        for center, first, second in (
            (face[0], face[1], face[2]),
            (face[1], face[2], face[0]),
            (face[2], face[0], face[1]),
        )
    )
    edge_faces: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)
    for a, b, c in ordered_faces:
        for start, end in ((a, b), (b, c), (c, a)):
            edge_faces[(min(start, end), max(start, end))].append((a, b, c))
    hinges: list[ShellHingeTerm] = []
    for (a, c), incident in sorted(edge_faces.items()):
        if len(incident) != 2:
            raise ShellTermsError("E_TOPOLOGY", "hinge.edge_incidence_invalid")
        rotations = [rotated for face in incident if (rotated := _rotate_at(face, a)) is not None]
        first = next((face for face in rotations if face[2] == c), None)
        second = next((face for face in rotations if face[1] == c), None)
        if first is None or second is None:
            raise ShellTermsError("E_TOPOLOGY", "hinge.orientation_invalid")
        hinges.append(
            ShellHingeTerm(
                (a, first[1], c, second[2]),
                parameters.rest_dihedral_rad,
                parameters.bending_stiffness_n_mm,
            )
        )
    hinges.sort(key=lambda t: t.vertices)
    if len(hinges) > MAX_HINGES:
        raise ShellTermsError("E_INPUT", "hinges.budget_exceeded")
    hinge_tuple = tuple(hinges)
    payload = _terms_payload(
        "EXPERIMENTAL_CLOSED_SHELL_TERMS",
        ordered_vertices,
        ordered_faces,
        parameters.sha256,
        corners,
        hinge_tuple,
    )
    encoded = jcs_bytes(payload)
    return ShellTerms(
        "EXPERIMENTAL_CLOSED_SHELL_TERMS",
        ordered_vertices,
        ordered_faces,
        parameters,
        parameters.sha256,
        corners,
        hinge_tuple,
        encoded,
        _hash(TERMS_PROFILE, encoded),
    )


def evaluate_shell_terms(terms: ShellTerms, points: Mapping[str, Vec3]) -> ShellEvaluation:
    """Evaluate energies in N*mm and negative-gradient forces in N."""
    _validate_terms(terms)
    if not isinstance(points, Mapping) or set(points) != set(terms.vertices):
        raise ShellTermsError("E_INPUT", "points.identifiers_invalid")
    coords = {key: _point(point) for key, point in points.items()}
    forces: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    shear_parts: list[float] = []
    bend_parts: list[float] = []
    try:
        for t in terms.corners:
            center, p, q = (coords[key] for key in (t.center, t.first, t.second))
            u, v = _sub_float(p, center), _sub_float(q, center)
            lu, lv = _length(u), _length(v)
            if lu <= MIN_EDGE_LENGTH_MM or lv <= MIN_EDGE_LENGTH_MM:
                raise ShellTermsError("E_INPUT", "shear.face_edge_degenerate")
            denominator = lu * lv
            if not math.isfinite(denominator) or denominator <= 0.0:
                raise ShellTermsError("E_INPUT", "shear.normalization_non_finite")
            cosine = math.fsum(u[i] * v[i] for i in range(3)) / denominator
            if not math.isfinite(cosine):
                raise ShellTermsError("E_INPUT", "shear.cosine_non_finite")
            if not -1.0 <= cosine <= 1.0:
                raise ShellTermsError("E_INPUT", "shear.cosine_out_of_range")
            delta = cosine - t.rest_cosine
            kdelta = t.stiffness_n_mm * delta
            shear_parts.append(0.5 * kdelta * delta)
            du = tuple(v[i] / denominator - cosine * u[i] / (lu * lu) for i in range(3))
            dv = tuple(u[i] / denominator - cosine * v[i] / (lv * lv) for i in range(3))
            _accumulate(forces, t.first, tuple(-kdelta * x for x in du))
            _accumulate(forces, t.second, tuple(-kdelta * x for x in dv))
            _accumulate(forces, t.center, tuple(kdelta * (du[i] + dv[i]) for i in range(3)))
        for hinge in terms.hinges:
            pts = cast(tuple[Vec3, Vec3, Vec3, Vec3], tuple(coords[key] for key in hinge.vertices))
            angle = _dihedral(pts)
            delta = math.remainder(angle - hinge.rest_dihedral_rad, math.tau)
            if abs(abs(delta) - math.pi) <= ANGLE_BRANCH_TOLERANCE_RAD:
                raise ShellTermsError("E_INPUT", "bending.angle_branch_ambiguous")
            bend_parts.append(hinge.stiffness_n_mm * delta * delta)
            gradient = _dihedral_gradient(pts)
            for key, row in zip(hinge.vertices, gradient, strict=True):
                _accumulate(forces, key, tuple(-2 * hinge.stiffness_n_mm * delta * x for x in row))
        shear, bending = math.fsum(shear_parts), math.fsum(bend_parts)
        total = math.fsum((shear, bending))
    except ShellTermsError:
        raise
    except (OverflowError, ValueError, ForwardBendingError) as error:
        reason = (
            error.reason
            if isinstance(error, ForwardBendingError)
            else "result.numeric_failure"
        )
        raise ShellTermsError("E_INPUT", reason) from error
    rows = tuple((key, cast(Vec3, tuple(row))) for key, row in sorted(forces.items()))
    if any(not math.isfinite(x) for x in (shear, bending, total, *(v for _, r in rows for v in r))):
        raise ShellTermsError("E_INPUT", "result.non_finite")
    maximum = max((math.hypot(*row) for _, row in rows), default=0.0)
    if not math.isfinite(maximum):
        raise ShellTermsError("E_INPUT", "result.non_finite")
    return ShellEvaluation(shear, bending, total, rows, maximum)


def _rotate_at(face: tuple[str, str, str], vertex: str) -> tuple[str, str, str] | None:
    for index in range(3):
        if face[index] == vertex:
            return face[index], face[(index + 1) % 3], face[(index + 2) % 3]
    return None


def _terms_payload(
    status: str,
    vertices: tuple[str, ...],
    faces: tuple[tuple[str, str, str], ...],
    parameter_hash: str,
    corners: tuple[ShellCornerTerm, ...],
    hinges: tuple[ShellHingeTerm, ...],
) -> dict[str, JSONValue]:
    return {
        "profile": TERMS_PROFILE,
        "status": status,
        "vertices": list(vertices),
        "faces": [list(face) for face in faces],
        "parameters_sha256": parameter_hash,
        "corners": [
            {
                "face": list(t.face),
                "center": t.center,
                "first": t.first,
                "second": t.second,
                "rest_cosine": t.rest_cosine,
                "stiffness_n_mm": t.stiffness_n_mm,
            }
            for t in corners
        ],
        "hinges": [
            {
                "vertices": list(t.vertices),
                "rest_dihedral_rad": t.rest_dihedral_rad,
                "stiffness_n_mm": t.stiffness_n_mm,
            }
            for t in hinges
        ],
    }


def _validate_parameters(p: ShellParameters) -> None:
    if not isinstance(p, ShellParameters):
        raise ShellTermsError("E_SCHEMA", "parameters.type_invalid")
    fresh = admit_shell_parameters(
        {
            "schema_version": p.schema_version,
            "status": p.status,
            "provenance_id": p.provenance_id,
            "rest_corner_angle_rad": p.rest_corner_angle_rad,
            "shear_stiffness_n_mm": p.shear_stiffness_n_mm,
            "rest_dihedral_rad": p.rest_dihedral_rad,
            "bending_stiffness_n_mm": p.bending_stiffness_n_mm,
        }
    )
    if p.canonical_bytes != fresh.canonical_bytes or p.sha256 != fresh.sha256:
        raise ShellTermsError("E_SCHEMA", "parameters.integrity_invalid")


def _validate_terms(t: ShellTerms) -> None:
    if not isinstance(t, ShellTerms) or t.status != "EXPERIMENTAL_CLOSED_SHELL_TERMS":
        raise ShellTermsError("E_SCHEMA", "terms.type_or_status_invalid")
    if (
        not isinstance(t.vertices, tuple)
        or not isinstance(t.faces, tuple)
        or not isinstance(t.corners, tuple)
        or not isinstance(t.hinges, tuple)
        or not isinstance(t.canonical_bytes, bytes)
        or not isinstance(t.sha256, str)
    ):
        raise ShellTermsError("E_SCHEMA", "terms.structure_invalid")
    try:
        audit = audit_surface_topology(
            list(t.vertices),
            [list(f) for f in t.faces],
            max_vertices=MAX_VERTICES,
            max_faces=MAX_FACES,
        )
    except (SurfaceTopologyInputError, TypeError) as error:
        raise ShellTermsError("E_TOPOLOGY", "terms.topology_invalid") from error
    if audit.status != "PASS":
        raise ShellTermsError("E_TOPOLOGY", "terms.topology_invalid")
    if tuple(sorted(t.vertices)) != t.vertices or tuple(sorted(t.faces)) != t.faces:
        raise ShellTermsError("E_SCHEMA", "terms.order_invalid")
    _validate_parameters(t.parameters)
    if t.parameters_sha256 != t.parameters.sha256:
        raise ShellTermsError("E_SCHEMA", "terms.integrity_invalid")
    expected = prepare_shell_terms(t.vertices, t.faces, t.parameters)
    if t.corners != expected.corners or t.hinges != expected.hinges:
        raise ShellTermsError("E_SCHEMA", "terms.semantic_content_invalid")
    encoded = jcs_bytes(
        _terms_payload(t.status, t.vertices, t.faces, t.parameters_sha256, t.corners, t.hinges)
    )
    if encoded != t.canonical_bytes or _hash(TERMS_PROFILE, encoded) != t.sha256:
        raise ShellTermsError("E_SCHEMA", "terms.integrity_invalid")


def _finite(value: object, reason: str) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        raise ShellTermsError("E_INPUT", reason)
    if isinstance(value, int) and abs(value) > SAFE_INTEGER:
        raise ShellTermsError("E_INPUT", reason)
    try:
        result = float(cast(int | float, value))
    except (OverflowError, ValueError) as error:
        raise ShellTermsError("E_INPUT", reason) from error
    if not math.isfinite(result):
        raise ShellTermsError("E_INPUT", reason)
    return result


def _point(value: object) -> Vec3:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ShellTermsError("E_INPUT", "points.coordinate_invalid")
    return cast(Vec3, tuple(_finite(x, "points.coordinate_non_finite") for x in value))


def _accumulate(forces: dict[str, list[float]], key: str, row: tuple[float, ...]) -> None:
    for axis in range(3):
        forces[key][axis] += row[axis]


def _hash(profile: str, encoded: bytes) -> str:
    return sha256(b"Crochet.AI\0" + profile.encode("ascii") + b"\0" + encoded).hexdigest()
