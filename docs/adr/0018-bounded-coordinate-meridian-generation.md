# 0018: Bounded explicit-coordinate meridian generation

Status: accepted implementation decision, 2026-10-06.

## Decision

Extend the analytic producer to the simple closed cardinal-axis coordinate
targets admitted by ADR 0017. Replace that checkpoint's deliberate unsupported
generator guard with the separate
[EXPLICIT_COORDINATE_MERIDIAN_V1 contract](../ANALYTIC_COORDINATE_GENERATION_V1.md).
Target admission, canonical schemas and independent verifier are unchanged.

Use exact rational input differences, bounded hypot enclosures certified by exact
squared-distance comparisons, exact cumulative approximate lengths and normalized
rational interpolation. A fixed two-step widening ceiling is simpler than
adaptive quadrature for piecewise-linear segments, and checks rather than assumes
the floating-point estimate's accuracy. Failed enclosures or excessive output
rounding fail explicitly. New intervals are numerical producer evidence.

Course/count/phase search and complete-IR compilation keep their existing
contracts. Add coordinate-only sampler provenance and signed axial samples to the
existing trace; preserve old-input fields and parameter behavior. New generic
pilot projects author explicit coordinates. Retain legacy authoring and all
saved data without migration or inferred signs.

## Alternatives and consequences

Silently converting radius/arclength profiles to axial positions would preserve
their ambiguity. Unchecked hypot/prefix accumulation would hide conditioning and
lost short segments. A new arbitrary-precision square-root or adaptive numerical
framework is unnecessary: exact rational enclosure tests allow bounded rejection
when the existing floating estimate cannot meet the declared tolerance.

The tolerance bounds total length error, while sample displacement has the
separately derived 2E plus conversion allowance bound. Neither proves physical
stitchability, calibrated dimensions, target coverage or V7. Independent search
replay still supports only its documented primitive subset and returns incomplete
evidence for coordinate targets. Extending that verifier is separate work.
