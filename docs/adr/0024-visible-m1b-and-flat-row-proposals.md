# ADR 0024: Explicit M1B replay and bounded flat-row proposals

## Status

Implemented as experimental profiles, 2026-10-18. This does not close backend
acceptance or authorize physical claims.

## Decision

Keep frozen M1A and the default V9 adapter unchanged. Add PATTERN_M1B_V1 as a
separate controlled text grammar and replay builder. Declarations and actions
carry visible construction information; the frozen external context resolves
only DesignSpec/material/color. Full independent semantic validation follows
binding. Select M1B in V9 explicitly and bind the profile in evidence identity.
This is preferable to embedding IR or adding hidden reconstruction context,
which would defeat independent parsing and ADR 0015.

Add a dedicated FLAT rectangular SC rows producer rather than routing flat
work through the closed amigurumi solver/forward model. An authoritative raw
rectangle record binds DesignSpec dimensions and frame; exact rational
pitch-times-count predicates, explicit search/resource ceilings and a declared
total order produce one complete best-prefix proposal. This model is a
discretization hypothesis. Existing independent semantic validation accepts or
rejects the emitted IR. Geometry and physical acceptance remain separate.

Both profiles reuse existing schema versions, canonicalization and error
boundaries. API/CLI/jobs expose the new operations without modifying stored
projects, goldens, dependencies or automatic release policy. See
[M1B](../PATTERN_M1B_V1.md) and [flat rows](../FLAT_SC_ROWS_V1.md) for exact limits.

## Consequences

Reserve proposals can now be exported/reimported structurally. Independent
hand-built branch, join, opening, yarn and six-family fixtures round-trip.
These are not generated branch geometry, garment/lace solvers or branch/open
mechanics. A flat rectangle is not yet a complete general flat-domain solver.
No successful V9 check can replace missing or failed geometry/physical gates.
