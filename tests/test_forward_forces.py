from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from math import fsum

import pytest

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_forces import (
    ForwardForceError,
    evaluate_initial_stretch_forces,
)
from crochet_ai.forward_initialization import (
    PROFILE as INITIALIZATION_PROFILE,
)
from crochet_ai.forward_initialization import (
    ForwardInitialization,
)
from crochet_ai.forward_stretch import ForwardStretchTerms, StretchTerm
from crochet_ai.json_types import JSONValue


def _artifacts(
    coordinates: tuple[tuple[str, tuple[float, float, float]], ...] = (
        ("node_a", (0.0, 0.0, 0.0)),
        ("node_b", (3.0, 4.0, 0.0)),
        ("node_free", (1.0, 1.0, 1.0)),
    ),
    terms: tuple[StretchTerm, ...] = (
        StretchTerm("COURSE", "node_a", "node_b", 3.0, 2.0, "response-1"),
    ),
) -> tuple[ForwardStretchTerms, ForwardInitialization]:
    projection_hash = "a" * 64
    material_hash = "b" * 64
    inputs_hash = "c" * 64
    anchor_groups = (("ring_0", "ring_1"),)
    payload: dict[str, JSONValue] = {
        "profile": INITIALIZATION_PROFILE,
        "status": "EXPERIMENTAL_INITIALIZATION",
        "projection_sha256": projection_hash,
        "material_sha256": material_hash,
        "forward_inputs_sha256": inputs_hash,
        "anchor_location_groups": [list(group) for group in anchor_groups],
        "coordinates_mm": [
            {"attachment_location_id": location_id, "xyz_mm": list(point)}
            for location_id, point in coordinates
        ],
    }
    encoded = jcs_bytes(payload)
    init_hash = sha256(
        b"Crochet.AI\0" + INITIALIZATION_PROFILE.encode("ascii") + b"\0" + encoded
    ).hexdigest()
    initialization = ForwardInitialization(
        "EXPERIMENTAL_INITIALIZATION",
        projection_hash,
        material_hash,
        inputs_hash,
        anchor_groups,
        coordinates,
        encoded,
        init_hash,
    )
    stretch_terms = ForwardStretchTerms(
        "EXPERIMENTAL_STRETCH_TERMS",
        projection_hash,
        material_hash,
        inputs_hash,
        terms,
    )
    return stretch_terms, initialization


def test_exact_two_node_spring_energy_force_and_zero_force_nodes() -> None:
    terms, initialization = _artifacts()
    result = evaluate_initial_stretch_forces(terms, initialization)
    forces = dict(result.forces_n)
    assert result.status == "EXPERIMENTAL_STRETCH_DIAGNOSTIC"
    assert result.energy_n_mm == pytest.approx(4.0)
    assert forces["node_a"] == pytest.approx((2.4, 3.2, 0.0))
    assert forces["node_b"] == pytest.approx((-2.4, -3.2, 0.0))
    assert forces["node_free"] == (0.0, 0.0, 0.0)
    assert result.maximum_force_n == pytest.approx(4.0)
    assert tuple(location_id for location_id, _ in result.forces_n) == (
        "node_a",
        "node_b",
        "node_free",
    )


def test_force_is_negative_finite_difference_energy_gradient() -> None:
    terms, initialization = _artifacts(
        coordinates=(("node_a", (0.0, 0.0, 0.0)), ("node_b", (4.0, 0.0, 0.0)))
    )
    force = dict(evaluate_initial_stretch_forces(terms, initialization).forces_n)["node_a"][0]
    step = 1e-6

    def energy_at(source_x: float) -> float:
        _, moved = _artifacts(
            coordinates=(("node_a", (source_x, 0.0, 0.0)), ("node_b", (4.0, 0.0, 0.0)))
        )
        return evaluate_initial_stretch_forces(terms, moved).energy_n_mm

    derivative = (energy_at(step) - energy_at(-step)) / (2.0 * step)
    assert force == pytest.approx(-derivative, abs=1e-8)


def test_internal_spring_forces_satisfy_newtons_third_law() -> None:
    terms, initialization = _artifacts()
    result = evaluate_initial_stretch_forces(terms, initialization)
    assert tuple(
        fsum(force[axis] for _, force in result.forces_n) for axis in range(3)
    ) == pytest.approx((0.0, 0.0, 0.0), abs=1e-14)


def test_energy_overflow_is_a_structured_failure() -> None:
    terms, initialization = _artifacts(
        coordinates=(
            ("node_a", (0.0, 0.0, 0.0)),
            ("node_b", (1e200, 0.0, 0.0)),
        )
    )
    with pytest.raises(ForwardForceError, match="term_result_non_finite"):
        evaluate_initial_stretch_forces(terms, initialization)


