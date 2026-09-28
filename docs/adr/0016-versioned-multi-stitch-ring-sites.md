# ADR-0016: Versioned multi-stitch ring sites

- Status: Accepted for implementation by explicit user approval, 2026-09-21.
- Approval scope: new backward-compatible semantics with separate tests and documentation.

## Problem and alternatives

Core 1.0 creates one MAGIC_RING_ANCHOR. A positive-base stitch retires its base,
so a second plain stitch cannot reuse that anchor. Treating six plain stitches
as one increase or reactivating retired locations would break existing contracts.
Changing 1.0 in place would also change the meaning of approved artifacts.

## Decision

Introduce schema 1.1.0 with semantics CROCHET_CORE_1.1.0 and capability
MULTI_STITCH_RING_V1. Keep the original schema file and core 1.0 semantics intact.
The separate 1.1 schema references unchanged 1.0 definitions and only broadens
MAGIC_RING attachment cardinality. Unknown schema/profile combinations fail.

One MAGIC_RING operation may explicitly create N distinct ordered
MAGIC_RING_ANCHOR locations on ONE physical ring, with producer ordinals 0..N-1.
These are single-use insertion sites, not N rings, stitches, or top loops.
Operation attachments, CREATE.created, and the initial cyclic frontier contain
the same ordered list. The first location is the explicit cyclic anchor.

For N > 1, each site must be used exactly once by one plain SINGLE_CROCHET in the
initial cyclic course of that branch, in site order. The course input is the
ring's output frontier and its stitch membership comprises those N stitches.
Skipping/closing unused sites, reusing a site, inserting shaping instead of a
plain stitch, spreading the ring start over multiple courses, or relabeling sites
as TOP_LOOP fails independent verification. All ordinary frontier ownership,
producer identity, event, yarn, arity and provenance rules remain applicable.

No automatic upgrade or downgrade is performed. Existing artifacts retain their
schema/profile and canonical bytes. The canonical collection registry does not
change; version and capability fields distinguish new artifacts. Existing
approved golden expectations are not changed or regenerated.

## Text and physical boundaries

Extended text must visibly declare the site count and attachment choices. The
parser cannot obtain them from PatternParseContext or a certification manifest.
The forward model must recognize sites with the same ring producer as one ring;
N must never be interpreted as a target radius or N independent components.
This exact construction extension is not a calibrated physical model.

## Independent acceptance

Use a handcrafted multi-site ring fixture built without the production parser,
exporter or solver. Test old-version rejection, mismatched version pairs, missing
capability, duplicate sites, wrong producer ordinals, unused/retired sites,
non-plain consumers, course splitting and site-order permutations. Re-run the
unchanged 1.0 tests and independent Node conformance vectors. New numerical or
canonical goldens still need separate human approval.
