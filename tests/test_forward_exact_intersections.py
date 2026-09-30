from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest
from test_forward_aabb_broadphase import _coordinates, _initialization, _inputs, _source
from test_forward_aabb_broadphase import _run as broadphase_run

from crochet_ai.forward_exact_intersections import (
    ForwardExactIntersectionError,
    _exact_zero_area,
    _in_shared_simplex,
    _triangle_intersections,
    diagnose_initial_exact_intersections,
)


def _p(x: float, y: float, z: float) -> tuple[Fraction, Fraction, Fraction]:
    return (Fraction.from_float(x), Fraction.from_float(y), Fraction.from_float(z))


def _triangle(*points: tuple[float, float, float]):
    return tuple(_p(*point) for point in points)


def test_nonadjacent_coplanar_overlap_is_found() -> None:
    first = _triangle((0, 0, 0), (2, 0, 0), (0, 2, 0))
    second = _triangle((0.5, 0.5, 0), (2, 0.5, 0), (0.5, 2, 0))

    assert _triangle_intersections(first, second)


def test_exactly_degenerate_triangle_is_rejected_by_exact_area_predicate() -> None:
    assert _exact_zero_area(_triangle((0, 0, 0), (1, 1, 1), (2, 2, 2)))
    assert not _exact_zero_area(_triangle((0, 0, 0), (1, 1, 1), (2, 2, 2.0000000000000004)))


def test_shared_edge_folded_overlap_has_points_beyond_edge() -> None:
    first = _triangle((0, 0, 0), (2, 0, 0), (0, 2, 0))
    second = _triangle((0, 0, 0), (2, 0, 0), (1, 1, 0))
    shared = {"a", "b"}
    coordinates = {"a": _p(0, 0, 0), "b": _p(2, 0, 0)}
    intersections = _triangle_intersections(first, second)

    assert intersections
    assert any(not _in_shared_simplex(point, shared, coordinates) for point in intersections)


def test_non_coplanar_crossing_is_found() -> None:
    first = _triangle((-1, 0, 0), (1, 0, 0), (0, 1, 0))
    second = _triangle((0, -1, -1), (0, 1, 1), (0, 1, -1))

    assert _triangle_intersections(first, second)


def test_coincident_triangles_with_distinct_identity_are_intersections() -> None:
    first = _triangle((0, 0, 0), (1, 0, 0), (0, 1, 0))
    second = _triangle((0, 0, 0), (1, 0, 0), (0, 1, 0))

    assert len(_triangle_intersections(first, second)) >= 3


def test_benign_shared_edge_and_vertex_simplex_are_allowed() -> None:
    edge_point = _p(1, 0, 0)
    edge_coordinates = {"a": _p(0, 0, 0), "b": _p(2, 0, 0)}
    assert _in_shared_simplex(edge_point, {"a", "b"}, edge_coordinates)
    assert _in_shared_simplex(_p(0, 0, 0), {"a"}, edge_coordinates)
    assert not _in_shared_simplex(_p(0, 1, 0), {"a"}, edge_coordinates)


def test_one_ulp_separated_triangles_are_exactly_disjoint() -> None:
    import math

    first = _triangle((0, 0, 0), (1, 0, 0), (0, 1, 0))
    x = math.nextafter(1.0, math.inf)
    second = _triangle((x, 0, 0), (2, 0, 0), (x, 1, 0))

    assert not _triangle_intersections(first, second)


def test_exact_diagnostic_accepts_finite_nonzero_area_below_float_area_range() -> None:
    from crochet_ai.forward_triangulation import triangulate_forward_surface_cells

    inputs = _inputs()
    source = _source()
    coordinates = tuple(
        (identifier, tuple(value * 1e-200 for value in point))
        for identifier, point in _coordinates()
    )

    result = diagnose_initial_exact_intersections(
        source,
        triangulate_forward_surface_cells(source),
        _initialization(inputs, coordinates),
        inputs,
    )

    assert result.status == "EXACT_INTERSECTION_DIAGNOSTIC_ONLY"


def test_current_open_cylinder_source_integrates_and_hash_is_deterministic() -> None:
    # Use the actual current source/triangulation/initialization pipeline fixture.
    from test_forward_pipeline_smoke import _run_pipeline

    pipeline = _run_pipeline((0, 0))
    _, _, _, inputs, initialization, cells, triangulation, _, broadphase = pipeline
    result = diagnose_initial_exact_intersections(
        cells, triangulation, initialization, inputs, broadphase
    )
    again = diagnose_initial_exact_intersections(
        cells, triangulation, initialization, inputs, broadphase
    )
    assert result.status == "EXACT_INTERSECTION_DIAGNOSTIC_ONLY"
    assert result.broadphase_sha256 == broadphase.sha256
    assert result == again


def test_supplied_broadphase_must_match_recomputed_provenance() -> None:
    from test_forward_aabb_broadphase import _initialization, _source

    from crochet_ai.forward_triangulation import triangulate_forward_surface_cells

    inputs = _inputs()
    source = _source()
    triangulation = triangulate_forward_surface_cells(source)
    initialization = _initialization(inputs)
    with pytest.raises(ForwardExactIntersectionError, match="broadphase_mismatch"):
        diagnose_initial_exact_intersections(
            source, triangulation, initialization, inputs,
            replace(broadphase_run(), sha256="0" * 64),
        )
