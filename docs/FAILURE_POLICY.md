# Failure policy

## Status and normative language

- **PROVEN / FORMAL:** A mandatory failed gate cannot be converted into a pass by aggregation, weighting, retry count, or user preference.
- **ENGINEERING DECISION:** The system fails closed. Rejection is a valid, reproducible outcome, not an exceptional fallback.
- **ENGINEERING DECISION:** `MUST`, `MUST NOT`, `REQUIRED`, and `SHOULD` are normative in this document.

This contract applies to input handling, solvers, canonical `CrochetIR`, forward simulation, verification, export, and physical evidence. A component may produce a proposed correction, but it MUST NOT mutate the authoritative artifact and claim that the original passed.

## Gate outcomes

Every V0-V10 gate emits exactly one outcome:

| Outcome | Meaning | Satisfies a mandatory gate? |
| --- | --- | --- |
| `PASS` | All checks required by the active profile completed and passed. | Yes |
| `WARNING` | No hard condition failed, but a named non-critical margin or evidence recommendation was not met. | Only if the profile explicitly permits it; never for `VERIFIED` |
| `FAIL` | At least one hard condition failed. | No |
| `INDETERMINATE` | The computation completed without a defensible pass or fail, for example because uncertainty was not bounded. | No |
| `NOT_RUN` | The gate did not execute. | No |

**PROVEN / FORMAL:** `FAIL`, `INDETERMINATE`, and `NOT_RUN` on a profile-required gate prevent `VERIFIED`. `WARNING` cannot represent an exact structural defect.

## Overall states

Overall state is derived from gate evidence and is always accompanied by `verification_profile_id` and the separate physical-validation status.

| State | Required interpretation |
| --- | --- |
| `REJECTED` | One or more mandatory gates returned `FAIL`. No pattern may be presented as usable. |
| `NOT_VERIFIED` | No hard failure has been established, but required evidence is missing, `NOT_RUN`, or `INDETERMINATE`. |
| `EXPERIMENTAL` | The declared computational profile passed, but one or more acceptance thresholds remain hypotheses, a permitted warning exists, or required physical calibration has not been established. |
| `VERIFIED` | Every mandatory gate in a versioned, calibrated profile returned `PASS`, provenance is complete, and there are no warnings. The claim's scope MUST be stated. |

**ENGINEERING DECISION:** Before a threshold profile is physically calibrated, a computationally successful artifact is at most `EXPERIMENTAL`. `VERIFIED` without a profile identifier is invalid.

## Error taxonomy

Each `FAIL` has one primary code and may include causally linked secondary diagnostics. Codes are stable API values; prose is localized separately.

| Code | Default gate | Exact use |
| --- | --- | --- |
| `E_INPUT` | V0 | Input is unreadable, non-finite, degenerate, ambiguously oriented, self-intersecting where forbidden, non-manifold where forbidden, or outside the selected domain contract. |
| `E_SCHEMA` | V1-V2 | Artifact violates its declared JSON Schema, uses an unsupported schema version, or omits a required field. |
| `E_REFERENCE` | V2-V3 | An ID is duplicate, dangling, has the wrong target kind, or crosses a forbidden scope. |
| `E_COUNT` | V3 | Declared arity, course count, attachment multiplicity, or derived accounting does not equal the independently recomputed value. |
| `E_FRONTIER` | V4 | A frontier transition is illegal, ambiguous, unaccounted, or leaves an undeclared open frontier. |
| `E_TOPOLOGY` | V4-V5 | Branch, boundary, component, orientation, split/join, or intended-opening topology violates the contract. |
| `E_GEOMETRY_UNREACHABLE` | V5 | An exact reachability proof or exhaustive bounded discrete search establishes that supported operations cannot satisfy the constraints. |
| `E_SEARCH_BUDGET` | V5 | A declared search budget ended before feasibility or infeasibility was established. This MUST NOT be reported as unreachable. |
| `E_FORWARD_DIVERGED` | V6 | The independent forward model diverged, encountered invalid model input, exhausted its numerical budget, or otherwise did not return `CONVERGED`. |
| `E_COLLISION` | V6-V8 | An unintended self-intersection, penetration, or forbidden contact remains under the active collision policy. |
| `E_SHAPE_THRESHOLD` | V7 | At least one hard member of the geometry metric vector exceeds its own threshold. |
| `E_MATERIAL_UNCERTAINTY` | V8 | Required material bounds are absent, robustness execution is incomplete, or a required uncertainty scenario fails. |
| `E_EXPORT_ROUNDTRIP` | V9 | Parsing an export does not recover a semantically equivalent canonical construction. |
| `E_DETERMINISM` | V2-V9 | Identical declared inputs and seed produce different canonical outputs or evidence outside explicitly excluded telemetry. |
| `E_PROVENANCE` | V10 | A required hash, implementation version, threshold profile, seed, software commit, or evidence link is absent or inconsistent. |
| `E_PHYSICAL_VALIDATION` | V10 | A measured artifact violates a frozen physical acceptance profile or cannot be linked to the claimed digital artifact. |
| `E_UNSUPPORTED_FEATURE` | V0-V5 | The request is valid in the wider domain model but not implemented by the selected schema/solver/profile. |
| `E_INTERNAL` | Any | An invariant internal to the verifier is violated. The result is never usable and MUST preserve diagnostic context. |

