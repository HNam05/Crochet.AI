# Independent surface topology audit V1

`SURFACE_TOPOLOGY_AUDIT_V1` inspects an explicit oriented triangle complex.
It does not import the cell builder, solver, projection, target or simulator.
It recomputes incidence, connectivity and vertex links from the supplied faces.
`PASS` means a connected closed oriented combinatorial surface with Euler
characteristic 2. This is a combinatorial sphere, not a geometric embedding,
an executable crochet proof, material calibration or physical validation.

## Admission and exact checks

Inputs are lists of unique nonempty ASCII vertex identifiers of at most 128
characters, and triangles containing three distinct declared identifiers.
Budgets are exact positive integers, excluding booleans, bounded by 30,000
vertices and 60,000 faces. List lengths are checked before allocating graph
structures. Malformed inputs and exhausted budgets return no partial audit.

The auditor checks duplicate unoriented faces, unused vertices, edge incidence
exactly two, opposite edge traversal, connectedness and a simple connected
cyclic link at every vertex. Pinching two otherwise valid spheres at one
vertex must fail the link check. Edge incidence and Euler characteristic alone
are insufficient. All checks use exact integer/string operations; there are
no numerical tolerances, coordinates or alignment parameters.

For a valid closed oriented 2-manifold, rational homology dimensions are
`b0 = components`, `b2 = components` and `b1 = 2 * components - Euler`.
The first equality follows from connectivity; each oriented closed component
has one fundamental 2-cycle. Euler's identity gives `b1`. These dimensions
are unavailable when the manifold/orientation prerequisites fail. A torus
therefore reports `(1, 2, 1)` and fails the sphere requirement; two separate
spheres report `(2, 0, 2)` and fail connectedness.

Traversal is iterative and bounded by admitted vertex/face incidence; graph
storage is linear in vertices plus faces. Canonical JCS input and result
hashes have separate profile domains. Exact input order remains bound to the
input digest even when reordering leaves the topology metrics unchanged.
Diagnostics, budgets and metrics belong to deterministic evidence; timing does
not. Hashes prove integrity links, not authenticity.

## Backend integration and remaining proof

API 1.0 `inspect_closed_surface_topology` accepts exactly DesignSpec,
MaterialProfile and CrochetIR. The server validates them, constructs the
target-free projection and closed cells, and independently audits the resulting
complex. Clients cannot submit faces, budgets, claimed hashes or evidence.
CLI `request` and durable jobs use this same boundary.

V4 retains the semantic frontier diagnostics and links the surface audit.
A failed audit is a topology failure. A successful audit alone is insufficient.
V4 also requires the independent [source-cell conformance proof](CLOSED_CELL_CONFORMANCE_V1.md)
and matching DesignSpec topology in the supported closed single-component SC
amigurumi scope. Unsupported construction stays `INDETERMINATE`. Hand-authored
tetrahedron, torus, disconnected and pinched fixtures prevent the builder from
being the auditor's only oracle. V6-V8 and physical acceptance are unchanged.
