# Canonical CrochetIR

Normative schema: [`schemas/crochet-ir.schema.json`](../schemas/crochet-ir.schema.json)

## Role and trust boundary

`CrochetIR` is the canonical, executable construction graph shared by all solver families, verifiers, forward models, parsers, and exporters.

**ENGINEERING DECISION:** A solver-private `ConstructionGraph` may plan primary paths, branches, frontier splits/merges, reattachments, and unavoidable seams. It is neither CrochetIR nor a pattern. A candidate becomes eligible for shared verification only after complete compilation to CrochetIR.

**PROVEN / FORMAL:** Local JSON Schema validity is necessary but cannot establish graph-wide reference resolution, event order, arity equality, frontier conservation, yarn continuity, or absence of unintended boundaries. The independent semantic validator must replay these invariants.

## Versioned envelope

Every artifact declares:

- `schema_version = "1.0.0"`;
- `semantics_profile = "CROCHET_CORE_1.0.0"`;
- an explicit `crochet_ir_id`;
- a content-addressed `design_spec_ref`;
- fixed units: millimetres, grams, and radians;
- `required_capabilities`, which an implementation must support or reject.

All defined object boundaries are closed. IDs are ASCII and type-prefixed. References are explicit; array position is never an implicit cross-reference.

`CROCHET_CORE_1.0.0` is an executable semantic profile, not a claim that every schema-extensible combination is supported. It accepts plain `CHAIN`, `SLIP_STITCH`, `SINGLE_CROCHET`, `HALF_DOUBLE_CROCHET`, `DOUBLE_CROCHET`, and `TREBLE_CROCHET`; binary SC increase/decrease; and all nine declared construction/accounting operations. Non-SC shaping, n-ary shaping, chain spaces, motif attachments, and advanced lace primitives require another capability/profile and otherwise fail with `E_UNSUPPORTED_FEATURE`. See [ADR-0007](adr/0007-v1-executable-stitch-and-operation-semantics.md).

## Entity tables and explicit order

| Table | Meaning |
| --- | --- |
| `colors` | Stable colors used by yarn sources |
| `yarns` | Physical yarn sources bound to content-addressed `MaterialProfile` revisions and one color |
| `attachment_locations` | Typed graph locations created by exactly one stitch or construction operation |
| `stitches` | Canonical stitch-family nodes with explicit bases and results |
| `construction_operations` | Non-stitch topology, lifecycle, yarn, color, and opening actions |
| `construction_sequence` | Total executable order plus active yarn/color state before and after each event |
| `courses` / `course_order` | Ordered row, round, or motif-pass membership |
| `frontiers` / `frontier_transitions` | Immutable boundary snapshots and ordered state transitions |
| `branches` / `components` | Explicit branch DAG and independently started construction components |
| `openings` | Declared intentional boundaries |
| `yarn_paths` | Ordered yarn segments bounded by attach/start and optional cut operations |
| `derivations` | Solver rule and parameter-hash trace for generated entities |
| `provenance` | Generator, complete flat parameter list/hash, seed, budget, inputs, commit, and canonicalization profile |

Entity-table order is non-semantic. All semantic order is explicit through indexes or ID arrays such as `construction_sequence.sequence_index`, `course_order`, course `member_event_ids`, ordered attachment lists, transition indexes, and yarn-segment `event_ids`.

## Stitch and attachment semantics

The canonical stitch enum is exactly:

`CHAIN`, `SLIP_STITCH`, `SINGLE_CROCHET`, `HALF_DOUBLE_CROCHET`, `DOUBLE_CROCHET`, `TREBLE_CROCHET`.

US/UK/German names and abbreviations never occur as stitch semantics. They are exporter profiles.

Each stitch declares `stitch_type`, `shaping`, `base_arity`, `top_arity`, ordered base and top attachment-location IDs, yarn, color, course, and derivation.

**PROVEN / FORMAL:**

