# WP4.14 — Config-v1 Negative Vectors and Canonicalization Attack Matrix

**Date:** 2026-11-05  
**Status:** Design / candidate test specification — not frozen  
**Branch:** `phase-0.2-planning`  
**Scope:** Negative parsing, canonicalization, digest binding, and fail-closed behavior for the proposed HND Application Config v1 identity.

## 1. Purpose and boundaries

This document defines adversarial inputs that an eventual Config-v1 implementation must reject deterministically. It complements:

- `WP4_14_HND_APPLICATION_CONFIG_V1_DESIGN_2026-11-05.md`
- `WP4_14_CONFIG_V1_CANONICAL_IDENTITY_AND_HASH_PREIMAGE_SPEC_2026-11-05.md`
- `WP4_14_CONFIG_V1_CANDIDATE_GOLDEN_VECTORS_2026-11-05.md`
- `WP4_14_LEGACY_COMPATIBILITY_AND_STATE_MIGRATION_MATRIX_2026-11-05.md`

This is a test-design artifact. It does not change application code, protocol behavior, durable stores, or CI workflows. No tests are claimed to have been executed. All values and expected outcomes remain candidates until the schema, bounds, and error contract are frozen.

## 2. Normative test principle

At every consensus-critical boundary, invalid or ambiguous input must fail closed:

1. Reject malformed bytes before constructing trusted protocol objects.
2. Reject duplicate JSON object keys before ordinary map/dictionary conversion.
3. Validate exact field sets, types, numeric ranges, and string grammars.
4. Verify component digests and the aggregate network identity against the exact specified preimages and domain separators.
5. Do not mutate durable or in-memory consensus state when validation fails.
6. Produce deterministic error categories; do not expose parser/runtime-specific wording as protocol behavior.

The recommended boundary rule is **canonical-byte equality**: parse the input under strict rules, serialize the resulting value using the frozen canonical profile, and require the resulting bytes to equal the submitted consensus-critical bytes. If the protocol instead chooses to accept noncanonical encodings and hash only normalized objects, that must be an explicit frozen decision with separate vectors for every accepted representation.

## 3. Negative vector matrix

| ID | Attack / malformed input | Required result | State effect |
|---|---|---|---|
| NEG-001 | Duplicate top-level key, e.g. two `network_id` members | Reject duplicate key before object construction | No mutation |
| NEG-002 | Duplicate nested key in config or manifest | Reject duplicate key at any nesting depth | No mutation |
| NEG-003 | Boolean supplied where integer is required (`true` / `false`) | Reject; booleans are not integer protocol values | No mutation |
| NEG-004 | Floating-point amount or limit, including `1.0` | Reject; integer-only fields require integer lexical form | No mutation |
| NEG-005 | Exponent notation for integer field, e.g. `1e3` | Reject under strict integer lexical grammar | No mutation |
| NEG-006 | NaN, Infinity, or -Infinity | Reject as invalid JSON numeric values | No mutation |
| NEG-007 | Negative value for unsigned field | Reject range violation | No mutation |
| NEG-008 | Value above approved U64 or field-specific maximum | Reject overflow / bound violation | No mutation |
| NEG-009 | Number represented through IEEE-754 rounding in a client implementation | Reject lossy conversion; use exact integer representation | No mutation |
| NEG-010 | Invalid UTF-8 byte sequence | Reject before JSON parsing | No mutation |
| NEG-011 | UTF-8 BOM when the frozen profile forbids it | Reject forbidden prefix | No mutation |
| NEG-012 | Unpaired Unicode surrogate escape | Reject invalid Unicode scalar value | No mutation |
| NEG-013 | NFC and NFD spellings treated as interchangeable without a rule | Reject nonconforming string or preserve exact code points per frozen grammar; never normalize implicitly | No mutation |
| NEG-014 | Invalid network identifier grammar, length, or character set | Reject identifier validation failure | No mutation |
| NEG-015 | Digest with uppercase hex when lowercase is required | Reject noncanonical digest text | No mutation |
| NEG-016 | Digest with wrong length, non-hex character, `0x` prefix, or whitespace | Reject digest syntax | No mutation |
| NEG-017 | Config content changed but old config digest retained | Reject config digest mismatch | No mutation |
| NEG-018 | Manifest allocation changed but old manifest digest retained | Reject manifest digest mismatch | No mutation |
| NEG-019 | Component digest changed but old aggregate network identity retained | Reject aggregate identity mismatch | No mutation |
| NEG-020 | Correct payload hashed with wrong domain separator | Reject digest mismatch | No mutation |
| NEG-021 | Domain separator missing its terminating NUL byte | Reject digest mismatch | No mutation |
| NEG-022 | Required field omitted | Reject missing-field validation | No mutation |
| NEG-023 | Unknown extra field supplied | Reject unless a frozen extension mechanism explicitly permits it | No mutation |
| NEG-024 | Unsupported config or manifest schema version | Reject unsupported version | No mutation |
| NEG-025 | Object members reordered or whitespace altered | Under canonical-byte equality, reject noncanonical bytes; otherwise only accept according to an explicitly frozen alternate rule | No mutation |
| NEG-026 | Allocation list reordered | Apply the frozen ordering rule; if canonical order is required, reject unsorted input | No mutation |
| NEG-027 | Duplicate allocation/account entry | Reject duplicate identity; do not silently merge | No mutation |
| NEG-028 | Allocation sum differs from declared total supply | Reject manifest invariant failure | No mutation |
| NEG-029 | Excessive input byte length, nesting depth, object members, or array length | Reject resource-limit violation before expensive processing | No mutation |
| NEG-030 | Same semantic config encoded with multiple byte representations | Accept exactly one frozen canonical representation at consensus boundary | No mutation |
| NEG-031 | Legacy manifest-only genesis hash presented as Config-v1 aggregate identity | Reject version/domain mismatch; never reinterpret legacy hash | No mutation |
| NEG-032 | Config-v1 payload has missing or mismatched application config hash | Reject InitChain/config identity validation | No mutation |
| NEG-033 | Durable store contains no Config-v1 identity or contains a different identity | Refuse startup; require the documented offline migration path | Existing store unchanged |
| NEG-034 | Config digest valid but CometBFT profile identity differs from the network's pinned profile | Reject startup/network compatibility check | No mutation |

