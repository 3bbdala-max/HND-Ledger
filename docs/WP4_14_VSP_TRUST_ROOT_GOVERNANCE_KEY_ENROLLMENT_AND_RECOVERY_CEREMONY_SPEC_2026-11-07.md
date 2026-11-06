# WP4.14 — VSP Trust Root, Governance-Key Enrollment and Recovery Ceremony

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Status:** Architecture specification; documentation-only  
**Decision:** Define a witnessed, out-of-band bootstrap and 2-of-3 governance authorization process for HND v0.2. No real keys are generated or enrolled by this document.  
**Production disposition:** NOT APPROVED for production governance, validator onboarding, production signing or public launch.

## 1. Purpose and boundary

The VSP decision selects operator-managed validator membership with a canonical signed Validator Set Profile and a 2-of-3 governance authorization threshold. This document specifies how the initial three governance public keys become trusted, how routine VSP changes are authorized, and how governance keys are rotated or recovered.

This is a design specification only. It does not generate keys, identify custodians, select a hardware vendor, create credentials, provision HSM/KMS resources, alter Genesis, implement a verifier, or authorize a production ceremony. No private key, seed phrase, recovery code, HSM credential or secret may be sent to ChatGPT, committed to Git, placed in CI, or written into ordinary project documentation.

## 2. Trust model and separation of duties

Three governance signing identities (G1, G2, G3) authorize VSP changes. The threshold is two valid signatures over the exact canonical VSP digest and its network context.

Mandatory separation:
- G1, G2 and G3 must have three distinct human custodians and independently administered custody domains.
- A custodian must not control another custodian's device, recovery factors, cloud account, HSM administration or authentication session.
- Governance keys must be distinct from validator consensus keys, P2P node keys, HND account keys, CI credentials, release-signing keys and backup-encryption keys.
- The routine validator operator must not be able to unilaterally enroll or replace governance keys.
- A 2-of-3 threshold tolerates one unavailable custodian for ordinary approvals; it does not tolerate compromise of two governance keys.
- Three keys on one machine, three accounts controlled by one administrator, or three signatures obtained through one shared approval channel do not constitute independent governance.

The independence of custodians and custody domains is an evidence requirement, not an assumption inferred from key count.

## 3. Initial trust-root bootstrap

The initial trust root cannot authenticate itself. Therefore its first enrollment must use a separately witnessed, out-of-band ceremony rather than a signature from a not-yet-trusted governance key.

Required sequence:
1. The protocol owner approves the exact network identity: chain ID, HND Genesis manifest digest, CometBFT Genesis digest, approved CometBFT version/source identity, initial VSP schema version and initial sequence.
2. Three custodians are selected and their independence/conflict-of-interest checks are recorded. Each custodian's identity is verified through an agreed in-person or independently authenticated channel.
3. Each custodian generates their governance key inside their own approved offline signing device or HSM boundary. Private key material never leaves that boundary.
4. Each custodian exports only the public key, algorithm identifier, key fingerprint and proof-of-possession signature over a unique ceremony challenge containing the chain ID, Genesis digests, ceremony nonce and role.
5. Two independent witnesses verify the public-key fingerprints directly with the custodians using an out-of-band comparison channel. They must not rely solely on a file, QR code or message supplied by one coordinator.
6. The complete initial trust manifest is assembled in canonical form. It includes the three public keys, threshold 2, network identity, sequence 0, ceremony timestamp, nonce, algorithm allowlist, custodian role identifiers and witness attestations. It contains no secret material.
7. The protocol owner and witnesses approve the exact manifest digest. The approval record and public manifest are distributed through at least two independently administered publication channels.
8. Every initial validator operator independently obtains the manifest from both channels, compares the digest, validates all proof-of-possession signatures and records an acknowledgement of the exact digest.
9. A node must fail closed if the trust manifest, network identity, digest, threshold, algorithm or witness evidence differs or is missing.

