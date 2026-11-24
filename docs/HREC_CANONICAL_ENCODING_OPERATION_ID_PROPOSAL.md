# HREC v1 canonical encoding and operation identity — decision proposal

**Status:** Proposed protocol decision; not frozen or production-approved.  
**Date:** 2026-11-24  
**Scope:** Deterministic cross-validator identity for one HND/CometBFT recovery-checkpoint transition.  
**Target:** HND v0.2 and the pinned CometBFT v0.40.0 build.

## 1. Decision requested

Adopt a small, versioned, fixed-order binary encoding for the immutable transition payload, with explicit field tags and lengths. Derive both the publication operation ID and the payload digest from the exact same canonical bytes using different SHA-256 domain-separation labels.

Do not use ordinary JSON serialization, map iteration order, floating-point values, locale-sensitive formatting, timestamps, random nonces, or validator-local identifiers in this identity.

This proposal deliberately does not choose the independent anchor's signature scheme, transport, certificate lifecycle, consensus trust root, or administration model. Those remain separate security decisions.

## 2. Canonical byte format

The encoding is:

```
magic = ASCII("HREC-TLV-V1") || 0x00
record = magic || field_1 || ... || field_22
field = tag_u16_be || value_length_u32_be || value
```

Rules:

- Fields MUST appear exactly once and in ascending tag order 1 through 22.
- Integers are unsigned, fixed-width, big-endian. No varints or leading/trailing padding.
- Digest values are exactly 32 raw bytes, not hexadecimal text.
- Text values are strict ASCII bytes, with no Unicode normalization or locale conversion. Reject bytes outside the permitted grammar.
- All lengths are byte lengths. Reject truncated, duplicate, unknown, out-of-order, or trailing data.
- The magic string and field list are versioned. Any field semantic or encoding change requires a new format/version and new domain-separation labels.
- A decoder MUST re-encode the parsed record and require byte-for-byte equality with the received bytes.

## 3. Immutable transition fields

| Tag | Field | Encoding and validation |
|---:|---|---|
| 1 | `network_id` | ASCII, 1–64 bytes, `[a-z0-9][a-z0-9._-]*` |
| 2 | `chain_id` | Exact ASCII chain ID, 1–50 bytes; reject control/space bytes |
| 3 | `genesis_hash` | 32-byte SHA-256 digest |
| 4 | `predecessor_checkpoint_sequence` | u64 big-endian |
| 5 | `predecessor_checkpoint_digest` | 32-byte digest of the exact predecessor checkpoint payload |
| 6 | `transition_height` | u64 big-endian; must be positive and equal HND post-commit height |
| 7 | `cometbft_block_id_hash` | 32-byte block header hash |
| 8 | `cometbft_part_set_total` | u32 big-endian; must be positive |
| 9 | `cometbft_part_set_hash` | 32-byte PartSetHeader hash |
| 10 | `predecessor_hnd_app_hash` | 32-byte HND app hash A[h-1] |
| 11 | `successor_hnd_app_hash` | 32-byte HND app hash A[h] |
| 12 | `predecessor_state_snapshot_digest` | 32-byte digest of retrievable complete predecessor-state bytes |
| 13 | `block_execution_input_digest` | 32-byte digest binding the full verified block and all HND execution inputs, including normalized evidence/misbehavior inputs |
| 14 | `signed_header_proof_digest` | 32-byte digest of the signed-header, commit, validator-set and associated proof bundle; the anchor must still verify the actual proof bytes |
| 15 | `protocol_config_digest` | 32-byte digest of the approved protocol/consensus configuration |
| 16 | `hnd_build_identity_digest` | 32-byte digest binding the exact deterministic HND execution build/source identity |
| 17 | `cometbft_binary_digest` | 32-byte digest of the exact CometBFT executable/build |
| 18 | `cometbft_profile_digest` | 32-byte digest of the approved CometBFT node/profile configuration |
| 19 | `trusted_light_client_root_digest` | 32-byte digest identifying the independently approved light-client trust root and trust policy |
| 20 | `hnd_store_schema` | u32 big-endian |
| 21 | `cometbft_version` | Exact ASCII version string; for this target, `0.40.0` |
| 22 | `bootstrap_flag` | Exactly one byte: `0x00` ordinary transition, `0x01` explicitly authorized Genesis bootstrap |

The transition height represents both the signed CometBFT proof-header height and the resulting HND application height. The verifier MUST enforce this equality. The header's AppHash at height h is the predecessor value A[h-1], not the successor A[h].

### Bootstrap constraints

For an ordinary transition (`bootstrap_flag=0`), predecessor sequence MUST be positive and predecessor checkpoint digest MUST be nonzero.

For the single, separately authorized Genesis bootstrap (`bootstrap_flag=1`), predecessor sequence MUST be zero and predecessor checkpoint digest MUST be 32 zero bytes. The anchor must permit this only through a witnessed, one-time bootstrap ceremony bound to the approved Genesis and initial validator trust root. A normal validator API credential must not be able to create or repeat bootstrap.

The all-zero predecessor digest is not a general "missing value" encoding.

## 4. Derived identities

Let `C` be the exact canonical record bytes defined above.

- `operation_id = SHA256(ASCII("HND-HREC-OPID-V1") || 0x00 || C)`
- `payload_digest = SHA256(ASCII("HND-HREC-PAYLOAD-V1") || 0x00 || C)`

Represent these digests externally as lowercase 64-character hexadecimal strings. Internally they are 32 raw bytes.

