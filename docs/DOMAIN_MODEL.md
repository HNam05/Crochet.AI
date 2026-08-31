# Domain Model

## Status vocabulary

- **PROVEN / FORMAL** denotes a logical invariant that follows from the model.
- **ESTABLISHED** denotes terminology or a technique supported by standards or published domain practice.
- **ENGINEERING DECISION** denotes a versioned project choice.
- **HYPOTHESIS** denotes a claim requiring numerical or physical calibration.
- **FUTURE** denotes an intended extension that is not an implemented capability.

These labels describe the strength of a claim, not the verification state of an individual pattern.

## Compiler boundary

The shared pipeline has four distinct artifacts:

1. `DesignSpec` records validated design intent, dimensions, material binding, and acceptance constraints.
2. A solver-private target model and optional `ConstructionGraph` record geometric analysis and a proposed construction strategy.
3. `CrochetIR` records the complete executable crochet construction.
4. Independent verification reports record structural, topological, physical, geometric, robustness, and export evidence.

**ENGINEERING DECISION:** `CrochetIR` is the only canonical construction representation. A `DesignSpec`, localized pattern text, target mesh, stitch mesh used inside a solver, or topology-planning `ConstructionGraph` cannot substitute for it.

**PROVEN / FORMAL:** `DesignSpec` cannot be an authoritative source of final stitch quantities. Those quantities first become authoritative as explicit, solver-produced nodes in `CrochetIR`, subject to verification.

**ENGINEERING DECISION:** A verification report references an immutable canonical IR hash. Verification does not amend an IR candidate in place.

## Shared domain concepts

| Concept | Meaning | Canonical owner |
| --- | --- | --- |
| design intent | Requested dimensions, shape, material, construction limits, and verification requirements | `DesignSpec` |
| target geometry | Analytic, mesh, planar, measurement, or motif-graph target used by a solver and later by geometry comparison | referenced by `DesignSpec` |
| construction plan | Solver-private branch/frontier strategy, possibly a Reeb- or Morse-style `ConstructionGraph` | solver |
| stitch semantics | A typed yarn operation with explicit incoming attachment locations and resulting top locations | `CrochetIR.stitches` |
| construction operation | A non-stitch state/topology action such as `JOIN`, `SPLIT`, or `COLOR_CHANGE` | `CrochetIR.construction_operations` |
| frontier | An ordered boundary of currently available attachment locations plus topology and lifecycle state | `CrochetIR.frontiers` and transitions |
| course | An explicitly ordered row, round, or motif pass | `CrochetIR.courses` |
| material response | Measured horizontal and vertical gauge plus bounded uncertainty; yarn and hook metadata are priors | `MaterialProfile` |
| evidence | Independent gate results and metric values | verification report |

All physical lengths are expressed in millimetres and masses in grams at schema boundaries. No locale-dependent numeric representation is permitted.

## Solver domains

The canonical project types are:

- `AMIGURUMI_3D`: stuffed or unstuffed three-dimensional forms;
- `GARMENT`: body-measurement, ease, drape, panel, yoke, and sleeve problems;
- `FLAT`: rows, rounds, grids, repeats, tiling, motifs, and colour regions;
- `LACE_MOTIF`: topology- and motif-heavy constructions.

**ENGINEERING DECISION:** These domains share schemas, stitch semantics, IR, export, provenance, material concepts, and verification infrastructure. They do not share one universal geometry solver. In particular, garments are not routed through an amigurumi solver merely to reuse code.

**FUTURE:** Garment cloth response, C2C/tapestry/mosaic/filet expansion, and complete lace primitives require their own typed solver and semantic specifications.

## Canonical stitch vocabulary

Internal stitch identifiers are independent of human terminology:

| Canonical identifier | US English export | UK English export | German export |
| --- | --- | --- | --- |
| `CHAIN` | chain (`ch`) | chain (`ch`) | Luftmasche (`Lm`) |
| `SLIP_STITCH` | slip stitch (`sl st`) | slip stitch (`sl st`) | Kettmasche (`Km`) |
| `SINGLE_CROCHET` | single crochet (`sc`) | double crochet (`dc`) | feste Masche (`fM`) |
| `HALF_DOUBLE_CROCHET` | half double crochet (`hdc`) | half treble crochet (`htr`) | halbes Stäbchen (`hStb`) |
| `DOUBLE_CROCHET` | double crochet (`dc`) | treble crochet (`tr`) | Stäbchen (`Stb`) |
| `TREBLE_CROCHET` | treble crochet (`tr`) | double treble crochet (`dtr`) | Doppelstäbchen (`DStb`) |

**ESTABLISHED:** US and UK crochet names conflict, including the meaning of `dc`. Therefore abbreviations and localized names are never accepted as canonical semantics.

**ENGINEERING DECISION:** Localization tables exist only at import/export boundaries. Importers must select a declared terminology profile and reject ambiguous undeclared terminology.

## Stitch arity, shaping, and executable V1 scope

A stitch node declares both:

- `base_arity`: the number of prior attachment locations used by the node;
- `top_arity`: the number of resulting attachment locations created by the node.

The referenced earlier nodes and locations remain in the graph. Only frontier availability changes.

**PROVEN / FORMAL:** Saying that a prior stitch was "consumed" cannot delete it or transfer its identity. An advance retires an attachment location from a frontier and creates new locations; it does not consume graph nodes.

The representational vocabulary and executable semantic profile are distinct. The schema exposes the six stable ordinary families so later domains do not require an IR redesign. `CROCHET_CORE_1.0.0` executes only these forms:

