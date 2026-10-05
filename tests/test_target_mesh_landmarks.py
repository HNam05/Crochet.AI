from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction
from math import nextafter

import pytest

from crochet_ai.target_mesh_boundaries import (
    diagnose_indexed_triangle_mesh_boundaries,
)
from crochet_ai.target_mesh_canonical_order import (
    diagnose_indexed_triangle_mesh_canonical_order,
)
from crochet_ai.target_mesh_decode import MESH_MEDIA_TYPE, decode_indexed_triangle_mesh
from crochet_ai.target_mesh_landmarks import (
    BoundaryLandmark,
    BoundaryLandmarkError,
    diagnose_boundary_landmark_eligibility,
)
from crochet_ai.v0_adjacent_profile import (
    PROFILE_ID as ADJACENT_PROFILE_ID,
)
from crochet_ai.v0_adjacent_profile import (
    resolve_v0_adjacent_numeric_profile,
)
from crochet_ai.v0_numeric_profile import PROFILE_ID, resolve_v0_numeric_profile

FRAME = "frame_landmark_test"
LIMITS = {
    "media_type": MESH_MEDIA_TYPE,
    "expected_coordinate_frame_id": FRAME,
    "max_bytes": 100_000,
    "max_vertices": 100,
    "max_faces": 100,
}
VERTICES = [
    (-2., -2., 0.), (2., -2., 0.), (2., 2., 0.), (-2., 2., 0.),
    (-1., -1., 0.), (1., -1., 0.), (1., 1., 0.), (-1., 1., 0.),
]
FACES = [(0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
         (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]


def encode(vertices: list[tuple[float, float, float]], faces: list[tuple[int, int, int]]) -> bytes:
    value = {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {"length_unit": "MILLIMETER", "handedness": "RIGHT_HANDED",
                              "coordinate_frame_id": FRAME},
        "vertices": [{"position_mm": list(p)} for p in vertices],
        "faces": [{"vertex_indices": list(f)} for f in faces],
    }
    return json.dumps(value, separators=(",", ":")).encode()


def setup(vertices: list[tuple[float, float, float]] = VERTICES,
          faces: list[tuple[int, int, int]] = FACES):
    raw = encode(vertices, faces)
    decoded = decode_indexed_triangle_mesh(raw, **LIMITS)
    order = diagnose_indexed_triangle_mesh_canonical_order(raw, decoded, **LIMITS)
    boundaries = diagnose_indexed_triangle_mesh_boundaries(raw, decoded, order, **LIMITS)
    return raw, decoded, order, boundaries


def run(raw: bytes, decoded, order, boundaries, landmarks, **budgets):
    limits = {"max_landmarks": 20, "max_vertex_pairs": 100,
              "max_landmark_edge_tests": 100}
    limits.update(budgets)
    return diagnose_boundary_landmark_eligibility(
        raw, decoded, order, boundaries, landmarks,
        profile=resolve_v0_numeric_profile(PROFILE_ID), **LIMITS,
        **limits,
    )


def run_adjacent(raw: bytes, decoded, order, boundaries, landmarks, *, profile=None):
    limits = {"max_landmarks": 20, "max_vertex_pairs": 100,
              "max_landmark_edge_tests": 100}
    return diagnose_boundary_landmark_eligibility(
        raw, decoded, order, boundaries, landmarks,
        profile=profile or resolve_v0_adjacent_numeric_profile(ADJACENT_PROFILE_ID),
        **LIMITS, **limits,
    )


def test_hand_computed_perpendicular_and_endpoint_projection() -> None:
    raw, decoded, order, loops = setup()
    outer = next(i for i, loop in enumerate(loops.boundary_loops) if len(loop) == 4
                 and set(tuple(order.derived_vertices_mm[v][:2] for v in loop)) ==
                 {(-2., -2.), (2., -2.), (2., 2.), (-2., 2.)})
    report = run(raw, decoded, order, loops, (
        BoundaryLandmark("landmark_perpendicular", FRAME, (0., -2., 0.25), 0.25),
        BoundaryLandmark("landmark_endpoint", FRAME, (-2., -2., 0.5), 0.5),
        BoundaryLandmark("landmark_outside", FRAME, (0., 0., 0.), 0.),
    ))
    results = {r.landmark_id: r for r in report.results}
    assert results["landmark_perpendicular"].candidate_loop_indices == (outer,)
    assert results["landmark_endpoint"].candidate_loop_indices == (outer,)
    assert results["landmark_outside"].classification == "UNMATCHED"
    perpendicular = results["landmark_perpendicular"].loop_distances[outer]
    endpoint = results["landmark_endpoint"].loop_distances[outer]
    assert perpendicular.squared_distance_numerator_mm2 == "1"
    assert perpendicular.squared_distance_denominator_mm2 == "16"
    assert endpoint.squared_distance_denominator_mm2 == "4"
    assert report.landmark_edge_tests == 24


def test_threshold_below_equality_above_for_zero_and_nonzero_tolerance() -> None:
    # Two connected faces with exact diameter one. Projection is the boundary vertex (0,0,0).
    vertices = [(0., 0., 0.), (.5, .5, 0.), (1., 0., 0.), (.5, -.5, 0.)]
    faces = [(0, 2, 1), (0, 3, 2)]
    raw, decoded, order, boundaries = setup(vertices, faces)
    s = 2. ** -40
    t = 2. ** -41
    lm = tuple(BoundaryLandmark(f"landmark_z-{name}", FRAME, (0., 0., z), 0.)
               for name, z in (("below", nextafter(s, 0.)), ("equal", s),
                               ("above", nextafter(s, 1.))))
    zero = run(raw, decoded, order, boundaries, lm)
    assert {r.landmark_id.removeprefix("landmark_z-"): r.classification for r in zero.results} == {
        "below": "UNIQUE", "equal": "UNIQUE", "above": "UNMATCHED",
    }
    lm_t = tuple(BoundaryLandmark(f"landmark_t-{name}", FRAME, (0., 0., z), t)
                 for name, z in (("below", nextafter(t + s, 0.)), ("equal", t + s),
                                 ("above", nextafter(t + s, 1.))))
    nonzero = run(raw, decoded, order, boundaries, lm_t)
    classifications = {
        r.landmark_id.removeprefix("landmark_t-"): r.classification for r in nonzero.results
    }
    assert classifications == {
        "below": "UNIQUE", "equal": "UNIQUE", "above": "UNMATCHED",
    }


def test_irrational_diameter_uses_exact_comparison_without_epsilon() -> None:
    vertices = [(0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.)]
    faces = [(0, 1, 2), (0, 2, 3)]
    raw, decoded, order, boundaries = setup(vertices, faces)
    assert len(boundaries.boundary_loops) == 1
    s = 2. ** -40
    report = run(raw, decoded, order, boundaries, (
        BoundaryLandmark("landmark_at", FRAME, (-s, -s, 0.), 0.),
        BoundaryLandmark("landmark_above", FRAME, (-s, -nextafter(s, 1.), 0.), 0.),
    ))
    assert report.diameter_numerator_mm2 == "2"
    assert report.diameter_denominator_mm2 == "1"
    assert {r.landmark_id: r.classification for r in report.results} == {
        "landmark_at": "UNIQUE", "landmark_above": "UNMATCHED",
    }


def test_two_loop_ambiguity_is_reported_without_iteration_tie_break() -> None:
    raw, decoded, order, boundaries = setup()
    report = run(raw, decoded, order, boundaries,
                 (BoundaryLandmark("landmark_middle", FRAME, (0., 0., 0.), 3.),))
    assert report.results[0].classification == "AMBIGUOUS"
    assert report.results[0].candidate_loop_indices == (0, 1)


def test_source_permutations_preserve_loop_candidate_positions() -> None:
    raw, decoded, order, boundaries = setup()
    first = run(raw, decoded, order, boundaries,
                (BoundaryLandmark("landmark_corner", FRAME, (-2., -2., 0.), 0.),))
    permutation = (5, 2, 7, 0, 3, 6, 1, 4)
    remap = {old: new for new, old in enumerate(permutation)}
    perm_vertices = [VERTICES[i] for i in permutation]
    perm_faces = [(remap[a], remap[b], remap[c]) for a, b, c in reversed(FACES)]
    raw2, dec2, order2, bounds2 = setup(perm_vertices, perm_faces)
    second = run(raw2, dec2, order2, bounds2,
                 (BoundaryLandmark("landmark_corner", FRAME, (-2., -2., 0.), 0.),))
    assert first.results[0].classification == second.results[0].classification == "UNIQUE"
    assert first.results[0].candidate_loop_indices == second.results[0].candidate_loop_indices


def test_tampered_profile_order_boundary_and_source_are_rejected() -> None:
    raw, decoded, order, boundaries = setup()
    profile = resolve_v0_numeric_profile(PROFILE_ID)
    landmark = (BoundaryLandmark("landmark_p", FRAME, (-2., -2., 0.), 0.),)
    with pytest.raises(BoundaryLandmarkError, match="profile_mismatch"):
        diagnose_boundary_landmark_eligibility(
            raw, decoded, order, boundaries, landmark,
            profile=replace(profile, profile_version="wrong"), **LIMITS,
            max_landmarks=2, max_vertex_pairs=100, max_landmark_edge_tests=100,
        )
    with pytest.raises(BoundaryLandmarkError, match="ordering_mismatch"):
        run(raw, decoded, replace(order, diagnostic_sha256="0" * 64), boundaries, landmark)
    with pytest.raises(BoundaryLandmarkError, match="boundary_mismatch"):
        run(raw, decoded, order, replace(boundaries, diagnostic_sha256="0" * 64), landmark)
    with pytest.raises(BoundaryLandmarkError, match="source_invalid"):
        run(b"bad", decoded, order, boundaries, landmark)


def test_v2_profile_uses_same_hash_locked_landmark_slack_as_v1() -> None:
    raw, decoded, order, boundaries = setup()
    landmark = (BoundaryLandmark("landmark_p", FRAME, (-2., -2., 0.), 0.),)
    v1 = run(raw, decoded, order, boundaries, landmark)
    v2 = run_adjacent(raw, decoded, order, boundaries, landmark)
    assert v1.results == v2.results
    assert v2.profile_id == ADJACENT_PROFILE_ID
    assert v2.profile_sha256 == resolve_v0_adjacent_numeric_profile(
        ADJACENT_PROFILE_ID,
    ).record_sha256


def test_forged_v2_profile_is_rejected() -> None:
    from dataclasses import replace

    raw, decoded, order, boundaries = setup()
    profile = resolve_v0_adjacent_numeric_profile(ADJACENT_PROFILE_ID)
    landmark = (BoundaryLandmark("landmark_p", FRAME, (-2., -2., 0.), 0.),)
    with pytest.raises(BoundaryLandmarkError, match="profile_mismatch"):
        run_adjacent(raw, decoded, order, boundaries, landmark,
                     profile=replace(profile, record_sha256="0" * 64))


def test_budgets_reject_before_pair_or_segment_work(monkeypatch: pytest.MonkeyPatch) -> None:
    import crochet_ai.target_mesh_landmarks as module

    raw, decoded, order, boundaries = setup()
    monkeypatch.setattr(module, "diagnose_indexed_triangle_mesh_diameter",
                        lambda *_args, **_kwargs: pytest.fail("diameter work started"))
    landmark = (BoundaryLandmark("landmark_p", FRAME, (-2., -2., 0.), 0.),)
    with pytest.raises(BoundaryLandmarkError, match="vertex_pair_budget_exhausted"):
        run(raw, decoded, order, boundaries, landmark, max_vertex_pairs=1)

    # Edge budget precheck precedes diameter and every point-to-segment test.
    with pytest.raises(BoundaryLandmarkError, match="edge_test_budget_exhausted"):
        run(raw, decoded, order, boundaries, landmark, max_landmark_edge_tests=1)


@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_budgets_require_positive_integer(bad: object) -> None:
    raw, decoded, order, boundaries = setup()
    lm = (BoundaryLandmark("landmark_p", FRAME, (-2., -2., 0.), 0.),)
    with pytest.raises(BoundaryLandmarkError):
        diagnose_boundary_landmark_eligibility(
            raw, decoded, order, boundaries, lm,
            profile=resolve_v0_numeric_profile(PROFILE_ID), **LIMITS,
            max_landmarks=bad, max_vertex_pairs=100, max_landmark_edge_tests=100,
        )


def test_landmark_types_frames_and_ids_are_validated() -> None:
    raw, decoded, order, boundaries = setup()
    cases = [
        (BoundaryLandmark("", FRAME, (0., 0., 0.), 0.),),
        (BoundaryLandmark("x", FRAME, (0., 0., 0.), 0.),),
        (BoundaryLandmark("landmark_x", "other", (0., 0., 0.), 0.),),
        (BoundaryLandmark("landmark_x", FRAME, (0., 0., float("inf")), 0.),),
        (BoundaryLandmark("landmark_x", FRAME, (0., 0., 0.), -1.),),
        (BoundaryLandmark("landmark_x", FRAME, (0., 0., 0.), 0.),
         BoundaryLandmark("landmark_x", FRAME, (0., 0., 0.), 0.)),
    ]
    for lm in cases:
        with pytest.raises(BoundaryLandmarkError):
            run(raw, decoded, order, boundaries, lm)


def test_landmark_set_order_preserves_evidence() -> None:
    raw, decoded, order, boundaries = setup()
    landmarks = (
        BoundaryLandmark("landmark_a", FRAME, (-2., -2., 0.), 0.),
        BoundaryLandmark("landmark_b", FRAME, (-1., -1., 0.), 0.),
    )
    first = run(raw, decoded, order, boundaries, landmarks)
    assert first == run(raw, decoded, order, boundaries, tuple(reversed(landmarks)))
    assert first.diagnostic_sha256 != run(
        raw, decoded, order, boundaries, landmarks, max_landmarks=19,
    ).diagnostic_sha256
    with pytest.raises(BoundaryLandmarkError, match="landmark_budget_exhausted"):
        run(raw, decoded, order, boundaries, landmarks, max_landmarks=1)


@pytest.mark.parametrize("x,y", [(-1, 0), (2, 0), (Fraction(1, 2), 1)])
def test_segment_projection_clamps_to_both_endpoints(x: Fraction, y: Fraction) -> None:
    from crochet_ai.target_mesh_landmarks import _point_segment_distance_squared

    assert _point_segment_distance_squared(
        (Fraction(x), Fraction(y), Fraction(0)),
        (Fraction(0), Fraction(0), Fraction(0)),
        (Fraction(1), Fraction(0), Fraction(0)),
    ) == 1
