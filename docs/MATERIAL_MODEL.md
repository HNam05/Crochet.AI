# Material Model

## Scope and evidence

`MaterialProfile` provides measured, target-independent parameters used by solvers and forward simulation. The V1 profile is intentionally small enough to identify from simple physical specimens.

- **ESTABLISHED:** crochet gauge is anisotropic; spacing along a course and spacing between courses need not be equal.
- **ENGINEERING DECISION:** yarn category and hook diameter are metadata/priors, never substitutes for measured pitch.
- **HYPOTHESIS:** two effective pitches and their uncertainty are sufficient for useful first-order solver proposals and F0 simulation.
- **FUTURE:** calibrated stretch, compression, friction, bending, drape, hysteresis, and stuffing-response parameters.

## V1 parameters

The strict schema is [`material-profile.schema.json`](../schemas/material-profile.schema.json). A profile contains:

- versioned profile identity;
- yarn metadata and hook diameter in millimetres;
- a non-empty registry of calibration responses, each with explicit stitch, course-mode, tension/maker, and fabric-state conditions;
- one or more span observations, effective pitches, and separate standard uncertainty within each response;
- a declared canonicalization profile and hash algorithm;
- measurement/provenance identifiers.

There is no scalar `stitch_size` field.

### Effective stitch pitch

`effective_stitch_pitch_mm` is the measured length along a course divided by the number of stitch intervals spanning that length under the recorded conditions:

```text
p_s = stitch_span_length_mm / stitch_span_count
```

For a tube, the span length may be a measured circumference. For a flat swatch, the protocol must define edge handling and interval counting. The observation records the interval count, not an ambiguous visual stitch count.

### Effective course pitch

`effective_course_pitch_mm` is the measured length in the course-advance direction divided by the number of course intervals:

```text
p_c = course_span_length_mm / course_span_count
```

Both are positive lengths in millimetres. They apply only to the canonical stitch type, `LINEAR` or `CYCLIC` course mode, maker/tension profile, and fabric state recorded in their calibration response's `measurement_conditions`.

## Calibration-response registry and canonicalization

Physical yarn identity and calibrated fabric response are separate concepts. `yarn` identifies the measured physical source and hook metadata. `calibration_responses` is a registry of gauge responses for that source; it does not create, replace, cut, or recolor a CrochetIR yarn.

Each response has a stable `response_id` and the semantic key:

```text
(canonical_stitch_type, course_mode, tension_profile_id, fabric_state)
```

For V1 selection, a forward run supplies the requested tension profile and fabric state. For every simulated stitch, it obtains `canonical_stitch_type` from the stitch node and `course_mode` from its referenced course, then requires exactly one matching response. Thus a `SINGLE_CROCHET` cyclic course followed by a `DOUBLE_CROCHET` linear course may use two responses from the same physical yarn without an invented `COLOR_CHANGE`, `CUT_YARN`, `ATTACH`, or other IR transition. Missing or ambiguous response keys are a fail-closed material-resolution error.

`MATERIAL_PROFILE_CANONICAL_JSON_V1` uses the shared I-JSON/binary64/JCS/domain-separated SHA-256 contract in [`CANONICALIZATION.md`](CANONICALIZATION.md). The `calibration_responses` array is sorted ascending by the full semantic key above and then `response_id`; `observations` and `source_record_ids` are sorted ascending by their IDs. No consumer may infer meaning from insertion order. The semantic validator rejects duplicate semantic keys, duplicate IDs, non-canonical array order, non-finite/overflowing numbers, unsafe integers, or a profile whose recomputed canonical bytes/hash differ from its binding. JSON Schema intentionally cannot express those global conditions.

## Identifiability

A parameter is admitted to V1 only when a planned fixture can estimate it without severe confounding.

| Parameter | Supporting observation | Identifiability limit |
| --- | --- | --- |
| Hook diameter | Direct tool measurement/label | Does not determine finished gauge |
| Stitch pitch | Multi-stitch span on swatch or tube | Confounded with stitch family, tension, state, and curvature |
| Course pitch | Multi-course span on same conditions | Confounded with stitch height, tension, state, and loading |
| Pitch uncertainty | Replicated spans/specimens or documented engineering bound | Sparse observations cannot establish a population distribution |

