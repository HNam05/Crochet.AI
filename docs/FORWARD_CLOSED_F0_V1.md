# Closed SC F0 execution contract

Profile `FORWARD_CLOSED_F0_V1` extends the earlier diagnostic profiles without
changing their behavior or claiming measured constitutive parameters.

## Recipe

Exact keys: `profile`, `closed_recipe`, `shell_parameters`, `contact_parameters`,
`solver_parameters`. The closed recipe is the complete previously admitted
`FORWARD_CLOSED_MECHANICS_PROTOTYPE_V1` recipe. Its unloaded document describes
elastic preparation; its outer declared pressure supplies loading. Shell terms
use explicitly declared uniform corner-rest angle and shear stiffness (N mm),
signed rest dihedral and bending stiffness (N mm), all HYPOTHESIS. Surface contact
uses separately declared activation distance, minimum clearance, stiffness
(N/mm), provenance and a cumulative pair budget. No defaults or target fields.

Solver parameters: version `1.0.0`, `initialization_rule`
`CANONICAL_LABEL_SINE_PERTURBATION_V1`, `start_count` 2 to 4,
`perturbation_mm` positive, and integer `seed` in [0, 4294967295]. Per-start
iterations/evaluations/trials and owned convergence tolerances are those explicitly
bound by the closed recipe. One bounded elastic preparation is separate work;
every complete objective callback is counted. Contact's declared work budget is
cumulative across starts and attempted steps, not silently reset per trial; it
must not exceed the bound config contact-pair budget. The inner config
`max_initializations=1` applies only to elastic preparation; the outer full-F0
`start_count` is the explicit exact initialization budget and every declared
start is required. `max_initialization_vertices` applies to every start, with
admission enforced by preparation before allocating that many coordinates.
No linear solver is called; `max_linear_iterations` is NOT_APPLICABLE.
Initial gauge normalization is followed by certified linear optimizer paths;
trial endpoints are not separately rotated, which would alter the certified
linear path.

## Numerical execution

Construction cells, stretch/rest terms and initialization depend only on the
physical semantic projection and material/recipe. Additional starts perturb the
canonical label-ordered coordinates under a recorded fixed arithmetic rule.
There is no target-informed primitive, coordinate, volume bound or best start.

The objective combines stretch, purse strings, corner shear, signed-dihedral
bending, declared pressure and piecewise-smooth contact repulsion. Forces are
their negative gradients. Closest-feature ties have a deterministic subgradient;
this does not establish a differentiable material law at feature switches.

Every accepted Armijo step has a full-interval contact/nondegeneracy certificate
under the contact contract, including actual adjacent shared-simplex semantics.
Static contacts outside declared adjacency or below the hard minimum clearance
reject the state. Inconclusive certificates cause backtracking; they are not a
proved collision. No temporal sample is treated as continuous-path proof.

At each initialization and final mode comparison, rigid gauge removes centroid translation and expresses coordinates in an
orthonormal frame of the first canonically ordered nondegenerate face. This
preserves shape and cannot register or fit to the target. A comparator may apply
only its separately declared rigid transform afterward.

Numerical convergence requires all owned force-residual, last accepted position
step and relative energy-change predicates across two repeated stationary
evaluations. An initially stationary state receives explicit repeat evaluations;
zero updates do not replace the force predicate. Every required start must
converge. Canonically gauged pairwise coordinate RMS must remain within the owned
mode-equivalence tolerance; materially different observed modes reject a unique
prediction. This bounded multistart rule does not prove global uniqueness.

## Evidence and status

Only `CONVERGED` exposes comparison-eligible predicted geometry. Other states
are `INVALID_MODEL_INPUT`, `DIVERGED`, `UNRESOLVED_COLLISION`,
`BUDGET_EXHAUSTED`, `NUMERICAL_FAILURE`, with geometry redacted, including nested
start records. Detailed counters, selected numerical policy, hashes, final
scalar terms and trial causes are retained. Independent convergence admission
must recompute residuals/contact and check the bound starts/criteria; a claimed
status or hash is insufficient.

CONVERGED is a numerical model outcome. Uniform stiffness/rest values, coarse
purse strings and repulsion remain HYPOTHESIS until dedicated identifying
fixtures support them. Overall physical status remains UNTESTED; calibrated
profile and holdout gates are independent. No production VERIFIED claim follows
from a diagnostic comparison or a numerically stationary hypothesis model.
