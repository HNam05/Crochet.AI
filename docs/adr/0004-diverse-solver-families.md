# ADR-0004: Diverse solver families

- Status: Accepted
- Date: 2026-08-30

## Context

Surfaces of revolution, freeform organic meshes, garments, flat patterns, and lace have different mathematical structure. A universal solver would obscure assumptions and weaken failure handling.

## Decision

Use algorithmically diverse solver families behind a shared candidate boundary:

- analytic global integer optimization for surfaces of revolution;
- geodesic level-set coupling for suitable freeform surfaces;
- bounded advancing-front search for difficult local geometry;
- separate future garment, flat-crochet, and lace solvers.

Redundancy compares independently reconstructed outcomes and invariants, not majority votes over stitch counts.

## Consequences

- Each solver declares applicability, budgets, tolerances, and failure modes.
- Multiple correct constructions may coexist.
- Shared infrastructure stops at DesignSpec routing, CrochetIR, material representation, and verification.
- A solver may return `NO_VERIFIED_SOLUTION_WITHIN_BUDGET` without triggering fallback fabrication.

