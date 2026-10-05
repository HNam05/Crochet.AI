from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
from typing import Any

import pytest
from conftest import resolved_artifacts

from crochet_ai.analytic_compile import CompileProvenance, compile_closed_schedule
from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_closed_cells import (
    PROFILE,
    ClosedCellsError,
    build_closed_surface_cells,
)
from crochet_ai.physical_projection import PhysicalSemanticProjection
from crochet_ai.validation import SemanticValidator


def admitted(
    counts: tuple[int, ...],
) -> tuple[dict[str, Any], dict[str, Any], PhysicalSemanticProjection, SemanticValidator]:
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    value = compile_closed_schedule(
        design,
        material,
        counts,
        (0,) * (len(counts) - 1),
        CompileProvenance("a" * 40, "b" * 64, (("fixture", "closed_cells"),)),
        max_stitches=100,
    )
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    return (
        value,
        material,
        PhysicalSemanticProjection(value, material, validator=validator),
        validator,
    )


def _edge_audit(cells: dict) -> None:
    faces = [tuple(face) for face in cells["faces"]]
    incidence: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    links: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for a, b, c in faces:
        assert len({a, b, c}) == 3
        for u, v, w in ((a, b, c), (b, c, a), (c, a, b)):
            incidence[tuple(sorted((u, v)))].append((u, v))
            links[w].append((u, v))
    assert all(len(directed) == 2 for directed in incidence.values())
    assert all(directed[0] == directed[1][::-1] for directed in incidence.values())
    assert len(cells["vertices"]) - len(incidence) + len(faces) == 2
    for vertex, link_edges in links.items():
        adjacency: dict[str, set[str]] = defaultdict(set)
        for a, b in link_edges:
            adjacency[a].add(b)
            adjacency[b].add(a)
        assert adjacency and all(len(neighbors) == 2 for neighbors in adjacency.values()), vertex
        seen = set()
        todo = [next(iter(adjacency))]
        while todo:
            node = todo.pop()
            if node not in seen:
                seen.add(node)
                todo.extend(adjacency[node] - seen)
        assert seen == set(adjacency), vertex


@pytest.mark.parametrize("counts", [(3,), (3, 3), (3, 4), (4, 3), (3, 4, 3)])
def test_closed_cells_are_oriented_combinatorial_spheres(counts: tuple[int, ...]) -> None:
    _, _, projection, _ = admitted(counts)
    result = build_closed_surface_cells(projection)
    cells = result.to_dict()
    assert cells["profile"] == PROFILE
    assert cells["status"] == "TOPOLOGY_ONLY"
    assert cells["projection_sha256"] == projection.sha256
    assert (
        result.sha256
        == sha256(
            b"Crochet.AI\0"
            + PROFILE.encode()
            + b"\0"
            + projection.sha256.encode()
            + b"\0"
            + result.rule_id.encode()
            + b"\0"
            + result.canonical_bytes
        ).hexdigest()
    )
    _edge_audit(cells)


def test_exact_and_one_below_budgets_are_enforced_before_output() -> None:
    _, _, projection, _ = admitted((3, 4, 3))
    cells = build_closed_surface_cells(projection).to_dict()
    assert (
        build_closed_surface_cells(
            projection, max_vertices=len(cells["vertices"]), max_faces=len(cells["faces"])
        ).to_dict()
        == cells
    )
    with pytest.raises(ClosedCellsError, match="vertex_budget_exceeded"):
        build_closed_surface_cells(
            projection, max_vertices=len(cells["vertices"]) - 1, max_faces=len(cells["faces"])
        )
    with pytest.raises(ClosedCellsError, match="face_budget_exceeded"):
        build_closed_surface_cells(
            projection, max_vertices=len(cells["vertices"]), max_faces=len(cells["faces"]) - 1
        )
    for kwargs in ({"max_vertices": True}, {"max_faces": 0}, {"max_vertices": 30_001}):
        with pytest.raises(ClosedCellsError):
            build_closed_surface_cells(projection, **kwargs)


@pytest.mark.parametrize("mutation", ["target", "seed", "generator", "color"])
def test_excluded_metadata_does_not_change_cells(mutation: str) -> None:
    source, material, projection, validator = admitted((3, 4))
    altered = deepcopy(source)
    if mutation == "target":
        altered["provenance"]["input_artifacts"] = [
            {"artifact_id": "asset_new", "artifact_role": "TARGET_GEOMETRY", "sha256": "f" * 64}
        ]
    elif mutation == "seed":
        altered["provenance"]["random_seed"] = 123
    elif mutation == "generator":
        altered["provenance"]["generator"]["name"] = "another-source"
    else:
        altered["colors"][0]["srgb_hex"] = "#FF0000"
        altered["colors"][0]["label"] = "red"
    changed_projection = PhysicalSemanticProjection(altered, material, validator=validator)
    assert changed_projection.canonical_bytes == projection.canonical_bytes
    assert build_closed_surface_cells(changed_projection) == build_closed_surface_cells(projection)


def test_cyclic_base_order_corruption_fails_closed() -> None:
    _, _, projection, _ = admitted((3, 4))
    value = projection.to_dict()
    value["stitches"][1]["base_attachment_location_ids"] = list(
        value["stitches"][2]["base_attachment_location_ids"]
    )
    forged = object.__new__(PhysicalSemanticProjection)
    object.__setattr__(forged, "canonical_bytes", jcs_bytes(value))
    object.__setattr__(
        forged,
        "sha256",
        sha256(b"Crochet.AI\0FORWARD_PHYSICAL_SEMANTICS_V1\0" + forged.canonical_bytes).hexdigest(),
    )
    with pytest.raises(ClosedCellsError, match="cyclic_span_partition"):
        build_closed_surface_cells(forged)


def test_projection_hash_cannot_bind_different_content() -> None:
    _, _, projection, _ = admitted((3,))
    value = projection.to_dict()
    value["courses"][0]["ordinal"] += 1
    forged = object.__new__(PhysicalSemanticProjection)
    object.__setattr__(forged, "canonical_bytes", jcs_bytes(value))
    object.__setattr__(forged, "sha256", projection.sha256)
    with pytest.raises(ClosedCellsError, match="projection_hash_mismatch"):
        build_closed_surface_cells(forged)


def test_target_data_cannot_be_passed_to_builder() -> None:
    _, _, projection, _ = admitted((3,))
    with pytest.raises(TypeError):
        build_closed_surface_cells(projection, target_mesh={})  # type: ignore[call-arg]
