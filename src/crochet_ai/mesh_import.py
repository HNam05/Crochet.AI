"""Strict, bounded Wavefront OBJ to IndexedTriangleMeshV1 adapter."""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from typing import cast

import rfc8785

from .canonical import SAFE_INTEGER, validate_ijson
from .json_types import JSONValue
from .schema import validate_schema

PROFILE = "WAVEFRONT_OBJ_TRIANGLES_V1"
SCHEMA_VERSION = "1.0.0"
_PARAMETER_FIELDS = {
    "profile",
    "schema_version",
    "source_unit",
    "coordinate_frame_id",
    "handedness",
    "max_source_bytes",
    "max_line_bytes",
    "max_vertices",
    "max_faces",
}
_LIMITS = {
    "max_source_bytes": (1, 16 * 1024 * 1024),
    "max_line_bytes": (16, 65_536),
    "max_vertices": (3, 100_000),
    "max_faces": (1, 200_000),
}
_UNIT_SCALE = {
    "MILLIMETER": Fraction(1),
    "CENTIMETER": Fraction(10),
    "METER": Fraction(1000),
}
_FLOAT_TOKEN = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_INTEGER_TOKEN = re.compile(r"[+-]?[0-9]+\Z")
_FRAME_ID = re.compile(r"frame_[A-Za-z0-9][A-Za-z0-9._-]{0,115}\Z")


class MeshImportError(ValueError):
    """Typed failure at the strict source-adapter boundary."""

    def __init__(self, code: str, reason: str, line_number: int | None = None) -> None:
        self.code = code
        self.reason = reason
        self.line_number = line_number
        super().__init__(f"{code}:{reason}")


@dataclass(frozen=True, slots=True)
class ObjImportParameters:
    profile: str
    schema_version: str
    source_unit: str
    coordinate_frame_id: str
    handedness: str
    max_source_bytes: int
    max_line_bytes: int
    max_vertices: int
    max_faces: int

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "profile": self.profile,
            "schema_version": self.schema_version,
            "source_unit": self.source_unit,
            "coordinate_frame_id": self.coordinate_frame_id,
            "handedness": self.handedness,
            "max_source_bytes": self.max_source_bytes,
            "max_line_bytes": self.max_line_bytes,
            "max_vertices": self.max_vertices,
            "max_faces": self.max_faces,
        }


@dataclass(frozen=True, slots=True)
class ObjImportResult:
    parameters: ObjImportParameters
    raw_source_sha256: str
    source_byte_count: int
    mesh_jcs_bytes: bytes
    mesh_jcs_sha256: str
    vertex_source_record_numbers: tuple[int, ...]
    face_source_record_numbers: tuple[int, ...]
    vertex_records: int
    face_records: int

    @property
    def mesh(self) -> JSONValue:
        """Return a fresh decoded copy of the canonical indexed mesh value."""
        import json

        return cast(JSONValue, json.loads(self.mesh_jcs_bytes.decode("utf-8")))

    def to_dict(self) -> dict[str, JSONValue]:
        scale = _UNIT_SCALE[self.parameters.source_unit]
        return {
            "profile": PROFILE,
            "schema_version": SCHEMA_VERSION,
            "status": "DECODED",
            "raw_source_sha256": self.raw_source_sha256,
            "source_byte_count": self.source_byte_count,
            "source_unit": self.parameters.source_unit,
            "unit_scale_to_mm": {
                "numerator": scale.numerator,
                "denominator": scale.denominator,
            },
            "source_coordinate_frame": {
                "coordinate_frame_id": self.parameters.coordinate_frame_id,
                "handedness": self.parameters.handedness,
            },
            "mesh_jcs_sha256": self.mesh_jcs_sha256,
            "mesh_jcs_bytes_utf8": self.mesh_jcs_bytes.decode("utf-8"),
            "vertex_source_record_numbers": list(self.vertex_source_record_numbers),
            "face_source_record_numbers": list(self.face_source_record_numbers),
            "work": {
                "vertex_records": self.vertex_records,
                "face_records": self.face_records,
                "maximum_source_bytes": self.parameters.max_source_bytes,
                "maximum_line_bytes": self.parameters.max_line_bytes,
                "maximum_vertices": self.parameters.max_vertices,
                "maximum_faces": self.parameters.max_faces,
            },
            "normalization": [
                "OBJ positive and relative negative indices resolved to zero-based indices",
                "declared source units converted to millimetres by the exact integer scale",
                "source axes, handedness, vertex/face order, and winding preserved",
                "negative zero normalized to positive zero for canonical binary64 output",
                "no vertex welding, deduplication, reorientation, or topology repair",
            ],
            "topology_status": "NOT_AUDITED_V0_REQUIRED",
            "mesh": self.mesh,
        }


