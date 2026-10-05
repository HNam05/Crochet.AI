# Analytic count proposal kernel, version 1

Implementation: `src/crochet_ai/analytic_counts.py`. This is an internal building
block for B3, not the complete analytic solver and not a verification gate.
It accepts explicit course circumferences in millimetres, positive stitch pitch
in millimetres, one inclusive integer count window per course, integer shaping
limits, and deterministic budgets. It does not accept a DesignSpec in place of
those resolved inputs. Target decoding, meridional course placement, angular
shaping placement, compilation to CrochetIR and physical verification remain
separate work. Its output is only `OPTIMAL_COUNT_PROPOSAL`, never
`CANDIDATES_EMITTED` or a verified pattern.

## Exact model

Inputs use immutable tuples and `Fraction` values. No binary floating-point
coercion, implicit rounding, numerical tolerance, or physical acceptance
threshold exists in this kernel. A future boundary adapter must document its
conversion from canonical binary64 inputs; no such conversion is inferred here.

Each adjacent count pair must admit nonnegative integers S, I, D with
`before = S + I + 2D`, `after = S + 2I + D`, `I * D = 0` and the declared
increase/decrease limits. Count windows are solver-private finite search domains,
not authoritative input stitch counts in DesignSpec. All first-layer counts in
its window are eligible; start and end policies must constrain the windows in
the later full solver.

The objective, in order, is maximum absolute circumference residual (mm), sum of
squared residuals (mm2), number of shaping operations, then lexicographically
smallest count tuple. It is a generation heuristic, not geometry acceptance.

Pass 1 computes the globally smallest attainable maximum residual T. Pass 2
restricts node residuals to at most T and minimizes the additive squared error,
shaping count and path tie-breaker. A single best `(max, sum)` prefix per state
is not sound: a later residual can equalize two prefix maxima and expose the
discarded prefix's smaller sum. `test_bottleneck_must_not_prune_additive_optimum`
records an independently reviewed legal counterexample.

## Bounded execution

Every tested predecessor/successor pair, including unreachable pairs, costs one
transition evaluation in each pass. Both passes share one budget. Count order
and predecessor order are ascending. Each layer counts retained reachable states.
The second pass retains a subset of first-pass reachable counts, so cannot exceed
the first-pass state bound. Layer/count-window budgets are checked before search.
Exhaustion returns no counts, transitions or objective, with a reason, consumed
edge count and completed-pass count. An empty reachable layer proves no feasible
path inside this declared domain, not impossibility outside it.

Implementation safety ceilings: 512 courses, 256 count values and retained states
per layer, 100000 count/shaping magnitude, 2000000 edge evaluations, numerator at
most 256 bits and denominator at most 128 bits per rational input. These are
versioned software resource limits owned by this kernel, not calibrated physical
limits. Requested budgets must be positive and at most these ceilings. A valid
domain wider than its requested budget yields exhaustion; malformed inputs or
requests outside implementation safety limits yield invalid input.

For M layers and width W, there are O(M W2) edge checks per pass. Rolling costs
use O(W) labels. Storing immutable path tuples for exact deterministic ties uses
O(M W) live count entries and adds O(M) copy/comparison cost per candidate in the
second pass. Rational arithmetic adds operand-bit-length costs. No wall-clock
measurement affects results.

## Evidence and boundaries

Producer instrumentation retains compact per-pass/layer state counts, work and
completion, including interrupted layers. These records belong to the external
[ANALYTIC_SEARCH_TRACE_V1](ANALYTIC_SEARCH_TRACE_V1.md); they do not change count
ordering, recurrence, work-unit definitions or independent verification status.

Hypothesis compares results against a separate exhaustive path oracle that
enumerates S/I/D arities. Tests cover empty reachable domains, exact budget
boundaries, second-pass exhaustion, rational limits, scaling and deterministic
ties. The oracle does not call the DP transition helper. The mathematical review
and tests establish the declared discrete model only: angular history, stacking,
material response, geometry, poles/openings and all non-analytic domains are not
implemented by this kernel.
