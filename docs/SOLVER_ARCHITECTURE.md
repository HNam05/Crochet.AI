# Solver Architecture

## Status and claim vocabulary

This document is a contract for future implementations. It does not claim that a production solver exists.

- **PROVEN / FORMAL:** follows from the stated discrete model or interface contract.
- **ESTABLISHED:** a method or interpretation supported by external mathematical or physical literature.
- **ENGINEERING DECISION:** a project choice that must remain stable unless replaced by an ADR.
- **HYPOTHESIS:** an uncalibrated numerical or physical assumption.
- **FUTURE:** deliberately outside the bootstrap implementation.

## Responsibility boundary

The deterministic pipeline after a validated `DesignSpec` is:

```text
validated DesignSpec + target representation + MaterialProfile
                              |
                              v
                 domain router / solver family
                              |
                    solver-private analyses
              (including a Construction Graph)
                              |
                  explicit compilation boundary
                              |
                              v
                   complete candidate CrochetIR
                              |
                 independent semantic validation
                              |
                 independent forward simulation
                              |
           target comparison and robustness verification
                              |
                  feasible-candidate selection
```

**ENGINEERING DECISION:** `DesignSpec`, a solver-private `ConstructionGraph`, a partial search state, and `CrochetIR` are different representations.

- `DesignSpec` records authoritative intent, constraints, and input references. It does not contain authoritative final stitch counts.
- A `ConstructionGraph` plans regions, branch obligations, frontier splits/joins, yarn continuity, and unavoidable seams. It is not executable and is never canonical.
- A partial solver state may contain target correspondences and heuristic geometry. It is not a valid pattern.
- `CrochetIR` is the only canonical executable construction representation. Shared validation, simulation, export, and hashing consume it.

Target geometry is permitted inside candidate generation. It is prohibited as a constraint, repair signal, initializer, or convergence aid inside the independent forward simulator. Target geometry re-enters only in the later geometry-comparison gate.

## Solver families

No universal geometry solver is planned.

| Family | Intended domain | Core method | Explicit non-scope |
| --- | --- | --- | --- |
| Analytic | Amigurumi surfaces of revolution such as spheres, cylinders, cones, ellipsoids, and tapered bodies | Meridional sampling plus global integer optimization of coupled course counts | Branching topology, arbitrary handles, garments |
| Geodesic | Suitable mostly continuous freeform surfaces | Geodesic distance, level sets, ordered adjacent-course coupling, topology-change detection | Highly degenerate level sets, general garment fit |
| Frontier | Complex meshes that resist a stable global parameterization | Local advancing-front operations with bounded beam search and rollback | Unbounded completeness claims |
| Garment | **FUTURE:** sized garments | Body measurements, ease, gauge, construction, grading, and later cloth response | Reusing the amigurumi solver as a substitute |
| Flat | **FUTURE:** blankets and planar work | Rows, grids, repeats, tilings, motifs, and color-region constraints | Arbitrary 3D surface fitting |
| Lace | **FUTURE:** motif and topology-heavy work | Typed motif/topology graph with explicit attachment semantics | Claiming full lace support from the basic stitch family |

Shared infrastructure ends at validated inputs, canonical CrochetIR, material representation, verification, provenance, and export. Domain-specific mathematical assumptions stay inside their solver family.

## Common solver invocation contract

Every invocation receives immutable, versioned inputs:

1. a schema- and semantically-valid `DesignSpec`;
2. the domain-appropriate target representation in millimetres, with a content hash;
3. a resolved `MaterialProfile` with separately measured stitch and course pitch;
4. a `SolverRunConfig` containing solver/version, numerical profile, deterministic search budgets, candidate limit, and seed when any seeded method is used;
5. an applicability declaration and selected construction constraints.

Every solver specification must state:

- preconditions and supported topology;
- exact discrete invariants;
- numerical tolerances, their units, rationale, owner, and validation path;
- deterministic work budgets measured in states, iterations, transitions, or candidates;
- asymptotic complexity and material memory bounds;
- complete rejection and exhaustion states;
- known common-mode risks with verification.

Wall-clock time may be an operational watchdog, but it is not a reproducible mathematical budget. If a watchdog interrupts work, the result is budget exhaustion, never an inferred no-solution result.

## Candidate compilation boundary

A solver may return zero or more complete candidate artifacts. A conceptual candidate envelope contains:

```text
CandidateArtifact
  crochet_ir                 complete canonical candidate
  solver_provenance          name, version, parameters, budgets, seed
  input_hashes               DesignSpec, target, MaterialProfile
  generation_diagnostics     non-authoritative solver residuals and traces
  construction_summary       claimed seams, cuts, reattachments, complexity
```

Generation diagnostics are evidence about the search, not verification results. Solver-private target correspondences, meshes, Construction Graph nodes, heuristic scores, and partial states must not be embedded as authoritative CrochetIR semantics. They may be retained in a non-canonical debug artifact whose hash is recorded separately.

Compilation is all-or-nothing:

- every stitch and construction operation has an explicit ID;
- all references resolve inside the candidate;
- ordered courses, yarn path, branches, and frontier transitions are explicit;
- each branch obligation terminates in a closure or declared intentional opening;
- no partial CrochetIR is emitted on cancellation or exhaustion.

These conditions do not make the candidate verified. They make it eligible for independent validation.

## Determinism and bounded search

**PROVEN / FORMAL:** a finite search with a fixed input, fixed ordering, fixed arithmetic policy, fixed seed, and deterministic work-count budget produces a reproducible prefix of the search space.

Therefore every bounded solver must:

