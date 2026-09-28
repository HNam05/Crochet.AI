"""Experimental force and energy diagnostic for prepared stretch artifacts.

This module evaluates only the declared spring terms at an experimental
initialization. It is not an optimizer, simulator, or verification gate.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256

from .canonical import jcs_bytes
from .forward_initialization import PROFILE as INITIALIZATION_PROFILE
from .forward_initialization import ForwardInitialization
from .forward_stretch import ForwardStretchTerms, StretchTerm
from .json_types import JSONValue

PROFILE = "FORWARD_STRETCH_DIAGNOSTIC_V1"


class ForwardForceError(ValueError):
    """Invalid, inconsistent, or numerically undefined stretch diagnostic input."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ForwardForceDiagnostic:
    """Immutable experimental spring energy and nodal force values."""

    status: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    energy_n_mm: float
    forces_n: tuple[tuple[str, tuple[float, float, float]], ...]
    maximum_force_n: float
    canonical_bytes: bytes
    sha256: str


def evaluate_initial_stretch_forces(
    terms: ForwardStretchTerms,
    initialization: ForwardInitialization,
) -> ForwardForceDiagnostic:
    """Evaluate experimental spring energy and negative gradient forces.

    The public boundary accepts only the immutable prepared terms and
    initialization artifact. It accepts no raw coordinates or target data.
    """

    if not isinstance(terms, ForwardStretchTerms):
        raise ForwardForceError("forces.terms_type")
    if not isinstance(initialization, ForwardInitialization):
        raise ForwardForceError("forces.initialization_type")
    if terms.status != "EXPERIMENTAL_STRETCH_TERMS":
        raise ForwardForceError("forces.terms_status")
    if initialization.status != "EXPERIMENTAL_INITIALIZATION":
        raise ForwardForceError("forces.initialization_status")
    for digest in (
        terms.projection_sha256,
        terms.material_sha256,
        terms.forward_inputs_sha256,
        initialization.projection_sha256,
        initialization.material_sha256,
        initialization.forward_inputs_sha256,
    ):
        if not _is_sha256(digest):
            raise ForwardForceError("forces.hash_invalid")
    if terms.projection_sha256 != initialization.projection_sha256:
        raise ForwardForceError("forces.projection_hash_mismatch")
    if terms.material_sha256 != initialization.material_sha256:
        raise ForwardForceError("forces.material_hash_mismatch")
    if terms.forward_inputs_sha256 != initialization.forward_inputs_sha256:
        raise ForwardForceError("forces.inputs_hash_mismatch")
    coordinates: dict[str, tuple[float, float, float]] = {}
    for coordinate in initialization.coordinates_mm:
        if not isinstance(coordinate, tuple) or len(coordinate) != 2:
            raise ForwardForceError("forces.coordinate_invalid")
        location_id, point = coordinate
        if not isinstance(location_id, str) or not location_id:
            raise ForwardForceError("forces.endpoint_invalid")
        if location_id in coordinates:
            raise ForwardForceError("forces.endpoint_duplicate")
        if (
            not isinstance(point, tuple)
            or len(point) != 3
            or any(not _finite_number(value) for value in point)
        ):
            raise ForwardForceError("forces.coordinate_invalid")
        coordinates[location_id] = (float(point[0]), float(point[1]), float(point[2]))
    _validate_initialization_integrity(initialization)

    if not isinstance(terms.terms, tuple) or not all(
        isinstance(term, StretchTerm) for term in terms.terms
    ):
        raise ForwardForceError("forces.term_type_invalid")
    for term in terms.terms:
        _validate_term(term)
    energy_total, force_rows, maximum_force = _evaluate_stretch_terms_at_coordinates(
        terms.terms, coordinates
    )

    result_payload: dict[str, JSONValue] = {
        "profile": PROFILE,
        "status": "EXPERIMENTAL_STRETCH_DIAGNOSTIC",
        "projection_sha256": terms.projection_sha256,
        "material_sha256": terms.material_sha256,
        "forward_inputs_sha256": terms.forward_inputs_sha256,
        "energy_n_mm": energy_total,
        "forces_n": [
            {"attachment_location_id": location_id, "xyz_n": list(force)}
            for location_id, force in force_rows
        ],
        "maximum_force_n": maximum_force,
    }
    encoded = jcs_bytes(result_payload)
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardForceDiagnostic(
        "EXPERIMENTAL_STRETCH_DIAGNOSTIC",
        terms.projection_sha256,
        terms.material_sha256,
        terms.forward_inputs_sha256,
        energy_total,
        force_rows,
        maximum_force,
        encoded,
        digest,
    )


