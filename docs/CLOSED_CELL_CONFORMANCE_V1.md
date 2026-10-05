# Closed cell source conformance V1

`CLOSED_CELL_CONFORMANCE_V1` independently verifies the existing
`cyclic-span-zipper-fan-caps/1` convention against validated CrochetIR.
It must not import the cell builder, physical projection, solver or their
extraction/triangulation helpers. The convention is unchanged. This is an
exact combinatorial mapping proof, not a material model or geometric embedding.

## Boundary and scope

The internal verifier receives transport-admitted CrochetIR, its populated
SemanticValidator registry, the supplied cell payload, and expected projection
and cell digests from the orchestrator. It semantically validates and hashes
the source itself. API clients cannot supply payloads, digests or trusted proof.
Only one component, branch and yarn, no openings, MAGIC_RING then cyclic binary
SC PLAIN/INC/DEC courses then CLOSE are supported. Each cycle has at least three
vertices. Course bases partition the entire preceding anchored cycle in order;
tops define the next cycle. Wider valid constructions return NOT_APPLICABLE.
Malformed source, payload or budgets produce no partial proof.

Limits are exact positive integers (booleans excluded): at most 30,000 vertices,
60,000 faces and 30,000 construction events. Referenced source tables are bounded
before semantic hashing. Internal callers must also preserve the API's transport
admission limits; these parameters are not a universal JSON parsing budget.
All source and surface identifiers have at most 128 ASCII characters.
There are no numerical tolerances or coordinate dependencies.

## Independent predicates

The source event sequence, course order, base and top IDs and frontier bindings
are authoritative. The cell vertices must equal exactly the sorted union of
ring anchors and produced tops, with no borrowed or omitted vertex.
Each face is inspected at its declared rule position; expected mesh arrays are
not constructed by invoking or replaying the builder's helpers.

For a source stitch with base prefix i and top prefix j in a band (B,T), each
base offset k requires the oriented face `(B[i+k], B[i+k+1], T[j])`.
Each top offset k requires `(B[i+base_arity], T[j+k+1], T[j+k])`.
Cycle indices wrap modulo their corresponding cycle lengths. These predicates
bind triangles to explicit stitch references, including both tops of INC and
both bases of DEC. Lower-advance slots precede upper-advance slots for each
stitch. Bands follow canonical course order. The initial reversed cap requires
`(B[0], B[k+1], B[k])`; the final forward cap requires
`(T[0], T[k], T[k+1])`, for k=1 through length-2.
All face slots must be accounted for exactly once, in the existing declared
face order and orientation. Sorting or repairing the submitted surface is
forbidden. The verifier checks lifecycle closure and complete event coverage.

The cell envelope must have exactly its documented keys/profile/status/rule,
the matching projection digest and a matching recomputed cell-content digest.
The proof binds canonical source, projection and cell digests; integrity links
do not authenticate arbitrary internal caller claims. Result JCS and SHA-256
use a separate conformance domain and exclude telemetry.

## V4 eligibility

Supported closed amigurumi V4 may PASS only when semantic frontier checks,
independent manifold/Euler/Betti checks and source conformance all pass, and
DesignSpec component/boundary requirements match. Unsupported construction or
missing proof stays INDETERMINATE; a mismatched generated mapping fails V4.
Passing V4 does not pass V5-V10 or change physical status from UNTESTED.
Hand-authored minimal source/face fixtures and topology-preserving diagonal
mutations are required, so producer output is not the only oracle. A valid
sphere using wrong source vertices must fail, even with refreshed hashes.
