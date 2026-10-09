# Geodesic Surface Draft Solver V1

## Status and scope

`GEODESIC_DRAFT_SOLVER_V1` is a bounded research producer for a complete
single-color, closed single-crochet draft on an independently admitted,
closed genus-zero triangle mesh. It emits canonical CrochetIR only after the
existing closed-schedule compiler and semantic validator accept the complete
schedule. A successful producer result is `CANDIDATES_EMITTED`, with
`verification_state: NOT_VERIFIED`, `physical_status: UNTESTED`, and
`comparison_eligible: false`. It is not an independent geometry, stitchability,
or physical verification result.

The solver uses target mesh geometry during proposal generation. That data is
not passed to the forward simulator. This implementation does not create
branches, split/join frontiers, seams, or topology operations beyond the
compiler's closed schedule.

## Input binding and anchors

The solver call supplies an exact source mesh byte string and a strict
versioned configuration plus explicit compiler provenance. The caller-owned
configuration's `parameter_profile_id` and `random_seed` must equal the
corresponding DesignSpec solver options. The seed is bound and recorded for
reproducibility but is not consumed because this solver uses no random choices.
`GEODESIC` must appear in `allowed_solver_families`; otherwise the result is
`NOT_APPLICABLE` before V0 or contour work. `max_candidate_evaluations` must
permit the single candidate this producer can emit.
`CompileProvenance.source_snapshot_sha256` binds the implementation snapshot;
it is never repurposed as the target-mesh digest. Its commit must match the
strict configuration's `software_commit`. Geodesic settings are recorded as
prefixed compiler parameters, while V0 work settings remain in the report.
The source mesh SHA-256 must match `source_mesh_sha256`; both pole indices name
vertices in that exact byte string. The solver checks index range and
distinctness, then maps them only through the source-to-normalized vertex map
returned by `inspect_v0_closed_mesh_v2`. Both source and normalized indices and
the V0 evidence/hash bindings are included in a successful report. The source
mesh's byte limit is checked before JSON parsing.

The end pole must be the unique farthest vertex from the start pole under the
computed edge graph distances. No coordinate-axis heuristic selects either
anchor. Material response selection is independently explicit by tension
profile, fabric state, stitch type, and cyclic course mode. Target dimensions
do not determine the material gauge.

The V0 admission is followed by an independent combinatorial topology audit.
The required Betti numbers `(1, 0, 1)` admit a connected, closed genus-zero
surface. Other topology fails as `NOT_APPLICABLE`.

## Distance field and contour construction

The graph is the normalized mesh's undirected one-skeleton. Each edge weight is
`math.hypot` of the three binary64 endpoint-coordinate differences, rounded to
binary64 by that operation. Dijkstra sums those represented edge lengths as
exact `Fraction` values. Thus arithmetic and tie behavior are deterministic
for the admitted bytes, but the graph metric is only an approximation to
continuous surface geodesic distance. The method label is
`EDGE_GRAPH_DIJKSTRA_PL_CONTOURS_V1`; no Heat Method or exact-surface
geodesic claim is made.

Let `D` be the graph distance from start to end and `p_c` the selected
effective course pitch in millimetres. The number of intervals is nearest
integer to `D / p_c`, with exact half ties rounded down. The solver requires at
least two intervals and at most the configured maximum. Interior levels are
uniformly placed at `D * i / intervals`, for `i = 1 .. intervals-1`. This is
an adaptive interval count, not a joint optimization of level positions.

For each level, every triangle is scanned. A level equal to any graph vertex
distance is rejected; the implementation does not snap or perturb it. A
strictly crossed edge is interpolated at the exact rational parameter
`(level-d0)/(d1-d0)` using the exact represented vertex coordinates. Each
regular triangle contributes zero or two crossings. The edge-crossing
adjacency must be exactly one connected cycle with degree two at every node.
Open, multiple, or branched contours fail closed. Polygon segment lengths are
computed from exact rational squared lengths and rounded by square root to
binary64; the reported perimeter is the exact sum of those represented segment
lengths.

These checks certify a single polygonal contour of the piecewise-linear graph
field on the admitted triangulation. They do not certify a contour of the
continuous geodesic distance field or invariance under remeshing.

## Course counts and CrochetIR

Each contour perimeter `L_i` and the selected effective stitch pitch `p_s`
form the count-search input in millimetres. A configured finite count window
is centered on nearest integer to `L_i / p_s`. The existing two-pass global
count DP chooses counts jointly across those contours under explicit
increase/decrease caps and work budgets. This reuses only the generic integer
count search; no analytic target profile or analytic solver result is reused.

The closed-schedule compiler is invoked with `GEODESIC_CLOSED_SC_V1`, so the
CrochetIR identifies the `GEODESIC` family and
`geodesic-graph-distance-closed-sc` generator. Its derivations use
`GEODESIC_COUPLING` and bind to the domain-separated solver-parameter hash,
which includes the DesignSpec profile and seed. The IR also records the
DesignSpec seed and one consumed candidate evaluation. The compiler emits a
full CrochetIR with a magic-ring start, cyclic courses, and closure. It is then
semantically validated against the same DesignSpec and MaterialProfile. No
partial CrochetIR is returned on failure. This positive prototype is limited
to a single uninterrupted closed
SC sequence; it makes no seam-optimality, branching, seamlessness, or
constructibility claim.

## Budgets, units, and failure behavior

All configuration fields are required and unknown fields are rejected. DesignSpec
solver-family, profile, seed, and candidate-budget applicability is checked
before mesh admission or solver work. The configuration bounds source byte size
and V0 work, graph edge-build visits,
Dijkstra heap pops and relaxation attempts, level intervals, triangle scans,
count values, DP states, transition evaluations, and total emitted stitches.
Each work counter is reported. The mesh vertex/face maxima are supplied to V0
admission; the topology audit is bounded by those admitted mesh sizes. No
implicit geometric epsilon, level snap, or tolerance is used. Distances and
perimeters are in millimetres; squared contour residuals are in mm².

Expected failure statuses include:

- `INVALID_SOLVER_INPUT` for malformed input, invalid anchors, or mismatched
  mesh/config bindings;
- `NOT_APPLICABLE` for failed V0 admission, disconnected graph, non-genus-zero
  topology, or an end anchor that is not uniquely farthest;
- `NUMERICAL_FAILURE` for degenerate or non-regular contour states;
- `SEARCH_BUDGET_EXHAUSTED` when a declared work bound is reached;
- `NO_FEASIBLE_CONSTRUCTION` when the fully bounded count proposal has no
  feasible count schedule;
- compiler errors propagated without emitting a candidate.

All failures set `candidate_crochet_ir` to null and preserve
`NOT_VERIFIED`/`UNTESTED` status. A future extension needs explicit
regular-level event handling before supporting branches, joins, openings, or
multiple components.