`E_UNSUPPORTED_FEATURE`, `E_SEARCH_BUDGET`, and `E_GEOMETRY_UNREACHABLE` are intentionally distinct. They mean, respectively, not implemented, not decided within budget, and demonstrated infeasible under the declared model.

## Structured diagnostic record

Every diagnostic MUST contain:

```yaml
diagnostic_id: stable-id-within-run
code: E_FRONTIER
gate: V4
severity: ERROR            # ERROR or WARNING
message_key: frontier.join.incompatible_order
summary: concise non-localized fallback text
artifact_hash: sha256:...
entity_refs: [frontier-a, frontier-b]
json_pointers: [/frontiers/2, /transitions/9]
expected: compatible orientation and equal join arity
observed: opposite orientation; arity 18 vs 17
units: null
tolerance_profile_id: null
implementation_version: verifier-frontier/1.0.0
cause_ids: []
reproducibility:
  software_commit: git-sha
  parameters_hash: sha256:...
  random_seed: null
```

Numerical diagnostics additionally MUST record observed value, threshold, comparison operator, units, tolerance rationale reference, and calibration owner or path. Search failures MUST record explored states, wall-independent work budget, deterministic tie-breaking policy, and seed if applicable. Sensitive local paths and personal data MUST NOT be required for reproducibility.

Diagnostics are ordered deterministically by gate, code, artifact location, and entity ID. Human prose MUST NOT be the only machine-readable distinction between failures.

## Critical failures

The following are always critical under every verification profile that reaches the relevant stage:

- non-finite authoritative numerical input;
- unsupported or invalid schema version;
- duplicate or dangling canonical ID;
- base/top arity or count mismatch;
- discontinuous active-yarn path not represented by an explicit cut and reattachment;
- illegal frontier transition or unaccounted branch state;
- unintended open boundary or incorrect declared topology;
- non-deterministic canonicalization;
- forward outcome other than `CONVERGED`;
- unresolved forbidden collision;
- any hard geometry threshold violation;
- semantic export round-trip mismatch;
- incomplete mandatory provenance.

No seam preference, visual similarity, average metric, user difficulty preference, or solver vote can override one of these failures.

## Normalization, correction, and retries

**ENGINEERING DECISION:** Only lossless, deterministic normalization declared by the input contract is allowed before validation, for example canonical number serialization or an unambiguous whole-mesh winding reversal. Each normalization event is recorded. Topology repair, hole filling, count invention, attachment guessing, and ambiguity resolution create a new proposed input and require a new verification run.

A retry is a new attempt with explicit changed parameters, budget, seed, or artifact hash. Evidence from an earlier run may be reused only when its complete input set and implementation version are content-identical. Solver fallback may try another candidate, but every candidate starts at the first gate affected by its content; the selected output must have one continuous evidence chain.

## Exceptions and process integrity

- There is no user override that converts a hard failure to pass.
- A threshold change is a versioned profile change, not a retry.
- A golden change requires explicit human approval as specified in [`TEST_STRATEGY.md`](TEST_STRATEGY.md).
- A verifier crash or missing dependency is `E_INTERNAL` or `INDETERMINATE`, never success.
- A warning waiver may allow research inspection, but the resulting state remains `EXPERIMENTAL` or `NOT_VERIFIED` as defined by the profile.

