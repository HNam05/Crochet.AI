# ADR-0002: Fail-closed verification

- Status: Accepted
- Date: 2026-08-30

## Context

Crochet construction can fail structurally even when an aggregate geometry score looks good. Missing evidence, ambiguous repair, and threshold averaging could produce unsafe claims of validity.

## Decision

Verification is a sequence of mandatory gates. Missing required evidence, invalid references, illegal frontier transitions, failed topology, simulation divergence, hard geometry failure, or semantic export mismatch prevents `VERIFIED`. Critical failures are never averaged into an overall score.

Validators return structured error codes and context and never silently repair authoritative input or CrochetIR.

## Consequences

- Rejection is a normal successful system outcome.
- Overall evidence is derived from gate results, not an opaque confidence percentage.
- Threshold profiles are versioned and distinguish hypotheses from calibrated values.
- Recovery may propose a new candidate or corrected DesignSpec, but that artifact must restart relevant gates.

