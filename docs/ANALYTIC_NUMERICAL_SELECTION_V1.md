# Analytic numerical candidate selection V1

`ANALYTIC_NUMERICAL_SELECTION_V1`, version `1.0.0`, is an additive experimental
batch operation. It does not change the default verification profile, schemas,
approved goldens, generator, physical acceptance or certification contracts.

## Local proof and downstream selection

The separate `ANALYTIC_NUMERICAL_CANDIDATE_V1` profile requires all V0–V10 in
their existing order. Its V5 scope is the independently proved analytic
construction, emitted-proposal membership, complete bounded search trace and
recorded search ties. A successful local proof may PASS only after every local
claim has been proved. The two old checkpoint omissions are explicitly deferred:
`deterministic_candidate_selection_and_tie_break` belongs to this later batch
selection artifact; `physical_verification` remains outside this uncalibrated
computational profile. They remain recorded as deferred obligations, not claimed
proved or removed from the old checkpoint. Every other missing check still
prevents local PASS. The old default V5 behavior is unchanged.

The old claim report also requests optional prototype metadata when none exists.
For a native IR with no `prototype.*` parameters, complete trace PASS and exact
emitted-proposal membership establish that these three prototype-only omissions
are not applicable. The local profile records that decision separately. Partial
prototype metadata or a non-native artifact cannot use this exemption; this
profile requires native membership. The underlying default claim report is
retained unchanged in linked evidence.

V6–V8 use fresh target-free F0, independent replay, all ten sampled-geometry hard
metrics and all five gauge scenarios. V9 and V10 also run for each candidate;
requiring their PASS before ranking is stronger than minimum V0–V8 feasibility
and keeps export/provenance defects out of the returned pattern. Source/runtime
consistency does not authenticate the checkout. No calibrated profile is
registered and physical status always remains `UNTESTED`.

## Inputs, limits and failure semantics

The batch receives DesignSpec, MaterialProfile, complete `search_evidence`
(`run_config`, `search_trace`, `candidate_proposals`), a numerical context and
`selection_policy`. Only native, closed, single-yarn analytic SC proposals in
the independently audited emitted batch are considered. Target meshes,
postprocessed prototype substitutions, supplied evidence/gate runners, source
identity overrides and calibration claims are not accepted inputs.

`selection_policy` has exactly `profile`, `schema_version`, and
`max_candidate_evaluations`; the profile/version are those above and the limit
is an integer from 1 to 8, no greater than DesignSpec's candidate limit. The
emitted batch itself contains at most eight proposals. The numerical context
must reserve exactly five scenario runs per candidate. Consequently at most
40 fresh forward/scenario runs are reserved; every F0/geometry/replay operation
retains its existing deterministic inner budget. There are at most nine complete
trace audits (one batch audit and one per evaluated candidate). Transport and
search-evidence complexity bounds also apply to direct calls.

Global design/material/context/runtime and complete trace admission precede
candidate execution. A contradicted trace rejects the batch; an unproved audit
returns incomplete evidence. A candidate defect or unsupported numerical source
is retained with its diagnostic and cannot become eligible. Unexpected internal
exceptions are not swallowed. Candidate evaluation is in the audited proposal
order. A budget-limited prefix never produces a selected output, even if a
prefix member passed. No result is called unreachable merely because none passed.

All emitted members must be accounted for. Generation terminal status, cause
and completeness are retained. Selection is only over this emitted finite set;
an exhausted generation search is never relabeled globally complete/optimal.
The batch evidence binds the full request, implementation identity, software
commit, profile, every candidate's verification evidence and ranking decision.
Timing is telemetry outside its canonical digest. The selection digest is
SHA-256 of `Crochet.AI\0ANALYTIC_NUMERICAL_SELECTION_V1\0` followed by JCS of
the result with `selection_evidence_sha256` set to the empty string and only
`candidate_results[*].verification.gates[*].telemetry` and
`selected_verification.gates[*].telemetry` removed. All other fields, including
linked evidence, remain bound. The returned result retains the telemetry.

## Ranking

Every required gate must be PASS, without missing checks, warnings or false
assertions. Only then derive construction counts from independently checked raw
IR and the metric vector from fresh V7 evidence. No generator score is used.
The total ordering is lexicographic:

1. sewn seams, yarn cuts, reattachments;
2. symmetric Chamfer, robust Hausdorff, `1 - silhouette_iou_min`, mean normal
   error, P95 normal error, section error, curvature error, relative volume error,
   landmark maximum error;
3. stitch count, course count, number of shaping nodes;
4. canonical CrochetIR SHA-256.

This explicit lexicographic order of the nine geometry metrics extends
coordinatewise Pareto dominance: a dominated vector cannot defeat its dominator at equal construction
cost. Incomparable metric vectors use the first differing declared component.
It resolves the generic partial-/total-order wording for this version only.
Binary64 observations are compared as exact rational values; IoU complement is
computed exactly for ranking. No numerical tolerance, weighted sum, threshold
normalization or aggregate confidence is introduced. Units remain those of
each separately gated metric. Complexity is O(k log k) comparisons of fixed-size
keys after bounded verification; evidence storage is linear in admitted input
and per-candidate evidence.

`SELECTED` returns the native IR, its full verification, exact ranking data and
the post-verification selection digest. It is at most `EXPERIMENTAL`.
`NO_FEASIBLE_CANDIDATE`, `INDETERMINATE`, `REJECTED`, and `BUDGET_EXHAUSTED`
return no selected IR and preserve all reached causes. `SELECTED` describes the
chosen candidate, not a PASS for every batch member. Rejected or incomplete
members remain visible with their reached evidence and causes; they are excluded
from ranking and do not veto a different fully passing member after full batch
accounting. A selected
candidate's export is still subject to the existing human/physical trial process.

## Required evidence

Tests cover two real independently audited numerical candidates, rejection of
a structurally simple but numerically failing candidate, exact metric dominance
and incomparable vectors, hash ties, missing/false evidence, manipulated search
membership, budget truncation, no-candidate terminals, default-profile isolation,
source/installed CLI and durable-job delivery. Synthetic compliant materials
and deliberately permissive test thresholds are labeled plumbing fixtures;
they cannot be promoted to physical acceptance.

Common-mode limits include shared constitutive/contact/comparison kernels,
sampled target surfaces and five endpoint scenarios. Selector tests use raw
independent ranking tables and dominance oracles, plus actual numerical runs;
mocked gate outcomes alone do not establish the integration's positive path.

## R1 topology comparison correction

Geometry comparator implementation `geometry-comparison/1.1.0` retains V/E/F
diagnostics but does not require identical triangulations for two independently
proved connected, closed, orientable genus-zero surfaces. Both records must
have components 1, boundary edges 0, Euler characteristic 2 and Betti tuple
(1,0,1). The reported comparison rule identifies that narrow classification.
Outside it, the previous strict full-record comparison remains; generalized
component/boundary correspondence is not established. No metric threshold,
manifold admission, volume or curvature rule is relaxed. Comparator version,
rule and result hash are bound transitively into numerical and selection evidence.
