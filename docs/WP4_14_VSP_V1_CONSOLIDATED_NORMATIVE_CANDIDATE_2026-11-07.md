# WP4.14 — VSP v1 Consolidated Normative Candidate

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Status:** Consolidated engineering candidate; NOT protocol-owner approved; NOT implemented  
**Supersedes for review:** conflicting VSP v1 draft fragments, but does not delete or rewrite historical design records  
**Change type:** Documentation only

## 1. Purpose and authority boundary

This document consolidates the current VSP design into one reviewable candidate contract. It resolves the known internal draft conflicts using the canonical schema, signature contract, strict-input review, and verified CometBFT v0.40.0 source findings.

It is **not** a protocol-owner approval, production trust-root enrollment, validator-roster approval, implementation authorization, or public-launch authorization. It must not be treated as frozen until the protocol owner explicitly approves the exact version and the unresolved policy decisions in §12 are closed.

## 2. Wire format

The complete VSP is one JSON envelope with exactly two top-level members:

- `payload`
- `signatures`

No other top-level member is allowed in v1. Duplicate members are rejected at every object depth before constructing ordinary dictionaries.

The entire input must:
1. be a bounded byte sequence;
2. decode as strict UTF-8 without BOM;
3. contain one JSON value and no trailing non-whitespace data;
4. contain no duplicate object member names, invalid Unicode scalar values, NaN, or Infinity;
5. validate against the exact schema below;
6. serialize byte-for-byte identically to RFC 8785 JCS serialization of the parsed complete envelope.

The signed payload bytes `P` are separately computed as JCS UTF-8 serialization of the parsed `payload` object. The signatures array is not part of `P` or the profile digest, but is part of the canonical envelope bytes.

No normalization or repair is allowed. Noncanonical input is rejected, not silently rewritten.

## 3. Exact payload schema v1

The payload has exactly these members:

| Field | Type and constraint |
|---|---|
| `schema` | exact ASCII string `hnd.validator-set-profile` |
| `schema_version` | integer exactly `1` |
| `chain_id` | non-empty ASCII identifier, bounded length; must equal independently provisioned network identity |
| `hnd_genesis_sha256` | exactly 64 lowercase hexadecimal characters |
| `cometbft` | exact object defined below |
| `profile_sequence` | positive integer; initial profile is 1 |
| `previous_profile_sha256` | null only for initial genesis profile; otherwise 64 lowercase hex digest |
| `activation` | exact object defined below |
| `validators` | non-empty array of exact validator objects |
| `total_voting_power` | positive integer equal to checked sum of validator powers and within CometBFT v0.40.0 maximum |
| `governance_policy` | exact object defined below; must match independent trust manifest |
| `change` | exact object defined below |

### 3.1 CometBFT identity object

Exact members:
- `version`: exact reviewed release string, initially `v0.40.0`;
- `source_commit`: exactly 40 lowercase hexadecimal characters;
- `binary_sha256`: exactly 64 lowercase hexadecimal characters.

The values must match an independently approved release manifest. A self-asserted binary hash inside the VSP is not proof of binary provenance. This object does not yet bind every consensus-affecting runtime configuration field; a separately reviewed profile digest/binding design remains required before production.

### 3.2 Activation object

Exact members:
- `kind`: `genesis` or `height`;
- `height`: unsigned integer.

Rules:
- Initial profile: sequence 1, predecessor null, kind `genesis`, height 0.
- Later profile: sequence exactly active sequence +1, predecessor exactly active digest, kind `height`, height strictly greater than the current committed height and satisfying an approved rollout lead-time policy.
- No skipped sequence, forked predecessor, reused activation height, rollback or retroactive activation.
- Expiry is **not** a v1 payload field in this candidate. Do not add it without an approved trusted-clock and offline-validation policy.

### 3.3 Validator object

Each validator has exactly:
- `consensus_key_type`: exact literal `ed25519`;
- `consensus_pubkey`: canonical RFC 4648 standard Base64 of exactly 32 raw bytes;
- `consensus_address`: exactly 40 lowercase hexadecimal characters representing 20 raw bytes;
- `voting_power`: positive integer no greater than the CometBFT v0.40.0 maximum;
- `operator_id`: unique ASCII identifier mapping to one accountable operator in a separately controlled operator register;
- `operator_attestation_ref`: non-empty controlled evidence reference; it is a pointer, not proof by itself.

Address derivation is fixed by CometBFT v0.40.0 Ed25519 source:

```text
consensus_address_raw = SHA-256(consensus_pubkey_raw)[0:20]
```

The decoded 20-byte derived value must equal the decoded VSP address. Each entry must also match exactly one CometBFT Genesis validator by decoded raw public key, decoded raw address and voting power.

Validator entries are sorted ascending by the 20 raw address bytes. Duplicate raw keys, addresses or operator IDs are rejected. Do not sort by locale-sensitive text rules.

Public profiles must not contain personal data. Operator references should be opaque controlled identifiers; the evidence register must remain access-controlled.

### 3.4 Governance policy object

Exact members:
- `policy_id`: exact ASCII identifier `hnd-vsp-2-of-3-v1`;
- `authorized_key_ids`: exactly three distinct key IDs, sorted bytewise ASCII ascending;
- `threshold`: integer exactly 2.

The independent trust manifest must contain exactly the same three key IDs and raw Ed25519 public keys with threshold 2. The payload cannot enroll, replace or override its own trust root.

For each governance public key, key ID is recomputed as:

```text
key_id = "gk1-" || lowercase_hex(
  SHA-256("HND-GOV-KEY-v1" || 0x00 || raw_ed25519_public_key)
)
```

Each raw governance public key is exactly 32 bytes. Governance keys are distinct from consensus, P2P, HND account, TLS, CI and release keys. Three keys must have genuinely separate custody and administrative domains.

### 3.5 Change object

Exact members:
- `type`: `initial`, `add`, `remove`, `power_change`, `key_rotation`, or `recovery`;
- `reason`: bounded descriptive Unicode string; not an authorization mechanism;
- `change_reference`: bounded ASCII change identifier.

The initial profile must use `initial`. Later types must accurately describe the complete before/after roster delta. A `recovery` type does not itself authorize trust-root recovery or bypass ordinary signatures.

## 4. Integer and voting-power rules

All JSON numeric fields are integer tokens only. Reject booleans, floats, exponent notation, strings, negatives, NaN and Infinity. The candidate general integer upper bound is `2^53-1` for cross-language JCS interoperability, but field-specific limits may be lower.

For CometBFT v0.40.0:

```text
MaxTotalVotingPower = floor((2^63 - 1) / 8)
                     = 1,152,921,504,606,846,975
```

Therefore:
- each active validator power is positive and no greater than this maximum;
- the sum is calculated with checked arithmetic;
- the total must not exceed this maximum;
- `total_voting_power` must exactly equal the recomputed sum;
- the VSP roster must exactly equal the CometBFT Genesis roster.

The 2^53−1 general JCS interoperability bound is stricter than CometBFT's voting-power maximum and therefore does not conflict for these fields. Keep all other fields within their own documented limits.

## 5. Canonicalization and cryptographic contract

Use a conforming RFC 8785 JCS implementation. Do not reuse HND's existing `canonical_json` helper as a JCS implementation.

Let `P` be the JCS UTF-8 bytes of the parsed payload:

```text
D = SHA-256(ASCII("HND-VSP-v1") || 0x00 || P)
M = ASCII("HND-VSP-AUTH-v1") || 0x00 || D
```

Each governance Ed25519 signature is over exactly `M`, not the JSON envelope, payload text, hexadecimal digest, or a different domain string.

Signature record exact members:
- `key_id`: one of the three independently enrolled IDs;
- `algorithm`: exact literal `ed25519`;
- `signature`: canonical Base64 of exactly 64 signature bytes.

The signatures array contains 2 or 3 records, ordered by ascending ASCII `key_id`. IDs must be distinct. At least two distinct enrolled keys must verify successfully. Unknown IDs, repeated IDs, unsupported algorithms, malformed/noncanonical Base64, wrong signature lengths and invalid signatures are hard failures.

No fallback signature formula is permitted.

## 6. Verification sequence

A pure verifier should accept bounded bytes and independently supplied expected context/trust material, then return a typed verified result or a stable error. It must not start services, access the network, mutate rollback state or load private keys.

