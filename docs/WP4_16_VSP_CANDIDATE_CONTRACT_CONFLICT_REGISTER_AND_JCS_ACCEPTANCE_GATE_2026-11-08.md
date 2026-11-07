# WP4.16 — VSP Candidate Contract Conflict Register and JCS Acceptance Gate

**Inspection date:** 2026-11-08  
**Branch:** `phase-0.2-planning`  
**Inspected commit:** `0a06bdc58aa55c2459cf6accd64a0459ff1d8f4f`  
**Change type:** Documentation only  
**Disposition:** VSP contract remains unratified; implementation must not begin against either conflicting candidate.

## 1. Exact-commit CI status

Workflow run `42420546073` targets the inspected commit `0a06bdc58aa55c2459cf6accd64a0459ff1d8f4f`.

At inspection:

- `hnd-v02-tests`: completed successfully. The isolated JCS cross-language compatibility spike and v0.2 test suite steps passed.
- `cometbft-single-node-smoke`: still in progress. The four-validator private-network smoke step was running; subsequent external-signer and authenticated Noise integration steps were pending.

Therefore the overall run is **not yet a completed success**. Passing the first job must not be reported as a successful full workflow.

Run link: https://github.com/3bbdala-max/HND-Ledger/actions/runs/42420546073

## 2. Critical discovery: two VSP v1 candidate contracts are incompatible

Static comparison of these two existing documents reveals material normative conflicts:

- `docs/WP4_14_VSP_V1_CANONICALIZATION_SIGNATURE_AND_GOLDEN_VECTOR_CONTRACT_2026-11-07.md`
- `docs/WP4_14_VSP_V1_SCHEMA_CANONICALIZATION_AND_CRYPTOGRAPHIC_TEST_VECTOR_DESIGN_2026-11-07.md`

Both are marked proposed/not approved, but they must not be treated as interchangeable or combined informally.

### 2.1 Payload field-set conflict

The canonicalization/signature contract proposes an exact payload with fields:

`schema`, `schema_version`, `chain_id`, `hnd_genesis_sha256`, `cometbft`, `profile_sequence`, `previous_profile_sha256`, `activation`, `validators`, `total_voting_power`, `governance_policy`, `change`.

The schema/test-vector design instead describes a different model including:

`hnd_network_id`, `hnd_protocol_version`, `hnd_genesis_manifest_sha256`, `cometbft_genesis_sha256`, `cometbft_profile_sha256`, `cometbft_source_commit`, `cometbft_binary_sha256`, `sequence`, `previous_vsp_sha256`, `activation_height`, `expires_at_unix`, and `validators`.

These are not merely alternate labels. They differ in identity binding, software identity, activation semantics, predecessor naming, and governance/policy representation. A verifier cannot accept both as one exact schema v1 without creating an ambiguous protocol.

### 2.2 Digest and signature preimage conflict

The canonicalization/signature contract proposes:

- `D = SHA-256("HND-VSP-v1" || 0x00 || JCS(payload))`
- `M = "HND-VSP-AUTH-v1" || 0x00 || D`
- Ed25519 signs the domain-separated digest message `M`.

The schema/test-vector design describes a different candidate:

- payload digest as `SHA-256(canonical_vsp_payload_bytes)`
- signature message as `UTF8("HND-LEDGER/VSP-SIGNATURE/V1") || 0x00 || canonical_vsp_payload_bytes`.

These produce different digest and signature bytes for the same payload. A signature generated under one proposal must not be expected to verify under the other. No implementation should guess which formula is intended.

### 2.3 Envelope and canonicality boundary

The first contract explicitly models an envelope with exact top-level keys `payload` and `signatures`, signs only the payload, and requires the raw payload byte slice to equal JCS output.

The second document also describes detached signatures and exact canonical payload bytes, but its schema and signing preimage differ. Before implementation, the project must specify the byte-level extraction rule: how the verifier obtains the exact original payload byte slice from the received envelope without parsing and reserializing it first. Canonicalizing a parsed nested object alone does not prove the original transmitted payload bytes were canonical.

