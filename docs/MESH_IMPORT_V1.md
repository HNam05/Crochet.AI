# Wavefront OBJ Triangle Import V1

## Status and boundary

`WAVEFRONT_OBJ_TRIANGLES_V1` is a dependency-free, bounded source adapter. It
decodes the deliberately small OBJ subset below into an
`IndexedTriangleMeshV1` JSON value. It does not certify topology, manifoldness,
orientation, geometric quality, or self-intersection. The returned status is
`DECODED` and the topology status is `NOT_AUDITED_V0_REQUIRED`; all geometry
must continue through the applicable V0 preflight profile.

The adapter was implemented from the project's own input contract and a
clean-room reading of the OBJ record/index model. No external parser source,
tests, or implementation-specific pseudocode was copied. No runtime package or
external executable is used.

## Request profile

Admission requires exactly these fields, with no unknown keys:

| Field | Meaning and bound |
| --- | --- |
| `profile` | `WAVEFRONT_OBJ_TRIANGLES_V1` |
| `schema_version` | `1.0.0` |
| `source_unit` | `MILLIMETER`, `CENTIMETER`, or `METER` |
| `coordinate_frame_id` | A schema-valid `frame_...` identifier supplied by the caller |
| `handedness` | Exactly `RIGHT_HANDED` |
| `max_source_bytes` | Positive; at most 16 MiB |
| `max_line_bytes` | 16 through 65,536 |
| `max_vertices` | 3 through 100,000 |
| `max_faces` | 1 through 200,000 |

The request's coordinate frame is a declaration, not a transform. OBJ has no
portable unit, axis, or handedness metadata. The adapter preserves the three
source coordinate axes in the declared right-handed frame and performs no
axis rotation, reflection, origin shift, or scale guessing. Unit factors are
exact integers: 1 mm/mm, 10 mm/cm, and 1000 mm/m. Each input coordinate is
first represented as binary64, multiplied by the exact integer factor as a
rational, then rounded to the canonical binary64 output. Overflow, and a
nonzero result rounded to zero, are rejected. Negative zero is normalized to
positive zero as required by canonical JSON number semantics.

## Accepted text subset

The input is a Python string that must encode as strict UTF-8. The exact
resulting UTF-8 bytes are hashed before parsing; comments, whitespace, line
endings, and Unicode comment text therefore remain part of source identity.
Source-byte and per-line byte limits are enforced. Blank lines and `#`
comments (including trailing comments) are ignored by parsing.
LF and CRLF delimit records. A bare carriage return inside a line is rejected.

The only data records accepted are:

```text
v x y z
f i j k
```

Each vertex has exactly three finite base-10 binary64 coordinates. The
adapter rejects homogeneous vertex coordinates and non-decimal forms,
non-finite values, lexical underflow to zero, unit-conversion overflow, and a
nonzero value lost to zero by unit conversion. The accepted numeric grammar is
an optional sign, decimal digits with an optional fractional part, and an
optional decimal exponent.

Each face has exactly three plain vertex indices. Positive indices are
one-based; negative indices are relative to the number of vertices already
declared; zero is invalid. Index tokens are bounded safe integers and must
resolve to already-declared vertices. Resolved indices are zero-based. A face
cannot repeat an index. Vertex and face source order and each face's winding
are preserved exactly.

Every other record or feature is rejected, including `vt`, `vn`, slash-form
corner tuples, polygons, lines, points, groups, objects, smoothing/material
directives, and free-form surfaces. Positive forward references, even if a
later vertex record might make them resolvable, are outside this strict
subset. There is no polygon triangulation, deduplication, welding,
reorientation, face deletion, or other repair.

## Output identity and evidence

The output mesh has the schema-defined `INDEXED_TRIANGLE_MESH_V1` shape, with
coordinates converted to millimetres. The source-frame identifier and
right-handed declaration are retained in its coordinate system. The result
contains:

- `raw_source_sha256`: SHA-256 of the exact original UTF-8 source bytes;
- `mesh_jcs_bytes` and `mesh_jcs_sha256`: RFC 8785 bytes and their plain
  SHA-256 for the decoded, source-order mesh value;
- source record-number arrays that map emitted vertices/faces to original
  non-comment OBJ line numbers;
- declared source unit, exact unit factor as numerator/denominator, source
  frame, parser profile/version, and bounded record counters.

The mesh JCS digest is not the canonical semantic mesh identity. The adapter
preserves source vertex/face order, while the canonical mesh identity is
computed only after V0's geometry checks and permitted canonical ordering.
Raw-source identity and decoded-mesh JCS identity are separate evidence and
need not match. The output does not claim V0 admission or any topology result.

## Complexity and failure behavior

Parsing is linear in source bytes plus emitted vertices/faces. Memory is
bounded by the source byte cap, line cap, and vertex/face caps. Coordinates
and indices are validated before insertion into the output arrays. Parameter
admission rejects unrecognized profiles, versions, units, frames, and budget
values before parsing.

`MeshImportError` carries a stable code, reason, and optional source line:

- `E_INPUT` for invalid text, numbers, indices, parameters, or decoded mesh;
- `E_UNSUPPORTED` for OBJ record types or constructs outside the subset;
- `E_BUDGET` for source, line, vertex, or face limits.

No partial mesh is returned on any failure. Successful conversion is a parser
result only. V0 remains responsible for empty/isolated geometry, duplicate
faces, vertex manifoldness, consistent winding, boundary expectations,
intersections, contacts, numerical quality, and any explicitly permitted
non-destructive canonical ordering.
