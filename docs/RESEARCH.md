# Research and clean-room policy

## Research status

- **ESTABLISHED:** Computational crochet, textile representations, geodesic processing, computational topology, and cloth/yarn simulation provide relevant concepts, but none is a drop-in correctness oracle for this project.
- **ENGINEERING DECISION:** External work informs independently written specifications and tests. `CrochetIR`, solvers, and verifiers remain project-native designs.
- **ENGINEERING DECISION:** Missing, ambiguous, restrictive, copyleft, or non-commercial source licenses stop code and dataset reuse until explicit review.
- **FUTURE:** A dependency or external dataset may be adopted only through a separate recorded license, security, maintenance, and common-mode review.

Last primary-source review for this bootstrap registry: **2026-08-31**. Repository evidence is pinned to the exact Git commit listed below rather than a mutable branch. License statements describe what the pinned official source stated at review time; they are not legal advice and must still be rechecked before reuse.

## Primary-source inspiration registry

| ID | Primary source | Reviewed repository revision | Established contribution or research lead | Applicability and limit | Code/data reuse status |
| --- | --- | --- | --- | --- | --- |
| `SRC-AMIGO` | Edelstein et al., [AmiGo: Computational Design of Amigurumi Crochet Patterns](https://doi.org/10.1145/3559400.3562005); [pinned official README](https://github.com/karinsifri/AmiGo/blob/38c2e6f9d8e216f24727a86873f61f7a089bac6c/README.md) | `38c2e6f9d8e216f24727a86873f61f7a089bac6c` | Crochet Graph construction from a closed mesh, geodesic-course concepts, and join-as-you-go amigurumi motivate the geodesic and topology research tracks. | Amigurumi-specific assumptions and demonstrated limitations do not establish general garments, lace, arbitrary branching, or this project's verifier. | Repository states CC BY-NC-SA 4.0. **No code, tests, or assets may be copied** under current policy; concepts only with attribution and independent derivation. |
| `SRC-CROCHETPARADE` | Tassev, [pinned CrochetPARADE manual](https://github.com/stassev/CrochetPARADE/blob/06e987b13ccfc94cfdfcebc1fe4664d37d2c6687/Manual.md) | `06e987b13ccfc94cfdfcebc1fe4664d37d2c6687` | A formal pattern language, explicit stitch graph, rendering, and debugging illustrate the value of executable crochet semantics. | Its grammar and runtime are not `CrochetIR` and are not an independent verification oracle. | Manual states computational components GPLv3 and manual CC BY-NC-SA 4.0. Concepts only; no code/manual text copying. |
| `SRC-CP-REMESHER` | Tassev, [pinned CrochetPARADE Remesher repository](https://github.com/stassev/CrochetPARADE_Remesher/tree/81f921d1ad2a5c2c975589361bd4e971f4c1c2c2) | `81f921d1ad2a5c2c975589361bd4e971f4c1c2c2` | Advancing-front, backtracking, frontier, and explicit failure concepts are relevant research leads for difficult surfaces. | A particular implementation is not evidence that its candidates satisfy this project's canonical, physical, or fail-closed contracts. | Repository states GPL-3.0-or-later. No source reuse without a deliberate project licensing decision; clean-room concepts only. |
| `SRC-STITCH-MESH` | Guo et al., [Representing Crochet with Stitch Meshes](https://textiles.cs.cmu.edu/publications/2020-crochet-meshes/), [DOI](https://doi.org/10.1145/3424630.3425409) | Not applicable: publication only | Explicit tiles, yarn continuity, previous/next loop relations, and past/future attachment relations support graph-first representation research. | Stitch meshes are an inspiration, not the canonical project IR; construction operations, frontier state, provenance, and verification remain separate requirements. | Publication may be cited. No verified implementation/library license was established in this review; no code or tile assets reused. |
| `SRC-DIGITAL-CROCHET` | Seitz et al., [Digital Crochet: Toward a Visual Language for Pattern Description](https://hirschfeld.org/writings/media/SeitzReinLinckeHirschfeld_2022_DigitalCrochetTowardAVisualLanguageForPatternDescription_AcmDL.pdf), [DOI](https://doi.org/10.1145/3563835.3567657) | Not applicable: publication only | Visual/domain-specific languages and executable pattern descriptions inform parser and authoring research. | User-facing notation does not replace unambiguous canonical semantics or independent validation. | Publication only reviewed. Associated implementation and artifact licenses remain unresolved; no reuse. |
| `SRC-SURF-REV` | Martinez and Lipnicki, [Automating Crochet Patterns for Surfaces of Revolution](https://arxiv.org/abs/2302.02205), [Bridges proceedings](https://archive.bridgesmathart.org/2023/bridges2023-195.html) | Not applicable: publication only | Meridional arc length, separate row/stitch gauge, circumference-derived counts, and distributed shaping support the analytic-solver research plan. | The method targets surfaces of revolution and does not establish general topology, physical fidelity, or global integer optimization requirements. | Paper concepts may be independently re-derived. A compatible license for the linked research code was not verified; no code reuse. |
| `SRC-GEOSTITCH` | [Pinned GeoStitch official repository](https://github.com/codebylexis/GeoStitch/tree/204384b67a41d4ee5ddb565d0e6502cce9898ad7) | `204384b67a41d4ee5ddb565d0e6502cce9898ad7` | Geodesic row/stitch coordinates, discrete distance, and angular optimization are research leads for parameterization experiments. | Repository claims and examples are not peer-reviewed acceptance evidence and do not replace Heat Method/topology analysis. | No license was verified at the pinned revision. **Unresolved: no code, tests, or assets may be reused.** |
| `SRC-CROCHETBENCH` | Li et al., [CrochetBench paper](https://arxiv.org/abs/2511.09483); [pinned official repository](https://github.com/Peiyu-Georgia-Li/crochetBench/tree/930b1962aae1be8875a8809fca02331775f9113c) | `930b1962aae1be8875a8809fca02331775f9113c` | Executable evaluation highlights the gap between textual similarity and structurally valid procedures. | It evaluates vision-language procedural reasoning, not deterministic geometry solvers or physical verification. CrochetPARADE execution is not this project's oracle. | Repository states code MIT and dataset CC BY-NC 4.0. Code still requires dependency review; dataset is not imported by default and non-commercial restrictions are a stop condition. |
| `SRC-HEAT` | Crane, Weischedel, Wardetzky, [The Heat Method for Distance Computation](https://arxiv.org/abs/1204.6216), [project/publication page](https://www.cs.cmu.edu/~kmcrane/Projects/HeatMethod/) | Not applicable: publication only | Heat-flow direction followed by a Poisson solve is an established method for approximate geodesic distance on suitable domains. | Discretization, boundary conditions, mesh quality, intrinsic operators, and convergence must be validated for project meshes. It does not solve crochet coupling or topology change. | Paper mathematics may be implemented independently with attribution. Each reference implementation has its own license and requires separate review. |
| `SRC-REEB` | Biasotti et al., [Reeb graphs for shape analysis and applications](https://doi.org/10.1016/j.tcs.2007.10.018) | Not applicable: publication only | Reeb graphs summarize connected components of level sets and motivate critical-point and branch-decomposition analysis. | A target Reeb graph is not a Construction Graph and never becomes CrochetIR automatically. Numerical stability and construction feasibility require separate work. | Publication concepts only; no source implementation selected. |
| `SRC-KNIT-YARN` | Kaldor, James, Marschner, [Simulating Knitted Cloth at the Yarn Level](https://www.cs.cornell.edu/~srm/publications/SG08-knit.html) | Not applicable: publication only | Yarn-level loop mechanics, inextensible flexible yarn, and yarn contact show why textile mechanics can differ from generic cloth. | The paper models knitting, not crochet. It motivates F2 only and does not validate F0 parameters. | Publication concepts only; no source-code license or reusable implementation established. |
| `SRC-SHELLS` | Grinspun et al., [Discrete Shells](https://doi.org/10.2312/SCA03/062-067) | Not applicable: publication only | Discrete stretching and bending energies motivate an intermediate anisotropic shell model. | Crochet is not a homogeneous shell; stitch direction, openings, branch topology, and stuffing need project-specific treatment. | Publication concepts only; implementation reuse not assessed. |
| `SRC-IPC` | Li et al., [Incremental Potential Contact](https://ipc-sim.github.io/); Li, Kaufman, Jiang, [Codimensional IPC](https://ipc-sim.github.io/C-IPC/) | Not applicable: publication only | Barrier-based nonpenetration, codimensional contact, thickness, strain limits, and friction are established high-fidelity research directions. | These methods are computationally heavier than F0 and do not identify crochet material parameters. They are future candidates, not V1 requirements. | Paper concepts only in this phase. Any code/dependency adoption requires exact license and transitive-dependency review. |
| `SRC-JCS` | Rundgren, Jordan, Erdtman, [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785); Bray, [RFC 7493 I-JSON](https://www.rfc-editor.org/rfc/rfc7493) and [RFC 8259 JSON](https://www.rfc-editor.org/rfc/rfc8259) | Immutable RFC publications | I-JSON constraints, IEEE 754 binary64 number serialization, recursive property ordering, unchanged array order, and UTF-8 provide the primary interoperability basis for structured content hashes. | JCS does not choose project collection semantics, safe integer bounds, or hash-domain separation; those remain explicit project decisions. | Standards text cited only; no external canonicalizer implementation copied. |
| `SRC-SHA256` | NIST, [FIPS 180-4 Secure Hash Standard](https://csrc.nist.gov/pubs/fips/180-4/upd1/final) | Immutable standard publication | Defines SHA-256 used for content-addressed artifacts and evidence. | A digest does not define the preimage; project profiles must specify canonical bytes and domain separation. | Standard algorithm; implementation comes from reviewed platform cryptography, not copied source. |
| `SRC-ROBUST-PREDICATES` | Jonathan Richard Shewchuk, [Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates](https://doi.org/10.1007/PL00009321), *Discrete & Computational Geometry* 18 (1997) | Not applicable: publication only | Adaptive error bounds and exact-sign escalation establish a primary mathematical basis for filtered orientation/incircle-style predicates on floating inputs. | The paper does not select project mesh tolerances, characteristic scale, contact semantics, or acceptance profiles; those remain explicit project decisions. | Publication mathematics cited only. No external predicate source code was copied or selected by this architecture pass. |

## Product research records

- [Yarnify3D review, 2026-10-04](research/YARNIFY3D_REVIEW_2026-10-04.md):
  public pattern-editor, preview and follow-along comparison with user-provided
  screenshots; recommendations only. Editor behavior behind login and physical
  accuracy remain untested. No external code, patterns or assets adopted.

## Adopted architecture versus inspiration

The following are project decisions, not claims that an external source proves the complete design:

- **ENGINEERING DECISION:** `CrochetIR` is canonical; external Crochet Graphs, stitch meshes, DSLs, and Construction Graphs are distinct representations.
- **ENGINEERING DECISION:** Analytic, geodesic, and frontier solvers are diverse candidate generators selected by domain and target class.
- **ENGINEERING DECISION:** An independent forward model receives no target geometry.
- **ENGINEERING DECISION:** V0-V10 verification is fail-closed and reports a metric vector rather than a single score.
- **ENGINEERING DECISION:** Structured hashes use project collection registries plus I-JSON/binary64 JCS and profile-domain-separated SHA-256.
- **HYPOTHESIS:** Heat-style geodesics plus Reeb/Morse-style analysis can support robust course/topology decomposition on project inputs.
- **HYPOTHESIS:** A calibrated anisotropic graph/spring F0 model is useful enough to reject poor candidates before more expensive physical models.

- [PDF and remote crochet testing, 2026-10-05](research/PROTOTYPE_PDF_REVIEW_2026-10-05.md):
  scoped PDF dependency/license review, current primary-source comparison and
  adopted versus future product improvements.

## Clean-room workflow

1. Open a research record with a precise question from [`RESEARCH_QUESTIONS.md`](RESEARCH_QUESTIONS.md).
2. Record source title, authors, DOI/official URL, accessed date, exact repository revision if applicable, and license evidence.
3. Extract only attributed mathematical ideas, empirical claims, assumptions, and limitations. Do not paste source code, tests, datasets, pattern text, proprietary figures, or implementation-specific pseudocode into project specifications.
4. Write a project-native contract stating invariants, inputs, outputs, failure modes, complexity/budget, and tests. Mark inference and hypotheses explicitly.
5. Implement from the project contract and primary mathematics. Record any external code consulted. Restrictive or uncertain code consultation triggers additional clean-room review before implementation is accepted.
6. Create original fixtures from equations or licensed project assets. Do not translate an external regression suite into this repository without explicit permission.
7. Before adding a dependency or dataset, review exact revision, license, notices, patents where relevant, transitive dependencies, security/maintenance, telemetry, and compatibility with intended distribution.
8. Keep external implementations optional. CI correctness never depends on a network service or third-party executable as the authoritative oracle.

Independent reimplementation still requires attribution to relevant research. “Clean room” is an engineering separation policy, not a claim of legal immunity.

## Stop conditions

Do not copy or adapt external implementation material when:

- the license is absent or cannot be tied to the exact files/revision;
- the terms are non-commercial or share-alike and project compatibility has not been explicitly approved;
- GPL or another copyleft obligation has not been deliberately accepted for this project;
- dataset provenance or downstream redistribution rights are unclear;
- a paper is accessible but its code/assets have no separate permission;
- the source would become a mandatory oracle whose assumptions overlap the solver under test.

Record the blocked source and continue with public mathematical literature, a clean independent design, or a permissively licensed dependency after review. Never infer permission from public availability.

## Research record output

Every completed research question reports:

- evidence label: `PROVEN / FORMAL`, `ESTABLISHED`, `ENGINEERING DECISION`, `HYPOTHESIS`, or `FUTURE`;
- cited primary sources and exact applicability limits;
- license status for every inspected code/data artifact;
- adopted decision or explicit “not adopted” outcome;
- unresolved uncertainty and the experiment/proof needed next;
- affected contract, ADR, fixture, and owner.