## 4. Parsing and canonicalization requirements

### 4.1 Duplicate-key detection

A normal JSON decoder that immediately materializes an object may silently keep the first or last duplicate key. That behavior is unacceptable for consensus-critical data.

The implementation must use a parser mode or token-level pass that detects duplicate member names at every object depth before creating the trusted config/manifest object. Tests NEG-001 and NEG-002 must include duplicates whose values differ, including cases where one value would otherwise make the document appear valid.

### 4.2 Exact numeric semantics

- Booleans must never satisfy integer-field validation.
- Floats, exponent notation, NaN, and infinities must be rejected for integer protocol fields.
- Numeric limits must be frozen per field, not inferred from the host language.
- JavaScript implementations must use `BigInt` or an exact decimal/integer parser for values outside the safe integer range.
- Python arbitrary-precision integers do not remove the need for explicit protocol bounds.
- Go implementations must not silently narrow values into `int64` without checked conversion.
- Every implementation must reject overflow before hashing, comparison, or state mutation.

The exact upper bounds for `max_amount`, `amount_max`, `nonce_max`, byte limits, and transaction-count limits remain open decisions. Tests must be parameterized from the frozen specification rather than inventing production limits here.

### 4.3 Unicode and identifiers

The protocol must choose one of these approaches for every consensus-critical string field:

1. Restrict the field to a narrow ASCII grammar; or
2. Define exact Unicode scalar-value acceptance and preserve code points byte-for-byte in canonical serialization.

Implicit NFC/NFD normalization is prohibited. If normalization is chosen, its algorithm, Unicode version, application point, and rejection/normalization behavior must be frozen and tested cross-language. Network identifiers and digest strings should preferably use narrow ASCII grammars.

### 4.4 Canonical JSON bytes

The canonical profile must define:

- UTF-8 encoding and BOM policy;
- duplicate-key rejection;
- object-key ordering;
- string escaping;
- whitespace and separators;
- integer lexical representation;
- treatment of Unicode;
- rejection of floats and non-finite numbers;
- exact field sets and array ordering.

Recommended rule: consensus-critical submitted bytes must equal the canonical serialization bytes. This avoids multiple wire encodings for one identity. If the project intentionally accepts noncanonical wire JSON, that alternative must be specified and threat-modeled before implementation.

### 4.5 Arrays and manifest allocations

Object-key sorting does not sort arrays. The manifest must explicitly define whether allocation order is semantically meaningful. Recommended approach: define a stable account-identity ordering, reject duplicate account identities, and reject unsorted allocations rather than silently sorting user-supplied input. The total allocation sum must equal the declared supply exactly, using bounded integer arithmetic.

## 5. Digest-binding attack cases

The Config-v1 identity chain must be tested as separate layers:

