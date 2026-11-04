# HND v0.2 — Canonical serialization and operation-identity review

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Status:** Source-review findings and test specification only  
**Reviewed source:** `hnd_v02/anti_rollback_reference.py`  
**Safety boundary:** Offline synthetic model only. No production cryptographic or signer assurance is implied.

## 1. Scope

This review examined `_canonical`, `_digest`, `_mac`, `AnchorRecord.unsigned()`, operation transaction-digest construction, identity validation, and `OfflineAntiRollbackModel.prepare()`.

The review is static. It did not execute the module or run tests.

## 2. Findings

### F01 — Non-finite floating-point values are accepted by the canonical encoder

The current call to `json.dumps` leaves `allow_nan=True` (the Python default). It can therefore encode `NaN`, `Infinity`, and `-Infinity`, although these tokens are not valid JSON under RFC 8259. Different languages and JSON implementations may reject them or handle them differently.

**Risk:** a digest described as canonical JSON may not be portable across implementations. A state containing non-finite values can acquire implementation-dependent acceptance behavior.

**Required change:** explicitly reject non-finite floats recursively before serialization, and set `allow_nan=False`. Do not silently coerce them to strings or null.

### F02 — JSON object-key coercion can create ambiguous representations

Python's JSON encoder converts supported non-string dictionary keys (such as integers) to strings. For example, a mapping keyed by integer `1` and a mapping keyed by string `"1"` can serialize to the same JSON object representation. A mapping containing both can also fail during sorted-key comparison.

**Risk:** application-level mappings that are not already constrained to string keys can be ambiguous or fail inconsistently.

**Required change:** require every object key at every nesting level to be a string before canonicalization. Reject non-string keys rather than relying on encoder coercion.

### F03 — The top-level state type is not validated at runtime

The `prepare(..., state: dict)` annotation is not a runtime check. The code computes a digest and stores a JSON round-trip of the supplied value without first requiring a top-level object. JSON arrays and scalar values are serializable and may pass despite the declared state contract.

**Risk:** callers may create records whose state shape differs from the documented API contract, complicating schema evolution and downstream validation.

**Required change:** require `state` to be a dictionary/object at the API boundary, then validate the complete nested state against an explicit versioned schema. A type annotation alone is insufficient.

### F04 — Unicode normalization policy is unspecified

The encoder uses `ensure_ascii=True` and sorted keys, but does not normalize Unicode strings or keys. Canonically equivalent Unicode text can have distinct code-point sequences and therefore distinct digests.

**Risk:** two components may disagree if one normalizes identifiers or text and another preserves original code points. This is not automatically a cryptographic collision; it is an interoperability and identity-policy ambiguity.

**Required decision:** define whether identifiers and selected textual fields must be NFC-normalized at validation boundaries. Preserve arbitrary user data only if byte/code-point distinctions are intentional and consistently specified. Never normalize silently after a digest has been calculated.

### F05 — Identity fields are authenticated in the record, but caller identity inputs are not validated for canonical form

The record MAC covers the unsigned record, including network, genesis, validator, signer, schema, HRS, sequence, digests, operation ID, and status. The model compares the four identity strings exactly with the instance tuple. However, the constructor and `prepare` do not establish a documented syntax/normalization contract for those identifiers or for `operation_id`.

**Risk:** visually equivalent or malformed identifiers may be treated as distinct identities by different layers. Exact string equality is only safe when all producers agree on one validated representation.

**Required change:** define and enforce field-specific formats, maximum lengths, allowed character sets, and normalization policy for network/genesis/validator/signer/operation identifiers. Validate before digest/MAC creation and again when reading externally persisted records.

### F06 — Generation identifier is a truncated convenience identifier, not a security proof

`generation_id` is derived from the first 24 hexadecimal characters of a SHA-256 digest over operation ID and state. This is a 96-bit truncated identifier. The full `state_digest` remains separately stored and checked, so the generation ID must not be treated as the integrity proof.

**Required rule:** retain full digest verification as authoritative; treat generation ID only as a lookup key. Production design must specify collision handling and must not overwrite an existing generation on identifier collision.

## 3. Positive observations

- The transaction digest is calculated from all unsigned record fields except `status`, allowing PREPARED-to-COMMITTED to preserve the same immutable operation payload digest.
- `AnchorRecord.unsigned()` includes all dataclass fields except the MAC, so the MAC input includes the identity and transition metadata.
- `_validate_identity` compares network/genesis/validator/signer context and checks schema version and the synthetic MAC.
- HRS integer validation explicitly rejects booleans, which are Python subclasses of `int`.

These are properties of the current reference code only. The fixed MAC key is explicitly test-only and does not establish external trust or production authentication.

## 4. Required regression tests

| ID | Input / condition | Required result |
|---|---|---|
| C01 | NaN, positive infinity, negative infinity at any nested depth | Reject before digest or generation persistence |
| C02 | Integer, boolean, null, tuple, or other non-string object key | Reject before digest |
| C03 | Top-level list, scalar, null, or string passed as state | Reject; only object/dict accepted |
| C04 | Nested unsupported object or non-JSON value | Reject deterministically |
| C05 | NFC and decomposed forms in fields designated as normalized identifiers | Apply the documented boundary rule consistently; never silently reinterpret after hashing |
| C06 | Empty, oversized, malformed, or disallowed identifier strings | Reject according to field-specific schema |
| C07 | Two distinct states sharing a truncated generation lookup prefix (test via controlled digest stub) | Detect collision; never overwrite; preserve full-digest checks |
| C08 | Same operation ID with any changed identity/HRS/predecessor/state payload | Reject conflicting reuse |
| C09 | PREPARED and COMMITTED forms of the same immutable operation | Transaction digest remains equal; record MAC differs because status differs |

The digest-stub test is a deterministic collision-path test, not an attempt to find a real SHA-256 collision.

## 5. Recommended implementation sequence

1. Specify a versioned state schema and field-specific identifier contracts.
2. Add a recursive canonical-input validator: string-only mapping keys, supported JSON types only, finite floats only, and explicit top-level object requirement.
3. Set `allow_nan=False` and keep deterministic separators/key ordering.
4. Decide and document Unicode normalization per field; validate before hashing.
5. Add the regression tests above and run them in an authorized Python 3.12 environment.
6. Only after tests pass, review whether the canonicalization format needs a version/domain prefix to prevent cross-protocol digest reuse.

## 6. Evidence and release status

No source code was changed in this review. No test was run. Findings F01–F06 are review findings, not confirmed exploit demonstrations. This document does not close any implementation gate.

The module remains an offline in-memory reference model with a fixed synthetic MAC key. Production signing, custody, durable anti-rollback, and release authorization remain prohibited pending implementation, independent review, and verified test evidence.
