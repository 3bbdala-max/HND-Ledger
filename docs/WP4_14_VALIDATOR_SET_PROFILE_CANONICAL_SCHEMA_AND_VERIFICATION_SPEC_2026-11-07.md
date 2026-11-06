# WP4.14 — Validator Set Profile (VSP) Canonical Schema and Verification Specification

**Date:** 2026-11-07  
**Branch:** phase-0.2-planning  
**Status:** Design specification; not implemented  
**Authority:** Applies the delegated v0.2 decision selecting operator-managed validator membership and 2-of-3 governance authorization.  
**Change boundary:** Documentation only. No source code, tests, workflows, Genesis, keys, deployment files, or runtime behavior changed.

## 1. Purpose and scope

Define one deterministic, signed package describing the complete CometBFT validator set for a specific HND network and activation point. Every operator must validate the same package and derive the same digest, validator addresses, total voting power, and activation decision.

This specification does not implement on-chain governance, staking, slashing, rewards, or automatic validator admission. It does not select a production validator roster or production voting-power distribution.

## 2. Normative design decisions

1. The VSP is a complete snapshot of the validator set, never a partial add/remove patch.
2. The canonical representation is JSON Canonicalization Scheme (JCS, RFC 8785) encoded as UTF-8. Duplicate JSON object keys are rejected before canonicalization.
3. Hash algorithm: SHA-256 over the canonical VSP payload excluding the detached signatures container. The digest is domain-separated with the literal ASCII prefix HND-VSP-v1 followed by a zero byte.
4. Governance signatures use Ed25519 and sign the 32-byte digest, with a second domain-separation prefix HND-VSP-AUTH-v1 followed by a zero byte.
5. Exactly three governance public keys are enrolled for this policy; at least two distinct valid signatures are required. The signer identities must be distinct enrolled governance key IDs.
6. Consensus public keys are distinct from governance keys, HND account keys, P2P node keys, and TLS keys.
7. Validator entries are sorted lexicographically by lowercase hexadecimal consensus address before hashing. Duplicate keys or addresses are rejected.
8. All integer values are unsigned decimal JSON integers within the supported implementation range; strings, floats, exponent notation, negative values, and booleans are rejected for integer fields.
9. Unknown fields are rejected in schema version 1. A future extension requires a new schema version, not silent interpretation.
10. No private key, seed, mnemonic, password, token, or secret material is permitted in a VSP.

## 3. Proposed package shape

The package is an envelope containing a payload and detached signatures. The payload is the only object hashed and signed.

~~~json
{
  "payload": {
    "schema": "hnd.validator-set-profile",
    "schema_version": 1,
    "chain_id": "hnd-<network-identifier>",
    "hnd_genesis_sha256": "<64 lowercase hex characters>",
    "cometbft": {
      "version": "v0.40.0",
      "source_commit": "<40 lowercase hex characters>",
      "binary_sha256": "<64 lowercase hex characters>"
    },
    "profile_sequence": 1,
    "previous_profile_sha256": null,
    "activation": {
      "kind": "genesis",
      "height": 0
    },
    "validators": [
      {
        "consensus_key_type": "ed25519",
        "consensus_pubkey": "<base64 public key bytes>",
        "consensus_address": "<lowercase hex address>",
        "voting_power": 10,
        "operator_id": "operator-001",
        "operator_attestation_ref": "evidence://<controlled-reference>"
      }
    ],
    "total_voting_power": 40,
    "governance_policy": {
      "policy_id": "hnd-vsp-2-of-3-v1",
      "authorized_key_ids": [
        "governance-key-1",
        "governance-key-2",
        "governance-key-3"
      ],
      "threshold": 2
    },
    "change": {
      "type": "initial",
      "reason": "Initial network validator profile",
      "change_reference": "HND-VSP-INIT-001"
    }
  },
  "signatures": [
    {
      "key_id": "governance-key-1",
      "algorithm": "ed25519",
      "signature": "<base64 signature over domain-separated digest>"
    },
    {
      "key_id": "governance-key-2",
      "algorithm": "ed25519",
      "signature": "<base64 signature over domain-separated digest>"
    }
  ]
}
~~~

