# Engineering Rules

This project is a deterministic crochet CAD/compiler. Read the relevant contract before changing a subsystem.

For backend continuation, first read [`docs/BACKEND_HANDOFF.md`](docs/BACKEND_HANDOFF.md)
for the latest implementation state, validation, local runtime and next bounded task.

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
- Follow the cost-aware delegation policy below for implementation work.
- Do not copy external source code without an explicit compatible-license review; record uncertainty instead.

## Cost-aware delegation policy

- The primary agent keeps the user-selected chat model (Astra is preferred) and owns planning, contracts, critical decisions, integration, and final review. Project configuration must not force the top-level model or reasoning effort.
- Bundle a coherent implementation task with its targeted tests. Delegate bounded implementation and exploration to one Luna/low worker by default; use up to three workers only for independent, non-overlapping tasks. Do not duplicate parent implementation or split work by file. Simple replies stay with the primary agent.
- For coordinated work requiring more judgment, the primary may explicitly choose the `implementer_medium` profile (Luna/medium). This is a task-specific override, not an automatic escalation. Do not automatically escalate to Sol/Astra or high effort, and do not permit recursive delegation.
- Give a short fresh-context brief with objective, relevant paths/contracts, owned files, baseline dirty edits, invariants, non-goals, acceptance checks, risk, model/effort, and a two-repair-attempt stop. Use `fork_turns=none` unless a relevant continuation needs context; send concise deltas to a continuing worker and use a fresh worker for unrelated work. Never omit or truncate required skill/contract reading.
- Read targeted files with `rg` and batched independent reads; avoid rereading unchanged files. Keep logs concise and preserve full diagnostics on failure. Do not blindly rerun or poll. After two unsuccessful repairs of the same failure, stop and report evidence plus the next hypothesis; the primary replans a bounded next action rather than respawning into the same failure.
- Run targeted checks per patch and the required full suite at integration or risk checkpoints. Preserve every acceptance requirement. Critical math, security, migration, and independent-verification decisions require primary review; worker output is evidence, not approval.
- Numeric effort and budget guidance is behavioral, not a hard runtime token or cost cap. Do not change global, cache, compaction, credential, or security settings; these policies do not guarantee savings. Where runtime usage metadata is available, record it under ignored `artifacts/agent-costs/` and summarize it in the final report. Unknown measurements stay null; this is not automatic billing integration.
- Cost preferences never weaken correctness, reproducibility, security, solver, licensing, tests, or independent-verification requirements. Preserve fail-closed behavior and all applicable subsystem contracts.

## Required reading

- Domain and inputs: [`docs/DOMAIN_MODEL.md`](docs/DOMAIN_MODEL.md), [`docs/DESIGN_SPEC.md`](docs/DESIGN_SPEC.md), [`docs/MESH_PREFLIGHT.md`](docs/MESH_PREFLIGHT.md)
- Canonical IR: [`docs/CROCHET_IR.md`](docs/CROCHET_IR.md), [`docs/CANONICALIZATION.md`](docs/CANONICALIZATION.md)
- Solvers/topology: [`docs/SOLVER_ARCHITECTURE.md`](docs/SOLVER_ARCHITECTURE.md), [`docs/TOPOLOGY_SEAMLESS.md`](docs/TOPOLOGY_SEAMLESS.md)
- Physics/materials: [`docs/FORWARD_MODEL.md`](docs/FORWARD_MODEL.md), [`docs/MATERIAL_MODEL.md`](docs/MATERIAL_MODEL.md)
- Verification/tests: [`docs/VERIFICATION.md`](docs/VERIFICATION.md), [`docs/TEST_STRATEGY.md`](docs/TEST_STRATEGY.md), [`docs/FAILURE_POLICY.md`](docs/FAILURE_POLICY.md)
- Research/licensing: [`docs/RESEARCH.md`](docs/RESEARCH.md)
- Foundational decisions: [`docs/adr/`](docs/adr/)
