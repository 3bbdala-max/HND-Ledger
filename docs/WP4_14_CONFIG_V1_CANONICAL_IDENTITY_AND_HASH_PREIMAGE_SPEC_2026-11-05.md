# HND Config v1 — Canonical Identity and Hash Preimage Specification

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Status:** Candidate protocol specification for review — not implemented and not yet frozen  
**Scope:** Canonical application-config bytes, config digest, aggregate network-genesis identity, validation rules, and golden-vector requirements.

## 1. Objective

Define an unambiguous, versioned identity for an HND Config-v1 network so that every validator derives the same digest from the same application configuration and Genesis manifest.

This specification is deliberately a candidate. It proposes exact hash preimages and strict validation behavior, but does not select production monetary parameters, authorize implementation, or claim that any golden vectors or tests have been executed.

## 2. Existing implementation boundary

The reviewed legacy implementation currently provides:

- `canonical_json(value)`: UTF-8 JSON, sorted object keys, compact separators, `ensure_ascii=False`, and `allow_nan=False`.
- `GENESIS_DOMAIN = b"HND-LEDGER/GENESIS\\x00"`.
- `genesis_manifest_hash(manifest)`: SHA-256 of the legacy Genesis domain concatenated with canonical manifest bytes.
- A legacy manifest with exactly `manifest_version`, `network_id`, `protocol_version`, `total_supply`, and `allocations`.

The existing manifest hash remains a legacy component hash. It is not the Config-v1 aggregate network identity.

## 3. Canonical JSON profile: HND-CJSON-1

Config-v1 objects must be encoded using the following profile:

1. UTF-8 encoding, with no byte-order mark.
2. JSON object keys sorted lexicographically by Unicode code point.
3. No insignificant whitespace: separators are exactly comma and colon.
4. Unicode characters are emitted directly (`ensure_ascii=false`); no implicit Unicode normalization is performed.
5. JSON floating-point values are forbidden.
6. NaN and positive/negative infinity are forbidden.
7. Integers are base-10 JSON integers with no leading plus sign, no leading zero except the value zero, and no exponent form.
8. Boolean values are not accepted where an integer is required.
9. Duplicate object keys are rejected before object construction.
10. Unknown keys and missing required keys are rejected at every schema level.
11. Strings must be valid Unicode scalar sequences; unpaired surrogate code points are rejected.
12. Each schema defines whether a string is ASCII-only, its maximum length, and its allowed syntax. No trimming, case folding, or Unicode normalization is implicit.

The existing Python encoder covers sorted keys, compact separators, direct Unicode output, and non-finite float rejection. The Config-v1 parser and validators must additionally enforce the strict type, duplicate-key, surrogate, key-set, and range requirements above before hashing. Cross-language implementations must follow this profile rather than relying on language-default JSON behavior.

## 4. Application config object

The candidate Config-v1 object has exactly these fields:

| Key | Type | Candidate validation |
|---|---|---|
| `config_version` | integer | Exactly 1 |
| `network_id` | string | Existing ASCII network ID grammar; 1–64 characters |
| `protocol_version` | integer | Positive and explicitly supported |
| `max_amount` | integer | Positive; no greater than `amount_max` |
| `max_block_transactions` | integer | Positive; explicit bounded protocol value |
| `max_transaction_bytes` | integer | Positive; explicit bounded protocol value |
| `amount_max` | integer | Positive portable maximum amount |
| `nonce_max` | integer | Exactly the supported unsigned 64-bit maximum for this version |
| `transaction_encoding` | string | Exactly `canonical-json-v1` |
| `recipient_policy` | string | Exactly `genesis-registered-only-v1` |

All integer fields require `type(value) is int` semantics (or equivalent in another language), not a permissive numeric conversion. Booleans, floats, numeric strings, nulls, and out-of-range values must fail.

The field names and enum labels are candidate v1 identifiers. Changing any field name, type, meaning, or enum value after vectors are frozen requires a new config version or protocol migration.

This schema does not contain private keys, seed phrases, credentials, ports, hostnames, peer addresses, log settings, or other node-local operational values.

## 5. Application-config digest

Let `C` be the validated Config-v1 object and `J(C)` be its HND-CJSON-1 UTF-8 encoding.

Proposed domain bytes:

```text
ASCII("HND-LEDGER/APP-CONFIG/V1") || 0x00
```

Proposed digest:

```text
application_config_hash =
    lowercase_hex(SHA256(domain || J(C)))
```

The digest is exactly 64 lowercase hexadecimal characters. Uppercase hex, prefixes such as `0x`, whitespace, or alternate encodings are invalid.

The digest commits to every field in the exact Config-v1 schema. No field may be excluded as “default” or reconstructed from local CLI flags.

## 6. Legacy manifest component hash

For a validated legacy-compatible manifest `M`, preserve the existing calculation exactly:

```text
manifest_hash =
    lowercase_hex(
        SHA256(
            ASCII("HND-LEDGER/GENESIS") || 0x00
            || J(M)
        )
    )
```

This value retains its historical manifest-only semantics. Do not change its domain, preimage, or meaning in place.

The manifest must be independently validated before it is used as a component of the new network identity. In particular, allocation entries must have exact schemas, deterministic ordering, unique account IDs, valid public-key/account-ID correspondence, positive integer amounts, and a sum equal to total supply.

## 7. Aggregate Config-v1 network-genesis identity

Define the exact aggregate preimage object `N` with exactly these keys:

```json
{
  "identity_version": 1,
  "manifest_hash": "<64 lowercase hex>",
  "application_config_hash": "<64 lowercase hex>"
}
```

