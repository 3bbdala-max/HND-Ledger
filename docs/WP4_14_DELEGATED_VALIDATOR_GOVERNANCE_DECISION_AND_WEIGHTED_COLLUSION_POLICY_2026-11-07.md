# WP4.14 — Delegated Validator Governance Decision and Weighted-Collusion Policy

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Decision authority:** User delegated project-level engineering decisions to the assistant for this continuation.  
**Review type:** Documentation-only architecture decision based on repository source and the preceding validator audits.  
**Decision:** Select **Option A — operator-managed validator membership** for HND v0.2. Do not implement on-chain validator governance in this release.  
**Change boundary:** This report only. No source, tests, workflows, validator keys, Genesis files, deployment configuration or runtime behavior changed.

## 1. Executive decision

The least risky and most proportionate v0.2 path is an **externally governed, signed validator-set profile**, not a new on-chain governance/staking subsystem.

This decision is based on the inspected implementation:
- HND's account Genesis manifest does not define CometBFT validator identities or voting power.
- `InitChain` does not authenticate the CometBFT validator list.
- `FinalizeBlock` does not emit validator-set or consensus-parameter updates.
- No HND validator registry, staking state machine, governance voting, timelock, slashing or validator-removal lifecycle is implemented.
- The current four-validator fixture assigns equal test power 10 to disposable identities. It is not a production roster or policy.
- Production signer fencing, durable anti-double-sign anchoring, independent operators and deployment fault-domain evidence remain unestablished.

Adding on-chain governance now would expand consensus-critical code and introduce unresolved economic, voting, emergency, appeal, upgrade and key-rotation semantics. It would be unsafe to infer stake from HND account balances. Therefore Option B is deferred and is not part of v0.2.

## 2. Chosen v0.2 governance model

The sole authority for initial membership and subsequent membership/power changes shall be a versioned, canonical, signed **Validator Set Profile (VSP)** distributed with the network release.

The VSP must bind:
- chain ID and HND Genesis manifest hash;
- CometBFT version and approved binary/source provenance identifier;
- profile schema version and monotonically increasing sequence;
- previous profile digest and exact current-set digest;
- target activation height (or explicit initial-genesis designation);
- complete validator consensus public keys, derived addresses and voting powers;
- exact total voting power;
- authorized change type and reason;
- approval signatures over the canonical package.

A node must reject a profile if any network, Genesis, software identity, sequence, predecessor digest, key/address, power, signature or activation check fails. Local TOML or Genesis edits must not silently override the authenticated profile. Private keys must never be included.

## 3. Authorization rule

Adopt a **2-of-3 authorization rule** for validator-set profile changes, with three distinct governance signing identities. The three signing identities must be held in separate administrative custody domains; merely generating three keys or storing them on separate machines under one administrator does not establish independence.

For v0.2:
- 2 valid signatures out of the 3 enrolled governance keys are required.
- Signatures must cover the exact canonical profile digest, chain ID, Genesis hash, sequence, predecessor digest and activation height.
- A signature for one network or sequence cannot be replayed on another.
- Governance signing keys are distinct from CometBFT consensus keys, HND account keys and P2P node keys.
- Governance-key enrollment/replacement itself requires a separately documented, witnessed ceremony and cannot be authorized by a single current key.
- If fewer than two valid governance keys are available, changes stop; there is no unilateral emergency bypass in v0.2.

The 2-of-3 rule is an engineering control selected for this project phase, not proof that the three custodians are independent. Custodian identities, custody boundaries and recovery procedures must be evidenced before production use.

## 4. Weighted voting-power and collusion policy

Consensus influence is measured by voting power, not validator count.

For a roster with total power (P):
- A coalition's power is the sum of the powers of all validators it controls.
- The CometBFT BFT safety assumption requires Byzantine power to remain strictly below (P/3).
- A commit requires more than (2P/3) precommit power.
- Exactly (P/3) is not “below one third”; at or above that boundary the standard safety assumption is no longer satisfied.
- A coalition with more than (2P/3) can meet the commit threshold; a coalition with one third or more can violate the standard Byzantine safety assumption.
- Validator count, company count and machine count are not substitutes for a control/ownership analysis.

### Test-fixture arithmetic only

The existing local fixture has four validators at power 10 each, so (P=40):
- one validator: 10/40 = 25%;
- two validators: 20/40 = 50%;
- three validators: 30/40 = 75%;
- more than two-thirds requires strictly more than 26⅔ power, hence at least 27 integer power units in this fixture;
- one-third is 13⅓ power, so 14 or more integer power units reaches/exceeds the one-third boundary.