- `base_arity == len(base_attachment_location_ids)`;
- `top_arity == len(top_attachment_location_ids)`;
- each top location has exactly one producer, the declaring stitch, at the matching ordinal;
- a base reference resolves to a location available on the applicable input frontier before the stitch event;
- a stitch event precedes every later use of its top locations.

Core arity rules are:

| Form | Base | Top |
| --- | ---: | ---: |
| `CHAIN` + `PLAIN` | 0 | 1 |
| non-chain + `PLAIN` | 1 | 1 |
| `SINGLE_CROCHET` + `INCREASE` | 1 | 2 |
| `SINGLE_CROCHET` + `DECREASE` | 2 | 1 |

Earlier stitches remain immutable graph nodes. Frontier transitions retire attachment availability, not stitches. `shaping` is a redundant, independently checked classification of the V1 family/arity tuple. Two plain SC nodes sharing a base are not the same canonical construction as one SC increase node.

Attachment location types are `TOP_LOOP`, `MAGIC_RING_ANCHOR`, `CHAIN_SPACE`, `FABRIC_ATTACHMENT_POINT`, and `MOTIF_ATTACHMENT_POINT`. The latter typed locations are extensibility points; capability support remains mandatory.

## Construction operations

Construction operations are separate from stitches:

| Operation | Required semantic effect |
| --- | --- |
| `MAGIC_RING` | create a ring anchor and initial cyclic frontier |
| `SPLIT` | one input frontier to at least two output branch frontiers |
| `RESERVE` | partition an input into continuing and reserved output obligations |
| `ATTACH` | explicitly start or reattach a yarn at declared locations/frontiers |
| `JOIN` | at least two frontiers to one, with `CROCHETED` or `SEWN` method |
| `COLOR_CHANGE` | one input yarn source to one output source, reflected in active yarn/color state |
| `CUT_YARN` | terminate one active yarn segment |
| `CLOSE` | terminate a frontier as `CLOSED` |
| `DECLARE_OPENING` | terminate a boundary as `DECLARED_OPEN` and link an opening record |

Every operation records all input/output frontier, attachment, and yarn references, even when the corresponding list is empty. Irrelevant fields use the explicit neutral value (`[]`, `null`, or `NONE`), not omission. The schema additionally makes the following operation contract fail-closed; cross-reference and lifecycle checks remain semantic-validator duties.

| Operation | Frontier cardinality | Attachment and yarn fields | Required neutral fields |
| --- | --- | --- | --- |
| `MAGIC_RING` | 0 input, 1 output | exactly 1 created ring anchor; 0 input and 1 output yarn | `join_input_mappings = []`, `opening_id = null`, `design_requirement_id = null`, `join_method = NONE` |
| `JOIN` | at least 2 input, exactly 1 output | at least 1 mapped attachment and at least 2 ordered `join_input_mappings`; no yarn-source transition | `opening_id = null`, `design_requirement_id = null` |
| `SPLIT` | exactly 1 input, at least 2 output | no direct attachment or yarn-source change | both opening fields `null`, `join_method = NONE` |
| `RESERVE` | exactly 1 input, at least 2 output | no direct attachment or yarn-source change | both opening fields `null`, `join_method = NONE` |
| `ATTACH` | 0 or 1 input, exactly 1 output | exactly 1 attachment, 0 input and 1 output yarn | both opening fields `null`, `join_method = NONE` |
| `COLOR_CHANGE` | 0 input, 0 output | no attachment; exactly 1 input and 1 output yarn | both opening fields `null`, `join_method = NONE` |
| `CUT_YARN` | 0 input, 0 output | no attachment; exactly 1 input and 0 output yarn | both opening fields `null`, `join_method = NONE` |
| `CLOSE` | exactly 1 input, exactly 1 terminal output | no direct attachment or yarn-source change | both opening fields `null`, `join_method = NONE` |
| `DECLARE_OPENING` | exactly 1 input, exactly 1 terminal output | no direct attachment or yarn-source change | non-null `opening_id` and `design_requirement_id`; `join_method = NONE` |

