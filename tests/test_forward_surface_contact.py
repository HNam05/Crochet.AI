from __future__ import annotations

import math

import pytest

from crochet_ai.forward_surface_contact import (
    ContactBudgetContext,
    ContactError,
    ContactParameters,
    ContactSurface,
    admit_contact_parameters,
    certify_contact_path,
    evaluate_contact,
    prepare_surface_contact,
)

FACES = ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3))
TETRA = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def params(**overrides: object):
    value: dict[str, object] = {
        "schema_version": 1,
        "status": "HYPOTHESIS",
        "provenance_id": "test-contact-hypothesis",
        "activation_distance_mm": 0.5,
        "minimum_clearance_mm": 0.1,
        "stiffness_n_per_mm": 2.0,
        "max_pair_evaluations": 1000,
    }
    value.update(overrides)
    return admit_contact_parameters(value)


def joined_tetrahedra(second_x: float):
    return prepare_surface_contact(
        TETRA + tuple((x + second_x, y, z) for x, y, z in TETRA),
        FACES + tuple(tuple(index + 4 for index in face) for face in FACES),
    )


def test_contact_energy_has_balanced_negative_gradient_forces() -> None:
    surface = joined_tetrahedra(1.3)
    context = ContactBudgetContext()
    coordinates = tuple(tuple(float(value) for value in point) for point in surface.vertices)
    result = evaluate_contact(surface, coordinates, params(), context)
    assert result.energy_n_mm > 0
    force = [0.0, 0.0, 0.0]
    for _, vector in result.forces_n:
        for axis in range(3):
            force[axis] += vector[axis]
    assert force == pytest.approx((0.0, 0.0, 0.0), abs=1e-12)
    assert result.static_report[0] == ("population_pairs", 28)
    assert context.pair_evaluations == context.broadphase_candidate_tests


def test_static_nonadjacent_crossing_is_rejected_and_adjacency_is_not_barriered() -> None:
    surface = joined_tetrahedra(0.1)
    with pytest.raises(ContactError, match="nonadjacent_triangles_intersect"):
        evaluate_contact(
            surface,
            tuple(tuple(float(value) for value in point) for point in surface.vertices),
            params(),
            ContactBudgetContext(),
        )


def test_exact_sweep_avoids_far_pairs_under_small_budget() -> None:
    surface = joined_tetrahedra(100.0)
    report = evaluate_contact(
        surface,
        tuple(tuple(float(value) for value in point) for point in surface.vertices),
        params(max_pair_evaluations=20),
        ContactBudgetContext(),
    )
    assert report.energy_n_mm == 0
    assert report.pair_evaluations < 28
    assert report.static_report[1][1] == report.pair_evaluations


def test_path_certificate_accepts_clear_step_and_rejects_endpoint_safe_crossing() -> None:
    surface = joined_tetrahedra(4.0)
    start = tuple(tuple(float(value) for value in point) for point in surface.vertices)
    stationary = certify_contact_path(surface, start, start, params(), ContactBudgetContext())
    assert stationary.status == "SAFE"

    crossing_end = tuple(
        (point[0] - (8.0 if index >= 4 else 0.0), point[1], point[2])
        for index, point in enumerate(start)
    )
    certificate = certify_contact_path(
        surface, start, crossing_end, params(), ContactBudgetContext()
    )
    assert certificate.status in {"INDETERMINATE", "BUDGET_EXHAUSTED"}
    assert certificate.status != "SAFE"


def test_target_free_parameter_admission_is_fail_closed() -> None:
    with pytest.raises(ContactError, match="status_must_be_hypothesis"):
        params(status="CALIBRATED")
    with pytest.raises(ContactError, match="pair_budget_out_of_range"):
        params(max_pair_evaluations=2_000_001)
    with pytest.raises(ContactError, match="activation_must_exceed_clearance"):
        params(activation_distance_mm=0.1)
    with pytest.raises(ContactError, match="schema_version_unsupported"):
        params(schema_version=1.0)
    with pytest.raises(ContactError, match="activation_distance_out_of_range"):
        params(activation_distance_mm=10**1000)


def test_invalid_degenerate_or_open_surface_is_rejected() -> None:
    with pytest.raises(ContactError, match="not_closed_consistently_oriented"):
        prepare_surface_contact(TETRA, FACES[:3])
    with pytest.raises(ContactError, match="degenerate_triangle"):
        prepare_surface_contact(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)), ((0, 1, 2),))


def test_rigid_translation_preserves_energy_and_far_geometry_has_no_force() -> None:
    surface = joined_tetrahedra(1.3)
    coords = tuple(tuple(float(value) for value in point) for point in surface.vertices)
    moved = tuple((p[0] + 4.0, p[1] - 3.0, p[2] + 2.0) for p in coords)
    first = evaluate_contact(surface, coords, params(), ContactBudgetContext())
    second = evaluate_contact(surface, moved, params(), ContactBudgetContext())
    assert second.energy_n_mm == pytest.approx(first.energy_n_mm, rel=1e-12)
    assert all(math.isfinite(value) for _, vector in first.forces_n for value in vector)


def test_force_matches_energy_direction_under_rigid_component_translation() -> None:
    surface = joined_tetrahedra(1.3)
    coords = tuple(tuple(float(value) for value in point) for point in surface.vertices)
    value = evaluate_contact(surface, coords, params(), ContactBudgetContext())
    component_force_x = sum(vector[0] for index, vector in value.forces_n if index >= 4)
    step = 1e-6

    def shifted(offset: float) -> float:
        moved = tuple(
            (point[0] + (offset if index >= 4 else 0.0), point[1], point[2])
            for index, point in enumerate(coords)
        )
        return evaluate_contact(surface, moved, params(), ContactBudgetContext()).energy_n_mm

    derivative = (shifted(step) - shifted(-step)) / (2 * step)
    assert component_force_x == pytest.approx(-derivative, rel=2e-6, abs=2e-6)


