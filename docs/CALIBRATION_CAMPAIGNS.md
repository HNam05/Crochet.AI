# Calibration campaign checkpoint

Status: implemented pilot data capture and draft derivation; no accepted physical
calibration. This complements [PHYSICAL_VALIDATION.md](PHYSICAL_VALIDATION.md)
and preserves the frozen MaterialProfile 1.0 estimator. It does not implement the
open Calibration Tube instruction generator, sphere/hourglass measurement
adapters, complete uncertainty model, human approval registry, or V10 acceptance.

## Versioned records and boundaries

`CalibrationCampaign` and `CalibrationMeasurement` have closed JSON object
boundaries, `record_version = 1.0.0`, strict I-JSON/binary64 admission, and owned
deeply immutable payloads. Their complete public field contract is enforced by
the constructors in `src/crochet_ai/calibration_campaign.py`; no existing JSON
schema or canonical golden was changed. Stable additive hash domains are:

- `CALIBRATION_CAMPAIGN_JSON_V1`: complete admitted campaign, with specimen
  assignments sorted by specimen ID and circumference courses sorted numerically.
- `CALIBRATION_MEASUREMENT_JSON_V1`: complete admitted measurement, with
  circumference readings, axial readings, and media records sorted by JCS bytes.

Both use the existing `Crochet.AI\0<profile>\0<JCS UTF-8>` SHA-256 preimage. All
other arrays retain order. A campaign binds a protocol ID, maker/material scope,
instrument, exclusions, repeats, assigned specimen roles, declared digital
artifact hashes, software commit, and source snapshot hash. Missing digital
hashes are explicit nulls and block derivation. Declared hashes do not prove that
the instructions were actually followed or that referenced assets are retrieved;
that remains part of the unimplemented physical/V10 acceptance chain.

Measurement records bind the campaign hash, assigned specimen, instrument,
timezone-aware observed time, every planned raw reading, mass, rest duration,
zero stuffing, untreated fabric, deviations, media/privacy/license statements,
and optional correction-parent hash. Their currently supported fixture is only
`CALIBRATION_TUBE`. Other fixture roles may be preassigned for later campaigns,
but their measurement adapters are unavailable. No specimen role comes from
the measurement payload or is inferred after seeing its result.

## Frozen pilot measurement and estimator

`CALIBRATION_TUBE_GAUGE_PILOT_V1` is an unreviewed protocol for constant-count
cyclic single crochet in relaxed, unstuffed, unwashed, unblocked tubes. At least
three independently crocheted calibration specimens are assigned before data
capture. End-effect regions are excluded before measurements; at least two
interior course bands, orientations 0/90 degrees, and two readings per setting
are required. The axial span is between course centres and counts intervals.

Only `FLEXIBLE_TAPE_RELAXED_PERIMETER_V1` is currently admitted: measure the
relaxed perimeter with a flexible tape without tension. Doubling a flattened
width is not a circumference adapter. The orientation labels record tape
placement, not a change to the measurand. Actual independence, conditioning and
correct use of the instrument remain human evidence, not software proof.

`TUBE_BASELINE_SPECIMEN_TYPE_A_V1` selects one raw observation per specimen,
by a rule fixed before data inspection: lowest predeclared interior course,
orientation 0, repeat 1, and axial-span repeat 1. This is the same keyed gauge
measurand on independently made specimens. Additional bands/repeats remain raw
records and yield explicit per-specimen range diagnostics in mm; they are neither
additional independent specimens nor silently pooled means.

Each baseline observation becomes a MaterialProfile 1.0 span/count observation.
The draft mean and Type-A standard uncertainty follow the existing left-to-right
binary64 and JCS observation ordering contract exactly. A physical zero Type-A
uncertainty fails derivation, rather than pretending the instrument is exact.
Within-specimen, instrument Type-B, method bias, covariance, between-maker and
model uncertainty are excluded and reported. A richer accepted uncertainty
model needs an additive future profile. No stiffness, bending, friction, stuffing,
stretch or shear coefficient is identified by these observations.

All derivations return `NOT_VERIFIED`, `UNTESTED`, `calibration_review = REQUIRED`
and range outcomes `REVIEW_REQUIRED` with no acceptance threshold. There is no
operation to promote a record or draft to CALIBRATED/PHYSICALLY_VERIFIED.

## Append-only local storage

`CalibrationStore` uses a separate explicitly named SQLite database with its own
application ID and `user_version = 1`. It checks exact column order/types,
primary/unique identities, correction-index predicate and foreign-key bindings.
It rejects unrelated or incompatible databases before changing their journal
mode, creates its tables atomically, and verifies stored
record hashes and SQL identity/link columns on reads. Campaign IDs and record
IDs are idempotent only for identical content. Revised scope/roles/protocols
require a new campaign ID. Corrections have a new record ID, reference an exact
earlier hash of the same campaign/specimen, and preserve every original reading;
forked corrections and ambiguous active specimen records fail closed.

Limits: 64 KiB per record, 100 campaigns, 10,000 measurement records and 64 MiB
aggregate payload. These are deterministic admission/resource limits, not
scientific tolerances. SQLite indexes/WAL/disk overhead and a full backup/restore
operational program remain P12 work. Hashes are integrity links, not signatures.

## API, CLI and printable handoff

Additive API 1.0 operations are `calibration_protocol`,
`inspect_calibration_campaign`, and `derive_calibration_material`. The last is a
stateless draft operation; authoritative correction history remains in the local
store. Generic API `request` and durable `jobs` also accept these operations.

```powershell
.venv/Scripts/python.exe -m crochet_ai.cli --json calibration protocol
.venv/Scripts/python.exe -m crochet_ai.cli --json calibration register --db artifacts/calibration/records.sqlite3 --record-file campaign.json
.venv/Scripts/python.exe -m crochet_ai.cli --json calibration record --db artifacts/calibration/records.sqlite3 --campaign-sha256 <campaign-hash> --record-file measurement.json
.venv/Scripts/python.exe -m crochet_ai.cli --json calibration show --db artifacts/calibration/records.sqlite3 --campaign-sha256 <campaign-hash>
.venv/Scripts/python.exe -m crochet_ai.cli --json calibration derive --db artifacts/calibration/records.sqlite3 --campaign-sha256 <campaign-hash> --profile-id mp_pilot --response-id mr_pilot --created-at <timezone-aware-ISO-time>
.venv/Scripts/python.exe -m crochet_ai.cli --json calibration packet --output output/pdf/measurement-packet.pdf
```

The packet command also accepts `--campaign-file` for frozen counts/IDs/hash
bindings and refuses to overwrite an existing file. Blank packets consist of a
protocol page and three separate specimen sheets. They are measurement documents,
not compiled CrochetIR instructions. The local browser exposes the blank packet
at `/api/calibration-protocol.pdf`; the prototype input panel links it. Before
authoritative fabrication the missing exact open-tube IR and exported instructions
must be implemented and bound. Existing closed-form prototype PDFs remain pilot
crochet instructions and can still be used for exploratory human feedback.

Tests use independent authored data vectors, specimen permutations, incomplete
and contaminated data, hidden repeat variation, role/ID conflicts, correction
forks, corruption, concurrent creation, database preservation, capacity boundaries,
CLI persistence, deterministic PDF text, and actual HTTP PDF bytes. Software
tests do not replace making specimens or reviewing instrument/model uncertainty.