The initial trust manifest digest must be pinned in the separately controlled deployment/release record. A Git commit alone is not the trust root.

## 4. Routine VSP authorization

For each validator addition, removal, voting-power change, consensus-key rotation or activation change:
- Prepare a complete canonical VSP, not a partial patch.
- Bind chain ID, HND Genesis digest, CometBFT Genesis/profile identity, schema version, monotonic sequence, predecessor digest, activation height and expiry.
- Obtain two signatures from two distinct enrolled governance keys.
- Verify signatures over the exact canonical digest; reject duplicate signer identities, unknown keys, unsupported algorithms, expired packages and signatures for another network or sequence.
- Recompute validator addresses, uniqueness, voting-power total and weighted coalition analysis.
- Publish the exact package and digest over the independent distribution channels.
- Require all operators to acknowledge the same digest before the agreed activation height.
- Record activation height and digest in independently retained audit records.

A valid 2-of-3 signature does not by itself establish that a proposed voting-power distribution is safe or decentralized. Concentration review remains a separate approval gate.

## 5. Governance-key rotation

Rotation is a trust-root transition, not a file-copy operation.

For planned rotation:
1. Create a new candidate public key in the replacement custodian's independently controlled signing boundary.
2. Verify proof of possession and custody separation.
3. Create a trust-manifest transition that identifies the old manifest digest, new manifest digest, effective sequence, activation time/height, reason and affected key identifiers.
4. Require two currently authorized governance signatures for the transition. A retiring key may participate; the transition must still leave three distinct enrolled keys after activation.
5. Obtain independent witness attestations and distribute the exact transition package through both publication channels.
6. Require operator acknowledgement and verify that all nodes agree on the next trust-manifest digest.
7. Activate the new trust manifest atomically. Reject old-sequence signatures and replayed transition packages.
8. Revoke, disable or securely retire the old key only after the transition is confirmed. Retain public audit evidence, never private key material.

A lost or suspected compromised key is immediately marked unavailable for new approvals through the incident procedure. If two uncompromised authorized keys remain, they may authorize a replacement transition. If fewer than two trustworthy keys remain, routine governance stops.

## 6. Emergency recovery and catastrophic trust-root loss

There is deliberately no unilateral emergency bypass in v0.2.

- If one key is lost, the remaining two may authorize a replacement, subject to proof of possession, independent witnessing and the normal transition checks.
- If one key is suspected compromised, stop accepting new packages signed by it while preserving evidence; two other uncompromised keys authorize the transition.
- If two keys are lost or compromised, the 2-of-3 trust root is no longer safe for routine recovery. Do not accept a self-declared replacement key, a GitHub commit, a validator majority, or a single operator's instruction as sufficient authority.
- Catastrophic recovery requires a separately pre-approved protocol-owner recovery process established before production. That process must specify independent identity verification, legal/organizational authority, witness quorum, publication channels, delay/notification period, validator halt conditions and a new trust-root pinning ceremony.
- Until that recovery process has been independently approved and implemented, the safe action is to halt governance changes and, if signing safety cannot be assured, halt the affected network rather than invent an emergency key.

The catastrophic recovery authority and threshold are intentionally unresolved here; inventing them without knowing the real custodians, legal control and operational environment would create false assurance. This is a blocking production gate.

## 7. Anti-replay, rollback and signer interaction

Every trust manifest and VSP must use a monotonically increasing sequence and predecessor digest. Nodes must reject:
- lower or repeated sequence numbers;
- wrong predecessor digest;
- wrong chain ID or Genesis digest;
- wrong activation height or expired package;
- duplicate, unknown or insufficient governance signers;
- non-canonical serialization or unsupported signature algorithms;
- a trust-manifest rollback after a newer manifest has activated.

Trust-root validity does not replace validator signer anti-double-sign controls. Consensus signing remains blocked until the signer has verified the active network identity, validator identity, current VSP digest and durable monotonic H/R/S state. A VSP transition must not reset or roll back anti-double-sign state.

