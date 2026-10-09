from __future__ import annotations

from dataclasses import replace

import pytest

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_shell_terms import (
    TERMS_PROFILE,
    ShellParameters,
    ShellTerms,
    ShellTermsError,
    _hash,
    _terms_payload,
    admit_shell_parameters,
    evaluate_shell_terms,
    prepare_shell_terms,
)


def _parameters(**changes: object) -> ShellParameters:
    value: dict[str, object] = {
        "schema_version": "1.0.0",
        "status": "HYPOTHESIS",
        "provenance_id": "declared-fixture-v1",
        "rest_corner_angle_rad": 1.2,
        "shear_stiffness_n_mm": 2.0,
        "rest_dihedral_rad": 0.0,
        "bending_stiffness_n_mm": 0.7,
    }
    value.update(changes)
    return admit_shell_parameters(value)


def _tetrahedron(
    parameters: ShellParameters | None = None,
) -> tuple[ShellTerms, dict[str, tuple[float, float, float]]]:
    vertices = ("a", "b", "c", "d")
    faces = (("a", "c", "b"), ("a", "b", "d"), ("a", "d", "c"), ("b", "c", "d"))
    terms = prepare_shell_terms(vertices, faces, parameters or _parameters())
    points = {
        "a": (0.0, 0.0, 0.0),
        "b": (1.0, 0.0, 0.0),
        "c": (0.0, 1.0, 0.0),
        "d": (0.0, 0.0, 1.0),
    }
    return terms, points


def test_terms_have_every_face_corner_and_each_shared_edge_once() -> None:
    terms, _ = _tetrahedron()
    assert len(terms.corners) == 3 * len(terms.faces) == 12
    assert len(terms.hinges) == 6
    assert all(len(set(hinge.vertices)) == 4 for hinge in terms.hinges)
    assert len({tuple(sorted((h.vertices[0], h.vertices[2]))) for h in terms.hinges}) == 6
    assert terms.canonical_bytes == _tetrahedron()[0].canonical_bytes


def test_energy_explicit_rest_is_independent_of_evaluation_coordinates() -> None:
    p = _parameters(rest_corner_angle_rad=1.1, rest_dihedral_rad=0.25)
    terms, points = _tetrahedron(p)
    deformed = dict(points, d=(0.2, -0.1, 1.3))
    actual = evaluate_shell_terms(terms, deformed)
    assert actual.shear_n_mm > 0
    assert actual.bending_n_mm > 0
    assert actual.total_n_mm == pytest.approx(actual.shear_n_mm + actual.bending_n_mm)
    # Rest parameters are declared data and do not get rebound to this input shape.
    assert terms.hinges[0].rest_dihedral_rad == 0.25


def test_all_coordinate_forces_match_energy_gradient_and_balance_force_torque() -> None:
    terms, points = _tetrahedron()
    points["d"] = (0.21, -0.13, 1.17)
    result = evaluate_shell_terms(terms, points)
    forces = dict(result.forces_n)
    epsilon = 1e-6
    for key in sorted(points):
        for axis in range(3):
            plus, minus = dict(points), dict(points)
            xp, xm = list(points[key]), list(points[key])
            xp[axis] += epsilon
            xm[axis] -= epsilon
            plus[key], minus[key] = (xp[0], xp[1], xp[2]), (xm[0], xm[1], xm[2])
            derivative = (
                evaluate_shell_terms(terms, plus).total_n_mm
                - evaluate_shell_terms(terms, minus).total_n_mm
            ) / (2 * epsilon)
            assert -derivative == pytest.approx(forces[key][axis], rel=2e-5, abs=2e-7)
    total_force = [sum(row[axis] for row in forces.values()) for axis in range(3)]
    total_torque = [0.0, 0.0, 0.0]
    for key, force in forces.items():
        x = points[key]
        cross = (
            x[1] * force[2] - x[2] * force[1],
            x[2] * force[0] - x[0] * force[2],
            x[0] * force[1] - x[1] * force[0],
        )
        total_torque = [total_torque[i] + cross[i] for i in range(3)]
    assert total_force == pytest.approx((0, 0, 0), abs=2e-12)
    assert total_torque == pytest.approx((0, 0, 0), abs=2e-12)


def test_rigid_transform_and_consistent_orientation_reversal_preserve_energy() -> None:
    terms, points = _tetrahedron()
    points["d"] = (0.18, 0.11, 1.2)
    energy = evaluate_shell_terms(terms, points).total_n_mm
    moved = {key: (p[1] + 3, -p[0] - 2, p[2] + 4) for key, p in points.items()}
    assert evaluate_shell_terms(terms, moved).total_n_mm == pytest.approx(energy)
    reversed_terms = prepare_shell_terms(
        terms.vertices, tuple((face[2], face[1], face[0]) for face in terms.faces), _parameters()
    )
    assert evaluate_shell_terms(reversed_terms, points).total_n_mm == pytest.approx(energy)


def test_malformed_forged_and_degenerate_inputs_fail_closed() -> None:
    with pytest.raises(ShellTermsError):
        admit_shell_parameters({"schema_version": "1.0.0", "status": "HYPOTHESIS"})
    with pytest.raises(ShellTermsError):
        _parameters(rest_corner_angle_rad=True)
    terms, points = _tetrahedron()
    with pytest.raises(ShellTermsError, match="integrity_invalid"):
        evaluate_shell_terms(replace(terms, parameters_sha256="f" * 64), points)
    collapsed = dict(points, d=points["a"])
    with pytest.raises(ShellTermsError):
        evaluate_shell_terms(terms, collapsed)
    with pytest.raises(ShellTermsError, match="topology"):
        prepare_shell_terms(("a", "b", "c"), (("a", "b", "c"),), _parameters())


@pytest.mark.parametrize("mutation", ["empty_corners", "partial_hinges", "changed_rest"])
def test_rehashed_semantically_forged_terms_fail_closed(mutation: str) -> None:
    terms, points = _tetrahedron()
    corners, hinges = terms.corners, terms.hinges
    if mutation == "empty_corners":
        corners = ()
    elif mutation == "partial_hinges":
        hinges = hinges[:-1]
    else:
        hinges = (replace(hinges[0], rest_dihedral_rad=0.1), *hinges[1:])
    payload = _terms_payload(terms.status, terms.vertices, terms.faces,
                             terms.parameters_sha256, corners, hinges)
    encoded = jcs_bytes(payload)
    forged = replace(terms, corners=corners, hinges=hinges, canonical_bytes=encoded,
                     sha256=_hash(TERMS_PROFILE, encoded))
    with pytest.raises(ShellTermsError, match="semantic_content_invalid"):
        evaluate_shell_terms(forged, points)


def test_extreme_finite_values_fail_on_result_overflow() -> None:
    terms, points = _tetrahedron(_parameters(shear_stiffness_n_mm=1e308))
    points["d"] = (1e100, 0.0, 1.0)
    with pytest.raises(ShellTermsError):
        evaluate_shell_terms(terms, points)


def test_extreme_finite_dot_product_failure_is_typed_and_fails_closed() -> None:
    terms, points = _tetrahedron()
    points["b"] = (1e308, 1e308, 0.0)
    points["c"] = (1e308, -1e308, 0.0)
    with pytest.raises(ShellTermsError):
        evaluate_shell_terms(terms, points)
