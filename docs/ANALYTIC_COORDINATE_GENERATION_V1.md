# Explicit coordinate meridian generation V1

This producer contract extends the existing analytic closed single-yarn SC
generator. It does not extend the independent search auditor, forward model or
V7 geometry acceptance. Candidates remain NOT_VERIFIED and physically UNTESTED.

## Admission and compatibility

Use DesignSpec 1.2's authoritative ordered radius/axial knots and the existing
ANALYTIC_COORDINATE_TARGET_V1 admission. Only simple closed pole-ended meridians
in a signed cardinal frame are supported. Exact input geometry predicates,
profile hashes and full axial extent remain unchanged. Interior radii at or below
the configured radius_zero_tolerance_mm are unsupported thin-neck inputs; do
not clamp them. No cap, axial sign or stitch count is added to the target.

Native sphere/ellipsoid and historical radius/arclength inputs retain their
existing generation semantics and serialized search format. Existing saved
projects are never upgraded or regenerated. New generic pilot targets use the
explicit representation; the historical silhouette writer remains available
for compatibility. Canonical CrochetIR and count/phase/compiler rules are frozen.

## Numerical algorithm and budgets

The producer algorithm is EXPLICIT_COORDINATE_MERIDIAN_V1. Coordinates are
represented binary64 millimetres. Compute each segment's differences dr,dz and
Q=dr^2+dz^2 exactly using rationals. A finite positive binary64 hypot estimate a
is only an estimate, even if its input differences were rounded for that call.

Starting at lo=hi=a, widen the bracket by at most two nextafter steps on each
side. Require finite nonnegative lo, positive hi and exact lo^2 <= Q <= hi^2.
The rational comparison certifies this segment-length enclosure independently
of hypot's accuracy. Failure to find a bracket is NUMERICAL_FAILURE; do not
refine indefinitely, substitute an epsilon or silently repair the profile.
Define e=max(a-lo,hi-a), using the exact rational value of a. Each segment's
true length differs from a by at most e. Sum E and all approximate cumulative
lengths in rational arithmetic, preserving strictly positive segment lengths.

The existing max_arc_panels budget counts segments for this algorithm, with at
most 128 segments under target admission. Insufficient budget is
SEARCH_BUDGET_EXHAUSTED. There is no quadrature or adaptive refinement here.
Exact rational preprocessing is O(n), lookup O(log n), and stored data O(n).
The fixed knot limit and finite binary64 exponent range bound rational sizes;
the existing invocation/trace/course budgets bound sample count and search work.
Solver-supplied sample fractions have bounded denominators (at most 1,024 from
512-course midpoint hypotheses); arbitrary large external Fraction objects are
not an API input. The sampling complexity also depends on rational bit lengths.
Target simplicity admission separately retains its 8,128-pair ceiling.

## Tolerance meaning and sampling

arc_length_abs_tolerance_mm bounds total meridian-length approximation error,
not physical accuracy or an accepted candidate-to-target distance. Require
E <= arc_length_abs_tolerance_mm - roundoff_allowance_mm. Converting the exact
approximate total to binary64 must introduce at most roundoff_allowance_mm.
Report E conservatively, rounding upwards if binary64 conversion rounds down.

Sample the declared normalized fraction u using rational u times the exact
sum of approximate lengths. Locate the segment in rational cumulative lengths,
then interpolate its authoritative radius and axial coordinate rationally.
At interior knots, bisect_right selects the next segment with zero weight.
Handle u=0 and u=1 explicitly. Convert returned s/radius/axial to finite binary64
and verify each conversion against roundoff_allowance_mm exactly. Here s is
meridian arclength, while axial is signed local position; neither is substituted
for the other. Nonmonotone axial movement and declared orientation are preserved.

For the exact unrounded interpolated point, its displacement from the true
u-arclength point along the meridian is at most 2E: prefix distortion contributes
at most E, and total-normalization distortion at most uE. The unit-speed path is
1-Lipschitz, so Euclidean displacement also has this bound. Separate radial and
axial rounding bounds delta give the conservative final bound 2E+2delta.
This is producer analysis of its admitted polyline, not an independent V7
certificate, coverage claim, model of yarn or physical crochet error bound.

Owner of these numerical policies: analytic geometry kernel. Validation uses
independent exact-length fixtures, high-precision numerical cross-checks,
scale/reflection/reversal properties and explicit conditioning failures. No
physical calibration is inferred. Nonfinite arithmetic, conversion overflow,
failed enclosures and excessive rounding are NUMERICAL_FAILURE, without fallback.

## Search, evidence and prototype delivery

Reuse the staged global count DP, phase DP and explicit complete-IR compiler.
Course positions remain joint normalized midpoint hypotheses along meridian
length; no independently rounded course counts or axial spacing are introduced.
Original work budgets, deterministic ties and structured terminal outcomes apply.

Coordinate-only proposal provenance records sampler version and numerical work/
error diagnostics. The unchanged ANALYTIC_SEARCH_TRACE_V1 envelope binds the
complete DesignSpec, target, material, run and source snapshots. Its outer
solver/count/phase algorithm identifiers remain unchanged; new coordinate samples
also record axial_mm as an exact rational representation of their binary64 output.
Sampler identity is recorded in the retained proposal's solver parameters.
These new fields/parameters do not appear on older input paths.

API/CLI/jobs reuse generation dispatch. New generic prototype projects preserve
the complete original proposals, trace and existing fixed-zero-phase final link.
Neither producer link nor sampler error analysis completes independent search
acceptance. The untouched sphere-only auditor returns INDETERMINATE with
unsupported_target_sampler for these profiles. Separate future work must replay
the numerical policy and search, implement V7 and complete calibrated physics.
