# Forward closed surface cells V1

`FORWARD_CLOSED_SURFACE_CELLS_V1` defines a deterministic, target-free
combinatorial triangulation for the single-component, single-branch, single-yarn
closed SC construction admitted by `PhysicalSemanticProjection`. Its result has
status `TOPOLOGY_ONLY`. It contains attachment IDs as vertices and oriented
triangles, plus the exact projection hash and rule identifier in canonical bytes.

This profile assigns no coordinates and computes no lengths, areas, energy,
material response, contact, or rest state. A valid cellulation does not establish
that the crochet construction has a geometric realization, is physically
reachable, or passes V4, V6, V7, V8, or any physical acceptance gate. This
builder is not an independent topology verifier.

## Preconditions and bounds

Input must be an admitted `PhysicalSemanticProjection`; target geometry,
landmarks, embeddings, and repair hints are absent from its interface. Only a
closed single-component/branch/yarn construction with a `MAGIC_RING`, cyclic
SC courses containing binary `PLAIN` (1:1), `INCREASE` (1:2), or `DECREASE`
(2:1) spans, and `CLOSE` is supported. Openings, extra operations, other stitch
families, ambiguous references, repeated IDs, inconsistent cycles, and course
cycles smaller than three are rejected.

The exact integer `max_vertices` and `max_faces` must each be positive and no
greater than 30,000 and 60,000 respectively. The implementation validates both
and computes required sizes before allocating output vertices or faces. Any
invalidity or exceeded budget raises an error and returns no partial complex.
With E construction events and C courses, ordering and build work are
O(E log E + C log C + V + F); memory is O(E + C + V + F). The projection digest
must match its exact canonical bytes. This internal interface assumes the
projection was admitted from validated IR; a hash is not an authenticity proof.

## Deterministic construction convention

The magic-ring anchor cycle is the first lower cycle, including every anchor.
Each course's ordered stitch bases must partition that entire lower cycle in its
anchored order, and its ordered tops must produce every upper-cycle vertex once.
For each stitch span, emit one lower advance for each base, then one upper
advance for each top. A lower advance from `b_i` to `b_(i+1)` at current `t_j`
emits `(b_i, b_(i+1), t_j)` and increments i. An upper advance at the current
`b_i` from `t_j` to `t_(j+1)` emits `(b_i, t_(j+1), t_j)` and increments j.
This explicit order fixes zipper
diagonals and opposing orientation on shared edges; it is a modeling convention.

Only the initial anchor cycle and terminal top cycle are capped, each by a fan
rooted at its first existing vertex. The lower cap is reversed against the first
annulus boundary, while the
terminal cap is oriented against the last annulus boundary. No virtual vertex
or geometry-dependent choice is introduced.

## Identity and limitations

The canonical payload includes the profile, `TOPOLOGY_ONLY`, projection SHA-256,
rule ID `cyclic-span-zipper-fan-caps/1`, sorted vertex IDs, and ordered oriented
faces. Its digest is domain-separated by profile, projection hash, and rule ID.
Target/provenance/color fields excluded by the physical projection cannot affect
the output. The fan caps can be poor geometric choices, and a combinatorially
closed oriented sphere can still be impossible or unsuitable for crochet
geometry. Those questions require separate, independently specified work.

## API inspection boundary

API 1.0 `inspect_closed_surface_cells` accepts exactly DesignSpec, resolved
MaterialProfile and CrochetIR. It validates source artifacts and creates the
target-free physical projection itself; clients cannot supply projections,
claimed hashes, target meshes or model/budget overrides. The response retains
`TOPOLOGY_ONLY`, `NOT_VERIFIED` and `UNTESTED`. Generic CLI `request` and durable
jobs share this boundary. This operation does not execute or pass V4/V6 and does
not replace the existing open-quad physical prototype.
