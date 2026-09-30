# Numerical geometry profile 2: explicit adjacent policy

Additive user-approved contract, 2026-09-30. The frozen profile 1 and its
schema remain unchanged. The authoritative new record is
`profiles/v0-mesh-numeric-profile-2.json`, validated against
`schemas/numerical-geometry-profile-1.1.schema.json`.

- Profile ID: `v0_num_mesh_binary64_adjacent_barycentric_v2`
- Profile version: `2.0.0`; record schema version: `1.1.0`
- Canonical SHA-256: `b3f5a562c89d47a8c6a07020f7b7626ef8fea25ea6951a866ffcbe80151de7ae`

The preimage remains `Crochet.AI`, NUL,
`V0_NUMERICAL_GEOMETRY_PROFILE_JSON_V1`, NUL, and RFC 8785 canonical record
bytes. Record version, profile ID and policy fields bind the new semantics.
The resolver rejects modified records. Its immutable result is not a
legacy-profile subclass and must not be passed to V1-only operations.

Existing binary64 threshold values, units and comparison operators are
preserved. The closed `adjacent_exclusion_policy` record adds:

- `policy_id`: `BARYCENTRIC_PAIR_LOCAL_V1`
- `lambda_source`: `REQUIRED_DESIGN_SPEC_REDUCED_RATIONAL_V1`
- `exclusion`: `PAIR_BOTH_INSIDE_OPEN_ZONE_V1`
- `unit`: `DIMENSIONLESS`, with rationale, owner and calibration path.

DesignSpec 1.1 supplies the mandatory reduced rational parameter described in
[`DESIGN_SPEC_1_1.md`](DESIGN_SPEC_1_1.md). No default, automatic reduction or
metric interpretation is permitted. The exact retained pair domain and
original-contact rejection rule are in
[`ADJACENT_RESIDUAL_EXPERIMENT.md`](ADJACENT_RESIDUAL_EXPERIMENT.md).

Schema admission and experimental residual computation do not establish full
V0 acceptance. Complete version-specific pipeline integration, clearance
classification, normalization and independent verification remain gates.
Retessellation invariance and physical calibration are not claimed.

The schema loader validates both versions. `schema_documents()` preserves its
legacy six-schema compatibility view; `include_additive_versions=True` returns
all eight schemas. CLI doctor and isolated installed smoke use the complete
view. Packaging includes both numerical records with byte-parity checks.
