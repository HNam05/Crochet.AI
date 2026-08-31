# Geometry representation contract

## Scope and authority

This document is the authoritative V0 representation contract for triangle-surface target geometry. It defines what an indexed mesh means before [`MESH_PREFLIGHT.md`](MESH_PREFLIGHT.md) applies a domain profile. It does not define a crochet solver, a Construction Graph, a forward-model surface, or a repair pipeline.

**ENGINEERING DECISION:** `IndexedTriangleMeshV1` is a decoded, immutable, right-handed, millimetre-valued triangle surface. Source formats are parser inputs, not alternate canonical geometry models.

**PROVEN / FORMAL:** Vertex/face incidence and coordinate coincidence are different relations. Two vertex records remain topologically distinct even when their coordinates are equal or numerically coincident.

## Source adapter boundary

```text
immutable source bytes + declared media type + declared coordinate frame/unit
    -> versioned parser adapter
    -> IndexedTriangleMeshV1 + source-index maps + parser evidence
    -> V0 inspection/optional canonical data-layout normalization
```

An adapter validates the complete source before producing a mesh. OBJ-style one-based and relative indices, or another format's indexing, may be translated only inside the named adapter and only according to that format's published rules. Translation occurs before canonical validation. A relative or negative source index is never retained as a canonical index. An unresolved, zero where the source forbids zero, negative after resolution, overflowing, fractional, or out-of-range reference fails `E_INPUT`; it is not clamped, wrapped, dropped, or repaired. Original record numbers and source indices are provenance only.

An adapter must declare its name/version, media type, source-byte SHA-256, source unit, unit conversion to millimetres, axis/handedness transform, and source-to-canonical index maps. Untagged units or guessed axes fail. The DesignSpec coordinate frame is authoritative.

## `IndexedTriangleMeshV1`

The logical record is:

```text
IndexedTriangleMeshV1
  representation_version = INDEXED_TRIANGLE_MESH_V1
  coordinate_system
    length_unit = MILLIMETER
    handedness = RIGHT_HANDED
    coordinate_frame_id
  vertices: ordered array<{ position_mm: [x, y, z] }>
  faces: ordered array<{ vertex_indices: [i0, i1, i2] }>
```

The closed machine representation conforms to [`../schemas/indexed-triangle-mesh.schema.json`](../schemas/indexed-triangle-mesh.schema.json). Parser/index maps and the source hash are mandatory V0 evidence but are not fields of this semantic mesh value and do not affect its content identity.

- A `VertexRecord` contains exactly one position `(x_mm, y_mm, z_mm)`. Each coordinate is an accepted I-JSON binary64 value and must be finite. The vertex identity is its zero-based array index.
- A `FaceRecord` contains exactly three ordered vertex indices `(i0, i1, i2)`. Face identity is its zero-based array index. Indices are mathematical integers in the I-JSON safe range and, for a mesh with `n` vertices, satisfy `0 <= i < n`.
- Canonical faces are triangles only. Polygons may be accepted only by a separately versioned adapter with a fully specified deterministic triangulation algorithm; V0 defines no such adapter. A parser must not guess a triangulation.
- Negative canonical indices and repeated indices within a face are invalid. Repeated indices are an exact combinatorial degeneracy even if the remaining coordinates differ.
- Caller-owned arrays and source bytes are immutable. Inspection operates on a defensive read-only representation; any normalized representation is a separate derived artifact.

Empty vertex or face arrays fail V0. A vertex not referenced by a face is isolated/unreferenced and fails. A face that shares no edge with any other face is an isolated face and fails all V1 mesh profiles.

## Identity, orientation, and adjacency

For face `(a,b,c)`, the directed edges are `(a,b)`, `(b,c)`, `(c,a)`. An undirected edge is the ordered pair `(min(u,v), max(u,v))`; this exact integer pair is its identity. Coordinate equality never changes edge identity.

- Two faces are edge-adjacent when they contain the same undirected edge.
- They are vertex-adjacent when they share a vertex identity but no edge.
- Interior manifold edge: exactly two incident faces.
- Boundary edge: exactly one incident face.
- Non-manifold edge: more than two incident faces. Zero-incidence edges do not exist in this representation.
- Consistent winding across an interior edge requires the two incident directed uses to be opposite.

A face-connected component is a maximal set of faces connected through shared undirected edges. Vertices referenced only by faces in one component belong to that component. A vertex shared by otherwise edge-disconnected fans exposes a vertex-manifold failure; it does not silently merge the face components.

The link of a vertex is constructed combinatorially from its incident triangles. A manifold interior vertex has one link cycle. A manifold boundary vertex has one link path with two endpoints. Multiple link components, branching link degree, a closed link at a boundary vertex, or any other link topology is a non-manifold vertex. This detects bow-tie vertices independently of edge incidence.

## Boundaries and surface state

The boundary graph contains precisely the boundary edges and their incident vertex identities. For an accepted orientable two-manifold with boundary, every boundary vertex has boundary degree two and each connected boundary component is a simple cycle. The cycle is a boundary loop. A component with boundary degree one has a boundary chain; branching, repeated vertices, chains, or other non-cycle boundary components fail rather than being repaired into loops.

