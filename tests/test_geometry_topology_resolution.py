"""Known surface topology, independent of triangulation size or ranking code."""

from copy import deepcopy
from math import cos, pi, sin

from hypothesis import given, settings
from hypothesis import strategies as st
from test_geometry_comparison import policy, subdivided_octahedron, tetra

from crochet_ai.geometry_comparison import compare_geometry


@given(level=st.sampled_from([0, 1, 2]), scale=st.sampled_from([0.5, 1.0, 2.0]))
@settings(max_examples=9, deadline=None)
def test_closed_sphere_topology_survives_exact_face_subdivision(level, scale):
    """Oracle: subdividing convex octahedron faces preserves the sphere.

    The independent midpoint fixture never calls production topology logic.
    Shrinking preserves a closed sphere; no geometric threshold is relaxed.
    """
    coarse = subdivided_octahedron(0)
    refined = subdivided_octahedron(level)
    for mesh in (coarse, refined):
        for vertex in mesh["vertices"]:
            vertex["position_mm"] = [scale * value for value in vertex["position_mm"]]
    result = compare_geometry(coarse, refined, policy())
    topology = result["metrics"]["topology"]
    assert topology["matches"] is True
    assert topology["comparison_rule"] == "CONNECTED_CLOSED_ORIENTABLE_GENUS_ZERO_V1"
    assert topology["predicted"]["vertices"] == 6
    assert topology["target"]["faces"] == 8 * 4**level
    for side in ("predicted", "target"):
        assert topology[side]["euler_characteristic"] == 2
        assert topology[side]["betti_1"] == 0
        assert topology[side]["betti_2"] == 1
    assert "topology_match" not in result["hard_failures"]
    assert result["threshold_evaluations"]["topology_match"]["status"] == "PASS"


def _torus():
    """Raw periodic torus triangulation; genus one is the independent oracle."""
    mesh = deepcopy(tetra())
    around, tube = 8, 6
    mesh["vertices"] = [
        {
            "position_mm": [
                (3 + cos(2 * pi * j / tube)) * cos(2 * pi * i / around),
                (3 + cos(2 * pi * j / tube)) * sin(2 * pi * i / around),
                sin(2 * pi * j / tube),
            ]
        }
        for i in range(around)
        for j in range(tube)
    ]
    mesh["faces"] = []
    for i in range(around):
        for j in range(tube):
            a, b = i * tube + j, ((i + 1) % around) * tube + j
            c, d = ((i + 1) % around) * tube + (j + 1) % tube, i * tube + (j + 1) % tube
            mesh["faces"].extend([{"vertex_indices": [a, b, c]}, {"vertex_indices": [a, c, d]}])
    return mesh


def test_closed_torus_cannot_use_sphere_resolution_exemption():
    result = compare_geometry(_torus(), tetra(), policy())
    topology = result["metrics"]["topology"]
    assert topology["predicted"]["euler_characteristic"] == 0
    assert topology["predicted"]["betti_1"] == 2
    assert topology["matches"] is False
    assert topology["comparison_rule"] == "STRICT_TOPOLOGY_RECORD_V1"
    assert "topology_match" in result["hard_failures"]


def test_open_surface_cannot_use_sphere_resolution_exemption():
    opened = tetra()
    opened["faces"].pop()
    result = compare_geometry(opened, tetra(), policy())
    topology = result["metrics"]["topology"]
    assert topology["predicted"]["boundary_edges"] == 3
    assert topology["matches"] is False
    assert topology["comparison_rule"] == "STRICT_TOPOLOGY_RECORD_V1"
    assert "topology_match" in result["hard_failures"]
