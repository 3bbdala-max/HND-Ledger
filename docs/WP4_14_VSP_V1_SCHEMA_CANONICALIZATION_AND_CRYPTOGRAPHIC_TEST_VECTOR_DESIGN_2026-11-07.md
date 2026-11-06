# WP4.14 — VSP v1 Schema, Canonicalization and Cryptographic Test-Vector Design

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Type:** Protocol design decision candidate; documentation only  
**Status:** PROPOSED — requires protocol-owner approval and independent cryptographic review  
**Production disposition:** NOT APPROVED

## 1. Purpose and scope

This document narrows the first VSP implementation package to a deterministic, side-effect-free verifier contract and its negative-test corpus. It does not implement a verifier, generate or enroll real keys, select production custodians, change dependencies, or authorize validator startup.

The verifier must be a pure function over explicitly supplied byte strings and context. It must not open sockets, start processes, write anti-rollback state, access private keys, or decide that a validator may start. Those are later integration and enforcement layers.

## 2. Proposed package model

Use two separate artifacts:

1. **Trust Manifest (TM):** independently bootstrapped and pinned out-of-band. It contains exactly three governance public-key records and a threshold of two. Its digest is distributed through the witnessed bootstrap ceremony and two independent publication channels.
2. **Validator Set Profile (VSP):** a canonical, signed statement of the authorized network identity, validator roster, consensus-relevant identity and monotonic update sequence.

Signatures are carried in a detached envelope, not embedded in the bytes being signed. This avoids recursive/self-referential signing and ensures every signer signs the same exact VSP payload.

### 2.1 Proposed VSP payload schema v1

The following is the proposed exact field set. Unknown fields are rejected in schema version 1; extensions require a new schema version or an explicitly defined extension registry.

| Field | Type / constraint | Meaning |
|---|---|---|
| `schema_version` | integer, exactly 1 | VSP schema |
| `chain_id` | non-empty bounded ASCII string | Exact CometBFT chain ID |
| `hnd_network_id` | non-empty bounded ASCII string | Exact HND application network ID |
| `hnd_protocol_version` | positive integer | HND protocol version |
| `hnd_genesis_manifest_sha256` | lowercase 64-hex string | HND manifest digest |
| `cometbft_genesis_sha256` | lowercase 64-hex string | Digest of exact approved CometBFT Genesis bytes |
| `cometbft_profile_sha256` | lowercase 64-hex string | Digest of version-classified consensus-affecting profile |
| `cometbft_source_commit` | lowercase 40- or 64-hex string | Exact reviewed source commit |
| `cometbft_binary_sha256` | lowercase 64-hex string | Approved binary digest |
| `sequence` | integer, 0 through 2^53−1 | Strictly increasing VSP sequence |
| `previous_vsp_sha256` | lowercase 64-hex string or null only at bootstrap | Digest of immediately preceding canonical VSP payload |
| `activation_height` | integer, 1 through 2^53−1 | First height at which the profile is active |
| `expires_at_unix` | integer, 1 through 2^53−1 | Expiry time; exact clock policy must be separately specified |
| `validators` | non-empty array | Complete authorized consensus validator roster |

Each `validators[]` record has exactly these fields:

| Field | Type / constraint | Meaning |
|---|---|---|
| `validator_id` | bounded ASCII identifier | Stable, non-secret operator-assigned identity |
| `consensus_pubkey_type` | exact allowlisted type string | CometBFT public-key type |
| `consensus_pubkey` | canonical Base64 encoding of raw key bytes | Consensus public key |
| `consensus_address` | lowercase fixed-length hex string | Address derived by the pinned CometBFT version |
| `voting_power` | positive integer, bounded by protocol policy | Exact CometBFT voting power |

Roster records must be sorted by the bytewise UTF-8 encoding of `consensus_address`. Duplicate validator IDs, public keys or addresses are rejected. The total voting power must be computed with bounded integer arithmetic and must match the complete CometBFT Genesis validator set exactly. The allowed maximum power and total-power bound remain explicit protocol-owner decisions; no production values are inferred from the equal-power CI fixture.

**Identity separation:** governance signing keys, CometBFT consensus keys, CometBFT P2P node keys and HND account keys are distinct roles. A VSP validator record identifies a consensus public key; it must not contain a private key, account secret, P2P private key or governance key.

## 3. Detached signature envelope

Proposed envelope schema:

- `envelope_version`: integer exactly 1
- `vsp_payload_sha256`: lowercase SHA-256 digest of the canonical VSP payload bytes
- `signatures`: array of records with exactly `governance_key_id`, `algorithm`, and `signature`

Each signature record must:
- refer to one key ID in the independently pinned TM;
- use the exact algorithm assigned to that TM key;
- contain canonical Base64 signature bytes of the algorithm's exact required length;
- be unique by governance key ID;
- verify over the same canonical payload bytes and domain-separated context.