| Form | `shaping` | `base_arity` | `top_arity` | V1 status |
| --- | --- | ---: | ---: | --- |
| `CHAIN` | `PLAIN` | 0 | 1 | executable |
| any listed non-chain family | `PLAIN` | 1 | 1 | executable |
| `SINGLE_CROCHET` increase | `INCREASE` | 1 | 2 | executable |
| `SINGLE_CROCHET` decrease | `DECREASE` | 2 | 1 | executable |
| non-SC or n-ary shaping | `INCREASE` / `DECREASE` | profile-defined | profile-defined | rejected by V1 with `E_UNSUPPORTED_FEATURE` |

The exact ordered attachment lists are authoritative; the integer arities are redundant assertions checked independently. This generalized representation permits taller stitch families without changing graph structure.

**ENGINEERING DECISION:** `INCREASE` and `DECREASE` are derived shaping classifications on one typed stitch-application node. They are not canonical stitch families, construction operations, or ambiguous textual macros. V1 recomputes `shaping` from the family and exact arity tuple; a mismatch is `E_COUNT`, not an alternative interpretation. A compiler may lower a compound node for physical simulation or localized export, but semantic round trips must recover the same compound node, ordered bases, and ordered tops.

Two plain stitches that share a base are not V1-equivalent to one increase node. This strict grouping prevents a parser from guessing whether prose described one shaping application or multiple independent events. [ADR-0007](adr/0007-v1-executable-stitch-and-operation-semantics.md) records the alternatives and migration boundary.

## Construction operations

The initial operation vocabulary is:

- `MAGIC_RING`: create a typed ring anchor and initial cyclic frontier;
- `SPLIT`: derive two or more branch frontiers from one frontier;
- `RESERVE`: retain a declared portion for later work while another portion proceeds;
- `ATTACH`: start or reattach yarn at an explicit location/frontier;
- `JOIN`: combine two or more frontiers by a declared crocheted or sewn method;
- `COLOR_CHANGE`: switch explicitly between yarn/color sources;
- `CUT_YARN`: terminate a yarn-path segment;
- `CLOSE`: move a frontier to the closed lifecycle state;
- `DECLARE_OPENING`: associate a boundary with an intentional design opening.

**ENGINEERING DECISION:** `JOIN`, `SPLIT`, `ATTACH`, and `COLOR_CHANGE` are construction operations, never ordinary stitch enum values. `MAGIC_RING` is a construction anchor/macro, not a magical primitive stitch.

`CROCHET_CORE_1.0.0` also executes `RESERVE`, `CUT_YARN`, `CLOSE`, and `DECLARE_OPENING`. They are required accounting operations rather than optional solver features: omitting them would make reserved branches, yarn discontinuities, closure, and intentional boundaries unverifiable.

**PROVEN / FORMAL:** Every operation is totally ordered in the construction sequence, uses typed references, and has an independently validated frontier/yarn state transition. No operation may silently infer an omitted target.

## Frontier semantics

A frontier has two orthogonal attributes:

- topology: `LINEAR` or `CYCLIC`;
- lifecycle: `ACTIVE`, `RESERVED`, `CLOSED`, or `DECLARED_OPEN`.

It also has an ordered list of available attachment-location IDs, a component and branch, and an active yarn or explicit `null`. A cyclic frontier records an anchor location so that its serialization has a deterministic origin.

Frontiers are immutable snapshots over ordered attachment-location IDs. Direct stitch IDs are insufficient because one stitch may produce multiple usable locations. Numeric ranges and a separate persistent-segment entity are not canonical V1 references. Ordered transitions create, advance, split, reserve, reattach, join, close, or declare an opening. Stitch order within a course provides the fine-grained advance; snapshots are required at course and topology/lifecycle boundaries.

Replay maintains one ownership ledger. Every produced attachment location is exactly one of active-live, reserved-live, retired, or retained on one declared-open boundary. It cannot be live in two frontiers. A branch-local reserved frontier is the persistent segment; solvers may compress it privately but must compile explicit IDs.

**PROVEN / FORMAL:** A terminal boundary is valid only when its immutable snapshot is `CLOSED` or `DECLARED_OPEN`; the latter must be covered exactly by an explicitly declared intentional opening. Any other terminal open boundary is unintended and fails verification.

**PROVEN / FORMAL:** A reserved frontier remains accountable until it is reattached, joined, closed, or declared as an opening. Losing a reserved branch is an error.

See [CROCHET_IR.md](CROCHET_IR.md) for the complete transition contract.

## Materials and geometry

**ESTABLISHED:** Horizontal stitch gauge and vertical course gauge describe different physical directions and are not interchangeable.

**ENGINEERING DECISION:** `MaterialProfile` stores effective stitch pitch and course pitch separately. Hook diameter and yarn metadata provide priors only. A design binds either an inline profile or a content-addressed profile reference.

**HYPOTHESIS:** First-order pitch measurements and bounded uncertainty are sufficient for the initial analytic solver and F0 forward model. Physical calibration must confirm or reject this.

The target geometry is available to solvers and to target-versus-result comparison. It is forbidden as a constraint or corrective field inside the independent forward simulator.

## Support and failure boundary

Schema acceptance means only that an artifact has the expected local shape. Independent semantic validation must also resolve all references, replay construction state, check arities, enforce capability support, and reject illegal transitions.

**ENGINEERING DECISION:** Unsupported stitch, lace, garment, or construction semantics fail explicitly. The presence of extensible graph locations such as chain spaces or motif attachment points does not imply operational support.

**FUTURE:** Typed chain spaces, picots, post stitches, clusters, puffs, bobbles, fans/shells, and motif attachment operations will be added through versioned semantic profiles, not overloaded basic stitch names.
