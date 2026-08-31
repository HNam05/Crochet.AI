---
name: solver-design
description: Design or review deterministic analytic, geodesic, frontier, garment, flat, or lace solvers and their candidate-selection contracts.
---

# Solver design

Start with [`docs/SOLVER_ARCHITECTURE.md`](../../../docs/SOLVER_ARCHITECTURE.md), then read only the relevant solver document.

- Declare inputs, outputs, preconditions, invariants, complexity, numerical tolerances, search budget, and rejection states.
- Produce candidate CrochetIR through an explicit compilation boundary; solver-private structures are not canonical.
- Use global integer reasoning for coupled counts. Do not disguise independent course rounding as optimization.
- Rank only candidates that pass hard structure and geometry gates. Then minimize seams, cuts/reattachments, residual error, and complexity lexicographically.
- A bounded solver must return a structured no-solution/budget failure instead of fabricating a pattern.
- Solver work must not weaken or co-evolve its independent verifier in an ordinary task.

Ask for mathematical review when topology, stability, or a new optimization formulation is materially risky.

