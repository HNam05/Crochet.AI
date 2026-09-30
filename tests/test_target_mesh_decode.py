from __future__ import annotations

import hashlib
import json
import operator
from dataclasses import FrozenInstanceError

import pytest

from crochet_ai.diagnostics import ArtifactValidationError
from crochet_ai.target_mesh_decode import (
    MESH_MEDIA_TYPE,
    DecodedIndexedTriangleMesh,
    MeshDecodeError,
    decode_indexed_triangle_mesh,
)

FRAME = "frame_test"


def mesh_value() -> dict[str, object]:
    return {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER",
            "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": FRAME,
        },
        "vertices": [
            {"position_mm": [0, 0, 0]},
            {"position_mm": [1, 0, 0]},
            {"position_mm": [0, 1, 0]},
            {"position_mm": [0, 0, 1]},
        ],
        "faces": [
            {"vertex_indices": [0, 2, 1]},
            {"vertex_indices": [0, 1, 3]},
            {"vertex_indices": [1, 2, 3]},
            {"vertex_indices": [2, 0, 3]},
        ],
    }


def encode(value: object | None = None) -> bytes:
    return json.dumps(mesh_value() if value is None else value, separators=(",", ":")).encode()


def decode(
    raw: bytes,
    *,
    media_type: str = MESH_MEDIA_TYPE,
    expected_coordinate_frame_id: str = FRAME,
    max_bytes: int = 100_000,
    max_vertices: int = 100,
    max_faces: int = 100,
) -> DecodedIndexedTriangleMesh:
    return decode_indexed_triangle_mesh(
        raw,
        media_type=media_type,
        expected_coordinate_frame_id=expected_coordinate_frame_id,
        max_bytes=max_bytes,
        max_vertices=max_vertices,
        max_faces=max_faces,
    )


def test_decodes_tetrahedron_with_raw_hash_identity_maps_and_frozen_result() -> None:
    source = encode()
    decoded = decode(source)
    assert decoded.vertices_mm[1] == (1.0, 0.0, 0.0)
    assert decoded.faces == ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))
    assert decoded.source_sha256 == hashlib.sha256(source).hexdigest()
    assert decoded.source_to_decoded_vertex_indices == (0, 1, 2, 3)
    assert decoded.decoded_to_source_vertex_indices == (0, 1, 2, 3)
    assert decoded.source_to_decoded_face_indices == (0, 1, 2, 3)
    assert decoded.decoded_to_source_face_indices == (0, 1, 2, 3)
    assert decoded.status == "DECODED_ONLY"
    immutable_field = "status"
    with pytest.raises(FrozenInstanceError):
        setattr(decoded, immutable_field, "PASS")
    with pytest.raises(TypeError):
        operator.setitem(decoded.faces[0], 0, 4)


def test_deterministic_repeat_and_integral_float_indices() -> None:
    value = mesh_value()
    faces = value["faces"]
    assert isinstance(faces, list)
    faces[0] = {"vertex_indices": [0, 2.0, 1e0]}
    raw = encode(value)
    assert decode(raw) == decode(raw)
    assert decode(raw).faces[0] == (0, 2, 1)


def test_duplicate_json_member_is_rejected() -> None:
    raw = (
        b'{"representation_version":"INDEXED_TRIANGLE_MESH_V1",'
        b'"representation_version":"INDEXED_TRIANGLE_MESH_V1"}'
    )
    with pytest.raises(MeshDecodeError) as error:
        decode(raw)
    assert error.value.reason == "mesh.invalid_ijson"


@pytest.mark.parametrize("token", [b"NaN", b"Infinity", b"1e400"])
def test_non_finite_numbers_are_rejected(token: bytes) -> None:
    raw = encode().replace(b"[0,0,0]", b"[" + token + b",0,0]", 1)
    with pytest.raises(MeshDecodeError) as error:
        decode(raw)
    assert error.value.reason == "mesh.invalid_ijson"


def test_unsafe_integer_and_mutable_source_are_rejected() -> None:
    raw = encode().replace(b"[0,0,0]", b"[9007199254740992,0,0]", 1)
    with pytest.raises(MeshDecodeError) as unsafe:
        decode(raw)
    assert unsafe.value.reason == "mesh.invalid_ijson"

    with pytest.raises(MeshDecodeError) as mutable:
        decode_indexed_triangle_mesh(
            bytearray(encode()),
            media_type=MESH_MEDIA_TYPE,
            expected_coordinate_frame_id=FRAME,
            max_bytes=100_000,
            max_vertices=100,
            max_faces=100,
        )
    assert mutable.value.reason == "mesh.source_bytes_required"


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("media_type", "application/json"),
        ("expected_coordinate_frame_id", "frame_other"),
    ],
)
def test_media_type_and_frame_are_explicit(override: str, value: str) -> None:
    with pytest.raises(MeshDecodeError) as error:
        decode(encode(), **{override: value})
    assert error.value.reason in {"mesh.unsupported_media_type", "mesh.frame_mismatch"}


@pytest.mark.parametrize("field,value", [("length_unit", "METER"), ("handedness", "LEFT_HANDED")])
def test_schema_rejects_unsupported_units_and_handedness(field: str, value: str) -> None:
    mesh = mesh_value()
    coordinates = mesh["coordinate_system"]
    assert isinstance(coordinates, dict)
    coordinates[field] = value
    with pytest.raises(ArtifactValidationError) as error:
        decode(encode(mesh))
    assert error.value.report.diagnostics[0].gate == "V0"


@pytest.mark.parametrize(
    ("indices", "error_type"),
    [
        ([0, 1.5, 2], ArtifactValidationError),
        ([0, -1, 2], ArtifactValidationError),
        ([0, 1, 4], MeshDecodeError),
        ([0, 0, 2], MeshDecodeError),
    ],
)
def test_invalid_face_index_cases_fail(
    indices: list[object], error_type: type[Exception]
) -> None:
    mesh = mesh_value()
    faces = mesh["faces"]
    assert isinstance(faces, list)
    faces[0] = {"vertex_indices": indices}
    with pytest.raises(error_type):
        decode(encode(mesh))


def test_unknown_fields_and_empty_arrays_fail_schema_gate_v0() -> None:
    mesh = mesh_value()
    mesh["extra"] = "not allowed"
    with pytest.raises(ArtifactValidationError) as unknown:
        decode(encode(mesh))
    assert unknown.value.report.diagnostics[0].gate == "V0"

    for field in ("vertices", "faces"):
        empty_mesh = mesh_value()
        empty_mesh[field] = []
        with pytest.raises(ArtifactValidationError) as empty:
            decode(encode(empty_mesh))
        assert empty.value.report.diagnostics[0].gate == "V0"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_bytes": 5}, "mesh.byte_budget_exhausted"),
        ({"max_vertices": 3}, "mesh.vertex_budget_exhausted"),
        ({"max_faces": 3}, "mesh.face_budget_exhausted"),
    ],
)
def test_positive_budgets_are_enforced_before_decoded_tuple_construction(
    kwargs: dict[str, int], message: str
) -> None:
    with pytest.raises(MeshDecodeError) as error:
        decode(encode(), **kwargs)
    assert error.value.reason == message


@pytest.mark.parametrize("invalid", [0, -1, True, 1.5])
def test_invalid_byte_budget_is_rejected(invalid: object) -> None:
    with pytest.raises(MeshDecodeError) as error:
        decode(encode(), max_bytes=invalid)
    assert error.value.reason == "mesh.max_bytes_invalid"
