# Closed closure and pressure prototype V1

Profile: `FORWARD_CLOSED_MECHANICS_PROTOTYPE_V1`. This experimental producer
extends closed shaped SC elastic preparation. It is not independent V6 evidence,
calibrated closure physics or an authoritative reconstructed crochet surface.

## Input and scope

`run_closed_forward_prototype` accepts the same source artifacts and `forward_run`
field as `inspect_shaped_forward_model`. Source admission validates DesignSpec,
MaterialProfile and CrochetIR. Only the PhysicalSemanticProjection, material and
explicit recipe reach mechanical execution. No target, source embedding, raw
coordinates, seed, color or generator metadata enters its objective.

The recipe has exactly four fields:

- `profile`: the profile above.
- `elastic_recipe`: the complete `FORWARD_SHAPED_ELASTIC_DIAGNOSTIC_V1` recipe.
  Its unloaded loading document declares the elastic preparation; the outer
  pressure document explicitly superposes the load for this profile.
- `closure_parameters`: `schema_version: "1.0.0"`, `status: "HYPOTHESIS"`,
  nonempty `provenance_id`, nonnegative `ring_rest_perimeter_mm` and
  `close_rest_perimeter_mm`, positive `ring_stiffness_n_per_mm` and
  `close_stiffness_n_per_mm`.
- `pressure_loading`: `schema_version: "1.0.0"`, `status: "USER_DECLARED"`,
  nonempty `loading_profile_id` and `provenance_id`, nonnegative
  `pressure_n_per_mm2`, positive `volume_limit_mm3` greater than the explicitly
  owned `volume_orientation_epsilon_mm3` tolerance.

All numbers must be native finite nonboolean I-JSON numbers. Unknown fields and
versions fail closed. There are no inferred closure rest lengths, coefficients,
pressure or volume limits. Immutable recipes are re-admitted and byte/hash bound.
Canonical schemas and the earlier unloaded forward profiles remain unchanged.

Supported construction: the existing closed single-component, single-branch,
single-yarn CYCLIC SC subset with PLAIN/INCREASE/DECREASE and exactly MAGIC_RING
and CLOSE. The independently audited oriented closed cell surface supplies faces;
ring anchors and the final consumed ordered frontier supply closure cycles.

## Energy and forces

For each closure cycle, `P` is its cyclic perimeter in mm, `P0` its declared rest
perimeter and `k` its declared stiffness in N/mm:

```
d = max(P - P0, 0)
E_closure = k * d^2 / 2          # N mm
T = k * d                      # N
```

Every edge a to b contributes `T * (x_b - x_a) / |x_b - x_a|` to the force on a
and the opposite to b. Inactive strings exert zero force and never push outward.
Zero or nonfinite edge lengths fail explicitly. This is a coarse purse-string
hypothesis; it does not model knots, individual closure yarn or cap bending.

For outward-oriented faces, signed volume uses a common deterministic reference
and compensated summation of scalar triple products divided by six. Volume must
exceed the declared orientation epsilon and remain at most the declared volume
limit, including at zero pressure. Pressure potential is `-p * V` in N mm.
Each face adds `p * cross(b-a, c-a) / 6` to each of its three vertex forces.
The complete objective adds existing elastic, closure and pressure energies and
their negative gradients. Rigid translations/rotations introduce no target frame.

Constant positive pressure can make this quadratic-spring model unbounded under
expansion: pressure grows cubically with scale. The independent volume limit is
an operational divergence guard, not an equilibrium volume, target constraint or
calibrated acceptance threshold. Global positive volume and closed manifold
topology do not exclude local inversion, degenerate cap triangles or intersection.

## Bounded numerical policy and result

Admission limits: one initialization, at most 2,048 vertices, 4,096 faces,
8,192 springs, 128 optimizer iterations, 512 complete objective callbacks and
32 line-search trials per iteration. Existing Armijo constants are recorded and
the forward-input hash binds budgets and owned tolerances. One bounded elastic
preparation energy evaluation is recorded separately. All complete objective
callbacks, including repeated points and failed trials, count against the declared
energy budget. No final objective evaluation occurs outside it.

Recoverable invalid volume or collapsed closure trial edges cause backtracking;
an invalid current evaluation or nonfinite arithmetic causes NUMERICAL_FAILURE.
Budget and line-search failures retain scalar diagnostics and counters but redact
coordinates and faces. No last-iterate or nested initial geometry is published.

Only `EXPERIMENTAL_FORCE_BALANCED` may publish debug coordinates. Its criterion
is the caller's owned force residual, not certified convergence. Position/relative
energy/mode-equivalence/contact tolerances and linear/contact budgets remain bound
configuration but do not imply completed checks. No multistart is performed.
Every bundle remains `comparison_eligible: false`, `NOT_VERIFIED`, `UNTESTED`,
V6 `NOT_RUN`. The result binds recipe/projection/material/cells/preparation hashes,
energy decomposition, perimeter/tension/volume diagnostics, policy and work trace.

## Local delivery

CLI and isolated jobs use the versioned backend operation. The loopback prototype
provides CSRF-protected `POST /api/forward/closed` with exactly
`{"project_id": "<64 lowercase hex characters>", "forward_run": <recipe>}`.
It reads the saved source artifacts and checks retained proposal integrity; it
does not update the pattern, preview, project, session or physical evidence.
The assembled backend request remains subject to byte/node/depth limits.

Outstanding: measured closure and cap material models, shaped shear/bending,
contact response and path safety, multistart, independent V6-V8/V10 and physical
calibration. English pattern/PDF rules and physical-trial gates are unchanged.
