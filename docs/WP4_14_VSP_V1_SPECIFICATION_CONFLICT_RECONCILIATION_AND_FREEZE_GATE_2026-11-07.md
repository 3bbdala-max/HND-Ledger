# WP4.14 — VSP v1 Specification Conflict Reconciliation and Freeze Gate

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Review type:** Cross-document protocol consistency audit  
**Change type:** Documentation only  
**Disposition:** VSP v1 is NOT FROZEN; no golden signatures/vectors should be generated against the conflicting drafts

## 1. Executive decision

The repository contains multiple VSP v1 schema and signature drafts that are not wire-compatible. The differences affect payload field names, nested object structure, sequence/bootstrap semantics, validator ordering and the Ed25519 signing preimage. They cannot all be normative simultaneously.

**Decision for engineering control:** do not generate golden signatures, write a verifier, add a JCS dependency, or change source/tests until one consolidated v1 contract is explicitly selected and reviewed.

Recommended reconciliation baseline:
1. Use `WP4_14_VALIDATOR_SET_PROFILE_CANONICAL_SCHEMA_AND_VERIFICATION_SPEC_2026-11-07.md` as the semantic schema baseline (complete snapshot, payload/envelope separation, chain and Genesis binding, CometBFT software identity, sequence/activation, roster, governance policy and change metadata).
2. Use `WP4_14_VSP_V1_CANONICALIZATION_SIGNATURE_AND_GOLDEN_VECTOR_CONTRACT_2026-11-07.md` for the exact cryptographic formula: JCS payload bytes, domain-separated SHA-256 profile digest, then Ed25519 over the separately domain-separated raw 32-byte digest.
3. Use `WP4_14_VSP_JCS_LIBRARY_SELECTION_AND_STRICT_INPUT_PIPELINE_REVIEW_2026-11-07.md` for the whole-envelope canonical-byte rule and strict raw-input pipeline.
4. Treat `WP4_14_VSP_V1_SCHEMA_CANONICALIZATION_AND_CRYPTOGRAPHIC_TEST_VECTOR_DESIGN_2026-11-07.md` and `WP4_14_VSP_SCHEMA_V1_CANONICALIZATION_AND_SIGNATURE_VECTOR_DESIGN_2026-11-07.md` as non-authoritative candidate drafts where they conflict with the three baseline documents above. Do not silently merge their field sets or signing formulas.

This is an engineering recommendation, not an approved protocol-owner decision. The baseline must be consolidated into one normative document before implementation.

## 2. Conflicts found

| Topic | Existing canonical schema / contract | Conflicting draft | Required resolution |
|---|---|---|---|
| Payload field structure | `schema`, `schema_version`, `chain_id`, `hnd_genesis_sha256`, nested `cometbft`, `profile_sequence`, `activation`, `validators`, `governance_policy`, `change` | Flat fields such as `hnd_network_id`, `hnd_protocol_version`, `cometbft_genesis_sha256`, `cometbft_profile_sha256`, `sequence`, `activation_height`, `expires_at_unix` | Select one exact field set; do not accept aliases in v1 |
| Software binding | Nested CometBFT version/source/binary identity in the canonical schema | Separate flat source commit and binary digest, plus an additional CometBFT profile digest | Define one nested object and exact profile digest semantics |
| Activation | Initial profile uses sequence 1, previous digest null, activation kind `genesis`, height 0; later profiles use height activation | Alternative draft permits sequence 0 and uses a direct positive `activation_height` | Retain the canonical schema's genesis-vs-height distinction unless protocol-owner changes it |
| Expiry | Canonical schema has no mandatory expiry field; timestamp policy is open | Alternative draft mandates `expires_at_unix` | Do not add mandatory expiry until clock trust, offline behavior and expiry semantics are approved |
| Validator records | `consensus_key_type`, `consensus_pubkey`, `consensus_address`, `voting_power`, `operator_id`, `operator_attestation_ref` | Alternative names include `consensus_pubkey_type`, `consensus_pubkey`, `validator_id` and omit some operator evidence fields | Freeze one exact nested record schema and identity vocabulary |
| Validator order | Canonical schema: sorted by lowercase hexadecimal consensus address | One draft: sorted by bytewise UTF-8 consensus address; another uses lowercase address but does not consistently define source encoding | Verify CometBFT v0.40.0 address representation, then freeze one bytewise ordering |
| Governance policy | Payload carries `governance_policy` with policy ID, authorized key IDs and threshold; trust manifest remains independent | Alternative draft fixes exactly three governance keys/threshold externally and omits policy metadata from its payload | Decide whether payload repeats immutable policy metadata; if repeated, verifier must require exact equality with trust manifest |
| Profile digest | `SHA-256("HND-VSP-v1" || 0x00 || JCS(payload))` | One draft uses a different `HND-LEDGER/VSP-SIGNATURE/V1` signing label directly over payload bytes | Use only the digest-then-sign formula from the golden-vector contract if selected |
| Ed25519 message | `"HND-VSP-AUTH-v1" || 0x00 || raw_profile_digest` | Alternative draft signs the complete canonical payload under another domain prefix | Do not accept both formulas; that would create ambiguous signatures |
| Envelope canonicalization | JCS library review recommends canonicalizing the entire envelope, while hashing/signing only canonical payload bytes | Earlier drafts describe canonical payload bytes but leave nested raw-byte extraction ambiguous | Adopt whole-envelope canonical bytes and independently JCS-serialize payload for digest |
| Trust bootstrap | Trust manifest pinned independently out-of-band; 2-of-3 distinct keys | Alternative schema embeds additional trust-manifest sequence/predecessor/expiry fields without a final transition contract | Keep trust-root lifecycle separate from VSP v1 until a dedicated trust-manifest schema is frozen |

