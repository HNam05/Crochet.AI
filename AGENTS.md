# Engineering Rules

This project is a deterministic crochet CAD/compiler. Read the relevant contract before changing a subsystem.

## Permanent rules

- Correctness, reproducibility, and explicit failure take priority over speed.
- After `DesignSpec`, generation is deterministic or uses bounded numerical search with recorded parameters and seed.
- `CrochetIR` is the canonical construction representation. Do not substitute prose or a solver Construction Graph.
- Fail closed. Never silently repair ambiguity, invent unsupported construction, or average a failed critical gate into a pass.
- Keep solver generation and independent verification separate. They should not normally change in the same task.
- Never weaken a test solely to obtain PASS. Golden changes require explicit human approval and are never auto-updated.
- Solver changes must state invariants, computational budget, tolerances, and known failure modes.
- Every numerical tolerance requires units, rationale, and an owner or calibration path.
- Preserve canonical stitch semantics; US/UK/German names exist only at export boundaries.
- Do not let target geometry constrain the independent forward simulation.
- Do not spawn subagents for trivial tasks. Use focused agents only when independent work materially improves quality or speed.
- Do not copy external source code without an explicit compatible-license review; record uncertainty instead.

## Required reading

- Domain and inputs: [`docs/DOMAIN_MODEL.md`](docs/DOMAIN_MODEL.md), [`docs/DESIGN_SPEC.md`](docs/DESIGN_SPEC.md), [`docs/MESH_PREFLIGHT.md`](docs/MESH_PREFLIGHT.md)
- Canonical IR: [`docs/CROCHET_IR.md`](docs/CROCHET_IR.md), [`docs/CANONICALIZATION.md`](docs/CANONICALIZATION.md)
- Solvers/topology: [`docs/SOLVER_ARCHITECTURE.md`](docs/SOLVER_ARCHITECTURE.md), [`docs/TOPOLOGY_SEAMLESS.md`](docs/TOPOLOGY_SEAMLESS.md)
- Physics/materials: [`docs/FORWARD_MODEL.md`](docs/FORWARD_MODEL.md), [`docs/MATERIAL_MODEL.md`](docs/MATERIAL_MODEL.md)
- Verification/tests: [`docs/VERIFICATION.md`](docs/VERIFICATION.md), [`docs/TEST_STRATEGY.md`](docs/TEST_STRATEGY.md), [`docs/FAILURE_POLICY.md`](docs/FAILURE_POLICY.md)
- Research/licensing: [`docs/RESEARCH.md`](docs/RESEARCH.md)
- Foundational decisions: [`docs/adr/`](docs/adr/)
