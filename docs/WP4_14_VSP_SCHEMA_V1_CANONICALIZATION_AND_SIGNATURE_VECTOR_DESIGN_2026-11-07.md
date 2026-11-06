# WP4.14 — VSP Schema v1, Canonicalization and Signature-Vector Design

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Type:** Documentation-only protocol design decision record  
**Status:** PROPOSED TEST PROFILE — NOT FROZEN, NOT IMPLEMENTED, NOT APPROVED FOR PRODUCTION

## 1. Decision summary

The first VSP verifier work package should be a pure, side-effect-free verifier using a deliberately small, closed schema and deterministic test vectors.

**Candidate cryptographic profile:** Ed25519, using the existing Python `cryptography` API family already used by HND transaction code. This is a compatibility-based candidate, not a production cryptographic approval. Production use requires an exact dependency lock, key-custody review, independent cryptographic review and protocol-owner approval.

**Canonicalization decision:** do not reuse the existing `hnd_v02.transaction.canonical_json` as the VSP wire canonicalization standard without additional constraints. It sorts keys and emits compact UTF-8 JSON, but it does not reject duplicate keys at parse time, and Python JSON number formatting is not a declaration of RFC 8785 JCS conformance. For VSP v1, use a restricted JSON value domain and RFC 8785 JSON Canonicalization Scheme (JCS), with conformance vectors and byte-for-byte canonical-input enforcement. If a reviewed JCS implementation cannot be selected and pinned, stop: do not silently substitute Python `json.dumps`.

No source code, test file, dependency, vector, key, Genesis, workflow or deployment setting was changed.

## 2. Source compatibility observations

Inspected source:
- `hnd_v02/transaction.py`: uses Ed25519 private/public key types from `cryptography`; transaction signatures use `TX_SIGNING_DOMAIN = b"HND-LEDGER/TX\\x00"`; `canonical_json` uses `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`.
- `hnd_v02/genesis.py`: defines a separate `GENESIS_DOMAIN = b"HND-LEDGER/GENESIS\\x00"` and hashes canonicalized manifest content.
- `requirements.txt`: `cryptography>=41.0` is not an exact reproducible dependency pin.
- Existing transaction and Genesis tests use Python `json.loads` for fixtures. They do not establish duplicate-member rejection for raw VSP documents.

Implications:
1. Ed25519 is already an available algorithm family in the current codebase and avoids introducing a second signing primitive for the first prototype.
2. The VSP must have a distinct signature domain, not reuse transaction or Genesis domains.
3. Existing HND canonical JSON is a useful internal precedent, not proof of JCS compliance.
4. The verifier must parse raw bytes with duplicate-member detection before any mapping/dictionary is created.
5. The production verifier dependency must be locked to an exact reviewed version with hashes/SBOM/provenance; current `cryptography>=41.0` is insufficient for reproducible production builds.

## 3. Proposed VSP v1 document

The following is a logical schema, not a ready-to-sign production document. Every field is required unless explicitly marked optional. Unknown fields are rejected in v1.

```json
{
  "schema": "hnd.vsp.v1",
  "chain_id": "hnd-example-network",
  "hnd_genesis_sha256": "<64 lowercase hex>",
  "cometbft_genesis_sha256": "<64 lowercase hex>",
  "cometbft_profile_sha256": "<64 lowercase hex>",
  "cometbft_source_commit": "<40 lowercase hex>",
  "cometbft_binary_sha256": "<64 lowercase hex>",
  "sequence": 1,
  "previous_vsp_sha256": "<64 lowercase hex>",
  "activation_height": 1,
  "expires_at": "2030-01-01T00:00:00Z",
  "validator_set": [
    {
      "validator_id": "operator-assigned-stable-id",
      "consensus_pubkey_type": "ed25519",
      "consensus_pubkey_base64": "<canonical base64 raw public key>",
      "cometbft_consensus_address": "<uppercase hex address derived by pinned CometBFT version>",
      "voting_power": 10
    }
  ],
  "total_voting_power": 10,
  "signature_policy": {
    "algorithm": "ed25519",
    "threshold": 2,
    "keyset_id": "<64 lowercase hex trust-manifest digest>"
  }
}
```

The example values are placeholders. The schema intentionally does not contain private keys, account signing keys, P2P node keys, governance secrets, hostnames, RPC credentials or signer socket secrets.

### 3.1 Field semantics