For `JOIN`, `attachment_location_ids` is the ordered join-site declaration and equals the ordered concatenation of every mapping's consumed locations. Each `join_input_mappings` item explicitly names one input frontier, its `FORWARD`/`REVERSED` orientation, and its consumed locations. After orienting each input, the output frontier sequence is the concatenation, in declared input-frontier order, of the locations not consumed by its mapping. If none remain, the sole output is `CLOSED`; otherwise it is `ACTIVE`. The paired `JOIN` transition retires exactly the consumed union and creates no locations. This rule is independent of solver geometry and makes a frontier merge executable rather than inferred from array position. `join_input_mappings` is required and `[]` for every non-`JOIN` operation. `ATTACH` with no input frontier starts an independent component; with one input frontier it is only legal when the paired transition is `REATTACH` from a reserved frontier.

**PROVEN / FORMAL:** A `JOIN`, `SPLIT`, `ATTACH`, or `COLOR_CHANGE` cannot be encoded as a stitch. `MAGIC_RING` is an anchor-producing construction macro, not a stitch type.

## Construction sequence and courses

Each stitch and construction operation occurs exactly once in `construction_sequence`. Sequence indexes are unique and contiguous from zero. Each event records active yarn and derived active color before and after it, plus any frontier-transition IDs caused at that point.

**PROVEN / FORMAL:** Adjacent events have matching yarn/color boundary state: event `i.after == event i+1.before`. A stitch event has a non-null active yarn equal to the stitch yarn, and its color equals the referenced yarn/color.

A course explicitly records component, branch, form (`LINEAR` or `CYCLIC`), turn mode, work direction, ordered member events, and input/output frontiers. `course_order` contains every course ID exactly once. Every stitch belongs to exactly one course, and the forward and reverse membership references agree.

## Frontier state machine

A frontier is an immutable snapshot containing:

- `topology`: `LINEAR` or `CYCLIC`;
- `lifecycle_state`: `ACTIVE`, `RESERVED`, `CLOSED`, or `DECLARED_OPEN`;
- an ordered set of currently available attachment locations;
- component, branch, active yarn, and creating transition;
- for available cyclic frontiers, a mandatory anchor that fixes serialization origin.

The canonical reference unit is an attachment location, never its producer stitch. A cyclic live frontier's first `attachment_location_ids` member equals `anchor_attachment_location_id`; a rotated array with the same anchor is invalid rather than a second serialization. A reserved frontier object is the persistent V1 segment. Numeric ranges, implicit cursors, and cross-frontier shared live locations are forbidden.

### Ownership ledger

After every event, the validator maintains a total map for every produced attachment location:

```text
ACTIVE(frontier_id, ordinal)
RESERVED(frontier_id, ordinal)
RETIRED(causing_event_id)
DECLARED_OPEN(opening_id, ordinal)
```

These states are mutually exclusive and exhaustive. `CLOSED` is a terminal frontier state, not a fifth location state: closing retires all locations that were live on the input frontier. An attachment may move from active to reserved and back without changing identity, but after retirement or declaration as an opening it never becomes live again.

Transitions are totally ordered and occur after a declared construction event. Each records `caused_by_subject_ref`, which must name the same subject as the construction-sequence event at `after_event_index`. Types are `CREATE`, `ADVANCE`, `SPLIT`, `RESERVE`, `REATTACH`, `JOIN`, `CLOSE`, and `DECLARE_OPENING`. Each names input/output snapshots and the created, retired, or reserved attachment-location deltas.

