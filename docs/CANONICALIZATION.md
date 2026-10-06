# Canonical numbers, bytes, hashes, and semantic projections

## Scope

This contract defines language-independent content identity for structured project artifacts. It does not define geometric tolerances or permit lossy normalization.

- **ESTABLISHED:** RFC 8785 JSON Canonicalization Scheme (JCS) constrains inputs to I-JSON, serializes numbers through IEEE 754 binary64 rules, sorts object properties deterministically, preserves array order, and emits UTF-8.
- **ENGINEERING DECISION:** Project collection registries run before JCS so arrays declared as mathematical sets have deterministic order while semantic sequences remain unchanged.
- **ENGINEERING DECISION:** SHA-256 preimages are domain-separated by artifact profile.
- **PROVEN / FORMAL:** If two accepted values have the same normalized data model and profile, the pipeline below emits identical bytes and hash in every conforming implementation.

Primary sources are [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785), [RFC 7493](https://www.rfc-editor.org/rfc/rfc7493), [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259), and [NIST FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final).

## Normative pipeline

For a structured artifact and declared canonicalization profile:

1. Parse JSON while detecting duplicate object names. Reject duplicates, invalid Unicode, invalid JSON number tokens, and trailing data.
2. Validate the schema and the profile's semantic preconditions before hashing.
3. Require every JSON number to round to a finite IEEE 754 binary64 value using round-to-nearest, ties-to-even. `NaN`, infinities, overflow, and implementation-defined rounding are errors.
4. Require every field declared as an integer to be mathematically integral after parsing and within `[-9007199254740991, 9007199254740991]`. Non-negative identifiers, indexes, counts, seeds, and budgets use `[0, 9007199254740991]` or a narrower schema bound.
5. Compose any profile-declared child projections, then apply the artifact owner's exhaustive ordered-vs-set registry without re-normalizing child-owned collections. Sorting keys are compared exactly as specified by the owning registry, never through locale collation.
6. Serialize the resulting data model with RFC 8785 JCS. Object names use the RFC's UTF-16-code-unit order; arrays are not reordered by JCS; strings are preserved without Unicode normalization; negative zero serializes as `0`.
7. Encode the JCS text as UTF-8 without a byte-order mark.
8. Form the preimage:

   ```text
   ASCII("Crochet.AI") || 0x00 || ASCII(profile_id) || 0x00 || jcs_utf8
   ```

9. Hash that preimage with SHA-256 and encode the digest as 64 lowercase hexadecimal characters.

Content-addressed external assets such as meshes, images, and source files are different: their `artifact.sha256` is SHA-256 of the exact retrieved bytes. A URI is not part of that raw-byte hash. A normalized mesh or parsed graph is a new derived artifact with its own profile, bytes, hash, and provenance; it never replaces the source hash.

### Recursive profile composition

Canonical projections compose as JSON data models before JCS serialization. If a DesignSpec contains `material_profile.binding_type = INLINE`, its canonicalizer must:

1. validate the embedded complete MaterialProfile;
2. call the authoritative `CANONICAL_MATERIAL_PROFILE_PROJECTION_V1` procedure defined in [`MATERIAL_MODEL.md`](MATERIAL_MODEL.md);
3. replace `material_profile.profile` in the DesignSpec working copy with that normalized JSON value;
4. normalize only the remaining DesignSpec-owned collections;
5. serialize and hash the complete result under `DESIGN_SPEC_CANONICAL_JSON_V1`.

The child projection is not serialized to a string and its standalone domain-separated hash is not embedded as a replacement for its content. Standalone MaterialProfile identity serializes the same projection under `MATERIAL_PROFILE_CANONICAL_JSON_V1`; parent and child hashes intentionally differ because their profile IDs and enclosing values differ. Failure to validate or project the child means the parent has no canonical bytes or hash.

## Number semantics

The authoritative numeric value in these JSON profiles is the parsed binary64 value, not the original decimal spelling. Therefore `1`, `1.0`, and `1e0` are identical, as are `-0` and `0`. Two spellings that round to different binary64 values are not semantically identical even when a human considers them close.

Locale syntax is never repaired. `1,5` is invalid JSON rather than another spelling of `1.5`; thousands separators and localized digit glyphs are also rejected. Physical tolerances are applied only after canonical input identity has been established and cannot alter content hashes.

Higher-precision future data must use a separately typed canonical string or rational object under a new profile. It must not silently widen the numeric domain of an existing profile.

## Profiles

| Profile | Structured value covered | Pre-JCS normalization owner |
| --- | --- | --- |
| `DESIGN_SPEC_CANONICAL_JSON_V1` | Complete DesignSpec, recursively including an inline canonical material projection | [`DESIGN_SPEC.md`](DESIGN_SPEC.md) collection registry plus `CANONICAL_MATERIAL_PROFILE_PROJECTION_V1` |
| `SURFACE_OF_REVOLUTION_PROFILE_CANONICAL_JSON_V1` | Radial-profile payload excluding its own hash | [`DESIGN_SPEC.md`](DESIGN_SPEC.md) ordered sample contract |
| `SURFACE_OF_REVOLUTION_COORDINATE_PROFILE_CANONICAL_JSON_V1` | DesignSpec 1.2 explicit radius/axial-coordinate profile excluding its own hash | [`ANALYTIC_COORDINATE_TARGET_V1.md`](ANALYTIC_COORDINATE_TARGET_V1.md); samples remain ordered |
| `CROCHET_IR_CANONICAL_JSON_V1` | Complete canonical CrochetIR | [`CROCHET_IR.md`](CROCHET_IR.md) collection registry |
| `MATERIAL_PROFILE_CANONICAL_JSON_V1` | Complete MaterialProfile | [`MATERIAL_MODEL.md`](MATERIAL_MODEL.md) authoritative material projection |
| `FORWARD_PHYSICAL_SEMANTICS_V1` | Target-free physical-semantic projection | [`FORWARD_MODEL.md`](FORWARD_MODEL.md) projection registry |
| `CROCHET_SEMANTIC_EQUIVALENCE_V1` | Execution-normalized construction-semantic projection | [`CROCHET_IR.md`](CROCHET_IR.md) equivalence algorithm |
| `INDEXED_TRIANGLE_MESH_CANONICAL_JSON_V1` | Geometry-valid normalized `IndexedTriangleMeshV1`, excluding parser provenance | [`GEOMETRY_MODEL.md`](GEOMETRY_MODEL.md) ordering registry |
| `V0_NUMERICAL_GEOMETRY_PROFILE_JSON_V1` | Complete immutable V0 numerical-profile record | [`NUMERICAL_GEOMETRY.md`](NUMERICAL_GEOMETRY.md); all objects closed and no arrays |

The profile ID is part of the hash preimage even when it is already present in the JSON. Identical JCS bytes under two profiles intentionally produce different digests.

## Project golden vectors

The first three input spellings below must parse to the same data model.

```json
{"b":1.0,"a":-0,"c":1e0}
```

```json
{ "c" : 1, "b" : 1, "a" : 0.0 }
```

```json
{"a":0,"b":1,"c":1}
```

Their JCS text is exactly:

```text
{"a":0,"b":1,"c":1}
```

| Profile | Expected SHA-256 |
| --- | --- |
| `DESIGN_SPEC_CANONICAL_JSON_V1` | `cdad409ca7db907c63cefbf9419ded3e5d98c912727fc679ca961c41e2f65fb7` |
| `CROCHET_IR_CANONICAL_JSON_V1` | `24b70ba3e19d9fed9d745864bdabf3dbbc691c5c0fd562e118d126ac2e79facb` |
| `MATERIAL_PROFILE_CANONICAL_JSON_V1` | `523c79e971d664987874a04775b9c77bb9bf53fc39addeaf53f3081d8fa305e5` |
| `CROCHET_SEMANTIC_EQUIVALENCE_V1` | `1738a2edfbdee2bcd7a179ad9fc7f28aaa393b0eab29535f3a27b23181729da4` |

The RFC 8785 number sample

```text
{"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}
```

has DesignSpec-profile hash `bae5838c18dfb2b1582606064ffbf24f7c838f753ffa8824baeab6f0445447bc`.

An implementation is not conforming until it passes the RFC 8785 Appendix B number vectors and project vectors in at least two independently maintained language runtimes. A disagreement is `E_DETERMINISM`; no runtime is selected as correct by majority vote.

## Adversarial cases

- Duplicate `value_mm` keys fail before one parser can keep the first and another the last.
- `9007199254740992` in an integer field fails even if a runtime can store it in a wider integer type.
- `1e400`, `NaN`, and `Infinity` fail rather than becoming infinities or strings.
- `-0.0` hashes like `0`; `0.0000000000000001` does not.
- Reordering a declared set is harmless after registry normalization; reordering `construction_sequence`, a frontier boundary, or a radial profile is a semantic change or an invalid artifact.
- NFC and NFD spellings of a display label remain byte-distinct under content identity. Display labels are excluded only where a separate semantic projection explicitly says so.

## Failure boundary

Canonicalization never repairs schema, references, topology, units, or unsupported features. A value that cannot be validated under its declared profile has no canonical content hash. Verification records the profile and implementation version used for every accepted digest.
