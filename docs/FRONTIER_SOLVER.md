# Bounded Frontier Solver

## Status and purpose

**FUTURE:** this is a contract for a later research solver, not an implementation claim.

The frontier solver is the fallback amigurumi family for meshes whose geometry or topology cannot be represented satisfactorily by one analytic profile or a stable global geodesic course system. It performs local advancing-front search with explicit rollback and finite work budgets.

It is not a license to invent a plausible-looking pattern. Failure and budget exhaustion are normal outcomes.

## Preconditions

- Target geometry passed independent preflight and uses millimetres.
- A deterministic seed/frontier hypothesis is available.
- Enabled stitch and construction operations have canonical base/top arities.
- A resolved `MaterialProfile`, numerical profile, and all deterministic budgets are present.
- Openings, allowed seams, reattachments, and unsupported techniques are explicit in `DesignSpec`.
- Collision and topology predicates required by the run are available at declared fidelity.

The solver returns `NOT_APPLICABLE` for unsupported non-manifold or ambiguous target topology. It does not repair target geometry or reinterpret construction constraints.

## Solver-private search state

A search state is not CrochetIR. It contains at least:

```text
SearchState
  partial_construction_graph
  partial_stitch_graph
  active_and_reserved_frontiers
  target_correspondences_and_local_frame
  branch_obligation_ledger
  yarn_continuity_state
  collision_acceleration_state
  exact_discrete_costs
  heuristic_geometry_bounds
  operation_trace
```

Target coordinates, closest-point correspondences, heuristic embeddings, and collision proxies are private to search. A state crosses the compilation boundary only after all construction obligations are discharged and a complete CrochetIR can be emitted.

## Operation set

The ordered operation registry is versioned. The initial conceptual set includes:

- place an ordinary supported stitch `(1,1)`;
- place a supported increase `(1,2)`;
- place a supported decrease `(2,1)`;
- advance or turn a linear/cyclic frontier;
- split and reserve a frontier;
- reattach to a reserved frontier with explicit `ATTACH` and yarn state;
- join compatible frontiers;
- close a frontier;
- terminate a frontier as a declared intentional opening;
- cut or change yarn only when permitted.

Every operation declares exact preconditions, the attachment locations it references, produced locations, frontier transition, yarn transition, inverse rollback record, and deterministic ordering key. Unsupported multiplicities or techniques are rejected.

## Hard pruning predicates

A state is discarded immediately when any exact predicate fails:

- invalid or duplicate reference;
- base/top arity mismatch or unreachable integer count;
- illegal frontier lifecycle transition;
- lost, duplicated, or unaccounted branch obligation;
- construction operation disallowed by `DesignSpec`;
- seam, cut, or reattachment limit exceeded;
- proven combinatorial self-crossing;
- collision penetration beyond the declared solver-side limit;
- lower bound on unavoidable target error already exceeds the solver's generation envelope;
- no legal terminal path remains under exact remaining obligations.

Solver-side geometry/collision predicates are search filters, not verification. Passing them does not imply physical or geometric validity.

## Search algorithm

**ENGINEERING DECISION:** use deterministic bounded beam search with bounded depth-first backtracking inside each retained beam state.

For each expansion layer:

1. enumerate applicable operations in registry order;
2. apply each operation to an immutable state or an exactly reversible transaction;
3. run hard pruning predicates;
4. compute a versioned lexicographic search key;
5. retain at most `beam_width` states, using the canonical operation trace as final tie-breaker;
6. compile complete states to candidate CrochetIR up to the candidate budget.

A search key may include lower-bound target residual, unresolved obligation count, construction discontinuities, frontier irregularity, and operation count. It is only a proposal heuristic. Global candidate selection occurs after independent verification under the project-wide ordering.

Rollback must restore graph connectivity, frontier order/state, yarn state, obligation ledger, collision structure, counters, and accumulated cost exactly. Stateful rollback equivalence is a required property test.