| Transition | Input/output snapshots | Required deltas and lifecycle result |
| --- | --- | --- |
| `CREATE` | 0 / 1 | at least one `created` location; no retired/reserved locations; output `ACTIVE` |
| `ADVANCE` | 1 / 1 | retired bases and created tops are explicit; no reserved locations; output `ACTIVE` |
| `SPLIT` | 1 / at least 2 | no created/reserved locations; output frontiers are `ACTIVE` and partition input availability |
| `RESERVE` | 1 / at least 2 | at least one reserved location; no created locations; exactly one continuing `ACTIVE` and at least one `RESERVED` output |
| `REATTACH` | 1 / 1 | all three deltas empty; `RESERVED` input becomes `ACTIVE` output and is paired with `ATTACH` |
| `JOIN` | at least 2 / 1 | no created/reserved locations; retired locations and explicit join mapping account for all consumed inputs |
| `CLOSE` | 1 / 1 | no created/reserved locations; all available input locations are retired; output `CLOSED` |
| `DECLARE_OPENING` | 1 / 1 | all deltas empty; output `DECLARED_OPEN` retains the declared boundary locations and has the matching non-null `opening_id` |

The schema enforces these cardinalities and neutral deltas where local information is sufficient. The independent validator enforces set equality, ordered partitioning, exact lifecycle states, operation/transition pairing, and reference resolution.

**PROVEN / FORMAL:**

1. A frontier snapshot is produced by exactly one transition and used only after that transition.
2. `RESERVED` frontiers cannot advance until an explicit `REATTACH` transition paired with `ATTACH`.
3. `ADVANCE` is an ordered rewrite: it preserves unused relative order, retires exactly the event's ordered bases, and inserts exactly that event's ordered tops at the rewrite position.
4. `SPLIT` partitions the declared available locations into disjoint ordered subsequences without loss, duplication, or a shared live junction.
5. `RESERVE` partitions one active sequence into exactly one active output and one or more reserved ordered outputs; its reserved delta equals their union.
6. `REATTACH` changes one reserved sequence to active without an attachment delta.
7. `JOIN` applies the explicit orientation/consumed mapping above and creates exactly one active or closed output.
8. `CLOSED` has no available locations or active yarn.
9. `DECLARED_OPEN` is linked exactly once to an `opening` and `DECLARE_OPENING` operation, and that operation plus the opening both carry the same non-null `DesignSpec.intentional_openings[].opening_requirement_id`.
10. Every initial, split, and reserved frontier obligation eventually reaches `CLOSED`, `DECLARED_OPEN`, or a validated join.

Stitch order within a course supplies fine-grained advancement. Immutable snapshots are required at course and topology/lifecycle boundaries, avoiding a quadratic full-frontier copy after every stitch while retaining deterministic replay.

An opening records its boundary locations, purpose, closure expectation, component, derivation, declaring operation, and the required `DesignSpec.intentional_openings[].opening_requirement_id`. The semantic validator resolves that ID against the content-addressed `design_spec_ref`, then requires purpose and closure expectation to agree. A terminal `ACTIVE` or `RESERVED` frontier is an unintended boundary and fails V4.

## Branches, components, and seams

Branches form an acyclic directed graph through `parent_branch_ids`; joins may give a branch multiple parents. Components represent independently started pieces. Courses and frontiers must agree on component and branch membership.

A sewn seam is represented only by `JOIN` with `join_method = SEWN`; crocheted joining uses `CROCHETED`. Seam, cut, and reattachment quantities are derived exact properties, not free metadata.

**PROVEN / FORMAL:** Every branch entry and terminal obligation is balanced by frontier transitions. An unaccounted branch is invalid even if a geometric metric would otherwise pass.

## Yarn paths and color

Each yarn source binds a material-profile ID, revision, hash, and color. A yarn path contains one or more ordered segments. Every segment explicitly records its start and end operation types. It starts at `ATTACH`, `MAGIC_RING`, or `COLOR_CHANGE`; it ends at `CUT_YARN`, `COLOR_CHANGE`, or an explicit live terminal (`end_operation_id = end_operation_type = null`).