## 8. Required evidence package

Before production approval, retain and independently verify:
- custodian identity and role attestations, with unnecessary personal data minimized;
- documented proof that custody/admin domains are independent;
- hardware/device model, firmware and security configuration evidence where applicable;
- public-key fingerprints and proof-of-possession results;
- witnessed initial ceremony record and exact trust-manifest digest;
- two independent publication-channel records and validator acknowledgements;
- successful planned-rotation drill;
- one-key-loss drill and one-key-compromise drill;
- catastrophic two-key-loss tabletop exercise and approved recovery authority;
- replay, rollback, wrong-network, duplicate-signature and malformed-package rejection tests;
- evidence that secrets never enter Git, CI logs, ordinary application logs or ChatGPT;
- independent security review of the ceremony and implementation.

Evidence must redact personal identifiers and all secret material while preserving verifiable public fingerprints, timestamps, approvals and digests.

## 9. Acceptance tests — proposed, not executed

| ID | Scenario | Required result |
|---|---|---|
| ROOT-T01 | Initial trust manifest lacks witness approval | Reject bootstrap |
| ROOT-T02 | One governance key attempts initial self-enrollment | Reject |
| ROOT-T03 | Duplicate public keys under different labels | Reject |
| ROOT-T04 | Proof-of-possession challenge is wrong | Reject |
| ROOT-T05 | Manifest chain ID differs from node | Fail closed |
| ROOT-T06 | HND Genesis digest differs | Fail closed |
| ROOT-T07 | CometBFT Genesis/profile digest differs | Fail closed |
| ROOT-T08 | Only one valid governance signature | Reject VSP |
| ROOT-T09 | Two signatures from the same key | Count as one; reject |
| ROOT-T10 | Two distinct enrolled signatures over exact digest | Accept authorization if all other policy checks pass |
| ROOT-T11 | Signature from unknown/retired key | Reject |
| ROOT-T12 | Signature replayed on another chain | Reject |
| ROOT-T13 | Old sequence or predecessor digest | Reject rollback |
| ROOT-T14 | Non-canonical serialization | Reject |
| ROOT-T15 | Unsupported algorithm or weak key parameters | Reject |
| ROOT-T16 | One custodian unavailable | Remaining two may authorize routine transition |
| ROOT-T17 | One key lost | Replacement transition requires remaining two |
| ROOT-T18 | One key suspected compromised | Compromised key excluded; remaining two authorize transition |
| ROOT-T19 | Two keys unavailable | Stop; no unilateral bypass |
| ROOT-T20 | Planned rotation with operator digest mismatch | Do not activate |
| ROOT-T21 | Old key signs after retirement | Reject |
| ROOT-T22 | Trust-root transition attempts to reset signer H/R/S | Reject |
| ROOT-T23 | Secret appears in repository or CI output | Fail security gate and rotate affected material |
| ROOT-T24 | Two distribution channels publish different digests | Halt rollout |
| ROOT-T25 | Independent recovery drill | Complete only with witnessed evidence and no secret disclosure |

These are acceptance criteria, not evidence of implemented behavior or executed tests.

## 10. Decision and release gate

**Selected v0.2 design:** three independently administered governance signing identities, 2-of-3 authorization for routine VSP changes, witnessed out-of-band initial trust-root enrollment, monotonic trust-manifest transitions, and no unilateral emergency bypass.

**Unresolved blocker:** the catastrophic recovery authority and quorum must be approved and rehearsed with real, independent custodians before production. The 2-of-3 rule is not a substitute for that plan.

**Status: NOT APPROVED** for production trust-root enrollment, validator onboarding, production signing, token issuance or public launch. No production keys were generated. No source, tests, workflows, Genesis, deployment files or runtime behavior were changed.

---
This document is an engineering specification, not a security certification, legal opinion or launch authorization.
