# Physical calibration and validation

## Scope

- **ESTABLISHED:** Yarn label and hook diameter alone do not determine finished crochet geometry; maker tension, stitch construction, loading, stuffing, and measurement conditions matter.
- **ENGINEERING DECISION:** Effective stitch pitch and effective course pitch remain separate measured quantities in millimetres.
- **ENGINEERING DECISION:** Calibration data used to fit a MaterialProfile is not also holdout evidence for physical verification.
- **HYPOTHESIS:** Initial protocols, parameter ranges, and acceptance thresholds are engineering hypotheses until repeated specimens support a versioned calibration profile.
- **FUTURE:** Dense 3D reconstruction, multiple-crocheter population models, high-fidelity friction/contact identification, and yarn-level material fitting are outside V1.

The first physical object is a simple tube. A complicated character is not a calibration fixture.

## Evidence roles

| Role | Purpose | May fit parameters? | May support `PHYSICALLY_VERIFIED` for the fitted claim? |
| --- | --- | --- | --- |
| Pilot | Debug instructions, instruments, and data capture | Exploratory only | No |
| Calibration | Estimate a versioned MaterialProfile and its measurement uncertainty | Yes, only predeclared identifiable parameters | No |
| Holdout validation | Test a frozen profile/model/threshold on independently made specimens | No | Yes |
| Reproduction | Repeat a frozen result with another specimen, lot, or crocheter | No, unless opened as a new calibration campaign | Yes, within its declared scope |

Specimen IDs and roles are assigned before measurements are inspected. Reclassifying a failed holdout as calibration requires a new campaign version; the original failure remains in provenance.

## Required provenance

Each campaign, specimen, and measurement has stable IDs. A specimen record contains at least:

- software commit;
- DesignSpec ID, canonical hash, and schema version;
- CrochetIR ID, canonical hash, and schema version;
- solver name/version, parameters, budget, and seed;
- forward-model, metric, verification, and threshold-profile versions;
- MaterialProfile ID/hash and whether it was fitted or frozen;
- exporter version, locale, printed instruction hash, and any documented crocheter deviation;
- yarn manufacturer/line, fibre content, nominal weight/category, colour, dye-lot or `unknown`, measured sample mass, and conditioning record;
- hook manufacturer/model, nominal size, measured diameter where available, and instrument;
- crocheter/tension-profile pseudonymous ID and relevant handedness/technique notes;
- start/end time or duration, environment measurements if available, and resting/conditioning duration;
- stuffing material, total stuffing mass in grams, insertion protocol, closure state, and rest time after stuffing;
- every raw measurement, unit, method, instrument ID, resolution/calibration information, operator, repeats, and observation notes;
- photographs or scans with content hashes, scale reference, view definition, capture metadata, and privacy/license status;
- derived-values script/version, parameters, output hash, exclusions, and rationale.

Missing values are explicit `unknown` or `not_measured`, never empty values interpreted as zero. Corrections append a superseding record and retain the original.

## Measurement conventions

All authoritative lengths are stored in millimetres and masses in grams. Raw instrument readings are retained at observed precision. Derived values MUST NOT contain more meaningful precision than their inputs support.

The campaign protocol freezes:

- whether measurements are relaxed, lightly supported, or loaded;
- surface or centreline convention;
- where course centre lines and cross-section planes are located;
- number and placement of repeated readings;
- environmental and rest conditions to record;
- stuffing and closure procedure;
- instrument resolution and calibration checks;
- outlier policy fixed before viewing results.

For a span across `k` course-centre intervals, effective course pitch is `measured_span_mm / k`, not height divided by a casually counted number of rows. For a tube course with `n` stitch intervals, effective stitch pitch is measured circumference divided by `n` under the frozen circumference convention. End-effect regions are declared in the protocol and excluded consistently, not post hoc.

MaterialProfile stores these values inside a keyed `calibration_responses[]` entry: `effective_gauge.effective_stitch_pitch_mm`, `effective_gauge.effective_course_pitch_mm`, `uncertainty.stitch_pitch_standard_uncertainty_mm`, `uncertainty.course_pitch_standard_uncertainty_mm`, and `uncertainty.basis`. The response also freezes canonical stitch type, `LINEAR`/`CYCLIC` course mode, tension profile, and fabric state. Standard uncertainty combines documented repeatability and instrument components using a named method. It is not presented as a confidence percentage.

## Identifiability rule

Only fit a parameter when at least one planned fixture changes observations in a way distinguishable from already fitted parameters.

| Parameter or evidence | Initial identifying fixture | Limit |
| --- | --- | --- |
| `calibration_responses[].effective_gauge.effective_stitch_pitch_mm` | Unstuffed Calibration Tube, several interior circumferences with fixed course count | Effective only for the response key's yarn/hook, canonical stitch, course mode, tension profile, and fabric state |
| `calibration_responses[].effective_gauge.effective_course_pitch_mm` | Unstuffed Calibration Tube, spans over several interior course intervals | Separate from stitch pitch and scoped to the same response key; end rows excluded by frozen rule |
| Corresponding standard uncertainties | Independent tube specimens and repeated readings | Initial same-crocheter uncertainty does not establish between-crocheter generality |
| Stuffing expansion response | Sphere series with at least two predeclared stuffing masses and adequate replication | **HYPOTHESIS:** fit only if distinguishable from pitch and measurement error |
| Transition/curvature adequacy | Hourglass holdout | Validation evidence by default, not a new fitted coefficient |
| Branch/topology adequacy | Y-Branch holdout | Validation evidence; does not identify friction or bending alone |