The verifier requires at least two valid signatures from two distinct, currently trusted governance key IDs. Extra signatures are permitted only if each is valid and unique; invalid or unknown signatures should cause rejection rather than be silently ignored. Signature ordering is canonicalized by ascending UTF-8 key ID before envelope serialization, although the detached envelope itself is not part of the signed payload.

## 4. Canonicalization and parser requirements

### 4.1 Candidate canonicalization

**Candidate:** RFC 8785 JSON Canonicalization Scheme (JCS) for VSP payload bytes, with a strict schema layered on top.

Rationale:
- the existing HND `canonical_json` helper sorts keys and uses compact UTF-8 JSON, but it is not documented as an RFC 8785 implementation;
- the existing Python JSON parser accepts duplicate object member names unless an explicit duplicate-detection hook is used;
- canonical signature bytes must be identical across independent implementations and languages.

No RFC 8785 implementation currently appears in the inspected `requirements.txt`. Therefore do not call the existing helper “JCS,” do not implement an ad hoc approximation, and do not add a dependency until a concrete library/version has been evaluated and pinned.

### 4.2 Strict parsing profile

Before canonicalization, the parser must:
1. enforce a documented maximum input size and nesting depth;
2. decode UTF-8 strictly and reject a BOM;
3. reject duplicate object member names at every nesting level;
4. reject invalid Unicode, lone surrogates and non-finite numeric values;
5. reject floating-point values entirely in schema v1;
6. require integer values within the exact safe range 0 through 2^53−1;
7. reject unknown fields and wrong JSON types (including booleans where integers are expected);
8. validate exact string alphabets, lengths and Base64 canonical form;
9. re-encode with the selected, independently tested JCS implementation and compare exact bytes with the supplied payload bytes.

The 2^53−1 bound is intentionally conservative for interoperable JSON number handling. If a future field needs a larger integer, define a decimal-string encoding in a new schema version; do not silently widen v1.

### 4.3 Hashing and domain separation

Proposed payload digest:

`SHA-256(canonical_vsp_payload_bytes)`

Proposed signing message:

`UTF8("HND-LEDGER/VSP-SIGNATURE/V1") || 0x00 || canonical_vsp_payload_bytes`

The signed payload itself binds chain ID, HND network ID, HND Genesis digest, CometBFT Genesis digest, profile digest, source commit, binary digest, sequence, predecessor digest, activation height, expiry and complete validator roster.

The signature envelope is detached and is not included in the payload digest. Trust-manifest pinning is separate from VSP signature verification. A self-signed or co-located trust manifest is not an acceptable bootstrap trust source.

## 5. Cryptographic algorithm proposal — not final approval

**Candidate for v1:** Ed25519, because the current codebase already uses the Python `cryptography` package and Ed25519 for HND transaction signatures, and the current dependency set already exposes the primitive.

This is a compatibility observation, not a production cryptographic approval. Before implementation:
- verify support and exact public-key/signature encodings in the chosen CometBFT/governance tooling;
- review key generation, custody device/HSM support, backup and recovery behavior;
- review algorithm policy, key rotation and future migration;
- pin the exact library version and test cross-language golden vectors;
- obtain independent cryptographic review.

Do not reuse transaction-signing domain strings, transaction keys or HND account keys for governance. The VSP domain string above is separate. No private key material is created or included in this document.

## 6. Trust manifest contract

The independently pinned TM must define:
- manifest schema version;
- exact chain ID and HND Genesis digest;
- exactly three governance key records with stable key IDs, algorithm IDs and canonical public-key encodings;
- threshold exactly 2 for routine VSP authorization;
- trust-manifest sequence and digest;
- bootstrap ceremony record reference and witness evidence digest;
- key status and effective/retirement sequence rules.

A routine VSP update cannot introduce a new governance key by itself. Key rotation is a separate witnessed transition authorized under the existing trust root and approved ceremony policy. Loss of two keys remains a halt condition until a separately approved catastrophic recovery process exists.

## 7. Verifier API contract

The first implementation should expose a pure interface conceptually equivalent to:

`verify_vsp(payload_bytes, envelope_bytes, trust_manifest_bytes, expected_context) -> VerifiedVSP | VerificationError`

Required properties:
- deterministic result for identical inputs;
- no filesystem or network access;
- no private-key access;
- no mutation of input objects or persistent state;
- bounded resource consumption;
- stable machine-readable error codes with no secret leakage;
- no “warning but continue” path;
- no authorization token that can independently start services.

The expected context must be supplied independently by the caller and include the pinned trust-manifest digest, expected chain/network identifiers, HND Genesis digest, actual CometBFT Genesis digest, actual profile digest, actual source/binary identity and local validator public identity. A value copied from the untrusted VSP is not an independent expected value.

The pure verifier does **not** establish anti-rollback. A separate stateful policy layer must compare sequence and predecessor digest against a protected monotonic anchor, then atomically commit acceptance. Until such an anchor exists, return a result explicitly marked unsuitable for production enforcement.

## 8. Golden-vector strategy

