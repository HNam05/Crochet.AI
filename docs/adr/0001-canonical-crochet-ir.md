# ADR-0001: Canonical CrochetIR

- Status: Accepted
- Date: 2026-08-30

## Context

Natural-language instructions, solver-private meshes, and topology-planning graphs omit relationships needed for deterministic validation and export. Multiple solver families still need one shared executable representation.

## Decision

CrochetIR is the sole canonical representation of a compiled construction. It explicitly records stitch and construction-operation IDs, base/top attachments, yarn path, courses, ordered frontier transitions, branches, openings, colors, cuts/reattachments, and provenance.

`DesignSpec` expresses intent. A `ConstructionGraph` expresses a solver's topology plan. Neither is CrochetIR. Canonical serialization and hashing are versioned parts of the IR contract.

## Consequences

- All solvers compile candidates to CrochetIR before shared verification.
- Exporters consume CrochetIR, not solver-private state.
- JSON Schema checks shape; an independent semantic validator checks graph-wide invariants.
- Schema evolution requires an explicit version and migration policy.
- Some domain techniques remain unsupported until their semantics can be represented without ambiguity.

