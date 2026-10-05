# Specification index

These documents are contracts. Labels distinguish **PROVEN / FORMAL**, **ESTABLISHED**, **ENGINEERING DECISION**, **HYPOTHESIS**, and **FUTURE** statements.

Backend continuation starts at [`BACKEND_HANDOFF.md`](BACKEND_HANDOFF.md).

## Product and representations

- [`PRODUCT.md`](PRODUCT.md)
- [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md)
- [`DESIGN_SPEC.md`](DESIGN_SPEC.md)
- [`CROCHET_IR.md`](CROCHET_IR.md)
- [`CANONICALIZATION.md`](CANONICALIZATION.md)
- [`GEOMETRY_MODEL.md`](GEOMETRY_MODEL.md)

## Solving and topology

- [`SOLVER_ARCHITECTURE.md`](SOLVER_ARCHITECTURE.md)
- [`ANALYTIC_SOLVER.md`](ANALYTIC_SOLVER.md)
- [`ANALYTIC_SEARCH_TRACE_V1.md`](ANALYTIC_SEARCH_TRACE_V1.md): input-bound producer search evidence, separate from verification
- [`ANALYTIC_TARGET_V1.md`](ANALYTIC_TARGET_V1.md): explicit sphere/ellipsoid targets and bounded target-side sampling
- [`GEODESIC_SOLVER.md`](GEODESIC_SOLVER.md)
- [`FRONTIER_SOLVER.md`](FRONTIER_SOLVER.md)
- [`TOPOLOGY_SEAMLESS.md`](TOPOLOGY_SEAMLESS.md)
- [`MESH_PREFLIGHT.md`](MESH_PREFLIGHT.md)
- [`NUMERICAL_GEOMETRY.md`](NUMERICAL_GEOMETRY.md)

## Physics and materials

- [`FORWARD_MODEL.md`](FORWARD_MODEL.md)
- [`FORWARD_CLOSED_CELLS_V1.md`](FORWARD_CLOSED_CELLS_V1.md): target-free topology-only INC/DEC cells and caps
- [`MATERIAL_MODEL.md`](MATERIAL_MODEL.md)
- [`PHYSICAL_VALIDATION.md`](PHYSICAL_VALIDATION.md)
- [`CALIBRATION_CAMPAIGNS.md`](CALIBRATION_CAMPAIGNS.md): frozen pilot records, draft gauge and printable measurement sheets

## Assurance

- [`BACKEND_IMPLEMENTATION_ROADMAP.md`](BACKEND_IMPLEMENTATION_ROADMAP.md): complete ordered backend implementation plan
- [`BACKEND_ACCEPTANCE_PLAN.md`](BACKEND_ACCEPTANCE_PLAN.md): implementation state and acceptance checkpoints
- [`VERIFICATION.md`](VERIFICATION.md)
- [`VERIFICATION_PIPELINE.md`](VERIFICATION_PIPELINE.md): implemented gate orchestration checkpoint and remaining gate boundaries
- [`SURFACE_TOPOLOGY_AUDIT_V1.md`](SURFACE_TOPOLOGY_AUDIT_V1.md): independent closed-surface manifold, Euler and Betti checks
- [`CLOSED_CELL_CONFORMANCE_V1.md`](CLOSED_CELL_CONFORMANCE_V1.md): independent raw-IR stitch-to-face and cap conformance
- [`ANALYTIC_CANDIDATE_CLAIMS_V1.md`](ANALYTIC_CANDIDATE_CLAIMS_V1.md): independent schedule and bound claims, with explicit incomplete V5 search evidence
- [`FAILURE_POLICY.md`](FAILURE_POLICY.md)
- [`TEST_STRATEGY.md`](TEST_STRATEGY.md)
- [`BENCHMARKS.md`](BENCHMARKS.md)

## Research and decisions

- [`RESEARCH.md`](RESEARCH.md)
- [`RESEARCH_QUESTIONS.md`](RESEARCH_QUESTIONS.md)
- [`adr/`](adr/)

When documents disagree, stop implementation and resolve the contract conflict with an ADR or explicit specification revision. JSON Schemas define serialized shape; Markdown specifications add semantic invariants that JSON Schema cannot express.