The values above are illustrative schema examples only. They are not a production chain ID, Genesis hash, binary digest, validator roster, operator attestation, or approved voting-power allocation. The sample 10/40 values mirror only the existing disposable equal-power test fixture.

## 4. Field requirements

### Network and software binding
- schema and schema_version identify the exact parser contract.
- chain_id must exactly match the running network identity.
- hnd_genesis_sha256 binds the profile to the independently approved HND Genesis artifact.
- CometBFT version, source commit, and binary digest bind the profile to the reviewed consensus implementation. Release engineering must independently verify source-to-binary provenance; a self-asserted digest alone is not proof.

### Sequence and activation
- Initial profile: sequence 1, previous digest null, activation kind genesis and height 0.
- Every later profile: sequence exactly previous sequence + 1, previous digest exactly the currently active profile digest, activation kind height, and a positive agreed activation height.
- Sequence rollback, skipped sequence, forked predecessor, reused activation, or chain mismatch is a hard rejection.
- The activation height must be sufficiently far in the future for all operators to verify and acknowledge the identical digest. The exact safety lead time remains a deployment parameter and must be specified before production.
- A profile cannot retroactively alter the validator set for already committed heights.

### Validator entries
- consensus_key_type must be explicitly supported by the pinned CometBFT release.
- consensus_pubkey must decode canonically and have the exact key length required by that key type.
- consensus_address must be recomputed from the decoded public key using the exact CometBFT address derivation and compared byte-for-byte.
- voting_power must be positive and fit the exact integer type and total-power limits of the pinned CometBFT release.
- operator_id must be unique and map to one accountable operating entity in the private operator register. Public profiles should not expose personal data.
- operator_attestation_ref is an evidence pointer, not proof by itself. The referenced evidence must establish control, administrative independence, hosting/account separation, and incident/recovery contacts.

### Governance signatures
- The governance policy must match the enrolled trust root delivered out-of-band for this chain.
- At least two different enrolled key IDs must sign the same canonical payload digest.
- Duplicate signatures, unknown key IDs, unsupported algorithms, malformed base64, invalid signatures, and signatures over any different digest are rejected.
- Governance keys must be held in separate administrative custody domains. Three keys controlled by one administrator do not constitute independent authorization.
- Governance-key enrollment and replacement require a separately witnessed trust-root ceremony. This VSP cannot authorize a unilateral replacement of its own trust root.

## 5. Deterministic verification algorithm

A conforming verifier must perform these steps in order and fail closed:

1. Parse strict UTF-8 JSON; reject duplicate keys, invalid Unicode, trailing data, and non-JSON extensions.
2. Validate exact schema version and reject unknown or missing required fields.
3. Validate canonical encodings, lowercase hexadecimal lengths, base64 canonical form, and integer syntax/ranges.
4. Confirm chain ID and HND Genesis digest against independently provisioned local trust anchors.
5. Confirm CometBFT version, source commit, and binary digest against the approved release manifest.
6. Canonicalize the payload using RFC 8785 and calculate the domain-separated SHA-256 profile digest.
7. Verify the 2-of-3 detached Ed25519 governance signatures against the independently provisioned governance trust root.
8. Verify profile sequence and predecessor against durable active-profile state; reject rollback, replay, or forks.
9. Validate activation semantics and ensure the node is not applying the profile at an incorrect height.
10. Validate every consensus public key, derive each address using the pinned CometBFT implementation, and reject duplicates.
11. Sum voting powers using checked arithmetic; require exact equality with total_voting_power and enforce the pinned CometBFT total-power ceiling.
12. Produce a deterministic validation result containing profile digest, sequence, activation height, validator count, and total voting power.
13. Persist the accepted profile digest and sequence atomically with the corresponding activation record before enabling signing under the new set.
14. If any check or durable write fails, do not start or continue signing with an ambiguous validator set.

The verifier must not rely solely on a local editable TOML file, an unsigned Genesis copy, a Git branch name, or a profile distributed by the same untrusted channel as the software binary.