def test_provenance_mismatches_and_statuses_are_rejected() -> None:
    terms, initialization = _artifacts()
    with pytest.raises(ForwardForceError, match="projection_hash_mismatch"):
        evaluate_initial_stretch_forces(replace(terms, projection_sha256="d" * 64), initialization)
    with pytest.raises(ForwardForceError, match="material_hash_mismatch"):
        evaluate_initial_stretch_forces(replace(terms, material_sha256="d" * 64), initialization)
    with pytest.raises(ForwardForceError, match="inputs_hash_mismatch"):
        evaluate_initial_stretch_forces(
            replace(terms, forward_inputs_sha256="d" * 64), initialization
        )
    with pytest.raises(ForwardForceError, match="terms_status"):
        evaluate_initial_stretch_forces(replace(terms, status="CONVERGED"), initialization)
    with pytest.raises(ForwardForceError, match="initialization_status"):
        evaluate_initial_stretch_forces(terms, replace(initialization, status="CONVERGED"))


@pytest.mark.parametrize(
    ("terms_override", "coordinates", "reason"),
    [
        (None, (("node_a", (0.0, 0.0, 0.0)), ("node_b", (0.0, 0.0, 0.0))), "zero_distance"),
        (
            (StretchTerm("COURSE", "missing", "node_b", 3.0, 2.0, "response-1"),),
            (("node_a", (0.0, 0.0, 0.0)), ("node_b", (3.0, 0.0, 0.0))),
            "endpoint_missing",
        ),
        (
            (StretchTerm("COURSE", "node_a", "node_b", 0.0, 2.0, "response-1"),),
            (("node_a", (0.0, 0.0, 0.0)), ("node_b", (3.0, 0.0, 0.0))),
            "rest_length_invalid",
        ),
        (
            (StretchTerm("COURSE", "node_a", "node_b", 3.0, float("nan"), "response-1"),),
            (("node_a", (0.0, 0.0, 0.0)), ("node_b", (3.0, 0.0, 0.0))),
            "stiffness_invalid",
        ),
        (
            None,
            (("node_a", (1e308, 0.0, 0.0)), ("node_b", (-1e308, 0.0, 0.0))),
            "displacement_non_finite",
        ),
    ],
)
def test_invalid_endpoints_and_numerics_fail_closed(
    terms_override: tuple[StretchTerm, ...] | None,
    coordinates: tuple[tuple[str, tuple[float, float, float]], ...],
    reason: str,
) -> None:
    terms, initialization = _artifacts(coordinates=coordinates)
    if terms_override is not None:
        terms = replace(terms, terms=terms_override)
    with pytest.raises(ForwardForceError, match=reason):
        evaluate_initial_stretch_forces(terms, initialization)


def test_duplicate_endpoints_and_terms_are_rejected() -> None:
    terms, initialization = _artifacts()
    duplicate_coordinates = replace(
        initialization,
        coordinates_mm=(
            *initialization.coordinates_mm,
            ("node_a", (2.0, 0.0, 0.0)),
        ),
    )
    with pytest.raises(ForwardForceError, match="endpoint_duplicate"):
        evaluate_initial_stretch_forces(terms, duplicate_coordinates)
    duplicate_terms = replace(terms, terms=terms.terms * 2)
    with pytest.raises(ForwardForceError, match="term_duplicate"):
        evaluate_initial_stretch_forces(duplicate_terms, initialization)


def test_nonfinite_coordinates_and_initialization_integrity_are_rejected() -> None:
    terms, initialization = _artifacts()
    nonfinite = replace(
        initialization,
        coordinates_mm=(
            ("node_a", (float("nan"), 0.0, 0.0)),
            *initialization.coordinates_mm[1:],
        ),
    )
    with pytest.raises(ForwardForceError, match="coordinate_invalid"):
        evaluate_initial_stretch_forces(terms, nonfinite)
    tampered = replace(initialization, coordinates_mm=initialization.coordinates_mm[:-1])
    with pytest.raises(ForwardForceError, match="initialization_integrity"):
        evaluate_initial_stretch_forces(terms, tampered)


def test_repeated_evaluation_has_identical_bytes_and_hash() -> None:
    terms, initialization = _artifacts()
    first = evaluate_initial_stretch_forces(terms, initialization)
    second = evaluate_initial_stretch_forces(terms, initialization)
    assert first.canonical_bytes == second.canonical_bytes
    assert first.sha256 == second.sha256


def test_public_api_does_not_accept_raw_coordinates_or_target_data() -> None:
    terms, initialization = _artifacts()
    with pytest.raises(TypeError):
        evaluate_initial_stretch_forces(
            terms,
            initialization,
            target_mesh={},  # type: ignore[call-arg]
        )