- `chain_id`: exact CometBFT chain ID; must match HND and both Genesis documents.
- `hnd_genesis_sha256`: HND Genesis manifest digest using the HND Genesis domain and established encoding.
- `cometbft_genesis_sha256`: digest of the exact CometBFT Genesis bytes accepted by the pinned CometBFT version. Parsing and semantic comparison are additional mandatory checks.
- `cometbft_profile_sha256`: digest of the reviewed, version-specific consensus/security profile representation. The profile field classification must be completed before the digest is meaningful.
- `cometbft_source_commit` and `cometbft_binary_sha256`: exact source and built binary identities; version tag alone is not enough.
- `sequence`: positive integer, strictly increasing for each chain/trust-root lineage.
- `previous_vsp_sha256`: exact digest of the previously accepted VSP. Initial sequence requires a separately specified bootstrap sentinel, not an omitted or arbitrary value.
- `activation_height`: positive integer; activation policy must account for all nodes and signer state.
- `expires_at`: UTC timestamp with exact RFC 3339 profile, no offsets other than Z, no fractional seconds in v1.
- `validator_set`: sorted lexicographically by stable `validator_id`; identifiers unique; public keys unique; derived CometBFT addresses unique; voting power positive and bounded by a protocol-defined maximum.
- `total_voting_power`: exact integer sum of all validator powers, checked with explicit bounds.
- `signature_policy`: algorithm and threshold are fixed by v1 policy; the document cannot weaken the trust-root threshold by changing this field.

Do not infer a production validator count, voting-power cap, minimum coalition threshold or fault-tolerance guarantee from the sample value 10.

## 4. Canonicalization and raw parser requirements

VSP v1 canonical bytes shall be RFC 8785 JCS bytes for the restricted schema. The implementation must:

1. Accept a bounded raw UTF-8 document only; reject UTF-8 BOM and invalid UTF-8.
2. Reject duplicate object member names at every nesting level during parsing, before constructing a normal dictionary.
3. Reject non-finite numbers, floating-point values, negative zero, exponent/number forms outside the schema and all numeric values where the schema requires an integer.
4. Reject booleans where an integer is required. In Python, use exact type checks; `isinstance(True, int)` is not sufficient.
5. Reject unknown and missing fields.
6. Reject non-canonical Base64, incorrect key lengths, uppercase/lowercase deviations in hex fields and invalid Unicode strings.
7. Enforce the schema's restricted value types; do not permit arbitrary JSON numbers or unconstrained free-form extension objects.
8. Canonicalize with a reviewed RFC 8785 implementation and compare the canonical output byte-for-byte with the signed input representation where canonical wire bytes are required.
9. Sign the exact canonical document bytes under the VSP-specific domain below.
10. Test cross-implementation vectors; Python-only self-consistency is not sufficient.

JCS canonicalization is not a substitute for semantic validation. Both byte-level and schema-level checks are required.

## 5. Signature construction and threshold verification

Candidate signing preimage:

```text
"HND-LEDGER/VSP/V1\x00" || UTF8(chain_id) || 0x00 || JCS(VSP_document)
```

The signature payload is the exact byte sequence above. The verifier must not sign a digest representation in one implementation and raw bytes in another. A SHA-256 digest of the complete preimage may be logged as the VSP signing digest, but signature input must be fixed consistently in the protocol specification and test vectors.

Each signature envelope is separate from the VSP document:

```json
{
  "schema": "hnd.vsp-signatures.v1",
  "vsp_sha256": "<64 lowercase hex>",
  "signatures": [
    {
      "key_id": "<64 lowercase hex>",
      "algorithm": "ed25519",
      "signature_base64": "<canonical base64 64-byte signature>"
    },
    {
      "key_id": "<64 lowercase hex>",
      "algorithm": "ed25519",
      "signature_base64": "<canonical base64 64-byte signature>"
    }
  ]
}
```

Verifier rules:
- trust manifest digest is pinned independently of the VSP and signature envelope;
- exactly the configured trust-root keyset is accepted;
- at least two distinct enrolled key IDs must verify successfully;
- duplicate key IDs are rejected even if signatures are byte-identical;
- unknown, revoked, expired or not-yet-active keys are rejected;
- signature algorithm is fixed by the trusted key record, not selected by an untrusted VSP field;
- each key ID is derived from a defined domain-separated public-key fingerprint representation;
- a valid signature over another chain, Genesis, sequence or VSP digest is invalid in this context;
- no private key is ever loaded by the verifier.

A 2-of-3 policy is an authorization threshold, not proof that the custodians are independent. Custody independence is established by external governance evidence.