## 6. Voting-power and concentration analysis

Consensus safety is weighted by voting power, not validator count. For total power P:
- a coalition controls the sum of the voting power of every validator it can direct;
- the standard CometBFT BFT safety assumption requires Byzantine voting power strictly below P/3;
- a commit requires more than 2P/3 precommit power;
- exactly one third is not below one third.

The release report must calculate coalition exposure for at least:
- each individual operator;
- each common owner or controlling entity;
- shared cloud account, region, network, signer, administrator, and recovery provider;
- every plausible coalition of operators sharing a failure or control domain.

No production per-validator cap, minimum operator count, or maximum concentration percentage is selected here. These require a threat model and verified operator/infrastructure evidence. A signature threshold does not replace this analysis.

## 7. Durable state and anti-rollback requirements

The active profile digest, sequence, activation height, and predecessor digest must be stored in durable state protected against ordinary local rollback. The storage design must bind this record to the HND/CometBFT recovery checkpoint and signer anti-double-sign state.

A restored backup with a valid internal checksum but an older profile sequence must be rejected unless an independently authenticated recovery procedure proves that the chain has not advanced beyond that checkpoint. Recovery must never reset consensus signing history.

The detailed storage mechanism, trust-anchor protection, and crash-atomic write protocol remain design gates for a later implementation specification.

## 8. Validator change lifecycle

For add, remove, power change, or consensus-key rotation:
1. Create a full replacement profile with sequence +1 and the exact active predecessor digest.
2. Produce before/after roster and weighted concentration analysis.
3. Obtain two valid governance signatures.
4. Distribute the exact package and verify identical digest at every operator.
5. Collect operator readiness acknowledgements against that digest.
6. Confirm the target activation height and the required rollout lead time.
7. Activate deterministically at the agreed height.
8. Fence removed/rotated signers and preserve their durable anti-double-sign records.
9. Record the resulting digest and height in independently retained audit records.

If any operator reports a different profile digest, halt the change; do not improvise a partial rollout. Recovery requires a newly authorized higher-sequence profile or a separately documented chain-recovery decision.

## 9. Acceptance tests required before implementation approval

These are proposed tests, not tests executed by this document:

- valid initial 2-of-3 profile accepted;
- 1-of-3, duplicate signer, unknown signer, malformed signature and wrong-key signatures rejected;
- signature replay across chain IDs, Genesis hashes, sequences and activation heights rejected;
- duplicate JSON keys, unknown fields, malformed UTF-8 and noncanonical encodings rejected;
- wrong Genesis hash, chain ID, CometBFT source commit or binary digest rejected;
- unsupported key type, malformed key, wrong address derivation and duplicate consensus key/address rejected;
- zero, negative, floating-point, string, overflow and inconsistent total voting power rejected;
- exact one-third and greater-than-two-thirds coalition calculations reported correctly;
- stale sequence, skipped sequence, wrong predecessor and profile rollback rejected;
- activation at wrong height and partial operator rollout fail closed;
- crash during durable profile activation cannot produce a profile/state mismatch;
- restore of an older but internally valid database cannot enable stale signing;
- key rotation fences the old signer and prevents simultaneous old/new signer use;
- all independent nodes derive byte-identical canonical digest and validator set.

## 10. Implementation gates and disposition

Before implementation begins, the project must:
- verify RFC 8785 library availability and cross-language test vectors;
- inspect the pinned CometBFT v0.40.0 source to confirm key encodings, address derivation, voting-power integer bounds, and total-power ceiling;
- define the independently provisioned governance trust root and witnessed replacement ceremony;
- define operator evidence and production concentration policy;
- define durable profile activation and signer-fencing integration;
- write the acceptance tests above and review them independently.

**Disposition: DESIGN SPECIFICATION ONLY — NOT IMPLEMENTED.** No production validator profile exists. No production keys or roster have been approved. Public launch and production signing remain **NOT APPROVED**.

---
This document is an engineering design artifact, not a security certification, legal opinion, decentralization proof, or launch authorization.