These values describe only the disposable equal-weight fixture. They are not production limits or a recommended production roster.

### Production power limits deliberately not invented

No numeric per-validator cap, minimum independent operator count, maximum coalition share or minimum total power is approved by this report. Such values require a measured threat model, expected operator population, deployment evidence and explicit economic/security analysis. Until then, production validator enrollment remains blocked. The profile verifier must nevertheless enforce positive bounded integer power, exact total, unique keys/addresses, deterministic canonical ordering and overflow-safe arithmetic.

## 5. Mandatory profile validation

Before a validator starts consensus or signs:
1. Verify canonical encoding and schema version.
2. Verify chain ID and HND Genesis hash.
3. Verify approved CometBFT version and binary/source provenance.
4. Verify sequence is exactly the expected next sequence and predecessor digest equals the active profile.
5. Verify at least two distinct authorized governance signatures.
6. Verify unique supported consensus public keys and derived validator addresses.
7. Verify each power is positive and within the exact CometBFT-compatible numeric range.
8. Verify the declared total equals the checked sum of member powers.
9. Recompute the profile digest and compare it with the independently distributed release reference.
10. Verify activation height and ensure all nodes apply the same profile at the same transition.
11. Fail closed before opening validator signing capability if any check fails.

A valid signature does not make an unsafe power distribution acceptable; the release process must separately produce a coalition/concentration analysis.

## 6. Change and activation process

For every add, remove, power change or consensus-key rotation:
- prepare a complete before/after roster, not a partial patch;
- include reason, ticket, expiry, sequence, predecessor digest and target height;
- obtain the required 2-of-3 governance signatures;
- independently recompute total power and coalition exposure;
- distribute the exact same package to all operators;
- require readiness acknowledgements against the same digest;
- activate deterministically at the agreed height;
- record the resulting profile digest and block height in operator audit records.

If any node has a different profile, it must not continue signing as though it were current. There is no automatic rollback to an old profile after a new profile has activated. Recovery must use a higher sequence and a newly authorized profile, while preserving signer anti-double-sign state.

Key rotation is not complete merely by copying a new key file. The old signer must be fenced, its durable H/R/S state preserved, and stale instances rejected before the new signer is enabled.

## 7. Scope explicitly deferred

Not included in HND v0.2:
- on-chain validator registry or governance token voting;
- staking or delegation;
- slashing, jailing, rewards or automatic evidence penalties;
- automatic admission/removal from HND transactions;
- permissionless validator onboarding;
- production numeric power caps or economic-security guarantees.

Any later proposal for Option B requires a separate protocol version, formal state-machine specification, deterministic migration/activation design, adversarial review and independent acceptance tests. HND account balances must not be silently treated as stake.

## 8. Required closure evidence — not yet present

The following are release gates, not completed work:
- three governance custodians with independently evidenced administrative custody;
- signed initial production VSP and independently published digest;
- production validator roster and operator-to-infrastructure mapping;
- approved production power/concentration policy;
- verifier implementation and fail-closed startup integration;
- signer-side fencing and durable anti-double-sign recovery;
- multi-node tests for wrong signatures, replay, stale sequence, wrong Genesis, duplicate keys, power overflow, exact one-third boundary, more-than-two-thirds coalition, uneven-power quorum, partial rollout and stale signer restart;
- independent security review and witnessed recovery drill.

No production validator keys, credentials or secret values should be committed to Git.

## 9. CI and verification provenance

This document is documentation-only. It does not claim that any proposed validation or acceptance test was executed. A CI result is attributable only to the exact commit SHA reported by GitHub Actions. A prior successful run on another commit does not validate this report or implement its requirements.

The previous audit's local four-validator CI evidence remains limited to a single CI runner and disposable test identities. It does not prove independent operators, independent infrastructure or production decentralization.

## 10. Disposition

**Architecture decision for v0.2: Option A selected — operator-managed, signed validator-set profiles with 2-of-3 governance authorization.**

**Production status: NOT APPROVED.** The decision resolves the architecture direction only. It does not authorize public launch, token issuance, production signing or deployment. The next safe engineering stage is a detailed VSP schema and deterministic verifier specification, still documentation-only, followed by explicit implementation gates and test design.

---
This is an engineering decision record, not a security certification, legal opinion, economic-security guarantee or launch authorization.
