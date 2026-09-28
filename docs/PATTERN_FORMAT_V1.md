# Pattern V1: implemented controlled-language subset

The canonical construction is CrochetIR. Pattern text carries visible executable
instructions, not an embedded source IR or certification payload. The current
implementation supports one non-branching component, one branch, chains, plain
single crochet, binary SC increases/decreases, yarn changes, sequential rows or
cyclic rounds, and final closure. It is not the complete M1B grammar.

## Boundary and example

`parse_pattern_text` produces typed text facts and checks instruction ordering,
markers, arities, live-loop totals and terminal state without external context.
`parse_pattern` binds those facts through the frozen `PatternParseContext`, which
contains only DesignSpec and external material/color bindings. It reconstructs
fresh CrochetIR and invokes the independent semantic validator. The context
cannot supply missing instructions or repair a contradiction.

```text
CROCHET PATTERN V1
Terminology: US

Materials
Yarn A: external material binding.

Instructions
Make a magic ring with Yarn A for 6 stitches; set Marker A.
Round 1 (cyclic, anchor Marker A):
Work 1 sc at Marker A; mark Marker G. (1)
Work 1 sc at Marker B; mark Marker H. (2)
Work 1 sc at Marker C; mark Marker I. (3)
Work 1 sc at Marker D; mark Marker J. (4)
Work 1 sc at Marker E; mark Marker K. (5)
Work 1 sc at Marker F; mark Marker L. (6)
Close work.

END
```

The six initial markers are distinct insertion sites on ONE ring, allocated in
declared order. They are not six rings or six top loops. Subsequent produced
markers follow alphabetic order A..Z, AA..AZ, etc. Totals count live TOP_LOOP
locations only. This visible multi-site start selects schema/core 1.1 and
`MULTI_STITCH_RING_V1`, as authorized in ADR-0016. The legacy singleton start
`Make a magic ring with Yarn A; set Marker A.` retains schema/core 1.0. No silent
version migration occurs.

## Implemented templates

- `Start Yarn A at Marker A.` starts a linear attachment frontier.
- `Row 1 (linear):` and `Round 1 (cyclic, anchor Marker A):` declare topology.
  Numbers are contiguous; the anchor must name the actual first live location.
- `Work 1 sc. (1)`, `Work 1 sc increase. (2)` and
  `Work 1 sc decrease. (1)` address the first consecutive live span.
- `Work 1 sc at Marker A; mark Marker G. (1)` explicitly addresses a base.
  Binary bases or tops use ` and ` between two marker labels. Explicit outputs
  must match the deterministic marker-creation order.
- `Work 1 ch. (1)` inserts at the supported terminal/wrap gap.
- `Change to Yarn B.` changes active yarn; returning to Yarn A opens a new
  segment instead of merging noncontiguous yarn history.
- `Close work.` is the unique final construction instruction.

Terminology profiles are US (`sc`, `ch`), UK (`dc`, `ch`) and German (`fM`, `Lm`).
Only stitch abbreviations are localized in this implementation; the surrounding
controlled-language templates remain English. All three bind to identical
canonical stitch semantics. Unsupported syntax and unsupported export semantics
raise structured failures, not approximate prose.

Input must use canonical LF newlines with a final newline, exact section headings
and no surplus text. Maximum UTF-8 text size is 100000 bytes and maximum line
count is 2000. These versioned parser-owned work limits bound expansion; they
are not crochet-domain or physical thresholds. Malformed Unicode and excessive
numeric fields fail closed.

## Export and evidence

Exporter marker/yarn labels depend on execution order, not entity-table storage
order. Explicit base/top text is used for multi-site rings and non-default spans.
Export rejects unexpressed frontier rotation, unsupported direction, interleaved
courses, branching, reservations, joins, seams, reattachments, intentional
openings and stitch families outside CHAIN/SC. A valid general CrochetIR can
therefore be outside this text subset.

`verify_semantic_round_trip` compares execution-normalized semantic bytes after
export and independent text rebinding. Detached `CertificationManifest` hashes
are evidence about source and text identity; they never enter parsing and are
not proof of physical validity or full V0-V10 acceptance. Imported provenance
still contains placeholder source-commit/parameter fields; it must not pass as a
complete production V10 record. Human golden approval and physical validation
are not inferred from software tests.

Regression tests include independently assembled IR, table permutations, all
three terminology profiles, colors A-B-A, arbitrary/truncated text, retired or
wrong markers, counts, extra commands after closure, ring-site corruption and
the unchanged core 1.0 conformance vectors. Advanced M1B export remains open.
