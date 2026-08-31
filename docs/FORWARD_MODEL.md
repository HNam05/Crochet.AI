# Independent Forward Model

## Purpose and trust boundary

The forward model reconstructs predicted physical geometry from canonical construction data:

```text
CrochetIR + MaterialProfile + LoadingProfile + ForwardModelConfig
                              |
                              v
                       crochet graph
                              |
                              v
                  predicted physical geometry
```

**ENGINEERING DECISION:** the target mesh, target point cloud, target landmarks, target distance fields, solver correspondences, solver embedding, and target-derived loss function are forbidden inputs. They may not initialize, constrain, repair, stop, or select a simulation.

Target geometry becomes available only after simulation, in a separate comparison stage. This interface separation is required to avoid circular verification.

## Claims and maturity

- **PROVEN / FORMAL:** excluding target data from the simulator prevents direct optimization of simulated coordinates against that target. It does not by itself prove physical accuracy or full independence.
- **ESTABLISHED:** spring, bending, shear, contact, and pressure energies are standard coarse physical modeling concepts.
- **HYPOTHESIS:** a course-level anisotropic graph/spring model predicts crochet shape accurately enough for useful first verification.
- **FUTURE:** higher-fidelity shell and yarn/contact models.

No forward-model result is `PHYSICALLY_VERIFIED` without physical benchmark evidence.

## Strict input contract

Permitted inputs are:

1. a schema- and semantically-valid canonical `CrochetIR`;
2. a resolved `MaterialProfile` with measured stitch/course pitch and uncertainty;
3. a `LoadingProfile` containing independently declared loading such as gravity, support, and stuffing pressure or mass-model parameters;
4. a versioned `ForwardModelConfig` containing model version, numerical coefficients, deterministic initialization rule, solver tolerances, and work budgets.

All inputs and their content hashes are recorded. A configuration that needs a target-derived desired volume, target surface attraction, target landmark pin, or solver-provided target embedding is invalid.

Pressure or stuffing inputs must be measured, user-declared, or obtained from a calibration profile independent of the current target geometry. A target volume computed from the mesh is prohibited as a loading parameter.

## Physical-semantic projection

Before graph derivation, the simulator creates a versioned `PhysicalSemanticProjection` from a valid CrochetIR. This projection is the sole construction input to initialization, caching, numerical optimization, and simulation. Its profile is `FORWARD_PHYSICAL_SEMANTICS_V1`; its canonical bytes and domain-separated hash use the shared I-JSON/binary64/JCS contract in [`CANONICALIZATION.md`](CANONICALIZATION.md) after the projection's semantic array ordering.

The projection includes only physical construction semantics: stitch family/shaping/base-top attachment relations, construction-operation effects, executable event order, course form and membership, frontier and branch connectivity, declared openings/closures, and physical-yarn material bindings where they differ. Source entity IDs may be retained solely as stable graph labels. It excludes, rather than merely ignores:

- `design_spec_ref` and every DesignSpec identifier or hash;
- CrochetIR `derivations` and all solver/generator provenance, parameters, traces, budgets, and seeds;
- every `input_artifact`, in particular `TARGET_GEOMETRY` and `AUXILIARY_GEOMETRY` roles and their hashes;
- solver embeddings, target correspondences, target-derived losses, and target-derived initialization material;
- colors and localized/export-only labels unless a separately resolved material binding proves a physical property difference.

The projection does not carry the enclosing CrochetIR hash, since that hash may bind excluded provenance. Its cache key is exactly the projection canonical hash plus resolved MaterialProfile hash, LoadingProfile hash, and ForwardModelConfig hash. A change only to DesignSpec identity, target-role provenance, solver provenance, or target-derived seed material must therefore produce identical projection bytes and cannot perturb initialization, caching, or optimizer selection. The implementation must include adversarial tests for each of these changes.

Projection construction is deterministic and fail-closed. It rejects unsupported semantics, references that cannot be resolved, physical-yarn bindings that cannot be resolved, and an attempted projection/API payload containing an excluded field. Excluded data in the source CrochetIR is deliberately not read. It records only the projection hash and forward inputs in the simulator trace; the V10 provenance layer may bind the full CrochetIR and DesignSpec outside this trust boundary.

## Material-response resolution