**PROVEN / FORMAL:** `COLOR_CHANGE` is an atomic boundary: its input yarn segment ends at that operation and its output yarn segment starts at that same operation. It is a state-boundary operation, not a member of either segment's `event_ids`; `event_ids` contains only work events strictly after the start boundary and strictly before the end boundary. A validator requires the declared start/end operation IDs and types to match the referenced operation, yarn direction, and construction-sequence order. Every non-boundary yarn work event belongs to exactly one segment of the referenced yarn; no work event appears in two segments. Cuts and reattachments therefore remain countable and reproducible.

`COLOR_CHANGE` changes active yarn/color explicitly. Exporters may phrase this naturally, but parsers must reconstruct the same event and yarn-path boundary.

## Provenance and deterministic canonicalization

Generation provenance records the solver family/name/version, a complete flattened typed parameter list and its hash, seed or explicit `null`, deterministic candidate-evaluation budget and usage, input artifact hashes, software commit, and canonicalization profile. Derivation records link generated subjects to versioned rules and parameter hashes.

Independent forward-model, metric, threshold, and verification versions belong in the verification report that references the canonical IR hash; they do not mutate this construction artifact.

**ENGINEERING DECISION:** `CROCHET_IR_CANONICAL_JSON_V1` is a content identity, not semantic equivalence. The shared number, JCS, UTF-8, safe-integer, domain-separated SHA-256, and failure rules are normative in [`CANONICALIZATION.md`](CANONICALIZATION.md). It is produced as follows:

1. validate schema and graph-wide invariants;
2. apply the ordered-vs-set registry below, rejecting duplicate keys or a collection whose order contradicts its declared semantic order;
3. preserve every explicitly semantic ordered array byte-for-byte after validation;
4. serialize using the shared RFC 8785/I-JSON profile;
5. hash the domain-separated `CROCHET_IR_CANONICAL_JSON_V1` preimage with SHA-256.

Duplicate IDs, duplicate parameter names, non-finite numbers, unresolved references, and locale-dependent values are rejected. RFC 8785 object-member ordering and number rendering are normative; profile implementations must not normalize strings, units, IDs, or array members beyond this registry.

| Path | Canonical treatment | Reason |
| --- | --- | --- |
| Top-level entity tables: `colors`, `yarns`, `attachment_locations`, `stitches`, `construction_operations`, `courses`, `frontiers`, `branches`, `components`, `openings`, `yarn_paths`, `derivations` | sort by the table's typed ID | table position is non-semantic |
| `construction_sequence`, `frontier_transitions` | sort by contiguous `sequence_index` / `transition_index` | index is the sole executable order |
| `course_order`, `course.member_event_ids`, `stitch.base_attachment_location_ids`, `stitch.top_attachment_location_ids`, `frontier.attachment_location_ids`, `construction_operation.attachment_location_ids`, `construction_operation.join_input_mappings`, `join_input_mapping.consumed_attachment_location_ids`, `sequence_event.frontier_transition_ids`, `yarn_path.segments`, `yarn_segment.event_ids`, and primitive-array `solver_parameter.value` | preserve declared order | construction, traversal, attachment, event, yarn chronology, or parameter value order is semantic |
| Input/output frontier and yarn ID arrays on operations, courses, and transitions; branch/component entry and terminal frontier arrays | preserve declared order | orientation and obligation order are semantic; validators check it matches the explicit mapping/replay |
| `frontier_transition.*_attachment_location_ids`, `opening.boundary_attachment_location_ids` | preserve declared order | they identify a boundary traversal order; set membership alone is insufficient |
| `branch.parent_branch_ids`, `branch.course_ids`, `component.branch_ids`, `required_capabilities`, `derivation.subject_refs`, `provenance.input_artifacts` | sort by typed ID or stable tuple (`entity_type`, referenced ID; artifacts by `artifact_id`) | membership is semantic but incidental input order is not |
| `provenance.solver_parameters` | sort by `name` | parameter map has no execution order |