def admit_obj_import_parameters(value: object) -> ObjImportParameters:
    """Admit a complete, exact-key versioned OBJ parser request."""
    if not isinstance(value, dict) or set(value) != _PARAMETER_FIELDS:
        raise MeshImportError("E_INPUT", "parameter_fields_invalid")
    if value["profile"] != PROFILE or value["schema_version"] != SCHEMA_VERSION:
        raise MeshImportError("E_INPUT", "parameter_profile_or_version_invalid")
    unit = value["source_unit"]
    if not isinstance(unit, str) or unit not in _UNIT_SCALE:
        raise MeshImportError("E_INPUT", "source_unit_unsupported")
    frame_id = value["coordinate_frame_id"]
    if not isinstance(frame_id, str) or not _FRAME_ID.fullmatch(frame_id):
        raise MeshImportError("E_INPUT", "coordinate_frame_id_invalid")
    if value["handedness"] != "RIGHT_HANDED":
        raise MeshImportError("E_INPUT", "source_handedness_unsupported")
    for name, (minimum, maximum) in _LIMITS.items():
        number = value[name]
        if type(number) is not int or not minimum <= number <= maximum:
            raise MeshImportError("E_INPUT", f"{name}_out_of_bounds")
    return ObjImportParameters(
        cast(str, value["profile"]),
        cast(str, value["schema_version"]),
        unit,
        frame_id,
        cast(str, value["handedness"]),
        cast(int, value["max_source_bytes"]),
        cast(int, value["max_line_bytes"]),
        cast(int, value["max_vertices"]),
        cast(int, value["max_faces"]),
    )