Physical yarn identity is not a gauge-response identity. A CrochetIR yarn remains a physical construction source used for continuity, cut, attach, and color semantics. For each projected stitch, the forward model resolves a `MaterialProfile.calibration_responses` entry using:

```text
(stitch.stitch_type, course.form, requested_tension_profile_id, requested_fabric_state)
```

The resolved response supplies the separate course and stitch pitches and their uncertainty. Different stitch families or `LINEAR`/`CYCLIC` modes may resolve to different responses under the same physical yarn without a synthetic yarn transition or a CrochetIR redesign. A missing or multiply matching response is `INVALID_MODEL_INPUT`; the simulator must never borrow a nearby response, average families, or infer a response from yarn metadata.

V1 accepts one resolved MaterialProfile for every physical-yarn binding in a projection. If multiple physical profiles are needed, a future explicit material-registry input must map each physical-yarn binding to a content-addressed profile before projection; implicit selection by color, event order, or response ID is forbidden.

## Crochet graph derivation

The simulator deterministically lowers `PhysicalSemanticProjection` into a non-canonical physical graph. At minimum it distinguishes:

- attachment/top-loop locations as simulation vertices or constrained vertex groups;
- course-direction adjacency;
- course-to-course attachment adjacency;
- yarn-path adjacency;
- shaping groups with explicit base/top arity;
- joins, attachments, closures, openings, and branch interfaces;
- physical-yarn material bindings where material properties differ.

Derivation must not use solver-private target coordinates. Projection graph labels define stable ordering. The derived graph may be cached only by the physical-semantic projection, material, loading, and model-configuration hashes.

## F0 graph/spring model

Let each physical vertex have position `x_v` in millimetres. F0 minimizes a coarse energy

```text
E_total = E_course + E_wale + E_shear + E_bend
        + E_contact + E_pressure + E_boundary
```

subject to exact graph/topology constraints.

### Anisotropic stretch

- Course-direction rest lengths derive from `effective_stitch_pitch_mm`.
- Course-to-course, or wale-direction, rest lengths derive from `effective_course_pitch_mm`.
- Yarn-path/attachment constraints derive only from physical-semantic projection content and the selected forward-model calibration profile.

A representative spring term is

```text
E_edge = 0.5 * k_edge * (||x_u - x_v|| - l0_edge)^2
```

with `l0_edge` in mm and `k_edge` in N/mm, giving energy in N mm. Separate coefficient families preserve anisotropy. One scalar stitch size is forbidden.

### Shear and bending

Shear terms penalize deviation of local course/wale angles from model rest angles. Bending terms penalize discrete curvature or dihedral changes across adjacent cells. Rest angles and stiffnesses belong to a versioned calibration profile, not the target mesh.

### Contact and collision

Self-contact prevents graph/surface elements from passing through one another beyond the declared penetration tolerance. F0 may use a coarse repulsion/barrier and broad-phase collision structure. A simulation that retains unresolved penetration above the configured limit returns `UNRESOLVED_COLLISION`.

### Stuffing/loading

For a closed oriented surface, a pressure term may use

```text
E_pressure = -p * V(x)
```

where pressure `p` is in N/mm^2 and signed volume `V` is in mm^3. Both orientation validity and loading provenance are required. Open or non-orientable constructions cannot use this term without an explicit alternative model.

### Rigid-mode removal

Deterministic gauge constraints may fix translation and rotation without selecting a target shape. Anchors are chosen from projection graph labels under a versioned rule. Reported geometry may later be rigidly aligned to the target only in the comparison stage.

## Initialization and optimization

Initialization must be a deterministic function of the physical-semantic projection, resolved material, loading, and model configuration. Allowed examples are a canonical graph layout, a fixed analytic primitive chosen from projection topology, or multiple seeded starts generated by a recorded target-independent rule.

The numerical optimizer must record:

- implementation and model version;
- initialization rule and seed;
- arithmetic/linear-solver policy;
- iteration/evaluation counters;
- energy terms and residual traces;
- convergence and collision diagnostics;
- all tolerances and budgets.

The minimum-energy state is not assumed unique. If permitted starts converge to materially different states, the result reports multimodality and the robustness policy determines whether verification can proceed.

## Result contract

`ForwardSimulationOutcome.status` is exactly one of:

| Status | Geometry eligible for comparison? | Meaning |
| --- | --- | --- |
| `CONVERGED` | Yes | All required convergence, topology, finite-value, and contact predicates pass. |
| `INVALID_MODEL_INPUT` | No | Input, units, unsupported topology, or prohibited data violates the contract. |
| `DIVERGED` | No | Iterates/energy/residuals violate the declared divergence predicate. |
| `UNRESOLVED_COLLISION` | No | Contact penetration remains above the hard simulation tolerance. |
| `BUDGET_EXHAUSTED` | No | A deterministic work limit is reached before convergence. |
| `NUMERICAL_FAILURE` | No | NaN/Inf, factorization failure, singularity beyond allowed rigid modes, or other numerical contract failure. |

Only `CONVERGED` carries authoritative predicted geometry. Every other status is fail-closed and includes structured diagnostics. A last iterate from a failed run may be retained as debug data but cannot enter the geometry gate.

A converged result records vertex/element geometry, graph-to-geometry mapping, energy decomposition, residuals, contact statistics, model/configuration hashes, input hashes, and deterministic run provenance.

## Budgets and tolerances

Required positive work budgets include `max_initializations`, `max_optimizer_iterations`, `max_energy_evaluations`, `max_linear_iterations`, and `max_contact_pairs_evaluated`. Exhaustion yields `BUDGET_EXHAUSTED`.

All tolerances are explicit and versioned:

| Tolerance | Unit | Predicate | Owner / validation path |
| --- | --- | --- | --- |
| `force_residual_n` | N | Maximum residual-force norm for convergence | Forward model / numerical convergence fixtures |
| `position_step_mm` | mm | Maximum accepted final coordinate update | Forward model / scale-aware convergence study |
| `relative_energy_change` | dimensionless | Plateau criterion over a declared window | Forward model / optimizer regression suite |
| `contact_penetration_mm` | mm | Hard maximum unresolved penetration | Contact model / collision fixtures and physical calibration |
| `volume_orientation_epsilon_mm3` | mm^3 | Rejects degenerate or inconsistent signed volume | Forward model / closed/open topology fixtures |
| `mode_equivalence_rms_mm` | mm | Determines whether target-independent starts found materially distinct states | Robustness verifier / multimodal benchmark suite |

There are no implicit production values during bootstrap. Numerical convergence tolerances are not target-geometry acceptance thresholds.

## Independence controls

- Simulator APIs use types that contain no target fields.
- Runtime dependency injection rejects target/correspondence objects.
- Test fixtures include a negative test proving target data cannot be supplied.
- Initial coordinates are reproducible from the physical-semantic projection, material, loading, and model-configuration hashes alone.
- Geometry comparison runs in a separate module after a successful outcome.
- Reuse of solver code, geometry kernels, or assumptions is recorded as common-mode risk and reviewed.
- Solver and independent forward-model changes should not normally be made in the same implementation task.

## Material uncertainty

Nominal simulation uses the recorded pitch estimates. Robustness verification performs separately recorded scenarios over declared stitch/course pitch uncertainty. Sampling or interval selection is deterministic and target-independent.

The minimal V1 MaterialProfile does not pretend to identify stiffness, friction, compression, drape, or stuffing response. F0 coefficients not identified by that profile come from a separately versioned model-calibration profile and remain **HYPOTHESES** until physical fixtures support them.

## Evolution

- **F0:** anisotropic course-level graph/spring model with coarse bending, shear, contact, and optional pressure.
- **F1 FUTURE:** anisotropic shell/surface elements with calibrated constitutive response.
- **F2 FUTURE:** yarn-level geometry, contact, friction, and richer stitch mechanics.

All levels preserve the same prohibited-target boundary and tagged result contract. Higher fidelity does not weaken fail-closed convergence requirements.

## Known failure modes

- Coarse graph topology may omit stitch-scale deformation or local buckling.
- Unknown coefficients can dominate apparent accuracy and create false precision.
- Multiple equilibria can make one deterministic initialization misleading.
- Pressure models can be invalid for openings, leakage, or poorly characterized stuffing.
- A converged numerical equilibrium can still be physically inaccurate.
- Shared stitch semantics between compiler and simulator remain a common-mode risk; semantic and physical benchmarks are both required.
