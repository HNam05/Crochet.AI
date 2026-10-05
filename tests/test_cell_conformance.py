from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

import pytest
from conftest import resolved_artifacts
from ring_fixtures import make_multi_ring_ir

import crochet_ai.cell_conformance as cell_conformance
from crochet_ai.analytic_compile import CompileProvenance, compile_closed_schedule
from crochet_ai.canonical import CanonicalProfile, canonical_hash, jcs_bytes
from crochet_ai.cell_conformance import (
    RULE_ID,
    SURFACE_PROFILE,
    CellConformanceInputError,
    inspect_closed_cell_conformance,
)
from crochet_ai.diagnostics import ArtifactValidationError
from crochet_ai.validation import SemanticValidator

PROJECTION = "a" * 64


def _manual_case() -> tuple[dict[str, Any], dict[str, Any], SemanticValidator]:
    design, material = resolved_artifacts()
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    ir = make_multi_ring_ir(3)
    # Each hand-authored plain stitch has one lower and one upper advance.
    lower = [f"loc_ring_{i}" for i in range(3)]
    upper = [f"loc_top_{i}" for i in range(3)]
    faces: list[list[str]] = []
    for i in range(3):
        faces.append([lower[i], lower[(i + 1) % 3], upper[i]])
        faces.append([lower[(i + 1) % 3], upper[(i + 1) % 3], upper[i]])
    faces.extend([[lower[0], lower[2], lower[1]], [upper[0], upper[1], upper[2]]])
    cells = {
        "profile": SURFACE_PROFILE,
        "status": "TOPOLOGY_ONLY",
        "projection_sha256": PROJECTION,
        "rule_id": RULE_ID,
        "vertices": sorted([*lower, *upper]),
        "faces": faces,
    }
    return ir, cells, validator


def _digest_cells(cells: dict[str, Any]) -> str:
    return sha256(
        b"Crochet.AI\0"
        + SURFACE_PROFILE.encode()
        + b"\0"
        + PROJECTION.encode()
        + b"\0"
        + RULE_ID.encode()
        + b"\0"
        + jcs_bytes(cells)
    ).hexdigest()


def _assert_sphere(cells: dict[str, Any]) -> None:
    edge_uses: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for face in cells["faces"]:
        assert len(set(face)) == 3
        for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge_uses.setdefault(tuple(sorted((start, end))), []).append((start, end))
    assert all(len(uses) == 2 and uses[0] == uses[1][::-1] for uses in edge_uses.values())
    assert len(cells["vertices"]) - len(edge_uses) + len(cells["faces"]) == 2


def _inspect(
    ir: dict[str, Any], cells: dict[str, Any], validator: SemanticValidator, **kwargs: Any
):
    return inspect_closed_cell_conformance(
        ir,
        cells,
        validator=validator,
        projection_sha256=PROJECTION,
        surface_cells_sha256=_digest_cells(cells),
        **kwargs,
    )


def test_hand_authored_minimal_ir_and_faces_pass() -> None:
    ir, cells, validator = _manual_case()
    report = _inspect(ir, cells, validator)
    assert report.status == "PASS"
    assert report.checked_face_count == 8
    assert report.checked_stitch_count == 3
    assert report.checked_course_count == 1
    assert report.source_ir_sha256 == canonical_hash(
        ir, CanonicalProfile.CROCHET_IR, validator=validator
    )
    assert (
        report.sha256
        == sha256(b"Crochet.AI\0CLOSED_CELL_CONFORMANCE_V1\0" + report.canonical_bytes).hexdigest()
    )
    assert report.to_dict()["status"] == "PASS"


def test_same_counts_but_wrong_source_ids_fail_and_are_deterministic() -> None:
    ir, cells, validator = _manual_case()
    forged = deepcopy(cells)
    rename = {identifier: f"foreign_{index}" for index, identifier in enumerate(forged["vertices"])}
    forged["vertices"] = [rename[identifier] for identifier in forged["vertices"]]
    forged["faces"] = [[rename[identifier] for identifier in face] for face in forged["faces"]]
    first = _inspect(ir, forged, validator)
    second = _inspect(ir, forged, validator)
    assert first.status == "FAIL"
    assert first.canonical_bytes == second.canonical_bytes
    assert "surface.vertex_set_mismatch" in first.diagnostics
    _assert_sphere(forged)


def test_wrong_sphere_with_refreshed_digest_fails_source_predicates() -> None:
    ir, cells, validator = _manual_case()
    forged = deepcopy(cells)
    remap = {"loc_top_1": "loc_top_2", "loc_top_2": "loc_top_1"}
    forged["faces"] = [
        [remap.get(identifier, identifier) for identifier in face] for face in forged["faces"]
    ]
    _assert_sphere(forged)
    report = _inspect(ir, forged, validator)
    assert report.status == "FAIL"
    assert any(item.startswith("surface.face_mismatch:") for item in report.diagnostics)


