# Crochet.AI

Crochet.AI is a research-grade foundation for a deterministic crochet CAD/compiler. Its long-term purpose is to translate a strict `DesignSpec` into physically plausible, formally valid, independently verified crochet instructions.

Milestone 0 is implemented: strict `DesignSpec`, `MaterialProfile`, and
`CrochetIR` runtime models; deterministic canonicalization and hashing; an
independent V1 semantic validator; and execution-normalized semantic
equivalence. The repository also contains a local human-test prototype and
bounded experimental forward-model components. Production solver acceptance,
LLM integration and physical verification remain open.

The working backend now also includes the non-branching
[Pattern V1 parser/exporter](docs/PATTERN_FORMAT_V1.md), the separately versioned
[multi-stitch ring extension](docs/adr/0016-versioned-multi-stitch-ring-sites.md),
an exact bounded [analytic count-search kernel](docs/ANALYTIC_COUNT_SEARCH.md),
closed-pole analytic candidate compilation, a versioned local API/CLI, durable
SQLite jobs, and a target-free physical-semantic projection. Read
[backend runtime usage and limits](docs/BACKEND_RUNTIME.md). These are research
components, not a production solver or physical simulator. See the
[backend acceptance plan](docs/BACKEND_ACCEPTANCE_PLAN.md) for remaining packages.

## Local crochet test

Open `Start-CrochetPrototype.cmd` (prefers the existing `.venv`) or run
`.\.venv\Scripts\python.exe tools/run_prototype.py`, then
visit <http://127.0.0.1:8765>. The local browser prototype generates single-color
sphere/ellipsoid/cylinder/cone/capsule/pear trial patterns from editable dimensions
and cyclic gauge, shows a schematic stitch layout, saves progress and records
test feedback. PDF export includes print instructions and a report worksheet
for a crocheter away from this computer; it requires no server at the recipient.
Results remain **NOT_VERIFIED / UNTESTED** until the required independent and
physical checks exist. Replace the demonstration gauge with your measurements.
See [the German testing guide](docs/PROTOTYP_TESTEN.md) and
[the prototype contract](docs/LOCAL_PROTOTYPE_V1.md). A separate mobile app is
deferred until after this browser test.

## Architectural contract

```text
natural language or image (optional, non-authoritative)
                         |
                         v
                    DesignSpec
                         |
                         v
        domain-specific candidate solvers
                         |
                         v
                 canonical CrochetIR
                         |
          +--------------+--------------+
          |                             |
          v                             v
 independent semantic validator   independent forward model
          |                             |
          +--------------+--------------+
                         |
                         v
       topology, geometry, robustness, and export gates
                         |
                         v
          verified human-readable pattern or rejection
```

`DesignSpec`, a solver's Construction Graph, and `CrochetIR` are distinct representations. CrochetIR is the canonical construction record. The forward model reconstructs predicted geometry only from a versioned physical-semantic projection of CrochetIR plus material/loading parameters; that projection excludes target identity, target-role provenance, and solver provenance as well as target geometry itself.

## Priorities

Candidate selection is lexicographic:

1. pass every hard structural and verification gate;
2. remain inside the hard geometry acceptance region;
3. minimize sewn seams;
4. minimize yarn cuts and reattachments;
5. minimize residual geometric error;
6. minimize unnecessary construction complexity.

The system rejects questionable results instead of averaging a critical failure into a score.

## Repository map

- [`docs/PRODUCT.md`](docs/PRODUCT.md): mission, scope, and roadmap
- [`docs/DESIGN_SPEC.md`](docs/DESIGN_SPEC.md): deterministic input boundary
- [`docs/CROCHET_IR.md`](docs/CROCHET_IR.md): canonical graph and frontier semantics
- [`docs/CANONICALIZATION.md`](docs/CANONICALIZATION.md): language-independent structured bytes and hashes
- [`docs/MESH_PREFLIGHT.md`](docs/MESH_PREFLIGHT.md): domain-specific V0 target validation profiles
- [`docs/SOLVER_ARCHITECTURE.md`](docs/SOLVER_ARCHITECTURE.md): diverse solver families and candidate selection
- [`docs/FORWARD_MODEL.md`](docs/FORWARD_MODEL.md): independent physical reconstruction contract
- [`docs/VERIFICATION.md`](docs/VERIFICATION.md): fail-closed V0-V10 gates
- [`docs/TEST_STRATEGY.md`](docs/TEST_STRATEGY.md): falsification-oriented test architecture
- [`schemas/`](schemas/): JSON Schema 2020-12 contracts
- [`docs/adr/`](docs/adr/): foundational architecture decisions
- [`.codex/`](.codex/): project Codex configuration and custom agents
- [`.agents/skills/`](.agents/skills/): focused project-local skills

## Development milestones

1. Specifications, schemas, repository structure, and test architecture.
2. **Current:** `DesignSpec` and canonical `CrochetIR` data types, JCS/domain-separated hashing, independent semantic validation, and V1 semantic equivalence.
3. Implemented non-branching parser/exporter subset; advanced M1B operations remain open.
4. In progress: analytic candidate pipeline; independent physical acceptance remains open.
5. F0 graph/spring forward model and geometric metric stack.
6. Physical benchmark calibration and threshold revision.
7. Geodesic solver experiments.
8. Seamless topology and bounded frontier solver experiments.
9. Separate garment, flat-crochet, and lace solver families.

The implementation milestone must not begin implicitly as part of an architecture pass.

## Status and evidence

No generated pattern should be called verified until all required gates have executable implementations and pass for that artifact. Physical status is reported separately as `UNTESTED`, `CALIBRATED`, or `PHYSICALLY_VERIFIED`.

## License and clean-room policy

Repository-authored work is released under the [Unlicense](LICENSE). Research may inform mathematical ideas, but external source code is not copied into this project unless its license is explicitly reviewed and compatible. See [`docs/RESEARCH.md`](docs/RESEARCH.md).
