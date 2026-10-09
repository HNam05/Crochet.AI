from __future__ import annotations

import hashlib
from typing import Any, cast

import pytest

from crochet_ai.canonical import parse_json
from crochet_ai.mesh_import import (
    PROFILE,
    MeshImportError,
    ObjImportParameters,
    admit_obj_import_parameters,
    import_wavefront_obj,
)
from crochet_ai.schema import validate_schema

FRAME = "frame_obj_fixture"
TETRA_OBJ = """# tetrahedron fixture
v 0 0 0
v 1 0 0
v 0 1 0
v 0 0 1
f 1 3 2
f 1 2 4
f 2 3 4
f 3 1 4
"""


def _params(**overrides: Any) -> ObjImportParameters:
    value: dict[str, object] = {
        "profile": PROFILE,
        "schema_version": "1.0.0",
        "source_unit": "MILLIMETER",
        "coordinate_frame_id": FRAME,
        "handedness": "RIGHT_HANDED",
        "max_source_bytes": 100_000,
        "max_line_bytes": 4096,
        "max_vertices": 100,
        "max_faces": 200,
    }
    value.update(overrides)
    return admit_obj_import_parameters(value)


def test_tetrahedron_decodes_to_schema_valid_mesh_without_claiming_topology_pass() -> None:
    result = import_wavefront_obj(TETRA_OBJ, _params())
    mesh = cast(dict[str, Any], parse_json(result.mesh_jcs_bytes))
    assert validate_schema("indexed_triangle_mesh", mesh).ok
    assert mesh["representation_version"] == "INDEXED_TRIANGLE_MESH_V1"
    assert mesh["coordinate_system"] == {
        "length_unit": "MILLIMETER",
        "handedness": "RIGHT_HANDED",
        "coordinate_frame_id": FRAME,
    }
    assert [item["position_mm"] for item in mesh["vertices"]] == [
        [0, 0, 0],
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
    ]
    assert [item["vertex_indices"] for item in mesh["faces"]] == [
        [0, 2, 1],
        [0, 1, 3],
        [1, 2, 3],
        [2, 0, 3],
    ]
    assert result.raw_source_sha256 == hashlib.sha256(TETRA_OBJ.encode()).hexdigest()
    assert result.mesh_jcs_sha256 == hashlib.sha256(result.mesh_jcs_bytes).hexdigest()
    assert result.raw_source_sha256 != result.mesh_jcs_sha256
    evidence = cast(dict[str, Any], result.to_dict())
    assert evidence["topology_status"] == "NOT_AUDITED_V0_REQUIRED"
    assert evidence["vertex_source_record_numbers"] == [2, 3, 4, 5]
    assert evidence["face_source_record_numbers"] == [6, 7, 8, 9]


def test_reversed_winding_is_preserved_and_not_reoriented() -> None:
    source = TETRA_OBJ.replace("f 1 3 2", "f 1 2 3")
    result = import_wavefront_obj(source, _params())
    mesh = cast(dict[str, Any], parse_json(result.mesh_jcs_bytes))
    assert mesh["faces"][0]["vertex_indices"] == [0, 1, 2]
    evidence = cast(dict[str, Any], result.to_dict())
    assert "winding preserved" in " ".join(evidence["normalization"])


def test_relative_indices_and_declared_units_resolve_deterministically() -> None:
    source = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf -3 -1 -2\n"
    result = import_wavefront_obj(source, _params(source_unit="METER"))
    mesh = cast(dict[str, Any], parse_json(result.mesh_jcs_bytes))
    assert mesh["vertices"][1]["position_mm"] == [1000, 0, 0]
    assert mesh["faces"][0]["vertex_indices"] == [0, 2, 1]
    evidence = cast(dict[str, Any], result.to_dict())
    assert evidence["unit_scale_to_mm"] == {"numerator": 1000, "denominator": 1}


def test_equivalent_centimetre_mesh_has_identical_decoded_mesh_jcs() -> None:
    centimetres = (
        TETRA_OBJ.replace("v 1 0 0", "v 0.1 0 0")
        .replace("v 0 1 0", "v 0 0.1 0")
        .replace("v 0 0 1", "v 0 0 0.1")
    )
    millimetres = import_wavefront_obj(TETRA_OBJ, _params())
    converted = import_wavefront_obj(centimetres, _params(source_unit="CENTIMETER"))
    assert converted.mesh_jcs_bytes == millimetres.mesh_jcs_bytes
    assert converted.raw_source_sha256 != millimetres.raw_source_sha256


