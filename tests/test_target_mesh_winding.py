from __future__ import annotations

import json
import math
from dataclasses import replace
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from crochet_ai import target_mesh_winding as winding
from crochet_ai.target_mesh_decode import MESH_MEDIA_TYPE
from crochet_ai.v0_numeric_profile import PROFILE_ID, resolve_v0_numeric_profile

FRAME = "frame_winding_test"
TETRA_VERTICES = [(0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.)]
TETRA_FACES = [(1, 2, 3), (0, 2, 1), (0, 1, 3), (0, 3, 2)]


def encode(vertices, faces):
    return json.dumps({
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {"length_unit": "MILLIMETER", "handedness": "RIGHT_HANDED",
                              "coordinate_frame_id": FRAME},
        "vertices": [{"position_mm": list(point)} for point in vertices],
        "faces": [{"vertex_indices": list(face)} for face in faces],
    }, separators=(",", ":")).encode()


def propose(vertices=TETRA_VERTICES, faces=TETRA_FACES, **budgets):
    raw = encode(vertices, faces)
    limits = {"max_bytes": 100_000, "max_vertices": 100, "max_faces": 100,
              "max_vertex_pairs": 100, "max_face_pairs": 100}
    limits.update(budgets)
    return winding.propose_indexed_triangle_mesh_winding(
        raw, media_type=MESH_MEDIA_TYPE, expected_coordinate_frame_id=FRAME,
        profile=resolve_v0_numeric_profile(PROFILE_ID), **limits,
    )


def test_closed_tetrahedron_keeps_positive_and_reverses_negative_as_whole_component():
    positive = propose()
    negative = propose(faces=[tuple(reversed(face)) for face in TETRA_FACES])
    assert positive.status == "WINDING_PROPOSAL_DIAGNOSTIC_ONLY"
    assert positive.components[0].event == "KEEP"
    assert negative.components[0].event == "WHOLE_COMPONENT_REVERSAL"
    assert negative.proposed_faces == positive.proposed_faces
    assert negative.source_sha256 != positive.source_sha256
    assert negative.diagnostic_sha256 != positive.diagnostic_sha256
    assert "canonical_mesh_identity" in positive.unresolved_gates


def test_missing_volume_component_evidence_fails_closed(monkeypatch):
    original = winding.diagnose_indexed_triangle_mesh_signed_six_volume
    monkeypatch.setattr(winding, "diagnose_indexed_triangle_mesh_signed_six_volume",
                        lambda *args, **kwargs: replace(original(*args, **kwargs), components=()))
    with pytest.raises(winding.MeshWindingError, match="volume_components_incomplete"):
        propose()


def test_missing_pair_evidence_fails_closed(monkeypatch):
    original = winding.diagnose_indexed_triangle_mesh_pair_relations
    monkeypatch.setattr(winding, "diagnose_indexed_triangle_mesh_pair_relations",
                        lambda *args, **kwargs: replace(original(*args, **kwargs), relations=()))
    with pytest.raises(winding.MeshWindingError, match="face_relations_incomplete"):
        propose()


def test_cube_and_positive_uniform_scale_translation_keep_the_proposal():
    cube = [(0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.),
            (0., 0., 1.), (1., 0., 1.), (1., 1., 1.), (0., 1., 1.)]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
             (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2),
             (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5)]
    base = propose(cube, faces)
    shifted = [(x * 16 + 1024, y * 16 - 512, z * 16 + 2048) for x, y, z in cube]
    transformed = propose(shifted, faces)
    reversed_cube = propose(cube, [tuple(reversed(face)) for face in faces])
    assert base.components[0].event == transformed.components[0].event == "KEEP"
    assert reversed_cube.components[0].event == "WHOLE_COMPONENT_REVERSAL"
    assert transformed.proposed_faces == base.proposed_faces
    assert reversed_cube.proposed_faces == base.proposed_faces


def test_single_reversed_face_and_unstable_volume_fail_closed():
    faces = TETRA_FACES.copy()
    faces[0] = tuple(reversed(faces[0]))
    with pytest.raises(winding.MeshWindingError, match="topology_invalid"):
        propose(faces=faces)
    threshold_tetra = [(0., 0., 0.), (1., 0., 0.), (.5, .5, 0.), (.5, .5, 2.**-35)]
    with pytest.raises(winding.MeshWindingError, match="orientation_indeterminate"):
        propose(vertices=threshold_tetra)


@pytest.mark.parametrize("height,stable", [
    (math.nextafter(2.**-35, 0.), False),
    (2.**-35, False),
    (math.nextafter(2.**-35, math.inf), True),
])
def test_exact_signed_volume_threshold_is_exclusive_for_both_windings(height, stable):
    vertices = [(-.5, 0., 0.), (.5, 0., 0.), (0., .5, 0.), (0., 0., height)]
    exact_six_volume = Fraction.from_float(height) / 2
    boundary = Fraction(1, 1 << 36)
    assert (exact_six_volume > boundary) is stable
    assert (exact_six_volume <= boundary) is (not stable)
    for faces, event in (
        (TETRA_FACES, "KEEP"),
        ([tuple(reversed(face)) for face in TETRA_FACES], "WHOLE_COMPONENT_REVERSAL"),
    ):
        if not stable:
            with pytest.raises(winding.MeshWindingError, match="orientation_indeterminate"):
                propose(vertices, faces)
        else:
            report = propose(vertices, faces)
            component = report.components[0]
            recorded = Fraction(
                int(component.signed_six_volume_numerator_mm3),
                int(component.signed_six_volume_denominator_mm3),
            )
            assert recorded == (exact_six_volume if event == "KEEP" else -exact_six_volume)
            assert int(component.signed_six_volume_denominator_mm3) == (
                exact_six_volume.denominator
            )
            assert component.event == event


