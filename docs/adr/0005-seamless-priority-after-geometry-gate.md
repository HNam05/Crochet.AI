# ADR-0005: Seamless-first only after a hard geometry gate

- Status: Accepted
- Date: 2026-08-30

## Context

Maximum seamless construction is a primary product goal, but unbounded preference for seamlessness could select visibly inaccurate shapes.

## Decision

Candidate selection is lexicographic. Structural validity and the hard geometry acceptance region are feasibility gates. Among feasible candidates, compare sewn seams first, then yarn cuts/reattachments, remaining geometry error, and unnecessary complexity.

## Consequences

- A slightly less accurate seamless candidate may beat a multi-piece candidate only when both pass every hard geometry requirement.
- A seamless candidate outside the acceptance region is ineligible, regardless of seam count.
- Geometry is a metric vector with a versioned comparison policy, not a single hidden weighted score.
- Thresholds begin as explicit engineering hypotheses and must be recalibrated using physical benchmarks.