## 3. Exact baseline formulas recommended for consolidation

Let `P` be RFC 8785 JCS UTF-8 bytes of the parsed `payload` object.

- Profile digest: `D = SHA-256(ASCII("HND-VSP-v1") || 0x00 || P)`
- Governance signature message: `M = ASCII("HND-VSP-AUTH-v1") || 0x00 || D`
- Each Ed25519 signature verifies against `M` and one public key from the independently pinned trust manifest.
- At least two distinct enrolled governance key IDs must verify.
- The complete envelope is strict UTF-8 JSON, duplicate-member-free, and its raw bytes must equal JCS serialization of the parsed envelope.
- The signature array is detached from `P` and is not included in `D`.

Do not implement alternate domain strings, direct-payload signatures, hex-digest signatures or fallback verification modes.

## 4. Additional unresolved protocol details

These must be resolved against the exact pinned CometBFT v0.40.0 source and independent review:

1. Consensus public-key type identifier and canonical Base64 encoding.
2. Exact CometBFT consensus address derivation and whether the wire representation is uppercase or lowercase hex. Do not infer this from generic Tendermint conventions.
3. Whether the address is encoded as raw bytes or a textual hex field for sorting and hashing.
4. Exact CometBFT voting-power integer type and maximum total power.
5. Exact consensus-affecting CometBFT profile field allowlist and canonical profile serialization.
6. Initial profile sequence and bootstrap sentinel; recommendation is sequence 1 with null predecessor only for the genesis profile.
7. Activation-height semantics and required operator acknowledgement lead time.
8. Whether an expiry field is needed and what trusted clock/availability policy governs it.
9. Whether operator evidence references belong in the signed public profile or in a separate confidential operator registry.
10. Stable error-code registry and maximum byte/depth/validator/signature counts.

## 5. Golden-vector generation gate

No vector package should be generated until all of these are true:
- one consolidated normative schema has an exact field list and nested types;
- the signature digest and preimage formulas are frozen;
- the whole-envelope canonicalization rule is frozen;
- duplicate-key parsing and resource limits are specified;
- CometBFT v0.40.0 key/address/power semantics are confirmed from the pinned source;
- one JCS implementation is pinned for a disposable compatibility spike and cross-checked by an independent implementation;
- protocol owner explicitly approves the wire contract.

After that gate, generate deterministic synthetic test keys only, and include exact payload bytes, canonical envelope bytes, digest, signature message, public keys, signatures and expected results. Synthetic private seeds must never be accepted by production provisioning.

## 6. Implementation boundary

This reconciliation is documentation-only. It changes no source code, tests, dependencies, workflow, Genesis, keys, validator roster, deployment configuration or runtime behavior. It does not authorize production trust-root enrollment or validator startup.

**Status: CONFLICT IDENTIFIED — SPECIFICATION NOT FROZEN — NOT APPROVED FOR PRODUCTION.**