No schema array is implicitly a set merely because it uses `uniqueItems`. The registry is exhaustive for nested CrochetIR arrays: an array not listed is invalid in this profile until the registry and semantic validator are extended together.

## Semantic equivalence and export round trips

Text equality and CrochetIR content-hash equality are not the V9 oracle. `CROCHET_SEMANTIC_EQUIVALENCE_V1` compares two schema- and semantically-valid IRs under the same executable semantic profile:

1. Project only construction-relevant fields. Preserve required capabilities; stitch family, shaping, arity, ordered incidence; construction operations and join method/orientation; total event/course/yarn order; active yarn/color changes; material-profile content hashes; frontier topology, lifecycle, ordered rewrites; branch/component topology; and opening purpose/closure/boundary semantics.
2. Remove `crochet_ir_id`, all original entity IDs after their references are captured, display labels, derivations, solver/search provenance, artifact URIs, software commit, source/target hashes, and `design_spec_ref`. V10 retains those facts and records the round-trip lineage separately.
3. Assign canonical labels without graph search:
   - events by contiguous `sequence_index`, and stitch/operation subjects by their event;
   - transitions by `transition_index`, and frontiers by producing transition plus output ordinal;
   - attachment locations by canonical producer subject plus `ordinal_within_producer`;
   - courses by `course_order`;
   - components by their first canonical course/event, branches by their first canonical course or frontier creation, yarns by their first before/after event use, colors by their first canonical yarn use, openings by their declaring operation event, and material bindings by their first canonical yarn use.
4. Alpha-rename every retained reference to those labels, apply the semantic projection's ordered-vs-set registry, then serialize/hash under [`CANONICALIZATION.md`](CANONICALIZATION.md).
5. The two IRs are equivalent if and only if the resulting JCS bytes are identical. A failed prerequisite or non-unique first-use label is `E_EXPORT_ROUNDTRIP` or `E_DETERMINISM`, never a heuristic isomorphism result.

Every retained entity must have the use named above; an unreachable table entry makes the IR semantically invalid before comparison. Where a first use names several entities of the same type, their already-semantic ordered reference position is the tie break. No original ID, localized label, object-member order, or entity-table insertion order may break a tie.

V1 deliberately preserves global event order, even between independent components. Reordering pieces, mirroring work, rotating a cyclic frontier away from its declared anchor, changing a join orientation, splitting one compound increase into two plain nodes, or changing a material binding is not equivalent. Alpha-renaming, table insertion order, non-semantic labels, whitespace, and supported German/US/UK wording are harmless after parsing.

[ADR-0009](adr/0009-execution-normalized-semantic-equivalence.md) records why general graph and partial-order equivalence were rejected for V1.

**FUTURE:** Parser/export support for advanced lace and garment techniques requires new typed semantics and round-trip fixtures before those capabilities can be declared.

## Required semantic validation

Beyond schema validation, V2–V4 must prove at minimum:

1. global typed-ID uniqueness and exact reference resolution;
2. every entity table and explicit order has one-to-one membership;
3. producer uniqueness, arity equality, and construction precedence;
4. contiguous event/transition/course order and state continuity;
5. course, branch, component, frontier, and yarn-path consistency;
6. legal operation-specific cardinalities, neutral values, operation/transition pairing, and capability support;
7. complete frontier replay, ordered delta conservation, lifecycle legality, and no unintended open boundary;
8. opening authorization against the referenced DesignSpec and exact seam, cut, reattachment, stitch-family, and shaping accounting;
9. yarn-segment boundary/type/order consistency, including atomic `COLOR_CHANGE` handoff;
10. DesignSpec/material/input hashes match resolved canonical bytes and replay/canonicalization are deterministic across locale, process, and map iteration order.

Any failure rejects the candidate; validators do not repair or infer missing construction.