## 3. Decision: freeze neither candidate yet

Until the protocol owner resolves the conflicts in a single authoritative decision record:

1. Both documents remain historical candidate proposals only.
2. No VSP production parser or verifier should be implemented.
3. No golden digest or signature should be generated and labelled authoritative.
4. No trust manifest or governance key should be provisioned.
5. No node pre-start authorization should depend on either proposal.
6. HND transaction and Genesis serialization must remain untouched.

This is a safety hold, not a failure of the existing HND test suite.

## 4. Required protocol-owner decisions

A single ratification record must answer all of the following before test vectors become normative:

| Decision | Required unambiguous outcome |
|---|---|
| Schema | One exact v1 field set, types, required/optional fields, and unknown-field policy |
| Network identity | Exact chain ID, HND network ID, Genesis and manifest digest bindings |
| CometBFT identity | Exact source commit, binary digest, Genesis digest and consensus-profile fields |
| Sequence | One field name, integer range, bootstrap value and strict monotonicity rule |
| Predecessor | One field name and exact bootstrap/null semantics |
| Activation | Exact height semantics, expiry policy and trusted clock assumptions |
| Digest | One exact byte formula including domain-separation label and NUL placement |
| Signature | One exact Ed25519 message preimage and encoding |
| Envelope | Exact envelope keys and byte-slice extraction procedure |
| Trust root | Exact manifest schema, 3-key/2-of-3 policy and witnessed bootstrap reference |
| Ordering | Exact byte-level ordering and uniqueness rules for validators and signatures |
| Errors | Stable rejection-code registry and fail-closed behavior |

The ratification record must include a machine-reviewable field map from the chosen schema to the exact CometBFT v0.40.0 configuration/Genesis fields.

## 5. JCS evidence: what passed and what remains unproven

The isolated compatibility spike currently contains five test methods and cross-checks five representative JSON samples between Python `rfc8785==0.1.4` and JavaScript `canonicalize@2.1.0`. The exact-commit CI step passed.

The tests cover representative property ordering, number serialization, UTF-16 property ordering, duplicate-member rejection in the Python parser helper, invalid UTF-8/BOM/non-standard constants/surrogates, and cross-language equality for the five samples.

This is a useful initial compatibility check, not full RFC 8785 conformance. Remaining work includes:

- the complete RFC 8785 Appendix B number serialization corpus;
- additional string escaping and Unicode edge vectors;
- parser-level duplicate-member rejection in every implementation that consumes the envelope;
- strict lexical integer-token validation before ordinary numeric conversion (including rejection of `1.0`, `1e0`, and booleans for integer fields);
- exact raw payload byte-slice extraction and canonical-byte equality;
- independent third-party review of expected canonical bytes.

The current JavaScript cross-check uses `JSON.parse`; therefore it does not independently demonstrate duplicate-member rejection. The Python helper's duplicate-key tests do not close that cross-language parser gap.

## 6. Golden-vector production sequence after ratification

Only after the single schema and signing formula are ratified:

1. Freeze a minimal synthetic payload and deterministic public test fixture seeds.
2. Generate canonical payload bytes and payload digest with implementation A.
3. Independently generate the same bytes and digest with implementation B.
4. Generate the exact signature preimage from the ratified formula.
5. Sign using deterministic test-only Ed25519 keys; verify with a second independent crypto implementation.
6. Record raw bytes, byte lengths, hex digests, public keys, key IDs, signatures and stable negative-test outcomes.
7. Add the vectors to tests only through a separately reviewed code change and require exact-commit CI.
8. Keep test keys permanently disjoint from any production governance or validator key material.

No expected digest or signature is fabricated in this report.

## 7. Scope and release boundary

This report adds documentation only. It changes no source, tests, workflow, dependency, Genesis, key, validator configuration or runtime behavior. It does not trigger a CI rerun.

**Decision:** VSP v1 remains NOT APPROVED. Resolve the candidate-contract conflict before implementation. The successful JCS spike is limited evidence for five representative cross-language samples and does not establish full RFC 8785 conformance or production VSP verification.
