# Visible construction language: PATTERN_M1B_V1

Implemented independently of the frozen M1A format. The new profile represents
visible construction instructions and reconstructs fresh CrochetIR. It carries
no serialized IR, base64, source hash, source UUID, or hidden reconstruction
payload. Source certification stays detached, as required by ADR 0015.

## Grammar and replay

The exact header is `CROCHET PATTERN M1B V1`, followed by `Terminology`, `Core`,
`Skills`, an empty line and `Instructions`. Each instruction is one LF-terminated
line. Fields are ordered, separated by semicolons, and end in a period. Visible
labels use `Piece`, `Branch`, `Course`, `Step`, `Boundary`, `Marker`, `Yarn`,
`Color`, or `Opening` followed by A through ZZZZ. Empty lists use `none`.
These names describe construction entities, not original artifact identities.

The executable field layout is the closed `LAYOUT` table in `pattern_m1b.py`:

| Instruction | Required fields, in order |
| --- | --- |
| Yarn | color |
| Piece | branches, starts, finishes |
| Branch | piece, parents, created, courses, enters, finishes |
| Course | number, piece, branch, form, turn, direction, starts, finishes, steps |
| Make a magic ring / Start yarn | yarn, sites, output |
| Reattach yarn | yarn, on, at, output |
| Change yarn | from, to |
| Cut yarn | yarn |
| Reserve / Split | on, outputs |
| Join | inputs, method, output |
| Close | on, output |
| Leave open | on, requirement, purpose, expectation, opening, output |
| Work followed by localized stitch instruction | bases, tops, on, gap, output, course, total |

Boundary descriptions name their piece, branch, topology, cyclic anchor and
active yarn, e.g. `Boundary A (Piece A/Branch A/cyclic/Marker A/Yarn A)`.
Reserve/split lists name an ordered marker partition and active/reserved state.
Join lists name input boundaries, orientation and consumed markers. Work lines
name exact bases/tops or chain insertion gaps. Replay computes immutable
frontier snapshots from these operations; snapshots are never embedded in text.
`total` is the resulting live TOP_LOOP count on the output boundary, excluding
ring/fabric anchors. It is checked after each action; it is not a final-round
total or a newly-created-stitch count. The separate human PDF retains final
round totals in parentheses.

Supported: core 1.0/1.1, all six plain stitch families, binary SC increases and
decreases, multiple ring sites, explicit turns/directions, multiple components,
branch ancestry, interleaved course membership, reserve/split/reattach, oriented
crochet and sewn joins, yarn changes/cuts, closure and declared openings. This
is a bounded structural codec, not a solver or proof of physical executability.
Stitch terms support US English, UK English and German; structural commands
remain the same controlled English grammar. Unknown syntax fails closed.

## External binding and trust

`parse_pattern_m1b_text` produces a frozen typed AST without a context. It
replays instructions into an unbound graph and calls the unchanged independent
SemanticValidator. Only absent external DesignSpec/MaterialProfile resolutions
are deferred at this stage. All structural errors reject the text.

`bind_pattern_m1b_semantics` re-admits even a directly constructed AST, resolves
the existing frozen `PatternParseContext` (DesignSpec plus symbolic yarn/material
and color bindings only), and runs the full validator without diagnostic
filtering. Context contains no construction hints and cannot restore a deleted
reserve, join, marker or stitch instruction. Shared Color symbols require equal
complete color bindings. Opening requirement identifiers are external DesignSpec
references and are printed as such, rather than renamed by graph normalization.

Imported graphs have fresh identifiers, IMPORT derivations, a visible-text
digest and an all-zero untrusted commit. Valid text can bind to another valid
external design: text does not authenticate its original source. Physical status
is UNTESTED and verification state NOT_VERIFIED. Source authentication and
detached accepted certification remain separate work.

The exporter uses semantic normalization for deterministic first-use labels.
The parser does not use a producer graph. Round-trip comparison uses the
existing semantic projection, so the normalizer is a shared comparison
dependency, not an independent proof of every possible graph equivalence.
Tests use separately constructed raw IR and mutated visible instructions.

## Budgets

At most 200,000 UTF-8 bytes, 8,192 lines, 4,096 replay events, 8,192 unique
attachment locations and 262,144 cumulative snapshot memberships. Invalid
Unicode, CRLF, malformed labels, unknown/duplicate fields, missing final newline,
nonconsecutive creation labels, dangling references, retired/reserved advances,
invalid partitions, wrong counts, anchors and external bindings are rejected.
The text ceiling can be reached before the event ceiling. No truncation or
silent approximation is allowed.

## Delivery

API/CLI/jobs operations:

- `export_m1b`: api_version, operation, design_spec, yarn_bindings, crochet_ir,
  terminology. Runs full semantic round-trip before returning pattern text.
- `import_m1b`: api_version, operation, design_spec, yarn_bindings, pattern.
  Returns freshly reconstructed IR/hash with UNAUTHENTICATED_IMPORT provenance.
- `verify_m1b_candidate`: the existing verify_candidate request shape, selecting
  this explicit V9 profile. Checks DE/US/UK round trips; other gates retain
  their own applicability. Branch/open/flat physical gates do not become PASS.

Each yarn binding has exactly symbol, material_profile, color_label, srgb_hex.
The transport accepts one through 32 bindings within the existing bounded JSON
request envelope; native text/replay ceilings remain independently enforced.
The new V9 adapter binds its selected profile in evidence hashes/version.
Default M1A verification behavior and frozen schemas/goldens are unchanged.
