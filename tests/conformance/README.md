# Canonical conformance vectors

Each positive vector is a static, already accepted domain value. A complete `CrochetIR` input must pass JSON Schema and independent semantic validation, including its resolved DesignSpec and MaterialProfile references, before its canonical projection, JCS UTF-8 bytes, domain-separated preimage, or SHA-256 value can be certified.

`crochet-ir.closed.valid.json` is the smallest closed construction used for this purpose: `MAGIC_RING`, one plain `SINGLE_CROCHET` `REPLACE_SPAN` advance, and a `CLOSE` transition. Its source was derived from the independently validated `make_closed_ir` test construction, then committed as static input. `crochet-ir.closed.canonical.json` is its static JCS projection; the vector records the profile-bound preimage prefix and digest. Python and the independent Node reference both compare their results with these committed values.

The schema-valid `tests/fixtures/schema-valid/crochet-ir.magic-ring-single-course.valid.json` deliberately remains a negative semantic-validation fixture. It has placeholder content hashes, incomplete yarn-path accounting, and an unintended active terminal frontier. It must never be a positive canonicalization vector.
