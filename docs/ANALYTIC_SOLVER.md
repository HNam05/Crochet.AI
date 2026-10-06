# Analytic Solver for Surfaces of Revolution

## Status

**FUTURE:** this is an implementation contract for a later milestone. No production analytic solver is delivered by the bootstrap.

The claim labels from [`SOLVER_ARCHITECTURE.md`](SOLVER_ARCHITECTURE.md) apply here.

## Applicability

The analytic solver targets amigurumi-like surfaces described by, or deterministically fitted to, a surface of revolution. Examples include spheres, cylinders, cones, ellipsoids, hourglass profiles, and tapered bodies.

Required preconditions are:

- a `DesignSpec` `ANALYTIC_SHAPE` with the exact primitive parameter contract in [`DESIGN_SPEC.md`](DESIGN_SPEC.md); for `SURFACE_OF_REVOLUTION`, a non-zero declared axis and a content-addressed, ordered non-negative radial profile `r(s)` parameterized by meridional arc length `s` in millimetres;
- a finite interval `s in [0, L]` with explicitly classified ends: closed pole, intentional opening, or interface to another construction;
- no handle, branching region, or level-set component change inside the region;
- a resolved `MaterialProfile` whose measurement conditions apply to the selected stitch family;
- construction constraints that can be expressed by the supported base/top arities;
- a complete numerical profile and deterministic work budget.

An axis fit to a mesh is a solver-private analysis. If the fit residual exceeds the declared applicability limit, the solver returns `NOT_APPLICABLE`; it does not force the mesh into a rotational model.

## Normative analytic target decoding

The solver accepts an analytic target only after V1 semantic validation. It consumes the following deterministic representation; it must not reinterpret labels, infer missing dimensions, or replace a profile with a fitted curve.

| Primitive | Deterministic target construction |
| --- | --- |
| `SPHERE` | Centre is `origin_mm`; radius is the resolved `RADIUS` measurement. |
| `CYLINDER` | Base-plane centre is `origin_mm`; axis is the coordinate-frame up axis; radius and axial extent are resolved from `RADIUS` and `AXIAL_LENGTH`. |
| `CONE` | Base-plane centre is `origin_mm`; axis is the coordinate-frame up axis; radius decreases linearly from resolved `BASE_RADIUS` to zero over resolved `AXIAL_LENGTH`. |
| `ELLIPSOID` | Centre is `origin_mm`; the equatorial plane is normal to the coordinate-frame up axis; semiaxes are resolved `EQUATORIAL_RADIUS` and `POLAR_RADIUS`. |
| `SURFACE_OF_REVOLUTION` | Axis origin is `origin_mm`; axis direction is the normalized declared `axis_direction`; `r(s)` is the piecewise-linear interpolation of the content-addressed ordered profile samples. |

For a `SURFACE_OF_REVOLUTION`, the profile hash covers the profile payload excluding the hash field, serialized with `SURFACE_OF_REVOLUTION_PROFILE_CANONICAL_JSON_V1`. Sample `j` must have `sample_index = j`; `s_0 = 0`; `s_(j+1) > s_j`; all radii are non-negative; and the final `s` equals the resolved `MERIDIONAL_LENGTH` within the versioned `arc_length_abs_tolerance_mm`. A `CLOSED_POLE` end must be within `radius_zero_tolerance_mm` of zero. An `INTENTIONAL_OPENING` must resolve to the corresponding DesignSpec opening requirement. Failure is `INVALID_SOLVER_INPUT`, not interpolation or endpoint repair.

DesignSpec 1.2 additionally supports authoritative radius/axial coordinates via
[ANALYTIC_COORDINATE_GENERATION_V1](ANALYTIC_COORDINATE_GENERATION_V1.md).
For its admitted simple closed pole-ended subset, derive meridional sample
positions using the separately versioned bounded numerical policy; preserve
axial signs and explicit caps. AXIAL_LENGTH binds full extent, not arclength.
Older radial-profile decoding remains unchanged and does not establish axial
embedding. Independent coordinate replay and geometry/physical gates remain open.

The profile is design intent and must never encode final stitch quantities, per-course counts, or shaping placement. The solver's course samples, integer counts, fitted mesh profile, and interpolator cache are solver-private diagnostics, not part of `DesignSpec` or canonical CrochetIR.