def test_topology_preserving_diagonal_flip_fails() -> None:
    ir, cells, validator = _manual_case()
    forged = deepcopy(cells)
    # Flip the shared diagonal while preserving the quad boundary.
    forged["faces"][0] = ["loc_ring_0", "loc_ring_1", "loc_top_1"]
    forged["faces"][1] = ["loc_ring_0", "loc_top_1", "loc_top_0"]
    _assert_sphere(forged)
    report = _inspect(ir, forged, validator)
    assert report.status == "FAIL"
    assert "surface.face_mismatch:0" in report.diagnostics


@pytest.mark.parametrize(
    "mutation", ["orientation", "cap", "event_order", "extra_face", "missing_face"]
)
def test_exact_order_orientation_caps_and_coverage(mutation: str) -> None:
    ir, cells, validator = _manual_case()
    altered = deepcopy(cells)
    if mutation == "orientation":
        altered["faces"][0][0], altered["faces"][0][1] = (
            altered["faces"][0][1],
            altered["faces"][0][0],
        )
    elif mutation == "cap":
        altered["faces"][-1] = altered["faces"][-1][::-1]
    elif mutation == "event_order":
        first = next(e for e in ir["construction_sequence"] if e["event_id"] == "ev_ring_0")
        second = next(e for e in ir["construction_sequence"] if e["event_id"] == "ev_ring_1")
        first["sequence_index"], second["sequence_index"] = (
            second["sequence_index"],
            first["sequence_index"],
        )
        with pytest.raises(ArtifactValidationError):
            _inspect(ir, altered, validator)
        return
    elif mutation == "extra_face":
        altered["faces"].append(list(altered["faces"][-1]))
    else:
        altered["faces"].pop()
    result = _inspect(ir, altered, validator)
    assert result.status == "FAIL"


def test_exact_budgets_and_boolean_oversize_rejection() -> None:
    ir, cells, validator = _manual_case()
    assert (
        _inspect(ir, cells, validator, max_vertices=6, max_faces=8, max_events=5).status == "PASS"
    )
    for kwargs in (
        {"max_vertices": 5},
        {"max_faces": 7},
        {"max_events": 4},
        {"max_vertices": True},
        {"max_faces": 60_001},
        {"max_events": 0},
    ):
        with pytest.raises(CellConformanceInputError):
            _inspect(ir, cells, validator, **kwargs)


def test_source_table_budget_is_checked_before_semantic_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ir, cells, validator = _manual_case()
    ir["colors"] = [{}] * 30_001

    def unexpected_hash(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("oversized source reached canonical hashing")

    monkeypatch.setattr(cell_conformance, "canonical_hash", unexpected_hash)
    with pytest.raises(CellConformanceInputError, match="source_table_budget_exceeded"):
        _inspect(ir, cells, validator)


def test_oversized_reference_label_is_rejected_before_semantic_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ir, cells, validator = _manual_case()
    ir["courses"][0]["member_event_ids"][0] = "x" * 129

    def unexpected_hash(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("oversized reference reached canonical hashing")

    monkeypatch.setattr(cell_conformance, "canonical_hash", unexpected_hash)
    with pytest.raises(CellConformanceInputError, match="invalid_source_identifier"):
        _inspect(ir, cells, validator)


def test_source_entity_table_permutations_keep_proof_deterministic() -> None:
    ir, cells, validator = _manual_case()
    baseline = _inspect(ir, cells, validator)
    reordered = deepcopy(ir)
    for name in (
        "attachment_locations",
        "stitches",
        "construction_operations",
        "courses",
        "frontiers",
    ):
        reordered[name].reverse()
    permuted = _inspect(reordered, cells, validator)
    assert permuted.status == "PASS"
    assert permuted.source_ir_sha256 == baseline.source_ir_sha256
    assert permuted.canonical_bytes == baseline.canonical_bytes


@pytest.mark.parametrize("counts", [(3, 4), (4, 3), (3, 4, 3)])
def test_increase_decrease_wrap_integration(counts: tuple[int, ...]) -> None:
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    ir = compile_closed_schedule(
        design,
        material,
        counts,
        (0,) * (len(counts) - 1),
        CompileProvenance("a" * 40, "b" * 64, (("fixture", "cell_conformance"),)),
        max_stitches=100,
    )
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    # Integration checks the producer; the minimal case above is a separate oracle.
    from crochet_ai.physical_projection import PhysicalSemanticProjection

    projection = PhysicalSemanticProjection(ir, material, validator=validator)
    from crochet_ai.forward_closed_cells import build_closed_surface_cells

    cells = build_closed_surface_cells(projection).to_dict()
    report = inspect_closed_cell_conformance(
        ir,
        cells,
        validator=validator,
        projection_sha256=projection.sha256,
        surface_cells_sha256=build_closed_surface_cells(projection).sha256,
    )
    assert report.status == "PASS"
