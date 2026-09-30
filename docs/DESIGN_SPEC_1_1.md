# DesignSpec 1.1: explicit adjacent exclusion zone

User-approved additive contract, 2026-09-30. The frozen 1.0 schema and numerical
profile remain unchanged. Version 1.1 preserves the existing domain, reference,
material, solver-budget, stitch-intent and gate requirements; no new solver or
physical capability follows from schema acceptance.

The normative schema is `schemas/design-spec-1.1.schema.json`. The root
`schema_version` is `1.1.0`. A mesh target may select the legacy numerical
profile or `v0_num_mesh_binary64_adjacent_barycentric_v2`.

With the new numerical profile, `target_geometry.adjacent_exclusion_zone` is
mandatory and closed:

```json
{
  "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
  "lambda": {"numerator": "1", "denominator": "2"}
}
```

The example is not a default or a recommended physical value. The numerator
and denominator are positive ASCII decimal strings without signs, whitespace
or leading zeroes. Both have at most 512 bits. Semantic validation requires
`0 < numerator < denominator` and coprimality. Unreduced fractions, floats,
booleans, missing values and out-of-range values fail; consumers never
auto-reduce, clamp or insert a zone size.

The legacy numerical profile forbids this field, including inside a 1.1
DesignSpec, so a supplied parameter cannot be silently ignored. Version 1.0
accepts neither the new numerical profile nor the new field. Non-mesh target
variants retain their closed existing shapes.

The existing DesignSpec canonical projection and domain separator are reused:
the projection algorithm and array registry are unchanged. The schema version,
numerical-profile ID, policy ID and complete reduced rational value participate
in the content hash. Changing the zone changes design identity; object-key
ordering does not. Referenced assets and material content remain separately
validated and hash-bound.

The zone is dimensionless and face-relative, not a metric-radius tube. Mesh
retessellation can change the retained regions and classifications. This is
explicitly accepted for the new version, not silently imposed on V1. See
`ADJACENT_RESIDUAL_EXPERIMENT.md` for the exact pair-domain equations. Full
original-face contact beyond an intended shared entity is always forbidden,
even inside the local zones.

Individual runtime operations must explicitly declare support for the new
profile. An old diagnostic rejects it as unsupported instead of substituting
the legacy profile or claiming V0 acceptance. Admission, normalization, complete
geometry verification and physical evidence remain separate release gates.