1. Canonical application config bytes and their domain-separated config digest.
2. Canonical manifest bytes and its domain-separated manifest digest.
3. Aggregate network identity preimage containing the exact approved component identities and schema/version fields.

For each layer, create at least these mutations:

- Flip one byte in the canonical payload while retaining the original digest.
- Change one digest nibble while retaining the original payload.
- Substitute a digest from a different valid fixture.
- Remove or alter the domain separator.
- Change the schema/version field without recomputing the digest.
- Recompute a component digest but retain the stale aggregate digest.
- Recompute the aggregate digest using a different component order or a missing component.

Every mutation must be rejected at the layer where it becomes invalid. A lower-layer digest must not be treated as proof that the aggregate network identity is valid.

## 6. Fail-closed and no-mutation assertions

Every negative vector must assert more than an error return. The test harness should capture and compare:

- application state hash before and after;
- ledger/account state before and after;
- committed height before and after;
- durable store bytes or canonical store digest before and after;
- whether any signing-capable operation was enabled;
- whether the node remained eligible to join/continue the network.

For invalid InitChain or startup configuration, the node must not become operational with partially accepted state. For durable-store mismatch, startup must stop without rewriting the existing store. Error logging must not disclose private keys, credentials, or secret material.

## 7. Resource-exhaustion and parser-hardening cases

Before parsing or canonicalizing untrusted configuration, the implementation needs approved upper bounds for:

- total input bytes;
- nesting depth;
- object member count;
- array length;
- string length;
- allocation count;
- maximum encoded transaction/config sizes.

The parser must reject over-limit inputs before unbounded recursion, allocation, hashing, or expensive normalization. Limits are consensus-critical when they affect acceptance; they must be bound to the Config-v1 identity or another explicitly pinned network profile. Local-only operational limits must not silently produce divergent consensus decisions.

## 8. Cross-language differential test plan

Run the same byte fixtures through each supported implementation (initially Python and Node.js; add Go/Java only if they become supported protocol implementations).

For every fixture, compare:

- accept/reject decision;
- structured error category;
- parsed field types;
- canonical output bytes;
- component digest;
- aggregate network identity;
- no-mutation assertions.

A mismatch between implementations is a release blocker. Golden positive vectors alone are insufficient; all negative vectors must have deterministic expected outcomes. No implementation may substitute host-language default JSON behavior for the frozen protocol profile.

## 9. Acceptance checklist

| Gate | Acceptance condition |
|---|---|
| NEG-A | Duplicate keys rejected at every object depth |
| NEG-B | Boolean, float, exponent, NaN, and infinity rejected for integer fields |
| NEG-C | All integer bounds checked without precision loss |
| NEG-D | Invalid UTF-8, BOM policy violations, and invalid Unicode rejected deterministically |
| NEG-E | String grammar and normalization policy frozen |
| NEG-F | Exact field sets and schema versions enforced |
| NEG-G | Canonical bytes and array-order policy enforced |
| NEG-H | Component and aggregate digest tampering rejected |
| NEG-I | Domain-separator and preimage mutations rejected |
| NEG-J | Legacy identity cannot be reinterpreted as Config-v1 identity |
| NEG-K | Resource limits enforced before expensive processing |
| NEG-L | Every rejection proves no state mutation and no signer enablement |
| NEG-M | Python and Node.js (and any additional supported implementation) produce identical outcomes |
| NEG-N | All tests run in the approved environment and results are recorded with commit SHA and command |

## 10. Open decisions before executable tests are frozen

1. Exact ASCII grammar and maximum length for `network_id` and other identity strings.
2. Exact numeric maxima and whether all monetary/nonce fields are U64.
3. Maximum canonical config, manifest, and transaction byte lengths.
4. JSON parser policy for BOM, Unicode escapes, and canonical-byte equality.
5. Allocation ordering rule and duplicate-account semantics.
6. Exact extension/versioning policy for unknown fields.
7. Whether CometBFT profile digest is part of the aggregate network identity or a separately pinned mandatory identity.
8. Stable machine-readable error categories for parser, schema, digest, startup, and migration failures.

These decisions must be resolved in the Config-v1 specification before turning this matrix into frozen executable vectors.

## 11. Current disposition

- This document is a candidate adversarial test specification only.
- No application code was modified.
- No CI workflow was modified.
- No test command was executed as part of this document.
- Candidate positive golden vectors remain candidates; they are not frozen protocol constants.
- Config-v1 implementation and public-network gates remain closed pending schema decisions, implementation, executable negative tests, migration validation, and independent review.