## Inputs and outputs

In addition to the common invocation contract, this solver receives:

- a validated analytic primitive decoded as above, or solver-private fitted profile samples `(s_j, r_j)` in millimetres from an eligible mesh;
- start/end construction policy and allowed course mode, cyclic or linear;
- allowed canonical stitch and shaping operations;
- integer bounds on course counts and shaping events;
- placement constraints such as a minimum angular separation from recent shaping events.

It emits complete CrochetIR candidates or one of the structured terminal outcomes in `SOLVER_ARCHITECTURE.md`. Fitted axes, target-profile samples, DP tables, and angular heuristics remain non-canonical diagnostics.

## Course placement

Let `p_c > 0` be `effective_course_pitch_mm`. Candidate course positions `s_i` are selected along meridional arc length, not along the axis coordinate. The initial construction policy determines the first usable course and whether a pole is represented by a `MAGIC_RING` macro/anchor.

The nominal spacing relation is:

```text
s_(i+1) - s_i approximately p_c
```

The implementation must choose the complete position sequence jointly so that endpoint handling and accumulated spacing residual are explicit. Repeatedly adding a rounded axial increment is not permitted.

At course `i`, the target circumference is

```text
C_i = 2 * pi * r(s_i)  [mm]
```

and the real-valued nominal stitch count is

```text
q_i = C_i / p_s
```

where `p_s > 0` is `effective_stitch_pitch_mm`. `q_i` is a proposal center, never an authoritative rounded count.

**HYPOTHESIS:** effective stitch/course pitch measured on calibration specimens is sufficient for useful first-order course proposals. Independent forward simulation and physical calibration must test this.

## Global integer model

The solver chooses an integer sequence `n_0, ..., n_(m-1)` globally. For a transition from `n_i` available bases to `n_(i+1)` top locations using ordinary 1-to-1 stitches, SC-style increases, and SC-style decreases, let:

- `S_i` be the number of `(base_arity=1, top_arity=1)` operations;
- `I_i` be the number of `(1, 2)` increases;
- `D_i` be the number of `(2, 1)` decreases.

Exact accounting requires:

```text
n_i       = S_i + I_i + 2 * D_i
n_(i+1)   = S_i + 2 * I_i + D_i
n_(i+1) - n_i = I_i - D_i
S_i, I_i, D_i are non-negative integers
```

**PROVEN / FORMAL:** any transition that cannot satisfy these equations and all declared operation limits is unreachable in this V1 operation set.

For the first implementation, a transition does not mix increases and decreases: `I_i * D_i = 0`. This is an **ENGINEERING DECISION** that removes redundant local reshaping from the initial search. A future formulation may relax it only with an explicit geometric need and verifier coverage.

Additional hard transition constraints include:

- every base location is referenced exactly according to its operation's base arity;
- no two decreases overlap a base location;
- increases/decreases respect per-course integer limits from `SolverRunConfig`;
- the ordered cyclic or linear correspondence does not cross itself combinatorially;
- terminal poles/openings follow their declared closure policy;
- no count is clamped or silently repaired.

## Dynamic program

A DP layer corresponds to a candidate course position. A state minimally contains:

```text
(course_index, stitch_count, recent_shaping_signature, angular_phase_class)
```

The recent-shaping signature covers the configured stacking-history window. An edge represents one exact reachable count transition plus one deterministic event-placement class. Backpointers reconstruct the complete course and operation sequence.

Candidate counts for a layer come from an explicit integer interval around `q_i`, intersected with DesignSpec and construction bounds. The interval is a search-domain choice, recorded in provenance. Excluding a count through that window means the algorithm is not globally complete outside the window.

The DP cost is a versioned lexicographic vector, for example:

```text
(
  maximum_course_circumference_residual_mm,
  sum_course_circumference_residual_squared_mm2,
  shaping_stack_violation_count,
  shaping_stack_proximity_penalty_rad,
  abrupt_transition_count,
  canonical_transition_trace
)
```

This generation cost proposes candidates only. It is not the hard geometry gate and cannot certify shape fidelity.

## Increase/decrease placement

For each chosen transition, shaping events are placed around the ordered course with a deterministic balanced-spacing algorithm. Candidate angular phases are evaluated jointly across the configured history window.

Required placement rules are:

- distribute events as evenly as the integer course permits unless a declared landmark/interface requires otherwise;
- minimize direct vertical stacking across nearby courses after satisfying exact count constraints;
- preserve cyclic order and orientation;
- break exact ties by canonical base-location ID;
- record placement phase and history-window parameters.

The no-stacking term is a construction-quality heuristic. It is not a theorem of physical stability.

## Budgets

The following positive-integer budgets are mandatory and measured as deterministic work counts:

| Parameter | Unit | Exhaustion point |
| --- | --- | --- |
| `max_course_hypotheses` | course-position sequences | Before adding another complete position sequence |
| `max_count_values_per_course` | integer count states per layer | Before expanding a wider count window |
| `max_dp_states_per_course` | retained states | During deterministic state pruning |
| `max_transition_evaluations` | DP edges evaluated | Before evaluating the next ordered edge |
| `max_placement_variants_per_transition` | angular placement classes | Before generating another placement |
| `max_emitted_candidates` | complete CrochetIR candidates | Before compiling another path |

Reaching any budget before the declared search domain is complete returns `SEARCH_BUDGET_EXHAUSTED`, together with the counter, configured limit, completed search prefix, and any already emitted candidates. It must not return `NO_FEASIBLE_CONSTRUCTION` solely because a budget was reached.

## Numerical tolerances

All values are required in the run's versioned numerical profile; bootstrap defines no hidden production values.

| Tolerance | Unit | Purpose and rationale | Owner / validation path |
| --- | --- | --- | --- |
| `axis_fit_rms_limit_mm` | mm | Applicability limit for a fitted rotational axis; separates model mismatch from floating-point noise | Analytic solver / rotational benchmark suite and later physical calibration |
| `arc_length_abs_tolerance_mm` | mm | Stops deterministic profile integration when the absolute quadrature estimate stabilizes | Geometry kernel / convergence study on analytic profiles |
| `radius_zero_tolerance_mm` | mm | Classifies a profile endpoint as a pole without relying on exact floating-point zero | Analytic solver / sphere, cone, thin-neck adversarial fixtures |
| `profile_monotonic_segment_tolerance_mm` | mm | Distinguishes numerical jitter from a true local radial reversal during segment decomposition | Analytic solver / perturbed-profile metamorphic tests |
| `angular_tie_tolerance_rad` | rad | Makes equal-cost placement ties deterministic | Analytic solver / rotation and canonicalization tests |

These tolerances do not define target-shape acceptance. Geometry thresholds belong to verification and are evaluated on independently reconstructed geometry.

## Complexity

Let `M` be course layers, `W` retained count/history states per layer, `P` reachable predecessor/placement variants per state, and `K` emitted paths.

- DP time is `O(M * W * P)` under the configured bounds.
- DP working memory is `O(W)` if only adjacent layers are retained, plus `O(M * W)` backpointer storage when reconstructing multiple paths.
- Candidate compilation is linear in emitted CrochetIR operations.

`P` can grow combinatorially if arbitrary event layouts are enumerated. The placement-class budget is therefore part of the mathematical contract, not an implementation detail.

## Rejection and failure states

- `NOT_APPLICABLE`: failed rotational fit, topology change, branch/handle, unsupported boundary, or incompatible material conditions.
- `NO_FEASIBLE_CONSTRUCTION`: complete declared DP domain has no exact reachable path.
- `SEARCH_BUDGET_EXHAUSTED`: any deterministic work counter stops an incomplete search.
- `NUMERICAL_FAILURE`: profile integration, fit, or conditioning misses its convergence contract.
- `INVALID_SOLVER_INPUT`: missing pitch, invalid units, non-positive pitch, missing tolerance, or contradictory bounds.
- Candidate-specific rejection diagnostics include unreachable course transition, uncloseable terminal frontier, and unsupported stitch arity.

## Known limitations

- **HYPOTHESIS:** circumference residual is a useful candidate-generation proxy, but it ignores stuffing, anisotropic deformation, local curvature, and crocheter technique.
- Axis-fitting ambiguity for near-spherical targets can change course orientation while leaving similar residuals.
- Abrupt narrow necks can require transitions that are mathematically reachable but physically poor; verification must reject them if the reconstructed geometry fails.
- A global count optimum can still have locally awkward shaping placement.
- The formulation does not support branches, handles, garments, or arbitrary lace topology.
