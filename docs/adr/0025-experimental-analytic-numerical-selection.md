# ADR 0025: Separate local candidate proof from numerical batch selection

Status: accepted for the additive experimental contract, 2026-10-19.

V5 precedes V6–V8 but the old checkpoint includes missing downstream selection
and physical verification in its V5 report. Requiring that unchanged V5 report
to PASS before selecting a numerically feasible candidate creates a cycle.

Changing the old profile would silently alter its obligations. Omitting V5 or
trusting client-supplied PASS reports would lose the independent local proof.
We instead add an explicit uncalibrated local-proof profile requiring all gates,
retain its deferred obligations in evidence, and issue a separate bounded
post-verification selection artifact. The default checkpoint and generator stay
unchanged. Every numerical candidate must pass fresh V6–V10 as well.

The fixed lexicographic metric order is a total extension of coordinatewise
Pareto dominance and resolves otherwise incomparable vectors without weighted
aggregation. It is versioned with the selection profile, not retroactively
imposed on other domains. Input/work limits and exact ranking are defined in
[ANALYTIC_NUMERICAL_SELECTION_V1](../ANALYTIC_NUMERICAL_SELECTION_V1.md).

Successful software execution remains experimental and physical status UNTESTED.
Authenticated execution, real material identification, calibrated thresholds,
holdouts and full R1–R4 release acceptance remain separate obligations.

Integration exposed an existing comparator defect: comparing full topology
records required equal triangulation counts, rejecting retessellated spheres.
The scoped implementation 1.1.0 compares independently proved connected closed
orientable genus-zero classes and retains all count diagnostics. Other scopes
keep the strict existing comparison. Independent subdivision and torus/open
counterexamples guard this correction; no geometric tolerance was loosened.
