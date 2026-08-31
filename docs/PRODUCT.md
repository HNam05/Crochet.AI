# Product Contract

## Mission

Build a deterministic crochet CAD/compiler that converts structured design intent and target geometry into physically plausible, formally valid, shape-faithful crochet patterns. The product is a compiler and verification system, not an LLM pattern writer.

**ENGINEERING DECISION:** Natural-language or image interpretation may eventually produce a proposed `DesignSpec`. It cannot provide authoritative stitch counts or bypass deterministic generation and independent verification.

## Pipeline and trust boundaries

1. Interpret optional unstructured input into a strict `DesignSpec`.
2. Validate input geometry, units, material measurements, and design constraints.
3. Route the design to one or more domain-specific solver families.
4. Emit complete candidate `CrochetIR` artifacts with provenance.
5. Validate schema, references, counts, frontiers, topology, and construction semantics independently.
6. Reconstruct predicted physical geometry using only CrochetIR, material data, and declared boundary/initial conditions.
7. Compare predicted and target geometry using a metric stack and hard thresholds.
8. Test robustness across allowed material/gauge uncertainty.
9. Export localized instructions and parse them back to semantic equivalence.
10. Return evidence and provenance, or reject.

**PROVEN / FORMAL:** If any mandatory gate is false, the conjunction of mandatory gates is false. A weighted score cannot alter that result.

## Product priorities

Candidate comparison uses a lexicographic order after hard feasibility:

1. structural and semantic validity;
2. hard geometry acceptance;
3. sewn-seam count;
4. yarn cuts and reattachments;
5. remaining geometric error vector under an explicitly versioned ordering;
6. unnecessary construction complexity.

**ENGINEERING DECISION:** Seamlessness has very high priority only inside the geometry acceptance region. An inaccurate seamless candidate cannot defeat an accurate multi-piece candidate that passes the threshold.

## Shared core and domain solvers

All domains share DesignSpec infrastructure, canonical CrochetIR, stitch semantics, parser/export boundaries, verification, material/provenance concepts, and evidence reporting. They do not share one universal geometry solver.

- **Amigurumi:** analytic, geodesic, seamless-topology, and advancing-front candidates for stuffed 3D forms.
- **Garments:** body measurements, ease, gauge, material response, construction style, grading, and future cloth simulation.
- **Flat crochet:** rows, grids, repeats, tiling, motifs, and color regions with stronger exact combinatorial guarantees where possible.
- **Lace:** typed topological/motif graphs and future primitives such as chain spaces, picots, clusters, puffs, post stitches, shells, and attachment points.

**ENGINEERING DECISION:** Garments are never routed through the amigurumi geometry solver merely to reuse code. Shared behavior belongs in CrochetIR and verification.

## User-visible evidence

Outputs expose separate evidence lanes rather than opaque confidence percentages:

- Structural Integrity: `PASS | FAIL`
- Topology: `PASS | FAIL`
- Geometry: metrics plus `PASS | FAIL`
- Material Robustness: `PASS | WARNING | FAIL`
- Construction: seam, cut, and reattachment counts
- Physical Validation: `UNTESTED | CALIBRATED | PHYSICALLY_VERIFIED`
- Overall: `VERIFIED | EXPERIMENTAL | NOT_VERIFIED | REJECTED`

`VERIFIED` requires all mandatory computational gates. It does not imply `PHYSICALLY_VERIFIED`.

## Non-goals for bootstrap

- production 3D geodesic or frontier solvers;
- high-fidelity yarn/contact simulation;
- production UI, cloud architecture, or LLM integration;
- universal stitch/technique support;
- scientifically established physical thresholds before experiments.

## Milestone sequence

1. Specifications, schemas, repository structure, and review controls.
2. DesignSpec + canonical CrochetIR + independent semantic validator.
3. Canonicalization, hashing, parser/exporter, and round-trip tests.
4. Analytic surface-of-revolution solver.
5. F0 independent forward model and geometry verification.
6. Physical calibration fixtures and empirical threshold profiles.
7. Geodesic and seamless-topology research prototypes.
8. Bounded frontier solver.
9. Separate garment, flat, and lace solver families.

## Hypotheses requiring calibration

- effective stitch/course pitch adequately predicts first-order geometry;
- the proposed F0 energy terms predict useful course-level shape;
- selected geometry metrics and thresholds correlate with human shape judgement;
- uncertainty intervals cover realistic crocheter tension and stuffing variation;
- seamless branching operations remain physically workable at predicted dimensions.

These are versioned engineering hypotheses, not established physical facts.