A component is closed when it has no boundary edges and open when it has one or more valid boundary loops. Watertightness in V0 means closed plus manifold edge/vertex incidence and no coincident, intersecting, or contacting geometry; it is not a library flag.

## Duplicate and coincident geometry

- Faces are duplicates when their three vertex identities form the same unordered set. Same cyclic order is a same-winding duplicate; opposite cyclic order is a reversed duplicate. Both fail, and neither is cancelled against the other.
- Exactly equal coordinate triples on distinct vertex identities are coincident coordinates and fail. Numerically coincident distinct vertices are classified only through the selected numerical profile and also fail. V0 never welds them.
- Coincident triangles have the same geometric support and area, regardless of vertex identities or winding. They fail separately from combinatorial duplicate faces.
- A triangle is geometrically degenerate when its three positions are collinear or its profile-normalized doubled area is at or below the selected threshold. An exactly repeated index is reported first as an exact degeneracy.

## Orientability and winding

Orientability is an exact combinatorial property: assign a binary orientation to faces so that every two-face interior edge is used oppositely. A contradiction in this constraint graph proves the component non-orientable. This test is separate from whether the supplied face order is already consistently wound.

Consistent orientation means every current two-face interior edge is oppositely directed. An orientable but locally inconsistent input fails; V0 does not flip an inferred subset of faces. Reversing every face of one consistently oriented component preserves consistency.

For a closed, consistently oriented component, outward orientation is determined only when the numerical profile certifies the sign of signed enclosed volume. A reliable negative sign permits one recorded whole-component reversal. A sign interval containing zero or a magnitude at/below the stability threshold is `ORIENTATION_INDETERMINATE` and cannot pass. Open components have no general canonical outward side; V0 reports orientability and consistency without inventing outwardness.

## Intersection and contact semantics

Intersection/contact classification uses topology first and the robust/numerical rules in [`NUMERICAL_GEOMETRY.md`](NUMERICAL_GEOMETRY.md):

- intended shared-edge adjacency: the geometric intersection is exactly the common edge of two manifold incident faces;
- intended shared-vertex adjacency: the geometric intersection is exactly their shared vertex identity;
- proper intersection: relative interiors cross;
- vertex-face touch or edge-edge touch: zero-clearance contact without relative-interior penetration;
- coplanar overlap: positive-area overlap in a common plane;
- coincident triangles: equal geometric support;
- near contact: disjoint primitives whose certified minimum distance is within the numerical profile threshold.

Normal intended adjacency is not self-intersection. Any extra overlap beyond the intended shared entity fails. Proper, touching, overlapping, coincident, or near-contact relations between non-adjacent faces in one component fail as self-contact/intersection. Proper intersection between components fails `E_INPUT`; zero-clearance or near inter-component contact fails `E_UNSUPPORTED_FEATURE` because intentional component contact has no V1 declaration model.

## Deterministic, non-destructive normalization

V0 may only:

1. convert declared source units/axes/indices into the canonical millimetre, right-handed, zero-based representation;
2. canonicalize `-0.0` to `0.0` as required by the shared number contract;
3. for a geometry-valid mesh with no coincident vertices, sort vertices lexicographically by canonical binary64 coordinates and retain both index maps;
4. rotate each face cyclically so its smallest canonical vertex index is first without changing winding, then sort faces lexicographically;
5. order components and boundary loops by their canonical vertex/face tuples and rotate a loop to its least vertex index while preserving induced direction;
6. reverse every face in one closed consistently oriented component only when signed-volume evidence reliably proves global inversion.

Every step records algorithm version and before/after hashes. Vertex welding, coordinate snapping, local face flipping, face deletion, hole filling, component dropping/merging, remeshing, smoothing, intersection removal, unit guessing, and topology changes are repairs and forbidden.

After the permitted ordering steps, the derived semantic mesh uses `INDEXED_TRIANGLE_MESH_CANONICAL_JSON_V1` from [`CANONICALIZATION.md`](CANONICALIZATION.md). The pre-JCS registry preserves `position_mm` and `vertex_indices` tuple order and the already-normalized vertex/face array order; no other arrays exist. Source provenance is hashed separately as evidence. Thus object-key order and original source record order cannot change the canonical derived-mesh identity.

## Determinism and invariants

Semantic V0 classification is invariant under source vertex renumbering, face ordering, rigid translation, rigid rotation, and positive uniform scale with equivalent unit conversion, subject to finite representable arithmetic and the scale-normalized numerical profile. Canonical diagnostics sort by gate, code, component canonical key, primitive kind, and canonical vertex/edge/face tuple. A numeric tie is either resolved by a specified canonical key when semantics are equal or reported ambiguous; iteration order is never a semantic tie-break.

The model is a triangle-surface boundary representation. Analytic targets, planar regions, motif graphs, future simulation meshes, and volumetric/FEM data require their own representations and do not weaken this contract.