def test_profile_must_be_the_locked_profile_type_and_record():
    profile = resolve_v0_numeric_profile(PROFILE_ID)
    with pytest.raises(winding.MeshWindingError, match="profile_invalid"):
        raw = encode(TETRA_VERTICES, TETRA_FACES)
        winding.propose_indexed_triangle_mesh_winding(
            raw, media_type=MESH_MEDIA_TYPE, expected_coordinate_frame_id=FRAME,
            profile=object(), max_bytes=100_000, max_vertices=100, max_faces=100,
            max_vertex_pairs=100, max_face_pairs=100,
        )
    altered = replace(profile, record_sha256="0" * 64)
    with pytest.raises(winding.MeshWindingError, match="profile_mismatch"):
        raw = encode(TETRA_VERTICES, TETRA_FACES)
        winding.propose_indexed_triangle_mesh_winding(
            raw, media_type=MESH_MEDIA_TYPE, expected_coordinate_frame_id=FRAME,
            profile=altered, max_bytes=100_000, max_vertices=100, max_faces=100,
            max_vertex_pairs=100, max_face_pairs=100,
        )


def test_open_fan_preserves_directed_source_winding():
    vertices = [(0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (1., -1., 0.)]
    report = propose(vertices, [(0, 1, 2), (1, 0, 3)])
    assert len(report.components) == 1
    assert report.components[0].event == "OPEN_ORIENTATION_NOT_NORMALIZED"
    assert report.components[0].decision == "NO_REVERSAL"
    assert report.volume_diagnostic_sha256 is None
    for source_index, face in enumerate(((0, 1, 2), (1, 0, 3))):
        mapped = tuple(report.source_to_proposed_vertex_indices[index] for index in face)
        start = mapped.index(min(mapped))
        expected = mapped[start:] + mapped[:start]
        proposed_index = report.source_to_proposed_face_indices.index(source_index)
        assert report.proposed_faces[proposed_index] == expected
    assert report.vertex_pair_work == 0


def test_source_reordering_has_complete_vertex_and_face_maps():
    perm = [2, 0, 3, 1]
    inverse = {old: new for new, old in enumerate(perm)}
    reordered_vertices = [TETRA_VERTICES[index] for index in perm]
    reordered_faces = [tuple(inverse[index] for index in face) for face in reversed(TETRA_FACES)]
    report = propose(reordered_vertices, reordered_faces)
    assert sorted(report.source_to_proposed_vertex_indices) == list(range(4))
    assert sorted(report.source_to_proposed_face_indices) == list(range(4))
    assert report.proposed_faces == propose().proposed_faces


@pytest.mark.parametrize("scale,offset", [
    (2.**-10, (512., -256., 64.)),
    (1., (-1024., 2048., 512.)),
    (2.**10, (0., 0., 0.)),
])
def test_tetrahedron_translation_and_scale_preserve_orientation_event(scale, offset):
    vertices = [(x * scale + offset[0], y * scale + offset[1], z * scale + offset[2])
                for x, y, z in TETRA_VERTICES]
    report = propose(vertices)
    assert report.components[0].event == "KEEP"
    assert report.proposed_faces == propose().proposed_faces


def test_aggregate_face_budget_precedes_relation_work(monkeypatch):
    monkeypatch.setattr(winding, "diagnose_indexed_triangle_mesh_pair_relations",
                        lambda *a, **k: pytest.fail("relations ran before aggregate cap"))
    with pytest.raises(winding.MeshWindingError, match="face_pair_budget_exhausted"):
        propose(max_face_pairs=5)


def test_vertex_budget_precedes_volume_work(monkeypatch):
    monkeypatch.setattr(winding, "diagnose_indexed_triangle_mesh_pair_relations",
                        lambda *a, **k: pytest.fail("relations ran before vertex cap"))
    monkeypatch.setattr(winding, "diagnose_indexed_triangle_mesh_signed_six_volume",
                        lambda *a, **k: pytest.fail("volume ran before aggregate cap"))
    with pytest.raises(winding.MeshWindingError, match="vertex_pair_budget_exhausted"):
        propose(max_vertex_pairs=5)


@pytest.mark.parametrize("name,value", [
    ("max_bytes", 0), ("max_vertices", -1), ("max_faces", True),
    ("max_vertex_pairs", 0), ("max_face_pairs", 0),
])
def test_budgets_are_explicit_positive_non_boolean_integers(name, value):
    with pytest.raises(winding.MeshWindingError, match=f"{name}_invalid"):
        propose(**{name: value})


def test_coincident_vertices_are_rejected_without_welding():
    vertices = TETRA_VERTICES.copy()
    vertices[3] = vertices[2]
    with pytest.raises(winding.MeshWindingError, match="geometry_degenerate_or_coincident"):
        propose(vertices=vertices)


def test_interpenetrating_closed_components_are_rejected():
    vertices = TETRA_VERTICES + [(x + .2, y, z) for x, y, z in TETRA_VERTICES]
    faces = TETRA_FACES + [tuple(index + 4 for index in face) for face in TETRA_FACES]
    with pytest.raises(winding.MeshWindingError, match="forbidden_original_face_contact"):
        propose(vertices, faces)


def test_mixed_open_closed_components_fail_without_partial_proposal():
    open_vertices = [(x + 4., y, z) for x, y, z in
                     [(0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (1., -1., 0.)]]
    vertices = TETRA_VERTICES + open_vertices
    faces = [*TETRA_FACES, (4, 5, 6), (5, 4, 7)]
    with pytest.raises(winding.MeshWindingError, match="mixed_open_closed_volume_unsupported"):
        propose(vertices, faces)


@settings(max_examples=100, deadline=None, derandomize=True)
@given(scale=st.integers(min_value=1, max_value=32),
       permutation=st.permutations((0, 1, 2, 3)))
def test_exact_tetra_volume_and_permutation_maps_have_independent_oracle(scale, permutation):
    """Volume equals scale³ with independent index remapping; Hypothesis shrinks/replays."""
    vertices = [(x * scale, y * scale, z * scale) for x, y, z in TETRA_VERTICES]
    base = propose(vertices)
    reordered = [vertices[index] for index in permutation]
    old_to_new = {old: new for new, old in enumerate(permutation)}
    faces = [tuple(old_to_new[index] for index in face) for face in TETRA_FACES]
    report = propose(reordered, faces)
    exact = Fraction(scale**3, 1)
    recorded = Fraction(
        int(report.components[0].signed_six_volume_numerator_mm3),
        int(report.components[0].signed_six_volume_denominator_mm3),
    )
    assert recorded == exact
    assert report.proposed_faces == base.proposed_faces
    assert sorted(report.source_to_proposed_vertex_indices) == [0, 1, 2, 3]
    assert sorted(report.source_to_proposed_face_indices) == [0, 1, 2, 3]
    assert report.required_vertex_pairs == 6
    assert report.vertex_pair_work == 6


def test_profile_subclass_cannot_forge_builtin_equality():
    from crochet_ai.v0_numeric_profile import V0NumericProfile

    class DeceptiveProfile(V0NumericProfile):
        def __eq__(self, other):
            return True

    original = resolve_v0_numeric_profile(PROFILE_ID)
    forged = DeceptiveProfile(
        original.profile_id, original.profile_version, original.thresholds, "0" * 64,
    )
    with pytest.raises(winding.MeshWindingError, match="profile_invalid"):
        winding.propose_indexed_triangle_mesh_winding(
            encode(TETRA_VERTICES, TETRA_FACES), media_type=MESH_MEDIA_TYPE,
            expected_coordinate_frame_id=FRAME, profile=forged,
            max_bytes=100_000, max_vertices=100, max_faces=100,
            max_vertex_pairs=100, max_face_pairs=100,
        )


def test_reversal_maps_bind_each_actual_source_face_and_vertex():
    vertices = [TETRA_VERTICES[index] for index in (2, 0, 3, 1)]
    old_to_new = {old: new for new, old in enumerate((2, 0, 3, 1))}
    faces = [tuple(old_to_new[index] for index in reversed(face))
             for face in reversed(TETRA_FACES)]
    report = propose(vertices, faces)
    assert report.components[0].event == "WHOLE_COMPONENT_REVERSAL"
    for source, point in enumerate(vertices):
        proposed = report.source_to_proposed_vertex_indices[source]
        assert report.derived_vertices_mm[proposed] == point
        assert report.proposed_to_source_vertex_indices[proposed] == source
    for source, face in enumerate(faces):
        mapped = tuple(report.source_to_proposed_vertex_indices[index] for index in face)
        flipped = (mapped[0], mapped[2], mapped[1])
        rotations = [flipped[i:] + flipped[:i] for i in range(3)]
        proposed = report.source_to_proposed_face_indices[source]
        assert report.proposed_faces[proposed] == min(rotations)
        assert report.proposed_to_source_face_indices[proposed] == source


def test_only_negative_closed_component_is_reversed():
    vertices = TETRA_VERTICES + [(x + 3., y, z) for x, y, z in TETRA_VERTICES]
    faces = TETRA_FACES + [tuple(index + 4 for index in reversed(face))
                           for face in TETRA_FACES]
    report = propose(vertices, faces)
    assert [component.event for component in report.components] == [
        "KEEP", "WHOLE_COMPONENT_REVERSAL"]
    assert report.components[0].source_face_indices == (0, 1, 2, 3)
    assert report.components[1].source_face_indices == (4, 5, 6, 7)
