# Diagnostic whole-component winding proposal

`propose_indexed_triangle_mesh_winding` is a non-mutating proposal, not V0
acceptance or a canonical semantic mesh identity. It re-decodes the source and
recomputes exact index topology, nondegeneracy, ordering, complete original
face-pair relations and, for closed meshes, algebraic signed six-volume.
The immutable V1 numerical profile is re-resolved before its thresholds are
read. Profile subclasses and altered records cannot stand in for the builtin.

An invalid topology, inconsistent local winding, coordinate coincidence,
degenerate face or forbidden original contact rejects the proposal. Whole-work
face and closed-volume vertex-pair caps are checked before those geometric
stages. Required vertex-pair work and actual evaluated work are separate;
all-open meshes evaluate no volume/diameter pairs.

A closed component with reliable positive algebraic six-volume is retained.
A reliable negative component may receive exactly one recorded
`WHOLE_COMPONENT_REVERSAL`; no individual-face repair is permitted. Equality
or insufficient magnitude at the immutable reliability boundary rejects as
orientation-indeterminate, with no partial proposal. The original source bytes
are never changed. The exact threshold fixture has diameter one and six-volume
`z/2`; values immediately below, on and above `z = 2^-35` are independently tested
in both winding directions.

All-open components preserve their source-directed winding, report
`OPEN_ORIENTATION_NOT_NORMALIZED` and carry no invented volume or outward
orientation. Mixed open/closed meshes are explicitly unsupported by this
bounded stage because the current signed-volume API requires a wholly closed
mesh. A source-bound per-component volume interface is the next software step
for that case; submesh bytes must not silently replace original provenance.

After a permitted reversal, faces are cyclically rotated and sorted anew, and
both face-index maps are rebuilt. Vertex coordinates and identities are not
rounded, welded or removed. Exact per-component volume values, component events,
all source/evidence/profile hashes, versions, maps, budgets and unresolved gates
are bound into a source-specific diagnostic digest. This digest is not the
canonical normalized-artifact hash required by complete V0 admission.

Near-contact/threshold completion, robust-backend admission certification,
boundary assignment, the full normalization record and physical validation
remain independent gates. Operation counts bound pair enumeration, not the
machine-dependent cost of arbitrary-precision integer arithmetic.