def import_wavefront_obj(source_text: str, parameters: ObjImportParameters) -> ObjImportResult:
    """Decode only vertex and triangular-face records; reject every other OBJ feature."""
    if not isinstance(parameters, ObjImportParameters):
        raise MeshImportError("E_INPUT", "parameters_not_admitted")
    parameters = admit_obj_import_parameters(parameters.to_dict())
    if not isinstance(source_text, str):
        raise MeshImportError("E_INPUT", "source_must_be_utf8_text")
    if len(source_text) > parameters.max_source_bytes:
        raise MeshImportError("E_BUDGET", "source_byte_budget_exceeded")
    source_byte_count = 0
    for character in source_text:
        codepoint = ord(character)
        if 0xD800 <= codepoint <= 0xDFFF:
            raise MeshImportError("E_INPUT", "source_contains_invalid_unicode")
        source_byte_count += (
            1 if codepoint <= 0x7F else 2 if codepoint <= 0x7FF else 3 if codepoint <= 0xFFFF else 4
        )
        if source_byte_count > parameters.max_source_bytes:
            raise MeshImportError("E_BUDGET", "source_byte_budget_exceeded")
    try:
        raw_bytes = source_text.encode("utf-8", "strict")
    except UnicodeEncodeError as error:
        raise MeshImportError("E_INPUT", "source_contains_invalid_unicode") from error
    if len(raw_bytes) != source_byte_count:
        raise MeshImportError("E_INPUT", "source_utf8_length_inconsistent")

    scale = _UNIT_SCALE[parameters.source_unit]
    points: list[list[float]] = []
    faces: list[list[int]] = []
    vertex_lines: list[int] = []
    face_lines: list[int] = []
    maximum_float = Fraction.from_float(sys.float_info.max)

    for line_number, raw_line in _bounded_lines(source_text, parameters.max_line_bytes):
        content = raw_line.split("#", maxsplit=1)[0].strip()
        if not content:
            continue
        fields = content.split()
        record = fields[0]
        if record == "v":
            if len(fields) != 4:
                raise MeshImportError(
                    "E_INPUT", "vertex_requires_exactly_three_coordinates", line_number
                )
            if len(points) >= parameters.max_vertices:
                raise MeshImportError("E_BUDGET", "vertex_budget_exceeded", line_number)
            point: list[float] = []
            for token in fields[1:]:
                if len(token) > 128 or not _FLOAT_TOKEN.fullmatch(token):
                    raise MeshImportError("E_INPUT", "vertex_coordinate_not_decimal", line_number)
                try:
                    source_value = float(token)
                except ValueError as error:
                    raise MeshImportError(
                        "E_INPUT", "vertex_coordinate_invalid", line_number
                    ) from error
                if not math.isfinite(source_value):
                    raise MeshImportError("E_INPUT", "vertex_coordinate_nonfinite", line_number)
                mantissa = token.lower().split("e", maxsplit=1)[0].lstrip("+-")
                if source_value == 0.0 and any(digit in "123456789" for digit in mantissa):
                    raise MeshImportError("E_INPUT", "vertex_coordinate_underflow", line_number)
                exact_scaled = Fraction.from_float(source_value) * scale
                if abs(exact_scaled) > maximum_float:
                    raise MeshImportError("E_INPUT", "unit_conversion_overflow", line_number)
                millimetres = float(exact_scaled)
                if not math.isfinite(millimetres) or (source_value != 0.0 and millimetres == 0.0):
                    raise MeshImportError("E_INPUT", "unit_conversion_not_finite", line_number)
                point.append(0.0 if millimetres == 0.0 else millimetres)
            points.append(point)
            vertex_lines.append(line_number)
        elif record == "f":
            if len(fields) != 4:
                raise MeshImportError(
                    "E_INPUT", "face_requires_exactly_three_plain_indices", line_number
                )
            if len(faces) >= parameters.max_faces:
                raise MeshImportError("E_BUDGET", "face_budget_exceeded", line_number)
            indices: list[int] = []
            for token in fields[1:]:
                if len(token) > 17 or not _INTEGER_TOKEN.fullmatch(token):
                    raise MeshImportError("E_INPUT", "face_index_not_bounded_integer", line_number)
                raw_index = int(token)
                if raw_index == 0 or abs(raw_index) > SAFE_INTEGER:
                    raise MeshImportError("E_INPUT", "face_index_zero_or_unsafe", line_number)
                resolved = raw_index - 1 if raw_index > 0 else len(points) + raw_index
                if not 0 <= resolved < len(points):
                    raise MeshImportError("E_INPUT", "face_index_out_of_range", line_number)
                indices.append(resolved)
            if len(set(indices)) != 3:
                raise MeshImportError("E_INPUT", "face_repeats_vertex_index", line_number)
            faces.append(indices)
            face_lines.append(line_number)
        else:
            raise MeshImportError("E_UNSUPPORTED", f"obj_record_unsupported:{record}", line_number)

    if not points or not faces:
        raise MeshImportError("E_INPUT", "mesh_requires_vertices_and_faces")
    mesh: dict[str, JSONValue] = {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER",
            "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": parameters.coordinate_frame_id,
        },
        "vertices": [{"position_mm": cast(JSONValue, point)} for point in points],
        "faces": [{"vertex_indices": cast(JSONValue, face)} for face in faces],
    }
    validate_ijson(mesh)
    schema_report = validate_schema("indexed_triangle_mesh", mesh)
    if not schema_report.ok:
        raise MeshImportError("E_INPUT", "decoded_indexed_triangle_mesh_schema_invalid")
    encoded = rfc8785.dumps(mesh)
    return ObjImportResult(
        parameters=parameters,
        raw_source_sha256=sha256(raw_bytes).hexdigest(),
        source_byte_count=len(raw_bytes),
        mesh_jcs_bytes=encoded,
        mesh_jcs_sha256=sha256(encoded).hexdigest(),
        vertex_source_record_numbers=tuple(vertex_lines),
        face_source_record_numbers=tuple(face_lines),
        vertex_records=len(points),
        face_records=len(faces),
    )


def _bounded_lines(source_text: str, maximum_bytes: int) -> Iterator[tuple[int, str]]:
    """Yield lines after bounding each slice; do not materialize a split-line list."""
    offset = 0
    line_number = 1
    while offset < len(source_text):
        newline = source_text.find("\n", offset)
        end = len(source_text) if newline < 0 else newline
        if end - offset > maximum_bytes:
            raise MeshImportError("E_BUDGET", "line_byte_budget_exceeded", line_number)
        line = source_text[offset:end]
        if newline >= 0 and line.endswith("\r"):
            line = line[:-1]
        if "\r" in line:
            raise MeshImportError("E_INPUT", "unsupported_line_ending", line_number)
        try:
            encoded_size = len(line.encode("utf-8", "strict"))
        except UnicodeEncodeError as error:
            raise MeshImportError(
                "E_INPUT", "source_contains_invalid_unicode", line_number
            ) from error
        if encoded_size > maximum_bytes:
            raise MeshImportError("E_BUDGET", "line_byte_budget_exceeded", line_number)
        yield line_number, line
        if newline < 0:
            break
        offset = newline + 1
        line_number += 1
