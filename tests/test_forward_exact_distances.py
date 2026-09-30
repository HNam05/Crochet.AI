from __future__ import annotations

import math
from fractions import Fraction

import pytest
from test_forward_aabb_broadphase import _coordinates, _initialization, _inputs, _source
from test_forward_pipeline_smoke import _run_pipeline

from crochet_ai.forward_exact_distances import (
    ForwardExactDistanceError,
    _pair_distance_squared,
    _point_segment_distance_squared,
    _point_triangle_distance_squared,
    _segment_segment_distance_squared,
    _triangle_distance_squared,
    diagnose_initial_exact_distances,
)
from crochet_ai.forward_exact_intersections import Triangle
from crochet_ai.forward_triangulation import triangulate_forward_surface_cells

Point = tuple[Fraction, Fraction, Fraction]


def _p(x: float, y: float, z: float) -> Point:
    return (Fraction.from_float(x), Fraction.from_float(y), Fraction.from_float(z))


def _q(x: Fraction, y: Fraction, z: Fraction) -> Point:
    return (x, y, z)


def _triangle(*points: tuple[float, float, float]) -> Triangle:
    first, second, third = points
    return (_p(*first), _p(*second), _p(*third))


def test_parallel_segments_have_exact_interior_distance() -> None:
    result = _segment_segment_distance_squared(
        (_p(0, 0, 0), _p(2, 0, 0)), (_p(0, 1, 0), _p(2, 1, 0))
    )
    assert result == 1


def test_skew_segment_stationary_minimum_is_interior() -> None:
    first = (_p(0, 0, 0), _p(2, 0, 0))
    second = (_p(1, -1, 1), _p(1, 1, 1))
    assert _segment_segment_distance_squared(first, second) == 1


def test_triangle_pair_minimum_is_interior_edge_edge_not_vertex_projection() -> None:
    first = _triangle((0, 0, 0), (2, 0, 0), (0.9, 0.1, 0))
    second = _triangle((1, -1, 1), (1, 1, 1), (1.1, -1, 1))

    # Every vertex projection misses the opposite triangle; the closest points
    # are the interiors (1, 0, 0) and (1, 0, 1) of the first two edges.
    assert _triangle_distance_squared(first, second) == 1
    assert all(_point_triangle_distance_squared(point, second) > 1 for point in first)
    assert all(_point_triangle_distance_squared(point, first) > 1 for point in second)


def test_point_triangle_projection_and_endpoint_clamp() -> None:
    face = _triangle((0, 0, 0), (2, 0, 0), (0, 2, 0))
    above_interior = _q(Fraction(1, 2), Fraction(1, 2), Fraction(3))
    assert _triangle_distance_squared((above_interior, _p(0, 0, 3), _p(0, 0, 4)), face) == 9
    assert _point_segment_distance_squared(_p(-1, 1, 0), (_p(0, 0, 0), _p(2, 0, 0))) == 2


def test_disjoint_triangles_one_ulp_apart_keep_exact_squared_gap() -> None:
    first = _triangle((0, 0, 0), (1, 0, 0), (0, 1, 0))
    x = math.nextafter(1.0, math.inf)
    second = _triangle((x, 0, 0), (x, 1, 0), (2, 0, 0))
    gap = Fraction.from_float(x) - 1
    assert _triangle_distance_squared(first, second) == gap * gap


def test_exact_intersection_returns_zero_and_separated_distance_is_symmetric() -> None:
    crossing = _triangle((0, 0, -1), (0, 0, 1), (0, 1, 0))
    base = _triangle((-1, 0, 0), (1, 0, 0), (0, -1, 0))
    assert _pair_distance_squared(crossing, base) == 0
    left = _triangle((0, 0, 0), (1, 0, 0), (0, 1, 0))
    right = _triangle((0, 0, 2), (1, 0, 2), (0, 1, 2))
    assert _triangle_distance_squared(left, right) == _triangle_distance_squared(right, left) == 4


def test_coplanar_containment_returns_zero_from_pair_dispatch() -> None:
    containing = _triangle((0, 0, 0), (4, 0, 0), (0, 4, 0))
    contained = _triangle((0.5, 0.5, 0), (1, 0.5, 0), (0.5, 1, 0))
    assert _pair_distance_squared(contained, containing) == 0