Create deterministic, test-only fixtures with fixed seed bytes generated exclusively inside the test suite. They must never be accepted as production keys.

Required golden vector set:
- canonical VSP payload bytes and SHA-256 digest;
- exact domain-separated signing message bytes;
- three test governance public keys and key IDs;
- two valid detached Ed25519 signatures over the same payload;
- one invalid signature;
- one signature over a different chain ID;
- one duplicate signer entry;
- one envelope with an unknown key ID;
- one payload with duplicate JSON member names;
- one payload with non-canonical whitespace/key ordering;
- one payload with a substituted validator key or voting power;
- one VSP with an incorrect predecessor digest or stale sequence.

Publish fixture input bytes and expected output digests in the test repository only after protocol-owner approval of the schema. Never place production keys, seeds, HSM exports, ceremony nonces or recovery material in golden vectors.

Cross-language verification must reproduce identical canonical bytes, payload digest and signature verification result. A Python-only self-test is insufficient evidence of interoperable consensus-critical encoding.

## 9. Negative-test acceptance matrix — proposed, not executed

| ID | Input mutation | Expected outcome |
|---|---|---|
| VSP-SCHEMA-T01 | Missing required payload field | Reject: schema |
| VSP-SCHEMA-T02 | Unknown payload field | Reject: schema |
| VSP-SCHEMA-T03 | Duplicate top-level JSON member | Reject: duplicate-member |
| VSP-SCHEMA-T04 | Duplicate nested validator member | Reject: duplicate-member |
| VSP-SCHEMA-T05 | Invalid UTF-8 or BOM | Reject: encoding |
| VSP-SCHEMA-T06 | Lone surrogate / invalid Unicode | Reject: unicode |
| VSP-SCHEMA-T07 | Float or exponent-form number | Reject: number-type |
| VSP-SCHEMA-T08 | Boolean supplied for integer field | Reject: field-type |
| VSP-SCHEMA-T09 | Integer above 2^53−1 | Reject: integer-range |
| VSP-SCHEMA-T10 | Non-canonical JSON bytes | Reject: canonical-bytes |
| VSP-SCHEMA-T11 | Payload exceeds byte/depth limit | Reject: resource-limit |
| VSP-SCHEMA-T12 | Roster not bytewise sorted | Reject: roster-order |
| VSP-SCHEMA-T13 | Duplicate validator address or public key | Reject: duplicate-validator |
| VSP-SCHEMA-T14 | Zero, negative or excessive voting power | Reject: voting-power |
| VSP-SCHEMA-T15 | CometBFT address does not derive from public key | Reject: validator-identity |
| VSP-SCHEMA-T16 | HND Genesis digest mismatch | Reject: hnd-genesis |
| VSP-SCHEMA-T17 | CometBFT Genesis/profile digest mismatch | Reject: cometbft-context |
| VSP-SCHEMA-T18 | Source commit or binary digest mismatch | Reject: software-identity |
| VSP-SCHEMA-T19 | One valid governance signature only | Reject: threshold |
| VSP-SCHEMA-T20 | Same governance key ID repeated twice | Reject: duplicate-signer |
| VSP-SCHEMA-T21 | Unknown or retired governance key | Reject: signer-trust |
| VSP-SCHEMA-T22 | Signature bit altered | Reject: signature |
| VSP-SCHEMA-T23 | Valid signature over another domain | Reject: signature-domain |
| VSP-SCHEMA-T24 | Valid signature over another chain ID | Reject: network-context |
| VSP-SCHEMA-T25 | Envelope payload digest mismatch | Reject: payload-digest |
| VSP-SCHEMA-T26 | Previous digest mismatch | Reject: predecessor |
| VSP-SCHEMA-T27 | Sequence decreases or repeats | Reject: sequence-policy |
| VSP-SCHEMA-T28 | Activation height invalid | Reject: activation |
| VSP-SCHEMA-T29 | Expired profile under trusted clock policy | Reject: expiry |
| VSP-SCHEMA-T30 | Same fixture verified in a second implementation | Exact bytes/digest/result must match |

All rows are proposed acceptance tests; none are claimed to have run.

## 10. Decisions still required

1. Protocol-owner approval of exact schema v1 field names, bounds and extension policy.
2. Approval of JCS and selection/pinning of a conformant implementation.
3. Independent approval of Ed25519 governance signature policy and supported custody devices.
4. Definition of CometBFT address derivation against the exact pinned CometBFT source version.
5. Definition of total voting-power bounds and activation/expiry clock policy.
6. Approval of trust-manifest transition and catastrophic recovery process.
7. Selection and threat-model review of a real anti-rollback anchor.
8. Independent cross-language cryptographic review.

Until these decisions are recorded, the schema is a candidate design, not an authoritative network protocol.

## 11. Change and release boundary

This document changes no source, tests, workflows, dependencies, Genesis, keys, validator settings or runtime behavior. It does not authorize implementation completion, production validator startup, production signing, token issuance or public launch.

**Final status: PROPOSED / NOT APPROVED.**
