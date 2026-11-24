# HREC Nested Evidence Artifact Formats — Design Proposal

Status: design proposal only. This document does not freeze a wire protocol, add recovery code, or authorize deployment.

Scope: define the HND-owned portion of the three nested artifacts referenced by the HREC operation-ID proposal, and identify the CometBFT-owned byte encodings that must be pinned before an interoperable implementation can be claimed.

## 1. Source-grounded findings

The current HND v0.2 implementation provides these concrete facts:

- `HNDLedger.snapshot()` returns the exact state object with keys `schema_version`, `network_id`, `protocol_version`, `genesis_hash`, `total_supply`, `balances`, `nonces`, `accepted`, `history`, and `state_hash`.
- The ledger state hash is SHA-256 over `HND-LEDGER/STATE\0 || canonical_json(_state_payload())`. The snapshot's `state_hash` is therefore reproducible by restoring the ledger from Genesis and replaying its transaction history.
- The ABCI durable store adds `schema_version`, network/protocol parameters, `genesis_hash`, `last_committed_height`, `ledger_snapshot`, `evidence_journal`, `app_hash`, and `store_hash`.
- The HND app hash is SHA-256 over `HND-ABCI-APP-STATE-V1\0 || canonical_json({ledger_state_hash, evidence_journal})`.
- The store hash is a local integrity checksum over the store payload without `store_hash`. It is not an authentication mechanism or an independent freshness proof.
- Store loading validates the schema, configuration, ledger snapshot by deterministic replay, evidence journal normalization, and recomputed app hash.
- The on-disk pretty-printed JSON is not the canonical digest input. The current canonical JSON helper emits UTF-8, sorted keys, compact separators, no ASCII escaping, and rejects non-finite numbers.

These findings make the logical HND snapshot envelope definable. They do not by themselves define a cross-language wire encoding or the CometBFT proof artifacts.

## 2. HND predecessor snapshot artifact (candidate HND-SNAPSHOT-V1)

### 2.1 Logical envelope

The artifact represents the complete HND predecessor application state at height `h-1`. Its logical object has exactly these fields:

| Field | Type | Rule |
|---|---|---|
| `format` | string | Exact value `HND-HREC-SNAPSHOT-V1` |
| `network_id` | string | Exact configured HND network identity |
| `chain_id` | string | Exact CometBFT chain ID; must equal the approved mapping to `network_id` |
| `genesis_hash` | lowercase hex | Exactly 32 bytes |
| `height` | unsigned integer | Exact predecessor application height |
| `app_hash` | lowercase hex | Exactly 32 bytes; recomputed from the restored ledger and evidence journal |
| `ledger_snapshot` | object | Exact HND ledger snapshot schema described in §1 |
| `evidence_journal` | array | Complete ordered normalized evidence journal at this height |

No additional, missing, or null fields are accepted. Unknown fields are rejected. The envelope does not include the pretty-printed store file, temporary-file name, filesystem metadata, or `store_hash`.

### 2.2 Canonical bytes and digest

The proposed semantic digest is:

`SHA256(ASCII("HND-HREC-HND-SNAPSHOT-V1") || 0x00 || canonical_envelope_bytes)`

The artifact manifest must record both byte length and digest. The exact canonical JSON profile is **not frozen by this proposal**. Reusing the current Python `canonical_json` helper without a language-neutral conformance specification is insufficient for Go/Python interoperability. Before freeze, specify escaping, Unicode handling, integer domain, key ordering, and rejection of floating-point values, then publish byte-for-byte vectors in both languages. Do not hash the indented on-disk representation.

### 2.3 Independent verification procedure

A verifier must:

1. Enforce a configured maximum artifact size before parsing.
2. Decode strict UTF-8; reject BOM, duplicate object keys, non-finite values, unknown fields, missing fields, nulls, and non-canonical bytes.
3. Verify the exact network, chain, Genesis, protocol, and snapshot schema identities against the independently approved configuration.
4. Restore `ledger_snapshot` from the pinned Genesis manifest using the HND deterministic replay implementation. Recompute and compare `state_hash`; do not trust balances or nonce maps supplied by the artifact.
5. Validate the entire evidence journal using the same strict normalization and ordering rules as the application. Reject duplicate evidence IDs and non-canonical records.
6. Recompute the HND app hash using the pinned app-hash domain and compare it to `app_hash`.
7. Verify that `height` is the height represented by the snapshot and that the artifact is the exact predecessor height required by the target transition.
8. Recompute the artifact digest from the canonical bytes and compare it to the manifest and the corresponding outer checkpoint field.

A matching digest proves byte identity only. It does not prove that the snapshot is fresh, authorized, or the correct predecessor. Those properties come from the authenticated checkpoint, signed CometBFT proof, and deterministic transition verification.

## 3. Block execution input artifact (candidate HND-EXECUTION-INPUT-V1)

The execution-input artifact must preserve enough information for an independent verifier to reproduce the exact HND transition at height `h`. Its logical manifest must bind:

- exact network, chain, Genesis, protocol configuration, HND build identity, and application schema;
- transition height `h`;
- complete CometBFT block identity, including block hash and complete PartSetHeader;
- the full block bytes retrieved from the pinned CometBFT block store, not merely transaction IDs or a caller-provided block hash;
- ordered transaction byte strings exactly as delivered to HND FinalizeBlock, including rejected transactions;
- the complete normalized misbehavior/evidence input supplied to HND FinalizeBlock, preserving order and every field that affects HND execution;
- the predecessor snapshot digest from §2;
- the expected predecessor app hash and independently recomputed successor app hash.