## 6. Trust-manifest minimum shape

A separately pinned trust manifest is required. It must contain:
- schema identifier and keyset ID;
- chain ID and HND/CometBFT Genesis digests;
- exactly three distinct governance public keys for the initial policy;
- fixed Ed25519 algorithm identifiers;
- threshold 2;
- key status and activation/revocation sequence;
- independently witnessed bootstrap ceremony reference/digest;
- trust-manifest sequence and predecessor digest.

The initial trust-manifest digest must be pinned out of band in the deployment/release trust channel. It must not be bootstrapped from the VSP it is intended to authenticate. The exact trust manifest schema and catastrophic recovery authority remain subject to protocol-owner approval.

## 7. Proposed golden and negative vector suite

These vectors are requirements for a future implementation; none have been generated or executed.

| ID | Vector | Expected |
|---|---|---|
| VSP-SIG-01 | One valid Ed25519 signature | Reject threshold |
| VSP-SIG-02 | Two valid signatures from distinct enrolled keys | Accept cryptographic threshold only |
| VSP-SIG-03 | Same key ID repeated twice | Reject |
| VSP-SIG-04 | Signature from unknown key | Reject |
| VSP-SIG-05 | Signature from revoked key | Reject |
| VSP-SIG-06 | One signature altered by one bit | Reject |
| VSP-SIG-07 | VSP changed after signatures created | Reject |
| VSP-SIG-08 | Signature from another chain ID | Reject |
| VSP-SIG-09 | Signature from another domain prefix | Reject |
| VSP-SIG-10 | Non-canonical Base64 signature | Reject |
| VSP-CAN-01 | Duplicate top-level JSON member | Reject before object creation |
| VSP-CAN-02 | Duplicate nested validator member | Reject before object creation |
| VSP-CAN-03 | Invalid UTF-8 or BOM | Reject |
| VSP-CAN-04 | Whitespace/key order differs from required canonical wire bytes | Reject |
| VSP-CAN-05 | Float, NaN, Infinity or negative zero in integer field | Reject |
| VSP-CAN-06 | Boolean substituted for integer sequence/power | Reject |
| VSP-CAN-07 | Unknown extension field | Reject |
| VSP-CAN-08 | Oversized document or validator array | Reject |
| VSP-BIND-01 | Wrong HND Genesis digest | Reject |
| VSP-BIND-02 | Wrong CometBFT Genesis digest | Reject |
| VSP-BIND-03 | Wrong profile/source/binary digest | Reject |
| VSP-BIND-04 | Duplicate consensus key/address | Reject |
| VSP-BIND-05 | Incorrect voting-power sum | Reject |
| VSP-BIND-06 | Sequence replay or predecessor mismatch | Reject |
| VSP-BIND-07 | Expired VSP or activation-height violation | Reject |

Positive vectors must be generated independently by at least two implementations and checked into the repository only after implementation approval. Do not put private signing keys into vectors; use public verification keys and deterministic test-only fixtures whose private seeds are clearly test-only and never reused.

## 8. Decisions deliberately left open

The following must not be guessed:
- exact JCS library and version, support status, maintenance and dependency lock strategy;
- exact Ed25519 key fingerprint encoding and key ID domain;
- trust-manifest bootstrap sentinel and sequence-zero representation;
- precise timestamp validity policy and trusted clock source;
- validator power upper bound, total-power bound and decentralization/coalition acceptance thresholds;
- CometBFT v0.40.0 address derivation and consensus-key type mapping as verified against pinned source;
- exact profile field classification and digest encoding;
- external monotonic anti-rollback mechanism and crash/recovery semantics;
- catastrophic recovery authority if two governance keys are lost or compromised;
- deployment OS/service hardening model and direct-binary bypass denial.

## 9. Next implementation gate

The next code change, when explicitly authorized, should be limited to:
1. strict raw JSON duplicate-member parser and bounded VSP schema validator;
2. canonicalization adapter with independently verified JCS vectors;
3. Ed25519 signature verification over the VSP-specific domain;
4. negative tests for parser, canonicalization, domain separation, threshold and key identity.

It must not start services, write anti-rollback state, enroll production keys or alter Genesis. Runtime integration is a later work package after the pure verifier passes independent review.

## 10. Disposition

**PROPOSED TEST PROFILE ONLY — NOT FROZEN.**  
**NOT IMPLEMENTED. NOT APPROVED FOR PRODUCTION.**

This document is a protocol design record, not a cryptographic certification, trust-root enrollment, production key ceremony or launch authorization.