def test_exact_source_bytes_and_decoded_mesh_have_separate_hashes() -> None:
    first = TETRA_OBJ
    second = "# λ comment\r\n" + TETRA_OBJ.replace("\n", "\r\n")
    one = import_wavefront_obj(first, _params())
    two = import_wavefront_obj(second, _params())
    assert one.raw_source_sha256 != two.raw_source_sha256
    assert one.mesh_jcs_bytes == two.mesh_jcs_bytes
    assert one.mesh_jcs_sha256 == two.mesh_jcs_sha256


@pytest.mark.parametrize(
    "source,reason",
    [
        (TETRA_OBJ + "vt 0 0\n", "obj_record_unsupported:vt"),
        (TETRA_OBJ + "vn 0 0 1\n", "obj_record_unsupported:vn"),
        (TETRA_OBJ + "g surface\n", "obj_record_unsupported:g"),
        (TETRA_OBJ + "f 1/1 2/2 3/3\n", "face_index_not_bounded_integer"),
        (TETRA_OBJ + "f 1 2 3 4\n", "face_requires_exactly_three_plain_indices"),
        (TETRA_OBJ + "f 0 2 3\n", "face_index_zero_or_unsafe"),
        (TETRA_OBJ + "f 1 2 999\n", "face_index_out_of_range"),
        (TETRA_OBJ + "f 999999999999999999999999 2 3\n", "face_index_not_bounded_integer"),
        (TETRA_OBJ + "f 1 1 3\n", "face_repeats_vertex_index"),
        (TETRA_OBJ.replace("v 0 0 0", "v nan 0 0", 1), "vertex_coordinate_not_decimal"),
        ("v 1e9999 0 0\n", "vertex_coordinate_nonfinite"),
    ],
)
def test_unsupported_or_malformed_records_fail_closed(source: str, reason: str) -> None:
    with pytest.raises(MeshImportError) as error:
        import_wavefront_obj(source, _params())
    assert error.value.code in {"E_INPUT", "E_UNSUPPORTED"}
    assert error.value.reason == reason


def test_unit_conversion_overflow_and_unrepresentable_underflow_are_rejected() -> None:
    with pytest.raises(MeshImportError, match="unit_conversion_overflow"):
        import_wavefront_obj("v 1e308 0 0\n", _params(source_unit="METER"))
    tiny = "v 1e-9999 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
    with pytest.raises(MeshImportError, match="vertex_coordinate_underflow"):
        import_wavefront_obj(tiny, _params(source_unit="METER"))


def test_source_line_vertex_and_face_budgets_are_enforced() -> None:
    with pytest.raises(MeshImportError, match="source_byte_budget_exceeded"):
        import_wavefront_obj(TETRA_OBJ, _params(max_source_bytes=16))
    with pytest.raises(MeshImportError, match="line_byte_budget_exceeded"):
        import_wavefront_obj("#" + "x" * 40, _params(max_line_bytes=32))
    with pytest.raises(MeshImportError, match="vertex_budget_exceeded"):
        import_wavefront_obj(TETRA_OBJ, _params(max_vertices=3))
    with pytest.raises(MeshImportError, match="face_budget_exceeded"):
        import_wavefront_obj(TETRA_OBJ, _params(max_faces=3))


@pytest.mark.parametrize(
    "overrides",
    [
        {"profile": "UNKNOWN"},
        {"schema_version": "2.0.0"},
        {"source_unit": "INCH"},
        {"coordinate_frame_id": "frame bad"},
        {"handedness": "LEFT_HANDED"},
        {"max_faces": True},
        {"max_vertices": 100_001},
        {"surprise": 1},
    ],
)
def test_import_parameters_are_versioned_strict_and_bounded(overrides: dict[str, object]) -> None:
    with pytest.raises(MeshImportError):
        _params(**overrides)


def test_directly_constructed_parameter_record_is_revalidated() -> None:
    forged = ObjImportParameters(
        PROFILE, "1.0.0", "INCH", FRAME, "RIGHT_HANDED", 100_000, 4096, 100, 200
    )
    with pytest.raises(MeshImportError, match="source_unit_unsupported"):
        import_wavefront_obj(TETRA_OBJ, forged)


def test_empty_mesh_and_invalid_utf8_scalar_fail_without_partial_output() -> None:
    with pytest.raises(MeshImportError, match="mesh_requires_vertices_and_faces"):
        import_wavefront_obj("# nothing\n", _params())
    with pytest.raises(MeshImportError, match="source_contains_invalid_unicode"):
        import_wavefront_obj("v \ud800 0 0\n", _params())
