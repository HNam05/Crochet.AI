# 0020: Closed shaped elastic preparation and diagnostics

Status: accepted implementation decision, 2026-10-08.

## Decision

Add [FORWARD_SHAPED_ELASTIC_DIAGNOSTIC_V1](../FORWARD_SHAPED_ELASTIC_V1.md)
alongside the existing plain strip pipeline. Reuse target-free projection,
material selection, closed-cell admission and the spring energy/force kernel.
Prepare explicit hypothesis rest rules for binary SC shaping and ring
incidences before producing deterministic initial coordinates.

Return a separately hashed experimental initial diagnostic through the existing
API/CLI/job framework. Preserve all old pipeline contracts, canonical schemas,
goldens, generator behavior and verification gates. Retain missing physical
mechanics and prohibit geometry-comparison eligibility.

## Alternatives and consequences

Relaxing the plain strip pipeline's shape guards would imply that its quad
shear/bending and final-contact algorithms support closed shaped triangles.
They do not. Deriving rest lengths from the initializer would make an
arbitrarily stress-free state and conceal missing mechanical calibration.
Explicit hypothesis rules and an additive diagnostic keep both limits visible.

This provides the missing construction-to-elastic preparation for closed
generated shapes. It does not complete P04/P05, establish contact or pressure
response, pass V6 or demonstrate physical accuracy. Initialization offsets and
arity multipliers require their own calibration and convergence studies.
