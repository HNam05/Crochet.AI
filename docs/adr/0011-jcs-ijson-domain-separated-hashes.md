# ADR-0011: JCS/I-JSON binary64 values and domain-separated hashes

- Status: Accepted
- Date: 2026-08-31

## Context

Whitespace and object order are harmless, but JSON runtimes differ in duplicate-key handling, integer precision, decimal parsing, negative zero, and exponent rendering. RFC 8785 alone must be paired with an explicit accepted numeric domain and project hash preimage.

## Decision

Structured artifacts use their exhaustive collection registry followed by RFC 8785 JCS over I-JSON-compatible values. Numbers have correctly rounded finite IEEE 754 binary64 semantics; integer fields are restricted to the safe integer range. Negative zero becomes zero. Duplicate keys, invalid Unicode, non-finite/overflowing values, and locale-number syntax fail closed.

SHA-256 hashes the domain-separated preimage `"Crochet.AI" || NUL || profile_id || NUL || jcs_utf8`. External asset hashes continue to cover exact raw bytes.

## Alternatives

- Raw JSON hashing was rejected because whitespace, key order, and number spelling differ.
- Arbitrary-precision decimal semantics were rejected for V1 because they add cross-language arithmetic and solver-conversion complexity.
- Decimal strings for every measurement were rejected as disproportionate; future values requiring more than binary64 receive an explicit typed profile.
- Undifferentiated SHA-256 of JCS bytes was rejected to prevent the same bytes being interpreted under different artifact profiles.

## Consequences

Semantically identical accepted numeric spellings hash identically across locales and runtimes. Existing profile identifiers become part of the cryptographic contract. Implementations must pass RFC and project vectors in independent runtimes before use.
