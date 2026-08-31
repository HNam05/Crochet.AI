---
name: seamless-topology
description: Work on construction frontiers, branch decomposition, Construction Graphs, Reeb or Morse-style topology, splits, joins, reservations, openings, or seamless construction planning.
---

# Seamless topology

Read [`docs/TOPOLOGY_SEAMLESS.md`](../../../docs/TOPOLOGY_SEAMLESS.md) and the frontier section of [`docs/CROCHET_IR.md`](../../../docs/CROCHET_IR.md).

- Keep the solver-private Construction Graph distinct from executable CrochetIR.
- Make every frontier lifecycle transition explicit: create, advance, split, reserve, reattach, join, close, or declare an intentional opening.
- Track branch obligations so an unaccounted or unintentionally open boundary is a hard failure.
- Seamlessness is optimized only after the hard geometry gate passes.
- Treat critical-point and Reeb-style methods as topology-planning tools, not proof that a crochet construction is physically feasible.
- Bound backtracking and expose exhaustion as a diagnostic outcome.

Include counterexamples for topology-changing operations and degenerate level sets.

