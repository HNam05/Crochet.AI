# Experimental adjacent triangle residual distance

This kernel reports exact minimum squared distance over point pairs where at
least one point is outside a declared, face-relative neighborhood of the
intended shared simplex. It is an experiment only: it does not alter the frozen numerical
geometry profile, V0 contact policy, verification gates, or any `PASS` result.

Callers must supply an exact rational `lambda_value` with `0 < lambda < 1`; there
is deliberately no default or calibration claim. Coordinates are exact
`Fraction` values or finite binary64 values interpreted as their exact rational
values. The declared one-vertex or two-vertex identity correspondence must have
exactly matching coordinates. Degenerate triangles, malformed indices, and
three shared vertices are rejected.

For a shared edge, barycentric coordinates are named so that `c` is the
coefficient opposite the shared edge. The retained region is the closed set
`c >= lambda` in each face. For a shared vertex with coefficient `a`, the
retained region is the closed set `b + c >= lambda`, equivalently
`a <= 1 - lambda`. Each retained polygon is triangulated exactly. The compared
set is `(R_A x B) union (A x R_B)`, where `A` and `B` are the original faces and
`R` is the closed complement of the open exclusion region. This requires
`pieces(R_A) * 1 + 1 * pieces(R_B)` exact triangle-pair evaluations. The count
is checked against explicit positive integer `max_piece_pairs` before any
distance pair is evaluated.

Before clipping, exact `triangle_relation` checks the original triangles. Any
intersection witness outside the declared shared simplex, including extra
point/segment contact, and any positive-area overlap is rejected. Thus the zone
never excuses unintended contact. Successful results contain the exact squared
distance plus immutable `EXPERIMENTAL` status, zone version, entity kind,
lambda, and evaluated pair count.

The only omitted pairs are those where both points lie in their respective
open exclusion zones. The closed retained sets make the minimum over the
included domain attained.

Lambda is dimensionless and face-relative. The result is not a millimetre tube,
physical clearance, thickness model, or retessellation-invariant surface
distance. Changing face shape or triangulation changes the retained region.
This standalone kernel has no acceptance threshold, physical calibration, or
claim of suitability for manufactured or textile contact decisions. The
versioned `inspect_v0_mesh_v2` operation consumes it through a source-bound
wrapper and applies numerical profile 2's immutable threshold; the kernel's
own result remains experimental.
The edge fixture's independent exact oracle is `4 * lambda^2`; an asymmetric
face-height regression distinguishes a mixed-pair result of `1` from a
retained-retained-only result of `5`. A bounded property test checks the edge
oracle across rational lambda values and checks translation and scale
covariance. Tests also permute face vertices, swap face order, and exercise
alternate fan diagonals for the shared-vertex quadrilateral.

## Mesh-wide diagnostic

`diagnose_indexed_triangle_mesh_adjacent_residual` re-decodes the complete source
and recomputes exact topology, nondegeneracy and ordering; no caller-supplied
intermediate report is trusted. It enumerates every unordered face pair,
including nonadjacent pairs charged to the enumeration budget. For adjacent
pairs, it checks aggregate predicted distance work (two primitive pairs per
shared edge, four per shared vertex) before the first residual kernel call.
The explicit lambda bit limit bounds numerator and denominator lengths.

Results retain exact squared millimetre distances per pair, source/ordered
index maps, source vertex identities, algorithm versions, ordering/topology
hashes, all budgets and a source-specific diagnostic hash. Unexpected original
contact fails with the offending ordered face pair and returns no partial
report. Nonadjacent distances are deliberately not part of this experiment.
It still supplies neither a clearance threshold nor complete V0 acceptance.