Friction, compression, bending, drape, and general stretch parameters remain **FUTURE** until dedicated fixtures and sensitivity analysis show practical identifiability. Adding poorly identifiable coefficients to improve fit is forbidden.

## Fixture sequence

### 1. Calibration Tube

**Purpose:** establish separate horizontal and vertical effective gauge with minimal geometry and no stuffing.

Protocol requirements:

- fixed canonical stitch type, constant stitch count per course, fixed number of courses, and explicit linear/cyclic construction mode;
- no shaping in the measurement region;
- start/edge/end regions identified separately;
- interior circumference measured at predeclared course bands in at least two orientations where flattening could bias results;
- axial span measured between marked course centres across multiple intervals;
- relaxed-state photographs with scale and a record of ovalization or curling;
- specimen mass and any blocking/washing treatment recorded.

**ENGINEERING DECISION:** The initial calibration campaign requires at least three independently crocheted tube specimens under the same declared profile so repeatability can be estimated. This supports only that profile, not a population claim.

### 2. Sphere

**Purpose:** test closed-round shaping, increase/decrease distribution, near-isotropic silhouette, closure, and stuffing response after tube calibration.

Record three orthogonal diameters, declared great-circle circumferences, mass before and after stuffing, stuffing mass, closure dimensions, and canonical-view silhouettes. Use the tube-derived pitches frozen. A predeclared stuffing-mass series may estimate one minimal expansion term; otherwise the sphere is validation-only.

Sphere symmetry does not validate branches, narrow necks, or local concavity. A low average surface error cannot hide a failed diameter, landmark, closure, or silhouette threshold.

### 3. Hourglass

**Purpose:** challenge repeated decreases/increases, narrow-waist reachability, shaping placement, local concavity, and cross-section accuracy.

Predefine cross-section planes at both lobes, waist, and transition regions. Measure circumference or contour, axial positions, total height, tilt/bending, and canonical silhouettes. Use a frozen MaterialProfile. The first campaign treats Hourglass as a holdout; fitting an extra parameter to it creates a new calibration version and requires another holdout.

### 4. Y-Branch

**Purpose:** validate frontier split/reservation/reattachment, intended openings, branch construction, seam/cut accounting, and physical branch geometry.

Record trunk and branch lengths, several branch circumferences, branch-point position, branch angles under a defined support condition, opening perimeters, closures, sewn seams, yarn cuts, reattachments, and any deviations from instructions. The physical stitch trace is checked against the CrochetIR construction trace. Geometry pass cannot override an unaccounted branch, attachment, or opening.

## Calibration workflow

1. Register campaign ID, hypothesis, fixtures, specimen roles, maker/material scope, parameter list, measurement protocol, exclusion rule, and analysis version.
2. Freeze software commit, DesignSpec, CrochetIR, instructions, instruments, and sample-size plan.
3. Make and measure specimens without changing authoritative instructions. Record any deviation as a failure-relevant event.
4. Preserve raw measurements and media before derivation.
5. Fit only predeclared identifiable parameters. Report residuals, sensitivity, parameter covariance/confounding diagnostics, and standard uncertainty.
6. Produce a new immutable MaterialProfile version linked to calibration records. Never overwrite the prior profile.
7. Run frozen holdouts. Report the full V7/V8/V10 evidence vector and every failure.
8. Human-review the profile and threshold proposal before it can support `CALIBRATED` or `PHYSICALLY_VERIFIED` claims.

## Physical acceptance

Physical thresholds use the same metric stack as computational comparison where measurable, supplemented by direct dimensions and construction audit. Every threshold has units, direction, rationale, owner, campaign link, and version. Thresholds are frozen before holdout fabrication.

- Structural/reference/frontier/topology mismatches are exact failures.
- Each hard physical dimension, cross-section, silhouette, landmark, and construction count passes separately.
- Missing required measurements yield `INDETERMINATE`, not pass.
- A damaged, deviated, or untraceable specimen is invalid evidence and remains recorded.
- Post hoc threshold widening cannot rescue the run; it creates a new profile evaluated on a new holdout.

**HYPOTHESIS:** Initial pilot limits are engineering screening limits, not scientifically general crochet tolerances. Generalization across crocheters, yarn lots, fibre types, hooks, techniques, and environments requires stratified campaigns and independent replication.

## Physical status

| Status | Minimum evidence |
| --- | --- |
| `UNTESTED` | No accepted physical calibration record applies to the artifact/profile. |
| `CALIBRATED` | A MaterialProfile was fitted from an accepted, versioned calibration campaign within the claimed maker/material scope. This does not mean this artifact was made. |
| `PHYSICALLY_VERIFIED` | A traceable holdout artifact made from the exact hashed instructions/profile passed a frozen physical verification profile. |

A failed holdout produces V10 `FAIL` with `E_PHYSICAL_VALIDATION`. The positive status remains a description of the underlying calibration scope and does not conceal the failed trial.

## Data governance

Raw records are append-only and content-addressed. Personal identity is not required; use pseudonymous crocheter IDs. Media inclusion requires recorded consent and license/privacy status. Large media may live in a governed artifact store, but repository manifests retain hashes and retrieval policy. Physical records are never fetched from an uncontrolled external service as a mandatory CI oracle.
