# Backend handoff

Latest checkpoint: 2026-10-05. Read this file before continuing backend work.
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

## Current implementation task

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

Local browser: `http://127.0.0.1:8765/`.
Start from repository root: `.venv/Scripts/python.exe -u tools/run_prototype.py --port 8765`.
Persistent private projects/feedback: `artifacts/local-prototype/` (ignored).
Eight saved legacy projects existed before this task; their sessions are preserved.
Nine projects are now saved, including a new traced sphere test project.
Generated PDFs under `output/pdf/` are local exports, not authoritative fixtures.
Do not infer installed runtime or remote branch state from this note; check live.

## Next work in order

1. Separate independent trace-admission/replay task. Bind untrusted producer trace
   to actual DesignSpec, material, run config and proposal IR; independently check
   windows, prefix/work/completion, staged count/phase objective and exact ties.
   Add exhaustive small-domain positive/negative oracles, interruption cases and
   tampered refreshed hashes. Do not import the producer solver as the verifier.
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