The anchor assigns the successor checkpoint sequence and commit receipt after accepting the transition. Those service-generated values, timestamps, PREPARED/COMMITTED status, retry count, local validator identity, and transport metadata MUST NOT be included in C. This keeps every honest validator's operation ID identical for the same transition.

The predecessor sequence and digest ARE included, preventing the same transition from being silently attached to a different checkpoint history.

The anchor MUST enforce:
- one immutable canonical payload per operation ID;
- rejection if an existing operation ID is presented with different canonical bytes or payload digest;
- no two different successor payloads may commit against the same predecessor checkpoint;
- byte-identical duplicate PREPARE/COMMIT requests are idempotent;
- a timeout is an unknown result and is reconciled by reading this same operation ID.

## 5. CometBFT and HND semantic checks

Before PREPARE, the independent verifier MUST establish all of the following:

1. The trusted light-client path authenticates the signed header and validator set for the exact chain and height.
2. The complete BlockID, including PartSetHeader total and hash, matches the verified block/commit identity.
3. The full block body and every HND execution input are available and digest to tag 13.
4. The predecessor snapshot bytes are retrievable and digest to tag 12; recomputing HND state from them yields tag 10.
5. The signed header's `AppHash` equals tag 10 (A[h-1]).
6. Deterministic execution of the exact HND build and inputs yields tag 11 (A[h]).
7. The local HND durable store and CometBFT native state/block store are consistent with this transition.
8. Genesis, network, protocol config, HND build, CometBFT binary/profile, store schema, and trust-root identities match the approved values.

A caller-supplied digest is a locator/integrity claim, not proof by itself. The verifier must fetch the referenced bytes and verify them.

## 6. Synthetic cross-language test vector

The following vector is intentionally synthetic and MUST NOT be used as a live network identity or Genesis configuration.

Input values:

- network_id = `hanadi-mainnet`
- chain_id = `hanadi-1`
- genesis_hash = `11` repeated 32 bytes
- predecessor_checkpoint_sequence = 7
- predecessor_checkpoint_digest = `22` repeated 32 bytes
- transition_height = 8
- block_id_hash = `33` repeated 32 bytes
- part_set_total = 1
- part_set_hash = `44` repeated 32 bytes
- predecessor_hnd_app_hash = `55` repeated 32 bytes
- successor_hnd_app_hash = `66` repeated 32 bytes
- predecessor_state_snapshot_digest = `77` repeated 32 bytes
- block_execution_input_digest = `88` repeated 32 bytes
- signed_header_proof_digest = `99` repeated 32 bytes
- protocol_config_digest = `aa` repeated 32 bytes
- hnd_build_identity_digest = `bb` repeated 32 bytes
- cometbft_binary_digest = `cc` repeated 32 bytes
- cometbft_profile_digest = `dd` repeated 32 bytes
- trusted_light_client_root_digest = `ee` repeated 32 bytes
- hnd_store_schema = 1
- cometbft_version = `0.40.0`
- bootstrap_flag = `0x00`

Expected canonical record length: **645 bytes**.

Expected SHA-256 results:

- `operation_id`: `b9c0787b0a0465391861fa2d866381490a56700c44ec94a78c465b409daa733d`
- `payload_digest`: `43211befca4a53aaa5d068cd0bc91d9d13f00d7a5e9bd8423c0e0031b30008ac`

Implementations in Go and Python MUST independently reproduce the exact 645-byte encoding and both digests. The test fixture should also store the complete canonical bytes as a checked-in binary or hex fixture generated from this table, not hand-maintained copies of the digest alone.

## 7. Mandatory negative and mutation tests

At minimum, test that:

- swapping any two fields is rejected;
- duplicate, missing, unknown, truncated, or trailing fields are rejected;
- changing a field length without changing its bytes is rejected;
- non-ASCII text, forbidden chain-ID bytes, and invalid network IDs are rejected;
- little-endian integers and variable-width integers are rejected;
- a 31-byte or 33-byte digest is rejected;
- zero PartSetHeader total is rejected;
- ordinary transition with zero predecessor sequence/digest is rejected;
- bootstrap with nonzero predecessor sequence/digest is rejected;
- transition height zero is rejected;
- changing any single field changes both derived digests;
- changing only PREPARED/COMMITTED status, service timestamp, retry count, or local validator ID does not change either digest because these values are not part of C;
- two independent implementations produce byte-identical C, operation ID, and payload digest;
- reusing an operation ID with altered canonical bytes is a fatal anchor conflict.

## 8. Open decisions that remain outside this encoding proposal

This proposal does not settle:
- the cryptographic signature/envelope format for anchor receipts;
- the transport protocol and authenticated service identity;
- trust-root rotation and validator-set governance;
- snapshot retention, availability, and witnessed restore;
- the exact approved Genesis ceremony and who can authorize it;
- maximum proof/snapshot sizes and retention periods;
- whether proof bundles are stored by the anchor or in independently administered content-addressed storage.

These are mandatory protocol/security review items. Do not begin production implementation while they remain unspecified.

## 9. Acceptance gate

This proposal may be promoted to a frozen protocol decision only after:
1. independent review of every field's security purpose and omission risk;
2. Go and Python implementations reproduce the test vector independently;
3. negative/mutation tests pass;
4. anchor concurrency tests prove idempotency and one-successor-per-predecessor behavior;
5. bootstrap is separately threat-modelled and witnessed.

No source code, workflow, runtime, signer, or production setting is changed by this document.