def test_forged_surface_and_parameter_records_are_revalidated() -> None:
    surface = prepare_surface_contact(TETRA, FACES)
    forged_surface = ContactSurface(surface.vertices, FACES[:3], surface.topology_sha256)
    coords = tuple(tuple(float(value) for value in point) for point in surface.vertices)
    with pytest.raises(ContactError, match="not_closed_consistently_oriented"):
        evaluate_contact(forged_surface, coords, params(), ContactBudgetContext())
    forged_parameters = ContactParameters(1, "CALIBRATED", "forged", 0.5, 0.1, 2.0, 100)
    with pytest.raises(ContactError, match="status_must_be_hypothesis"):
        evaluate_contact(surface, coords, forged_parameters, ContactBudgetContext())


def test_vertex_adjacent_cube_path_has_a_fixed_separating_axis() -> None:
    vertices = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 1.0),
        (1.0, 1.0, 1.0),
        (0.0, 1.0, 1.0),
    )
    faces = (
        (0, 2, 1),
        (0, 3, 2),
        (4, 5, 6),
        (4, 6, 7),
        (0, 1, 5),
        (0, 5, 4),
        (3, 7, 6),
        (3, 6, 2),
        (0, 4, 7),
        (0, 7, 3),
        (1, 2, 6),
        (1, 6, 5),
    )
    surface = prepare_surface_contact(vertices, faces)
    coords = tuple(tuple(float(value) for value in point) for point in surface.vertices)
    result = certify_contact_path(surface, coords, coords, params(), ContactBudgetContext())
    assert result.status == "SAFE"


def test_coplanar_adjacent_cap_edge_is_permitted_without_area_overlap() -> None:
    from fractions import Fraction

    from crochet_ai.forward_surface_contact import _validate_static_adjacency

    first = (
        (Fraction(0), Fraction(0), Fraction(0)),
        (Fraction(1), Fraction(0), Fraction(0)),
        (Fraction(0), Fraction(1), Fraction(0)),
    )
    second = (
        (Fraction(0), Fraction(0), Fraction(0)),
        (Fraction(1), Fraction(0), Fraction(0)),
        (Fraction(0), Fraction(-1), Fraction(0)),
    )
    _validate_static_adjacency(first, second, (0, 1, 2), (0, 1, 3), (0, 1))

    from crochet_ai.forward_surface_contact import _validate_path_adjacency

    overlapping = (
        (Fraction(1), Fraction(0), Fraction(0)),
        (Fraction(0), Fraction(0), Fraction(0)),
        (Fraction(1, 5), Fraction(1, 2), Fraction(0)),
    )
    with pytest.raises(ContactError, match="adjacent_endpoint_relation_invalid"):
        _validate_path_adjacency(
            first, overlapping, first, overlapping, (0, 1, 2), (1, 0, 3), (0, 1)
        )


def test_candidate_budget_exhaustion_is_explicit_and_cumulative() -> None:
    surface = joined_tetrahedra(1.3)
    coords = tuple(tuple(float(value) for value in point) for point in surface.vertices)
    context = ContactBudgetContext(pair_evaluations=1)
    with pytest.raises(ContactError, match="pair_evaluation_budget_exhausted"):
        evaluate_contact(surface, coords, params(max_pair_evaluations=2), context)
    assert context.pair_evaluations == 2


def test_clearance_boundary_is_admissible() -> None:
    surface = joined_tetrahedra(1.125)
    coords = tuple(tuple(float(value) for value in point) for point in surface.vertices)
    result = evaluate_contact(
        surface,
        coords,
        params(minimum_clearance_mm=0.125),
        ContactBudgetContext(),
    )
    assert result.energy_n_mm > 0.0


def test_surface_caps_precede_topology_work_and_duplicates_are_rejected() -> None:
    with pytest.raises(ContactError, match="surface_size_limit_exceeded"):
        prepare_surface_contact(((0.0, 0.0, 0.0),) * 2049, FACES)
    with pytest.raises(ContactError, match="surface_size_limit_exceeded"):
        prepare_surface_contact(TETRA, FACES * 1025)
    with pytest.raises(ContactError, match="duplicate_face"):
        prepare_surface_contact(TETRA, (*FACES, FACES[0]))
    with pytest.raises(ContactError, match="coincident_vertices"):
        prepare_surface_contact((TETRA[0], TETRA[0], TETRA[2], TETRA[3]), FACES)


def test_extreme_finite_energy_and_exact_conversion_fail_with_typed_errors() -> None:
    from fractions import Fraction

    from crochet_ai.forward_surface_contact import _finite_energy_sum, _fraction_to_float

    surface = joined_tetrahedra(1.3)
    coords = tuple(tuple(float(value) for value in point) for point in surface.vertices)
    with pytest.raises(ContactError, match="pair_energy_not_finite"):
        evaluate_contact(
            surface,
            coords,
            params(activation_distance_mm=1e100, stiffness_n_per_mm=1e308),
            ContactBudgetContext(),
        )
    with pytest.raises(ContactError, match="closest_point_delta_conversion_overflow"):
        _fraction_to_float(Fraction(10**400), "closest_point_delta")
    with pytest.raises(ContactError, match="energy_sum_not_finite"):
        _finite_energy_sum([1e308, 1e308])