## Construction Graph boundary

The state may refine a solver-private Construction Graph while exploring branch paths. The graph records region and frontier obligations, not stitch execution. It must never be serialized in place of CrochetIR.

Compilation succeeds only when:

- each planned region has explicit stitch/operation realization;
- every frontier is closed or a declared opening;
- every reservation is resumed or intentionally terminated;
- every join/split/attach is represented explicitly;
- yarn cuts and reattachments are counted from the executable operation sequence;
- no target correspondence is required to interpret the resulting CrochetIR.

## Deterministic budgets

Every run supplies positive integer limits:

| Parameter | Unit | Meaning |
| --- | --- | --- |
| `max_seed_hypotheses` | seeds | Initial frontier states attempted |
| `beam_width` | states per layer | Retained states after total ordering |
| `max_search_depth` | operations | Longest partial trace |
| `max_state_expansions` | states | Applied successor operations |
| `max_backtracks` | rollback branches | Local alternatives revisited |
| `max_collision_queries` | queries | Broad/narrow-phase checks |
| `max_topology_alternatives` | Construction Graph plans | Branch decompositions attempted |
| `max_emitted_candidates` | complete candidates | CrochetIR artifacts compiled |

The first reached counter stops further expansion. If the declared search space was not completely explored, the result is `SEARCH_BUDGET_EXHAUSTED`. Already completed candidates may continue to independent verification, but no partial candidate is emitted.

At orchestration level, if every independently checked candidate fails or the search ends before a passing candidate is found, the user-facing result is `NO_VERIFIED_SOLUTION_WITHIN_BUDGET` with generation and rejection diagnostics preserved.

## Numerical tolerances

No hidden values exist; all belong to a versioned numerical profile.

| Tolerance | Unit | Purpose | Owner / validation path |
| --- | --- | --- | --- |
| `target_projection_tolerance_mm` | mm | Acceptable residual for a local closest-point computation | Frontier solver / analytic surfaces and retessellation tests |
| `local_frame_degeneracy_mm2` | mm^2 | Rejects insufficient geometric support for a stable local frame | Geometry kernel / thin-feature adversarial fixtures |
| `collision_clearance_mm` | mm | Solver-side conservative separation rule | Collision module / contact convergence and physical fixtures |
| `orientation_tie_tolerance_rad` | rad | Deterministic equality for competing local directions | Frontier solver / rigid-rotation tests |
| `heuristic_cost_tie_tolerance_mm2` | mm^2 | Stable ordering of numerically equal geometry keys | Frontier solver / reproducibility tests |

`collision_clearance_mm` is a **HYPOTHESIS** until calibrated. It cannot be reused silently as the independent verifier's collision threshold.

## Complexity and resource bound

Let `B` be beam width, `D` search depth, `A` maximum applicable operations per state, and `Q` collision-query cost. Unpruned work is bounded by `O(min(max_state_expansions, B * D * A) * Q)` plus topology alternatives. Memory is `O(B * state_size)` for immutable snapshots, or less with verified reversible deltas.

The finite budget bounds execution but does not prove completeness over all crochet constructions.

## Failure states and limitations

- `NO_FEASIBLE_CONSTRUCTION` is valid only after complete enumeration of the explicitly declared finite domain.
- `SEARCH_BUDGET_EXHAUSTED` reports the limiting counter and unexplored frontier size.
- `NUMERICAL_FAILURE` reports projection, local-frame, or collision-kernel failure.
- `INVALID_SOLVER_INPUT` covers missing tolerances/budgets or contradictory constraints.
- Search can miss a valid pattern through heuristic beam pruning.
- Solver-side collision proxies can produce false positives or false negatives.
- A locally valid advancing sequence can create a globally uncloseable frontier; the obligation ledger and backtracking expose rather than hide this.
- A complete discrete construction may still fail independent physical simulation or the hard geometry gate.