- define a total order for operations, states, and equal-cost ties;
- record all integer and numerical budgets in provenance;
- use deterministic reductions and stable canonical identifiers;
- record the pseudo-random generator and seed if randomized sampling is explicitly enabled;
- distinguish proven infeasibility in a completely enumerated declared domain from premature exhaustion;
- return structured failure instead of fabricating or silently repairing a candidate.

At minimum, terminal generation outcomes are:

| Outcome | Meaning |
| --- | --- |
| `CANDIDATES_EMITTED` | One or more complete candidates were compiled; none is thereby verified. |
| `NOT_APPLICABLE` | Solver preconditions do not hold for this design/target. |
| `NO_FEASIBLE_CONSTRUCTION` | The finite declared search domain was completely explored and no state satisfied its exact constraints. |
| `SEARCH_BUDGET_EXHAUSTED` | A deterministic work budget ended exploration before completeness. |
| `NUMERICAL_FAILURE` | Required numerical analysis did not satisfy its declared convergence or conditioning contract. |
| `INVALID_SOLVER_INPUT` | A required, already-resolved input or parameter violates the invocation contract. |

After independent verification, the orchestration layer may return `NO_VERIFIED_SOLUTION_WITHIN_BUDGET` when no generated candidate passes every required gate. That state must preserve whether generation exhausted, completed without a feasible state, or emitted candidates that verification rejected.

## Feasibility gates and candidate selection

Candidate selection occurs after independent verification. A candidate is feasible only if all mandatory gates pass, including:

1. CrochetIR schema and semantic structure;
2. reference, count, frontier, branch, and topology accounting;
3. independent forward-model convergence without prohibited target input;
4. every hard target-geometry threshold in the active threshold profile;
5. any material-robustness requirement declared mandatory by `DesignSpec`.

**PROVEN / FORMAL:** an infeasible candidate is not a member of the ranking set. No ranking term can compensate for a failed gate.

Feasible candidates are ordered lexicographically by the following versioned tuple:

```text
(
  sewn_seam_count,
  yarn_cut_count,
  yarn_reattachment_count,
  residual_geometry_metric_vector,
  construction_complexity_vector,
  canonical_crochet_ir_hash
)
```

The geometry metric vector and construction-complexity vector each require a documented total ordering. The final hash is only a deterministic tie-breaker and has no quality meaning. No hidden weighted sum or average may move a candidate across the hard geometry boundary.

This ordering permits a seamless candidate with somewhat higher residual error to beat a multi-piece candidate only when both are already inside every hard geometry limit.

## Solver redundancy

Different stitch-count sequences can be valid constructions of similar physical geometry. Majority voting over stitch counts is therefore invalid.

Algorithmic redundancy operates at reconstructed outcomes:

1. diverse solver families independently compile CrochetIR candidates;
2. the same independent semantic validator checks exact invariants;
3. the independent forward model reconstructs predicted geometry from each candidate;
4. verification compares topology, geometry metrics, robustness, and construction cost;
5. the selector ranks only feasible candidates.

Multiple LLM-generated implementations of the same formulation do not establish N-version independence. Shared libraries between generation and verification must be documented as common-mode risk.

## Numerical-policy registry

No physical acceptance threshold is a solver tolerance. Solver tolerances only control geometry preprocessing, numerical convergence, and discrete candidate enumeration. They are supplied through a versioned numerical profile and copied into provenance.

Each entry must provide:

| Field | Requirement |
| --- | --- |
| `name` | Stable parameter identifier |
| `value` and `unit` | Finite numeric value with explicit unit, or a dimensionless value |
| `purpose` | Predicate or convergence test it controls |
| `rationale` | Why finite precision requires it |
| `owner` | Geometry kernel, named solver family, forward model, or verifier |
| `validation_path` | Convergence study, adversarial fixture, or physical calibration profile |

There are no implicit production defaults during bootstrap. Missing required tolerances is `INVALID_SOLVER_INPUT`; an implementation must not guess them.

## Invariants shared by all solvers

**PROVEN / FORMAL:** every accepted implementation preserves these contracts.

- Integer stitch and attachment counts remain integer throughout candidate construction.
- A reachable count transition is justified by explicit base/top arity operations, not independent rounding.
- Canonical stitch identifiers are unambiguous; localized US, UK, or German names are absent from solver logic.
- `JOIN`, `SPLIT`, `ATTACH`, and `COLOR_CHANGE` are construction operations, not ordinary stitch substitutions.
- Every solver-created branch has a corresponding frontier obligation.
- Every emitted candidate is complete and deterministic under its recorded run configuration.
- Search exhaustion, numerical failure, and verified geometric rejection remain distinguishable.
- Solver self-scores never substitute for independent verification.

## Known architectural failure modes

- A router can choose an inapplicable solver when target classification is ambiguous. The safe outcome is multiple bounded attempts or `NOT_APPLICABLE`, not coercion.
- A numerically stable geodesic field can still induce a construction topology that is physically impossible.
- A solver and verifier can share the same modeling error. Diverse methods and physical benchmarks reduce but do not eliminate this risk.
- A candidate can pass nominal material simulation yet fail under uncertainty. Robustness is a separate gate.
- Search budgets can exclude a valid construction. Exhaustion must never be reported as mathematical impossibility.

## Bootstrap and future work

- **ENGINEERING DECISION:** the first production solver milestone is the analytic surface-of-revolution family after DesignSpec, CrochetIR, and the semantic validator exist.
- **FUTURE:** geodesic and frontier implementations, garment/flat/lace solvers, topology optimization, learned proposals, and portfolio scheduling.
- **HYPOTHESIS:** the stated candidate ranking and practical solver families will yield constructions that correlate with human judgments after physical calibration.
