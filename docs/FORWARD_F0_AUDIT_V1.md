# FORWARD_CLOSED_F0_AUDIT_V1

This package replays successful `FORWARD_CLOSED_F0_V1` evidence from the admitted
physical projection, material profile, recipe, and claimed result. It has no
target-geometry parameter. It rebuilds the initial surface, independently
implements the deterministic label-sine perturbation and rigid gauge, then
recomputes objective forces, line-search decisions, continuous-path checks,
stationarity, multi-start agreement, and the winning coordinates.

`audit_closed_f0(projection, material, recipe, result, *, validator, policy,
gauge_scenario=None, gauge_policy=None)` returns a closed diagnostic record.
The policy profile is `FORWARD_F0_AUDIT_POLICY_V1` and explicitly sets bounded
objective/contact counters and absolute tolerances for coordinates (mm), force
(N), and energy (N*mm), each with owner, rationale, and validation path. The
current ceilings are 20,000 replay objective evaluations and 2,000,000 contact
pair evaluations. Exhaustion returns `INDETERMINATE`; malformed or mismatched
evidence returns `FAIL`. A successful return means only that the successful
producer artifact can be replayed within declared diagnostic arithmetic tolerances.
Every start's coordinates and the selected prediction must match canonical
replay exactly regardless of the diagnostic coordinate tolerance. The auditor
enforces each start's original objective budget as well as its own cumulative
replay budget. Failure reports retain actually consumed work.

Recipe bytes are bounded at 2,000,000 before parsing; decoded recipe/result
values are bounded at depth 64 and 100,000 nodes before recursive hashing.
Oversized text and cyclic in-process values fail explicitly before model work.

The auditor does not import the F0 runner or optimizer. It shares mechanical,
shell, and exact contact constitutive kernels with the producer, and uses the
same Python binary64 and math library. These are common-mode limitations, as are
source authentication and the assumed physical model. Reports always retain
`verification_state=NOT_VERIFIED`, `physical_status=UNTESTED`,
`constitutive_status=HYPOTHESIS`, and `authenticity=NOT_ESTABLISHED`. This audit
is consumed by the optional hypothesis-only V6 adapter; it does not establish
physical validation or independent proof of shared geometry/contact algorithms.

The tests exercise a real successful F0 artifact and rehashed coordinate
tampering, contact-budget exhaustion, plus an accepted Armijo step with changed
alpha and omitted-step mutations. The accepted-step arithmetic fixture tests
the replay state machine; it is not a physical model fixture.
