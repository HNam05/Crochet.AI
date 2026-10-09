# Forward surface contact V1

## Scope and evidence

`FORWARD_SURFACE_CONTACT_V1` is a target-free computational contact hypothesis
for an immutable closed, consistently oriented triangle surface. Its API accepts
only indexed surface topology, trial coordinates, explicit contact parameters,
and a caller-owned work counter. It has no target mesh, target correspondence,
raw CrochetIR, or target-derived initialization input. A `HYPOTHESIS` stiffness
in N/mm produces energy in N mm; neither it nor the declared distances are
physically calibrated. A successful path certificate is a mathematical
continuous-step predicate under exact represented coordinates, not physical or
V6 acceptance.

## Static energy and hard clearance

Input binary64 coordinates are converted to their exact rational values.
Preparation requires nondegenerate triangles, no coincident vertex records,
two oppositely directed incident faces per edge, and one cycle in every vertex
link. Preparation admits at most 2,048 vertices and 4,096 faces before building
topology maps, and rejects duplicate unordered faces. Thus boundary and
non-manifold topology fail closed. Every unordered face
pair is included if its exact, distance-expanded AABBs survive sweep-and-prune.
The x-axis active comparisons are charged before their y/z predicates; exact
pair predicates are separately counted. A box expanded by the activation
distance can add candidates but cannot omit a pair whose Euclidean distance is
below the activation distance. The same expansion also covers the smaller hard
minimum clearance.

For nonadjacent faces the kernel enumerates vertex-to-triangle projections and
all nine edge-to-edge closest points, with rational barycentric weights and a
deterministic exact-distance tie break. Exact triangle relation distinguishes
intersection from positive distance. For distance `d` in mm, activation `a` in
mm, and hypothesis stiffness `k` in N/mm, the per-pair term is

```text
E = 1/2 k max(a - d, 0)^2                 [N mm]
F_A = k max(a - d, 0) (q_A - q_B) / d    [N]
F_B = -F_A
```

The point forces are distributed to triangle vertices using the exact
closest-point barycentric weights. The hard `minimum_clearance_mm` is checked
before the soft energy; equality is admissible, strict shortfall is
`UNRESOLVED_COLLISION`, and zero distance is a collision. The force direction
is the negative energy gradient. Shared-edge and shared-vertex pairs are
classified exactly and their witnesses must lie in the actual shared simplex;
positive-area coplanar overlap and extra intersection are rejected. These
intentional shared entities receive no distance barrier.

## Continuous linear-path certificate

For a linear step, every triangle lies in the convex hull of its endpoint
vertices. Exact swept AABBs expanded by the hard clearance therefore include
every nonadjacent pair that could violate clearance. The broadphase also
accounts for pairs discarded by its y/z slab test; candidate and exact-predicate
counters are distinct. Pair budget is cumulative in the explicit
`ContactBudgetContext`, including across line-search trials.

For an included nonadjacent pair, let `d0` be its exact start minimum distance,
and let `mA` and `mB` be the maximum endpoint displacement of a vertex in each
triangle. For every `t` in `[0,1]`, the set-distance Lipschitz bound gives

```text
d(t) >= d0 - mA - mB.
```

The certificate uses a rational inward square-root bound for `d0`, outward
bounds for both motion magnitudes, each widened by at most eight binary64
`nextafter` steps and checked by exact squaring. It certifies clearance only if
the resulting lower bound is strictly greater than the declared gap. Failed
outward/inward conversion is `INDETERMINATE`.

For a vertex-adjacent pair, form the four signed vectors from the common vertex
to the two off-vertex points in each face. The exact nearest point to their
convex hull is enumerated over all nonempty simplices (at most four points).
Its vector is a fixed separating axis. Strictly positive dot products for all
four vectors at both endpoints imply strict separation for every linear
interpolation, since each dot product is linear in time. No verified axis means
`INDETERMINATE`. Before either adjacency proof, exact triangle relations at both
endpoints must have all witnesses contained in the declared common simplex;
`COPLANAR_AREA` and any extra point or segment are endpoint collisions.

For an edge-adjacent pair, use the shared edge endpoints and the two opposite
vertices. Their oriented tetrahedral determinant is a cubic polynomial in time.
Power coefficients are converted algebraically to degree-three Bernstein
coefficients; a strict common sign proves the four points never become
coplanar, hence the triangles intersect only in the shared edge. If that proof
fails, the dot product of the two oriented face normals is a degree-four
polynomial. Strictly positive Bernstein coefficients prove that any
coplanarity has the non-overlapping adjacent orientation. Otherwise the pair is
`INDETERMINATE`. These checks use exact polynomial coefficients; no temporal
sampling is treated as proof.

For exact power coefficients `c_i` of a degree-`n` polynomial,
`p(t) = sum(c_i * t^i)`, the converted Bernstein coefficient is
`b_k = sum(c_i * C(k,i) / C(n,i), i=0..k)`. The polynomial lies in the convex
hull of its Bernstein coefficients on `[0,1]`; therefore `min(b_k)` is a
conservative lower bound and a strictly positive minimum proves strict
positivity throughout the step. Coefficients and sign decisions remain exact
fractions.

Every moving triangle is guarded over the full step. Its normal is quadratic;
the degree-two Bernstein coefficients of `n(t) dot n(0)` give a conservative
lower bound `L`. Require `L > 0` and

```text
L^2 > MIN_AREA_VECTOR_MM2^2 * ||n(0)||^2
L^2 > MIN_TRIANGLE_QUALITY^2 * max_endpoint_edge_squared^2 * ||n(0)||^2.
```

Because each edge is linear, its squared norm is convex and is bounded above
on the interval by the larger endpoint value. The inherited guards
`MIN_EDGE_LENGTH_MM`, `MIN_AREA_VECTOR_MM2`, and `MIN_TRIANGLE_QUALITY` are
arithmetic stability guards owned by `forward_bending.py`, with its documented
scale-study limitation; they are not contact clearances or calibrated material
thresholds. Endpoint edge length and face-area guards are also checked exactly.

Any failed sign, unsupported shared topology, exact-arithmetic uncertainty, or
exhausted budget cannot produce `SAFE`. Results are `SAFE`,
`UNRESOLVED_COLLISION` (static or endpoint evidence), `BUDGET_EXHAUSTED`, or
`INDETERMINATE`; a trial line search must reject both non-safe path outcomes.

## Limits

The sufficient path tests intentionally return `INDETERMINATE` for safe paths
they cannot prove. The nonadjacent displacement bound can be conservative, and
edge-adjacent polynomial sign conditions can be inconclusive. The coefficient
is uncalibrated, no friction or yarn-scale contact is represented, and no
physical specimen evidence is implied. `SAFE` establishes only the stated
continuous linear-path clearance/topology predicate for the given exact
represented coordinates and admitted surface.