Required order:
1. Bound input length and decode strict UTF-8; reject BOM.
2. Parse JSON with duplicate-key detection at every depth; reject nonstandard constants and trailing data.
3. Enforce exact top-level and nested field sets, types, identifier grammars and resource limits.
4. Serialize the entire parsed envelope using JCS; require exact byte equality with input.
5. Independently serialize payload using JCS to obtain `P`.
6. Verify chain ID and HND Genesis digest against provisioned local expected context.
7. Verify CometBFT release identity against an independent approved release manifest.
8. Recompute profile digest `D` and signature message `M`.
9. Verify at least two distinct governance signatures against the separately provisioned trust manifest.
10. Enforce sequence, predecessor and activation rules against the current active-profile record.
11. Decode each consensus key, derive address from CometBFT v0.40.0 rules, check canonical address and uniqueness.
12. Validate validator powers with checked arithmetic and enforce the upstream maximum.
13. Compare the complete VSP validator set with the independently parsed CometBFT Genesis set.
14. Return the same deterministic digest, sequence, activation height, roster and total to every conforming node.

Durable anti-rollback, signer fencing, activation writes and service-start enforcement are separate stateful/runtime components and are not supplied by this pure verifier.

## 7. Required test corpus

All tests below are proposed and unexecuted:

- **Wire/parser:** duplicate top-level and nested keys; BOM; invalid UTF-8; unpaired surrogate; trailing data; noncanonical whitespace; key ordering; string escaping; excessive size/depth; unknown/missing fields.
- **Numbers:** bool/float/exponent/string/negative; 2^53−1 boundary; values above general limit; voting power at upstream max; total at max; overflow and mismatch.
- **JCS:** RFC 8785 Appendix B; UTF-16 ordering edge cases; independent Python and JavaScript canonicalizers produce identical bytes and digest.
- **Governance:** 0/1/2/3 valid signatures; duplicate signer; unknown key; key ID recomputation mismatch; wrong chain/Genesis/sequence/activation replay; wrong domain prefix; altered payload; malformed Base64.
- **Consensus identity:** 31/32/33-byte public key; derived address match/mismatch; uppercase or malformed address; duplicate key/address; unsorted roster.
- **Genesis binding:** missing, extra, substituted or power-altered validator; same count but different roster; wrong CometBFT Genesis.
- **Sequence/activation:** wrong initial tuple; skipped sequence; stale predecessor; fork; reused or past activation height.
- **Stateful follow-up:** crash-consistent activation; old database restore; signer fencing; direct CometBFT launch bypass; service start with invalid or stale profile.

Do not mark any proposed test as passed until it is implemented and executed on a recorded commit.

## 8. Dependency decision

The `rfc8785` Python package v0.1.4 is only a candidate for a disposable compatibility spike. It is not an approved production dependency. Before adoption, pin package and artifact hashes, verify provenance and license, run RFC vectors, and compare results against an independently pinned JavaScript implementation. Duplicate-key detection must be implemented separately.

No dependency should be added by this documentation change.

## 9. Explicitly out of scope

This candidate does not:
- choose real validator operators, power allocations or production keys;
- prove operator independence or decentralization;
- provision governance trust roots or recover lost keys;
- implement anti-rollback, signer anti-double-sign, or crash-safe profile activation;
- bind all runtime CometBFT configuration fields to a complete approved profile digest;
- create or modify HND or CometBFT Genesis;
- implement VSP parsing, signature verification, startup gates or deployment;
- authorize public launch, production signing, token issuance or exchange listing.

## 10. Reconciliation record

This candidate selects:
- the nested payload schema and sequence/activation semantics from the canonical schema specification;
- the `HND-VSP-v1` digest and `HND-VSP-AUTH-v1` Ed25519 message from the golden-vector contract;
- whole-envelope JCS byte equality from the strict-input review;
- Ed25519 key/address derivation and voting-power ceiling from the CometBFT v0.40.0 source findings.

It rejects the conflicting flat-field schema, alternate direct-payload signature formula, sequence-zero bootstrap variant, and unapproved mandatory expiry field. Historical documents remain in the repository as design records; this consolidated candidate is the sole proposed review baseline until explicit approval.

## 11. Required approval and remaining policy gates

Before this candidate can become normative:
1. Protocol owner approves the exact field set and canonicalization/signature formulas.
2. CometBFT profile binding is expanded to cover every consensus-affecting runtime configuration input and a reproducible binary/source provenance record.
3. Operator attestation data model and privacy controls are approved.
4. Activation lead-time and operator acknowledgement policy are specified.
5. Governance trust-manifest bootstrap, key custody and catastrophic recovery are approved.
6. Resource limits are numerically specified.
7. A JCS library compatibility spike passes independent cross-language vectors.
8. Independent security review approves the final contract and implementation plan.

**Final disposition: CONSOLIDATED CANDIDATE — NOT FROZEN — NOT IMPLEMENTED — NOT APPROVED FOR PRODUCTION.**
