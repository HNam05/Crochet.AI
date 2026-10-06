# Backend handoff

Latest checkpoint: 2026-10-06. Read this file before continuing backend work.
This is a working implementation checkpoint, not full backend acceptance.

## Repository and product

- Primary checkout: `C:\Users\hanne\OneDrive\Dokumente\Crochet\Crochet.AI`.
- Repository: `https://github.com/HNam05/Crochet.AI`, branch `main`.
- User authorized continuing backend implementation and committing/pushing the
  code and status notes in the current request. Never force-push.
- Local browser testing comes first; a separate mobile app is still required
  later. Current prototype layout is sufficient; prioritize backend completion.
- CrochetIR is canonical. Preserve solver/verifier separation, deterministic
  bounded generation, fail-closed gates, frozen schemas and human-approved goldens.

## Implemented so far

- Canonical schemas/hash profiles and exact semantic/reference/frontier checks.
- Bounded analytic closed-pole single-yarn SC proposals, global count DP followed
  by phase DP, explicit compilation to complete CrochetIR.
- Local six-shape pilot, live instruction/stitch progress and schematic object
  preview, saved projects/sessions, optimistic revision conflicts, feedback.
- English printable PDF: Round/R1 notation, MR/SC increases/decreases, parenthetic
  total stitches at the end of each round, no newly-created-stitch totals.
- Versioned API/CLI, durable SQLite jobs, bounded transport/process isolation,
  wheel packaging and isolated installation checks.
- Calibration campaign/store, printable measurement packet and draft material
  derivation. Physical measurements are not invented or accepted as calibrated
  merely because their software records validate.
- V0 mesh admission and ideal sphere/ellipsoid target subset. Generic signed
  radial targets and native cylinder/cone interface semantics remain partial.
- Target-free shaped-cell construction, independent surface manifold/Euler/Betti
  audit and independent raw-IR-to-cell conformance. V4 can PASS only in the
  documented closed single-component/branch/yarn SC subset.
- Independent V5 candidate-claims subset: counts, binary transitions, balanced
  shaping, phases, construction maxima, parameter/hash/material/run conditions.
  Contradictions FAIL; absent complete search/physical evidence stays incomplete.
- Experimental target-free stretch/shear/bending and contact diagnostics are
  computational slices, not complete physical F0/V6 acceptance.

## Previous producer checkpoint

Producer-only `ANALYTIC_SEARCH_TRACE_V1`: input/config/target/source bindings;
ascending hypothesis prefix; exact circumference/window inputs; per-pass/layer
count and phase work/state accounting; interruption and terminal causes;
proposal IR hashes. Immutable JCS trace/hash is outside canonical IR and exposed
by generation API/CLI/jobs. New prototype projects persist a separate hashed
proposal-to-final link for FIXED_ZERO_CONTINUOUS_V1 recompilation. Legacy projects
are not rewritten or given invented traces. Trace reservation is bounded at
8,192 attempted course slots per invocation.

The independent V5 checker is deliberately unchanged in this producer task.
Trace integrity/availability does not establish independently verified search.
Full verification remains NOT_VERIFIED and physical status UNTESTED.

## Independent replay checkpoint

`ANALYTIC_TRACE_AUDIT_V1` now independently replays the complete staged bounded
sphere/equal-axis-ellipsoid search. It recomputes input/config/material/target
bindings, samples, integer windows, both count-DP passes, phase-DP objectives and
exact ties, all layer work/interruptions, ascending hypothesis prefix, remaining
global budgets, terminal cause and original proposal hash order. Every supplied
raw proposal is independently checked for actual count/phase schedule, bounds,
declared source/config consistency and work claims. Proof work is capped at
6,000,000 units. Neither replay kernel imports producer generation code.

API/CLI/jobs expose `inspect_analytic_search_trace`. Optional `search_evidence`
on `verify_candidate` binds the audit into V5 evidence. False trace claims FAIL;
missing original proposals, proof exhaustion or unsupported samplers remain
INDETERMINATE. Native candidate membership is checked before confirming trace
checks. V5 still awaits physical feasible-selection evidence. Audit PASS does
not authenticate source execution or pass V6-V8/V10; the report explicitly says
source_authentication=NOT_VERIFIED and physical_status=UNTESTED.

The prototype verification route now replays stored traces diagnostically.
Current stored projects contain only the original proposal hash, so their exact
original-proposal binding remains incomplete. Legacy requests are unchanged.
Do not regenerate missing proposals or silently rewrite existing projects.

Independent small exhaustive/hand oracles caught and repaired a DEC-center
arity error in the new verifier before integration acceptance. Count/phase
producer implementations, authoritative schemas and goldens are unchanged.

## Validation and runtime

Previous accepted V5 claims checkpoint: 1,050 Python tests, Ruff, strict mypy on
79 source modules, five independent Node canonical vectors, ten frontend tests;
wheel dependency/isolated smoke and CLI/HTTP proof equality passed.
Current trace checkpoint: 1,062 Python tests passed in 412 seconds; 48 targeted
analytic tests and four API/job/prototype/legacy tests also passed. Ruff, strict
mypy on 80 source modules, five Node canonical vectors and ten frontend tests
passed. Wheel dependency and isolated installed smoke checks passed. HTTP,
source CLI and installed CLI producer traces/proposal hashes agree exactly.
The pre-instrumentation solver comparison preserves both proposal hashes.
Code and this handoff are versioned together on `main`. For exact publication
revision, compare `git rev-parse HEAD` with `git ls-remote origin refs/heads/main`;
never treat an old note as confirmation of current GitHub or runtime state.