def _evaluate_stretch_terms_at_coordinates(
    terms: tuple[StretchTerm, ...],
    coordinates: dict[str, tuple[float, float, float]],
) -> tuple[float, tuple[tuple[str, tuple[float, float, float]], ...], float]:
    """Private pure energy/force kernel for already-bound artifacts and trial points."""

    if not isinstance(terms, tuple) or not all(isinstance(term, StretchTerm) for term in terms):
        raise ForwardForceError("forces.term_type_invalid")
    for term in terms:
        _validate_term(term)
    ordered_terms = sorted(
        terms,
        key=lambda term: (
            term.edge_type,
            term.source_location_id,
            term.target_location_id,
            term.response_id,
        ),
    )
    seen_terms: set[tuple[str, str, str, str]] = set()
    energy_terms: list[float] = []
    force_parts: dict[str, list[list[float]]] = defaultdict(lambda: [[], [], []])
    for term in ordered_terms:
        term_key = (
            term.edge_type,
            term.source_location_id,
            term.target_location_id,
            term.response_id,
        )
        if term_key in seen_terms:
            raise ForwardForceError("forces.term_duplicate")
        seen_terms.add(term_key)
        if term.source_location_id == term.target_location_id:
            raise ForwardForceError("forces.endpoint_duplicate")
        source = coordinates.get(term.source_location_id)
        target = coordinates.get(term.target_location_id)
        if source is None or target is None:
            raise ForwardForceError("forces.endpoint_missing")
        delta = tuple(target[index] - source[index] for index in range(3))
        if any(not math.isfinite(value) for value in delta):
            raise ForwardForceError("forces.displacement_non_finite")
        distance = math.hypot(*delta)
        if not math.isfinite(distance):
            raise ForwardForceError("forces.distance_non_finite")
        if distance == 0.0:
            raise ForwardForceError("forces.zero_distance")

        extension = distance - term.rest_length_mm
        try:
            energy = 0.5 * term.stiffness_n_per_mm * extension**2
            scale = term.stiffness_n_per_mm * extension / distance
        except OverflowError as error:
            raise ForwardForceError("forces.term_result_non_finite") from error
        source_force = tuple(scale * value for value in delta)
        if (
            not math.isfinite(extension)
            or not math.isfinite(energy)
            or not math.isfinite(scale)
            or any(not math.isfinite(value) for value in source_force)
        ):
            raise ForwardForceError("forces.term_result_non_finite")
        energy_terms.append(energy)
        for axis in range(3):
            force_parts[term.source_location_id][axis].append(source_force[axis])
            force_parts[term.target_location_id][axis].append(-source_force[axis])

    energy_total = _finite_fsum(energy_terms, "forces.energy_non_finite")
    force_rows: list[tuple[str, tuple[float, float, float]]] = []
    maximum_force = 0.0
    for location_id in sorted(coordinates):
        components: tuple[float, float, float] = (
            _finite_fsum(force_parts[location_id][0], "forces.sum_non_finite"),
            _finite_fsum(force_parts[location_id][1], "forces.sum_non_finite"),
            _finite_fsum(force_parts[location_id][2], "forces.sum_non_finite"),
        )
        magnitude = math.hypot(*components)
        if not math.isfinite(magnitude):
            raise ForwardForceError("forces.norm_non_finite")
        maximum_force = max(maximum_force, magnitude)
        force_rows.append((location_id, components))

    return energy_total, tuple(force_rows), maximum_force


def _validate_term(term: StretchTerm) -> None:
    if not isinstance(term, StretchTerm):
        raise ForwardForceError("forces.term_type_invalid")
    if not isinstance(term.edge_type, str) or term.edge_type not in {"COURSE", "WALE"}:
        raise ForwardForceError("forces.term_type_invalid")
    if any(
        not isinstance(value, str) or not value
        for value in (term.source_location_id, term.target_location_id, term.response_id)
    ):
        raise ForwardForceError("forces.term_provenance_invalid")
    if not _finite_number(term.rest_length_mm) or term.rest_length_mm <= 0:
        raise ForwardForceError("forces.rest_length_invalid")
    if not _finite_number(term.stiffness_n_per_mm) or term.stiffness_n_per_mm <= 0:
        raise ForwardForceError("forces.stiffness_invalid")


def _validate_initialization_integrity(initialization: ForwardInitialization) -> None:
    coordinates = initialization.coordinates_mm
    if len({location_id for location_id, _ in coordinates}) != len(coordinates):
        raise ForwardForceError("forces.endpoint_duplicate")
    payload: dict[str, JSONValue] = {
        "profile": INITIALIZATION_PROFILE,
        "status": initialization.status,
        "projection_sha256": initialization.projection_sha256,
        "material_sha256": initialization.material_sha256,
        "forward_inputs_sha256": initialization.forward_inputs_sha256,
        "anchor_location_groups": [list(group) for group in initialization.anchor_location_groups],
        "coordinates_mm": [
            {"attachment_location_id": location_id, "xyz_mm": list(point)}
            for location_id, point in coordinates
        ],
    }
    encoded = jcs_bytes(payload)
    expected_hash = sha256(
        b"Crochet.AI\0" + INITIALIZATION_PROFILE.encode("ascii") + b"\0" + encoded
    ).hexdigest()
    if encoded != initialization.canonical_bytes or expected_hash != initialization.sha256:
        raise ForwardForceError("forces.initialization_integrity")


def _finite_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _is_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _finite_fsum(values: list[float], reason: str) -> float:
    try:
        result = math.fsum(values)
    except OverflowError as error:
        raise ForwardForceError(reason) from error
    if not math.isfinite(result):
        raise ForwardForceError(reason)
    return result
