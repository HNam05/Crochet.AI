# Numerical verification context V1

`NUMERICAL_VERIFICATION_CONTEXT_V1` is an internal, exact-field package for
fresh hypothesis-model numerical runs. It does not change the frozen pipeline
profile or claim calibration, ideal-surface certification, or physical
verification.

The context has exactly `profile`, `schema_version`, `forward_run`,
`target_sampling`, `comparison_policy`, `scenario_policy`, `audit_policy`,
`rigid_alignment`, and `max_scenario_runs`. The profile version is `1.0.0`;
`forward_run` is admitted by `FORWARD_CLOSED_F0_V1`; scenario runs are bounded
from five to nine. The alignment is a finite 4x4 proper rigid transform with
orthonormal rotation, determinant +1, and an affine final row. It is applied
after target-free F0 and before comparison; it cannot scale, deform, or affect
solver initialization.

`target_sampling` retains the analytic sampler policies. For a `MESH_3D`
DesignSpec it instead requires exactly
`{"profile":"MESH_ADMITTED_TARGET_SURFACE_V1","schema_version":"1.0.0"}`.
The numerical runner then requires the original `mesh_json` bytes and the same
`V0MeshBudgets` supplied to the pipeline. It reruns closed, single-surface V0
admission, checks the source hash and coordinate frame against the DesignSpec,
requires the closed amigurumi profile with one expected component and exact
Euler characteristic 2, and compares directly with V0's authoritative
normalized `IndexedTriangleMeshV1`.
This branch performs no interpolation, resampling, repair, or reinterpretation;
its evidence records the source, normalized-mesh, and V0 evidence hashes.
Missing bytes/budgets, changed source bytes, a wrong sampling profile, or frame
mismatch fail closed. Analytic target handling remains unchanged.

`build_numerical_gate_runners` takes admitted DesignSpec, MaterialProfile,
CrochetIR, validator, context, a 40-character software commit, and the exact
source snapshot mapping `{source_snapshot_sha256, implementation_identity}`.
The verifier recomputes both values from the running source/runtime and rejects
mismatches. This checks metadata consistency; checkout/commit authenticity
remains `UNCONFIRMED`. It returns callbacks for V6, V7, V8, and V10, plus
input hashes and the artifact state produced by those callbacks. V6 runs a
fresh target-free F0, checks its serialized result digest,
required starts and work bounds, and independently replays the converged
coordinates and accepted optimizer steps with `FORWARD_CLOSED_F0_AUDIT_V1`.
The audit is separately hashed and must pass before V6 can pass. The replay
shares constitutive energy, shell, and contact kernels with the producer, so
those remain explicit common-mode limitations. Replay budget exhaustion is
`INDETERMINATE`; a mismatch fails closed. Neither replay nor source hashes
authenticate the executing checkout. V7 consumes that exact audited V6
prediction, creates a target-only sampled mesh, registers the predicted mesh
rigidly, and applies the supplied comparison policy. V8 builds the exact five
nominal/endpoint material cases, reuses V6 for nominal, and freshly runs all
four corners under one cumulative cap. Every converged scenario requires the
independent replay audit; failed endpoints fail V8 and audit/work incompleteness
remains `INDETERMINATE`. V10 binds the five audit hashes, DE/US/UK semantic
export round trips, runtime identity, and source snapshot, and always records
physical status `UNTESTED`. Its provenance chain labels source execution
authentication `NOT_ESTABLISHED` and commit-to-checkout binding `UNCONFIRMED`;
the V10 consistency scope does not support an authenticated release claim.

The comparator's policies remain diagnostic hypotheses. A PASS means only
that every declared metric in the supplied comparison policy passed against
the selected target representation: an analytic sampled binary64 mesh or the
V0-normalized admitted mesh. The analytic sampler excludes binary64 rounding from its
reported bound, so this does not prove ideal-surface acceptance. F0's uniform
constitutive parameters are hypotheses, and the five empirical endpoints do
not prove continuous uncertainty coverage. Gate PASS values do not imply
`VERIFIED`, `CALIBRATED`, or `PHYSICALLY_VERIFIED`.

Each comparison-policy landmark uses exactly
`{name, predicted_vertex_index, target_xyz_mm}`. The prediction coordinate is
looked up from the decoded predicted mesh at that index; policy input cannot
assert its own predicted coordinate. `target_xyz_mm` is a declared diagnostic
coordinate in the DesignSpec frame. In numerical verification, the integration
must bind every declared DesignSpec landmark name, position, and frame to the
policy and ensure the normalized threshold respects each declared tolerance.
The standalone comparator validates and reports its supplied declaration but
does not authenticate it against a DesignSpec. A zero normalized landmark
threshold is permitted for zero-tolerance declarations; other non-topology
hard thresholds remain strictly positive.

The rigid transform is admitted as a right-handed isometry with fixed binary64
checks: absolute orthonormality and determinant error at most `1e-10`, and final
affine-row error at most `1e-12`. These dimensionless tolerances are owned by
`NUMERICAL_VERIFICATION_CONTEXT_V1`, justified as binary64 isometry admission
checks, and validated by the context-admission tests. Translation is in mm and
has no independent shape tolerance. Comparison metric thresholds retain their
own explicit unit, owner, rationale, and validation path; angular metrics use
degrees and normalized metrics use `1`. The topology mismatch threshold must be
exactly `0`, so any topology mismatch fails.

`audit_policy` has exactly `profile='FORWARD_F0_AUDIT_POLICY_V1'`, bounded
`max_replay_objective_evaluations` (1..20,000) and
`max_contact_pair_evaluations` (1..2,000,000), nonnegative finite absolute
coordinate/force/energy replay tolerances, and nonempty owner, rationale, and
validation-path fields. These tolerance values are caller-admitted review
policy; they do not imply calibration. The audited numerical scope is
`TARGET_FREE_F0_COMPUTATIONAL_REPLAY`, with authenticity `NOT_ESTABLISHED`.

| Capability | Status |
| --- | --- |
| Bounded target-free F0 execution and independent replay | Experimental computational evidence |
| Sampled-mesh comparison and five material endpoint scenarios | HYPOTHESIS; ideal-surface and continuous-uncertainty claims excluded |
| Source snapshot/runtime consistency | Checked; checkout authenticity unconfirmed |
| Material calibration, physical artifact acceptance | Not established; physical status remains `UNTESTED` |