Independent replay checkpoint: 1,114 full-suite tests passed in 550.37 seconds.
After the final direct-call evidence-size guard, 90 count/phase/audit/API/pipeline
tests passed in 17.09 seconds. Ruff and strict mypy (84 source modules), five Node
canonical vectors and ten frontend tests passed. Final wheel build/install,
dependency check and isolated smoke passed. Source and installed CLI return
identical PASS reports for the historical native sphere proposal (44,289 proof
units); source CLI and live HTTP return identical INDETERMINATE stored-project
reports with only original_proposal_artifacts missing. Nine projects are retained.
The focused independent review found no additional fail-open computational claim.

Local browser: `http://127.0.0.1:8765/`.
Start from repository root: `.venv/Scripts/python.exe -u tools/run_prototype.py --port 8765`.
Persistent private projects/feedback: `artifacts/local-prototype/` (ignored).
Eight saved legacy projects existed before this task; their sessions are preserved.
Nine projects are now saved, including a new traced sphere test project.
Generated PDFs under `output/pdf/` are local exports, not authoritative fixtures.
Do not infer installed runtime or remote branch state from this note; check live.

## Next work in order

1. Separate producer/persistence task: retain complete original proposal artifacts
   for new projects with bounded storage/transport and versioned final relation.
   Existing historical hash-only projects remain incomplete. The independent
   sphere trace-replay package above is implemented; broader target samplers,
   proposal-to-final verification and physical feasible selection remain open.
2. Version complete generic analytic target coordinates before V7. Current r(s)
   does not determine axial movement signs for general profiles.
3. Complete physical rest/shaping/loading/contact model for actual generated
   INC/DEC cells and open calibration fixtures; retain target-free simulation.
4. Implement independent V6 convergence, V7 geometry comparison, V8 material
   robustness and feasible-candidate selection, then V10 bound provenance.
5. Complete uncertainty/calibration provenance, broader topology/solver domains,
   M1B/full export acceptance, recovery/security/release acceptance. See the full
   roadmap; this list does not waive any package acceptance requirement.
6. Collect real crochet feedback/specimen measurements. Human physical trials and
   new golden approvals are separate gates. Develop the separate mobile app later.

## Reading and commands

Contracts: `BACKEND_IMPLEMENTATION_ROADMAP.md`, `BACKEND_ACCEPTANCE_PLAN.md`,
`ANALYTIC_SEARCH_TRACE_V1.md`, `ANALYTIC_CANDIDATE_CLAIMS_V1.md`,
`VERIFICATION_PIPELINE.md`, then the affected subsystem contract/skill.

Quality: `.venv/Scripts/python.exe -m pytest -q`,
`.venv/Scripts/python.exe -m ruff check src tests tools`,
`.venv/Scripts/python.exe -m mypy src`, `git diff --check`.
Node: `tools/canonical_reference.mjs tests/conformance/canonical-vectors.json`
and `tools/prototype_frontend_tests.mjs`.
CLI: `python -m crochet_ai.cli --json request --request-file <request.json>`.
Build/install evidence and cost notes live under ignored `artifacts/`; missing
worker token/cost measurements remain null. Never report software tests as
physical proof or call the complete backend finished from this checkpoint.

## Faster continuation without reducing acceptance

Prioritize R1 end-to-end completion; R2/R3 remain promised later scopes. Bundle
one coherent acceptance package per checkpoint, including API/persistence/status
integration, rather than serial small producer-only changes. Independent count
and phase replay implementations were developed concurrently; primary owned
the envelope, API integration and critical review. Use at most the documented
bounded worker count and keep generation/independent verification separate.

Run each worker's targeted oracle tests, then one complete suite at integration.
Run Ruff/mypy/Node independently in parallel; installed-wheel checks verify the
delivered package. Full-suite `--durations=15` evidence is retained under ignored
`artifacts/backend-trace-audit/pytest-full.log`. Optimize measured hotspots next;
do not add test parallelism or cross-module shared mutable fixtures without
evidence. Physical measurement work can proceed alongside software completion,
but must use real specimens and cannot be inferred from software checks.

Measured suite hotspots include prototype trace/legacy persistence (37.87 s),
V5 proof-budget routing (26.70-27.45 s) and shape generation (up to 26.30 s).
These remain required checks. Investigate repeated generation/validation before
sharing fixtures or adding parallel pytest execution. The initial local pip
installer continued consuming CPU after its successful-install message; that
owned helper was stopped after installed-package verification. A local-only
wheel invocation with --no-index/--no-deps and --disable-pip-version-check plus
dependency check finished in 4.04 s. This is a per-command release-check choice,
not a global pip, cache, credential or security configuration change. The full
suite timing is not a controlled before/after speed comparison. Worker token and
cost measurements were unavailable and remain null in ignored agent-cost notes.