Observed spans remain within each response so an independent semantic validator can recompute per-observation pitches and check consistency with that response's stored estimates/uncertainties. JSON Schema validates shape and units but cannot establish statistical validity.

Stiffness, friction, bending, compression, drape, circumferential/axial stretch, and stuffing expansion are excluded from V1 MaterialProfile. They require dedicated loading fixtures and may otherwise be mutually confounded. F0 forward-model coefficients therefore belong to a separately versioned model-calibration profile and remain hypotheses.

## Uncertainty

Each response's `stitch_pitch_standard_uncertainty_mm` and `course_pitch_standard_uncertainty_mm` are separate non-negative standard-uncertainty estimates. `basis` records whether they come from replicated combined uncertainty or an engineering bound converted by a documented protocol.

They are not confidence percentages and do not imply a normal distribution. Zero is schema-valid only for exact synthetic fixtures; the semantic/calibration policy must reject an unjustified physical zero.

V1 does not encode covariance. Therefore robustness verification must not infer probabilistic independence. It uses a documented conservative scenario/interval policy and reports the limitation. Correlation and hierarchical maker/lot effects require a future schema version.

## Measurement conditions

Gauge is invalid outside its stated conditions unless an explicit transfer/calibration rule exists. Every calibration response requires:

- one canonical stitch type, never localized `dc`-style terminology;
- course mode `LINEAR` or `CYCLIC`;
- `tension_profile_id` identifying the crocheter/machine and technique profile;
- fabric state `RELAXED_UNSTUFFED`, `BLOCKED_UNSTUFFED`, or `STUFFED`.

Changing hook or yarn lot requires a new profile. Changing stitch family, course mode, maker/tension, blocking, or stuffing requires a distinct response, or an explicit experimental applicability record; it does not imply a change in the CrochetIR yarn path.

## Yarn and hook metadata

Yarn description, manufacturer/product/lot/color/fibre/linear-density fields identify what was measured and support priors when no calibrated profile exists. They do not authorize fabricated pitch values.

If only yarn category and hook diameter are known, the system may create an explicitly `EXPERIMENTAL` proposal using a separately versioned prior, but it cannot label the material calibrated or pass a verification requirement that demands measured gauge.

## Resolution and provenance

A DesignSpec may embed a schema-valid MaterialProfile or reference `profile_id`, `revision`, and a SHA-256 content hash through a trusted registry. Reference resolution is semantic, not supplied by JSON Schema. The resolved profile is canonicalized with `MATERIAL_PROFILE_CANONICAL_JSON_V1` and must match all three binding values before solver invocation.

Provenance records the measurement protocol, source record/specimen IDs, creation time, and software commit used for derivation. Physical benchmark records additionally bind the software, solver, DesignSpec, CrochetIR, maker/tension, stuffing, measurements, and images as specified in `PHYSICAL_VALIDATION.md`.

## Validation rules

Schema validation is necessary but not sufficient. Semantic material validation must fail closed when:

- units are missing or a pitch/hook value is non-positive;
- a response has a duplicate or ambiguous semantic key, or a requested stitch/course response is absent;
- an observation references no known specimen/source record;
- stored pitch is inconsistent with observations under the declared protocol;
- uncertainty has no supported basis or is unjustifiably zero for physical data;
- measurement conditions do not match the requested stitch/course mode;
- a profile reference cannot be resolved exactly;
- provenance or revision is ambiguous.

No validator silently substitutes a yarn-category prior for a missing measured pitch.

## Calibration path

1. Start with a multi-span flat swatch or calibration tube to estimate separate pitches for each required stitch/course response.
2. Repeat measurements/specimens to estimate practical uncertainty without false precision.
3. Use sphere and hourglass fixtures to test whether pitches transfer to curvature and shaping.
4. Use a Y-branch to test branch/topology and local gauge effects.
5. Version any updated profile or model coefficient; never mutate evidence behind an existing hash.

Thresholds and parameter ranges remain **HYPOTHESES** until these physical fixtures support a versioned calibration profile.

## Future schema evolution

Future versions may add measurement covariance, directional stretch, compression, bending, friction, drape, stuffing expansion, moisture/temperature history, and learned hierarchical priors. Multiple stitch families and course modes are already expressed as distinct calibration responses in V1. New fields require an identifiable fixture, units, uncertainty, provenance, and an explicit schema/profile migration. Unknown properties remain rejected at V1 boundaries.