The artifact digest must use a distinct domain, proposed as `HND-HREC-EXECUTION-INPUT-V1\0`, over a canonical manifest that references content-addressed binary payloads. Each payload entry must contain a fixed media/type identifier, byte length, digest algorithm, and digest. Manifest entry ordering must be fixed by numeric tag, not filesystem or map iteration order.

### 3.1 Deterministic replay

The verifier must authenticate the full block against the signed header's BlockID and PartSetHeader, check the predecessor app hash relationship, reconstruct the exact HND FinalizeBlock inputs, execute transactions in original order with the pinned HND build, apply the normalized evidence journal rules, and recompute the successor app hash. A transaction result list or app hash supplied by the artifact is an expected output to compare, never an input to trust.

### 3.2 Remaining CometBFT byte-level gate

The exact serialization of the full block, BlockID/PartSetHeader, and evidence objects must be pinned to CometBFT v0.40.0 generated protobuf types and the precise marshal/unmarshal APIs used by that release. This proposal deliberately does not assume that arbitrary protobuf encoders produce interchangeable canonical bytes. Before freeze, inspect the exact v0.40.0 source definitions and specify:

- the authoritative block-store representation and conversion path;
- canonical block hash and PartSetHeader recomputation procedure;
- protobuf message types and deterministic marshal rules, if serialized protobuf bytes are used as artifact payloads;
- the exact mapping from CometBFT evidence to the HND misbehavior records passed to FinalizeBlock;
- limits for block bytes, transaction count/size, evidence count/size, and nested depth.

Until those rules and cross-language vectors exist, the execution-input artifact format remains incomplete.

## 4. Signed-header proof artifact (candidate HND-COMMIT-PROOF-V1)

The proof artifact must contain retrievable proof material, not only a digest. Its logical contents are:

1. the signed header at height `h`;
2. the commit for the exact block ID at height `h`;
3. the validator set required to verify that commit;
4. the trusted light-client root and validator-set transition material needed to authenticate the height-`h` validator set;
5. the exact CometBFT chain ID and pinned protocol/release identity;
6. the verification mode and result metadata, including the trust root identity and the complete sequential verification range.

The verifier must use the upstream CometBFT v0.40.0 light-client verification implementation or an explicitly pinned equivalent. The initial prototype profile is sequential verification; skipping verification is not permitted by this proposal. It must validate signatures, voting power, chain ID, height, time/trust constraints, validator-set transitions, commit BlockID, and the signed header. It must not accept a caller-provided boolean such as `verified=true` as proof.

### 4.1 Remaining proof serialization gate

The exact byte representation and digest inputs for signed headers, commits, validator sets, and trust material remain unresolved. They must be derived from the exact v0.40.0 source types and canonical signing-byte rules. A digest of a locally re-encoded object is not a substitute for the upstream verification procedure. Cross-language test vectors must include valid proofs, invalid signatures, wrong chain IDs, insufficient voting power, wrong BlockID/PartSetHeader, validator-set changes, stale trust roots, and missing intermediate headers.

## 5. Content-addressed artifact manifest

The three nested artifacts should be stored in a content-addressed manifest with:

- a manifest format/version identifier;
- fixed numeric tags for artifact classes;
- exact byte length and SHA-256 digest for each object;
- an explicit media/encoding identifier and schema version;
- a bounded retrieval URI or storage key that is not itself trusted as proof;
- retention and availability requirements covering the full recovery period.

Retrieval must be followed by length and digest verification. A URI, object-store ETag, local filename, or database row ID is not an integrity proof. Compression is excluded from v1 unless the compressed and uncompressed byte identities, algorithm, parameters, and decompression limits are specified and tested. The digest is over the exact artifact bytes defined by the relevant artifact profile.

## 6. Cross-language conformance requirements

Before any nested artifact profile is frozen, independent Go and Python implementations must reproduce identical bytes and digests from the same semantic fixtures. The conformance suite must include:

- empty and maximum-sized collections;
- Unicode and escaped-string edge cases;
- integer boundaries and rejection of floats, booleans-as-integers, and out-of-range values;
- duplicate keys, unknown fields, nulls, malformed hex, and non-canonical encodings;
- reordered transactions and reordered evidence;
- changed predecessor snapshot, Genesis, network, chain ID, or protocol configuration;
- truncated, oversized, and digest-mismatched payloads;
- corrupted block/commit/validator-set proof material.

Every vector must publish the semantic input, exact encoded bytes in hex, byte length, and expected digest. Tests must fail closed on any mismatch.

## 7. Decisions that remain open

This proposal does not freeze:

- the language-neutral canonical JSON or binary encoding profile;
- the exact CometBFT v0.40.0 protobuf/block-store byte representation;
- the exact CometBFT evidence-to-HND misbehavior mapping;
- the light-client trust-root bootstrap, rotation, expiry, and witnessed recovery policy;
- artifact maximum sizes, retention periods, storage availability SLA, and disaster-recovery ownership;
- whether the current HND snapshot replay model is performant enough for the intended chain scale.

These are protocol gates, not implementation details to be guessed during coding. No source runtime, signer, listener, workflow, key, trust root, or production configuration is changed by this document.