No chain ID, validator list, CometBFT profile, node endpoint, or secret is included in this HND application identity. CometBFT's own Genesis and network profile remain separately pinned artifacts.

Proposed domain bytes:

```text
ASCII("HND-LEDGER/NETWORK-GENESIS/V1") || 0x00
```

Proposed aggregate digest:

```text
network_genesis_hash =
    lowercase_hex(SHA256(domain || J(N)))
```

The aggregate digest therefore commits to both the complete allocation manifest (through `manifest_hash`) and the complete application config (through `application_config_hash`).

The application Genesis envelope should carry:
- the full validated manifest;
- the full validated application config;
- `manifest_hash`;
- `application_config_hash`; and
- `network_genesis_hash`.

The envelope itself must have an exact schema and canonical encoding. The application recomputes all three digests; it must not trust supplied digest strings without recomputation.

## 8. Trusted pinning and startup checks

A digest is not an origin-authentication mechanism if an attacker can replace both the artifact and the expected digest.

Before validator startup, a trusted release/deployment process must provide independently authenticated expected values for:
- application config digest;
- manifest hash;
- aggregate network-genesis digest; and
- the separately pinned CometBFT network-profile digest.

Startup and InitChain must independently check:
1. strict envelope schema and canonical encoding;
2. config schema and supported version;
3. config network ID and protocol version against the chain ID and manifest;
4. manifest validity and allocation invariants;
5. recomputed manifest hash;
6. recomputed config digest;
7. recomputed aggregate network-genesis digest;
8. equality with independently pinned expectations; and
9. equality with the config digest recorded in durable state on restart.

A mismatch at any stage is a hard failure. No fallback to legacy hash interpretation is permitted.

## 9. Golden-vector package

Before implementation, a vector package must be created with fixed inputs and independently reproduced outputs.

Each vector record must contain:
- vector identifier and purpose;
- exact input JSON bytes in UTF-8 (not merely a pretty-printed object);
- expected canonical JSON bytes, represented as hex;
- exact domain bytes, represented as hex;
- exact preimage bytes, represented as hex;
- expected SHA-256 digest;
- expected validation result and error category; and
- independent implementation/version that generated the expected value.

Required positive vectors:
- minimum valid config values within the schema's approved bounds;
- a representative non-production config;
- a manifest with one allocation;
- a manifest with multiple sorted allocations;
- complete aggregate network identity;
- Unicode handling for any field that permits Unicode (if no field permits it, assert that such input is rejected).

Required negative vectors:
- missing and unknown keys;
- duplicate JSON keys;
- boolean in every integer position;
- float, exponent notation, NaN, and Infinity;
- negative, zero, and over-limit integers where prohibited;
- uppercase, short, long, or non-hex digest;
- wrong domain separator;
- altered config field with unchanged config digest;
- altered allocation with unchanged manifest digest;
- altered component digest with unchanged aggregate digest;
- wrong network ID or protocol version;
- unpaired surrogate;
- alternate Unicode normalization form where a string grammar permits it;
- legacy manifest hash supplied as the Config-v1 aggregate hash.

Expected digests must be generated independently (for example, two separate implementations) and cross-checked. Do not calculate the “expected” value using the same production function under test.

## 10. Required test IDs

| ID | Acceptance behavior |
|---|---|
| ID01 | Canonical JSON bytes match the frozen HND-CJSON-1 vectors |
| ID02 | Duplicate keys are rejected before hashing |
| ID03 | Booleans and floats are rejected in integer fields |
| ID04 | Non-finite numbers and unpaired surrogates are rejected |
| ID05 | Unknown and missing schema keys are rejected |
| ID06 | Config digest matches independent golden vectors |
| ID07 | Legacy manifest digest remains byte-for-byte compatible with legacy vectors |
| ID08 | Aggregate network identity matches independent golden vectors |
| ID09 | Changing any config field changes the config digest |
| ID10 | Changing manifest content changes the manifest hash and aggregate identity |
| ID11 | Changing either component hash changes the aggregate identity |
| ID12 | Legacy manifest hash cannot pass as aggregate Config-v1 identity |
| ID13 | Supplied hashes are recomputed and compared, never blindly trusted |
| ID14 | Config-v1 envelope and durable store require the same pinned config digest |
| ID15 | Python and at least one independent implementation produce identical vectors |

These are requirements only. No test execution is claimed.

## 11. Open decisions before freeze

The following must be decided explicitly before the schema is frozen:

1. Final numeric bounds for `max_amount`, `max_block_transactions`, `max_transaction_bytes`, and `amount_max`.
2. Whether `nonce_max` is fixed to the current unsigned 64-bit limit or changed through a new protocol version.
3. Exact maximum byte length for canonical config and Genesis envelopes.
4. Exact string grammar for network ID and any future string-valued protocol fields.
5. Whether the envelope repeats `manifest_hash` as a top-level field or carries it only through a strictly defined nested identity object.
6. Exact CometBFT profile digest format and its separate trust/pinning procedure.
7. Independent vector generator and review ownership.

No production supply, distribution amount, token precision, or public economic policy is chosen by this document.

## 12. Gate decision

**Decision: candidate hash preimages and validation profile documented; schema freeze and implementation remain blocked pending review and independent golden vectors.**

Do not modify application code or CI workflows based solely on this candidate. Do not open G2–G4 or infer public-network/production readiness.

The next step is to resolve the open schema decisions, generate independent canonical byte/hash vectors, and obtain a review sign-off before any implementation begins.
