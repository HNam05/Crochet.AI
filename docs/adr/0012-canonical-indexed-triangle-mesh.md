# ADR-0012: Canonical indexed triangle mesh

- Status: Accepted
- Date: 2026-08-31

## Context

V0 could not be implemented deterministically while mesh identity, units, source indexing, parser normalization, and permitted repairs were implicit. Geometry libraries also differ on whether coincident coordinates imply one vertex and whether input ordering is semantic.

## Decision

V0 mesh profiles consume immutable `IndexedTriangleMeshV1`: finite IEEE-754 binary64 coordinates in a declared right-handed millimetre frame, zero-based safe-integer vertex indices, and ordered triangle records. Vertex and face identity are array positions; coordinate coincidence never merges topological identity. Undirected edges use `(min(vertex_a, vertex_b), max(vertex_a, vertex_b))`; components are connected through shared edges.

The closed structured representation is schema-backed. After permitted ordering, its derived content hash uses `INDEXED_TRIANGLE_MESH_CANONICAL_JSON_V1`; parser provenance and source-index maps remain separate evidence and cannot change semantic mesh identity.

Source-format indexing, units, axes, and handedness are resolved by a named versioned adapter before the canonical model. Unsupported polygons are rejected rather than guessed. V0 may reorder records with source maps, normalize negative zero, and reverse an entire reliably inverted closed component. It may not weld, snap, locally flip, delete, fill, remesh, or otherwise repair geometry.

## Alternatives

- Library-native mesh objects were rejected because their identity, indexing, and mutation rules are not a portable contract.
- Coordinate-derived vertex identity was rejected because it silently changes topology.
- Implicit source conventions were rejected because equivalent parsers could disagree.
- Automatic repair was rejected because it changes the authoritative target and provenance.

## Consequences

Parser correctness and V0 geometry validity are independently auditable. Equivalent source numbering and ordering may normalize to the same derived representation without changing incidence. Future polygonal, volumetric, simulation, or planar representations require separate versioned contracts rather than loosening this triangle-surface model.