def test_exact_distance_rational_denominator_can_exceed_binary64_integer_range() -> None:
    height = 2.0**-54
    first = _triangle((0, 0, 0), (2, 0, 0), (0, 2, 0))
    second = _triangle((0, 0, height), (2, 0, height), (0, 2, height))
    distance = _pair_distance_squared(first, second)
    assert distance == Fraction(1, 2**108)
    assert distance.denominator > 2**53


def test_open_cylinder_integrates_all_pair_exact_diagnostic_deterministically() -> None:
    _, _, _, inputs, initialization, cells, triangulation, _, _ = _run_pipeline((0, 0))
    result = diagnose_initial_exact_distances(cells, triangulation, initialization, inputs)
    repeated = diagnose_initial_exact_distances(cells, triangulation, initialization, inputs)
    assert result.status == "DISTANCE_DIAGNOSTIC_ONLY"
    assert result.all_pair_count == 24 * 23 // 2
    assert result.nonadjacent_pair_count < result.all_pair_count
    assert result.minimum_squared_distance_numerator is not None
    assert result.minimum_squared_distance_denominator is not None
    assert result == repeated
    assert result.sha256 == repeated.sha256


def test_identity_shared_faces_are_excluded_and_budget_is_all_pairs() -> None:
    inputs = _inputs(28)
    source = _source()
    triangulation = triangulate_forward_surface_cells(source)
    initialization = _initialization(inputs)
    result = diagnose_initial_exact_distances(source, triangulation, initialization, inputs)
    assert result.all_pair_count == 28
    assert result.nonadjacent_pair_count < 28
    too_small_inputs = _inputs(27)
    too_small_initialization = _initialization(too_small_inputs)
    with pytest.raises(ForwardExactDistanceError, match="pair_budget_exhausted"):
        diagnose_initial_exact_distances(
            source, triangulation, too_small_initialization, too_small_inputs
        )


def test_shared_ids_define_adjacency_even_when_distinct_ids_share_coordinates() -> None:
    inputs = _inputs(28)
    source = _source()
    triangulation = triangulate_forward_surface_cells(source)
    coordinates = dict(_coordinates())
    coordinates["upper_2"] = coordinates["lower_0"]
    initialization = _initialization(inputs, tuple(sorted(coordinates.items())))

    result = diagnose_initial_exact_distances(source, triangulation, initialization, inputs)
    assert result.nonadjacent_pair_count < result.all_pair_count
    assert result.minimum_squared_distance_numerator == "0"
    for first_index, second_index in result.minimizing_face_pairs:
        first_ids = set(triangulation.triangles[first_index].attachment_location_ids)
        second_ids = set(triangulation.triangles[second_index].attachment_location_ids)
        if first_ids.isdisjoint(second_ids):
            first_positions = {coordinates[identifier] for identifier in first_ids}
            second_positions = {coordinates[identifier] for identifier in second_ids}
            if first_positions.intersection(second_positions):
                break
    else:
        pytest.fail("coordinate coincidence between distinct IDs was not retained as a pair")


def test_input_integrity_and_canonical_rational_encoding() -> None:
    inputs = _inputs(28)
    source = _source()
    triangulation = triangulate_forward_surface_cells(source)
    initialization = _initialization(inputs)
    result = diagnose_initial_exact_distances(source, triangulation, initialization, inputs)
    assert b'"status":"DISTANCE_DIAGNOSTIC_ONLY"' in result.canonical_bytes
    if result.minimum_squared_distance_numerator is not None:
        rational = Fraction(
            int(result.minimum_squared_distance_numerator),
            int(result.minimum_squared_distance_denominator or "0"),
        )
        assert str(rational.numerator) == result.minimum_squared_distance_numerator
        assert str(rational.denominator) == result.minimum_squared_distance_denominator
    with pytest.raises(ForwardExactDistanceError, match="forward_inputs_binding_mismatch"):
        diagnose_initial_exact_distances(
            source,
            triangulation,
            _initialization(inputs, forward_inputs_sha256="d" * 64),
            inputs,
        )
