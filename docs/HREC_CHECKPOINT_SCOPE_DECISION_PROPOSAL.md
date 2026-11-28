# HREC checkpoint scope — decision proposal

**Status:** Proposed architecture decision; requires protocol-owner ratification and independent security review.
**Controlling inputs:** [DEC-HREC-01](DECISION_HREC_RECOVERY_POLICY_2026-11-18.md) and [HREC-CP-01](HREC_INDEPENDENT_CHECKPOINT_INTERFACE_DESIGN_2026-11-18.md).
**Related draft:** `HREC_CHECKPOINT_PROTOCOL_V1_DRAFT.md`
**Target:** HND v0.2 / pinned CometBFT v0.40.0.
**No implementation authorization is granted by this proposal.**

## Recommendation

Use one **network-global checkpoint stream per HND network and Genesis identity**, not one competing global sequence per validator.

The checkpoint represents an authenticated HND application-state transition plus the CometBFT signed block that produced it, not the health or local disk state of an individual validator. The anchor must accept an advancement only after it verifies the signed header/commit and full block against trusted validator-set history, checks the header's AppHash against the predecessor HND state, and deterministically executes the exact HND transition to reproduce the successor app hash. A caller's assertion, local HND database, local CometBFT database, ABCI Info response, or app-hash value by itself is insufficient.

## Why network-global

A per-validator global sequence creates competing writers: validators naturally observe and persist different heights at different times. A lagging but healthy validator could be blocked from advancing its own checkpoint by another validator's later height, or a single validator could accidentally become the network's freshness authority.

A network-global checkpoint avoids that split-brain authority. All validators compare their local state against the same authenticated chain checkpoint. A lagging validator remains quarantined from signing until it has safely caught up and reconciled.

## Required verification model

The anchor is a monotonic checkpoint store plus a verifier. It is not a consensus engine and must not invent finality. Checkpoint publication is forbidden inside the HND ABCI `Commit` handler: the HND store is durable before CometBFT's subsequent native `Store.Save(state)`. The only currently acceptable candidate is a reviewed hook after pinned CometBFT `ApplyVerifiedBlock` returns successfully, followed by independent reads of both stores. The current repository has no such hook. The pinned v0.40.0 candidate call sites and available read-only interfaces are identified in `HREC_CHECKPOINT_PUBLICATION_BOUNDARY_PROPOSAL.md`; a shared helper and exact patch remain unimplemented.

For each proposed transition from HND application state `A[h-1]` to `A[h]`, the verifier must:
- verify chain ID and Genesis/trust-root identity;
- verify the CometBFT v0.40.0 signed header at height `h` using the pinned upstream light-client implementation and a previously trusted light-client state;
- verify commit/header height and BlockID linkage, validator-set hash binding, cryptographic signatures, voting power, and validator-set transitions;
- verify the full block `h` against the signed BlockID, including its header hash and PartSetHeader;
- require `Header[h].AppHash == A[h-1]`;
- execute the full block with the exact approved HND build, Genesis, protocol configuration, transactions, and all state-affecting evidence inputs to derive `A[h]`; the complete predecessor state snapshot must be retrievable, because an app hash alone cannot reconstruct it;
- require the derived `A[h]` to match the local durable HND state and checkpoint candidate.

The source-grounded one-block relationship is documented in `HREC_COMETBFT_V0400_APPHASH_SEMANTICS.md`. The initial prototype should use upstream `SequentialVerification()` rather than custom signature logic or skipping verification. Any future skipping mode must freeze trust level, witness independence, trust period, clock drift, and attack handling, with independent review. This proposal does not assert that a verifier or anchor is already implemented.

## Local node recovery remains separate

The global checkpoint proves an authenticated chain position. It does not prove that a particular validator's local HND or CometBFT database is intact.

Each node must, while quarantined:
1. read and authenticate the current network checkpoint and trusted light-client state;
2. inspect its local HND and CometBFT native state without enabling signing or listeners;
3. compare the local application state with deterministic execution from the anchored predecessor and verified full block, not by comparing same-height Header.AppHash values;
4. remain quarantined on missing proof material, stale trust root, invalid block, replay mismatch, or ambiguous state;
5. replay only from an authenticated predecessor under DEC-HREC-01 and verify the exact derived HND app hash;
6. pass the independent activation gate before enabling any service.

A validator-specific local recovery receipt may be recorded as operational evidence, but it must not advance or replace the network-global checkpoint.

## Anchor write authority

Any authorized submitter may propose a checkpoint, but only the anchor's independent verifier may accept it. The anchor must enforce one monotonic sequence per network/Genesis namespace, reject conflicting successors, and persist the verified commit proof or a content-addressed reference to durable proof material.

The verifier and anchor administration must be separated from validator hosts and their ordinary credentials. Loss of the anchor must fail closed. Restoring the anchor from backup must preserve or independently re-establish the highest verified checkpoint; an older backup must never silently lower the accepted height.

## Consequences and unresolved decisions

Benefits:
- one authoritative network freshness position;
- no race between validators with different local heights;
- validator recovery is evaluated against consensus-authenticated chain data;
- a single validator's local disk is not treated as a trust root.

Costs and open questions:
- the anchor must implement or use a reviewed CometBFT light-client verifier;
- validator-set transitions, trust periods, skipped-height verification, and clock drift become security-critical;
- the anchor becomes an availability dependency for safe startup/recovery, so outages must fail closed;
- a version-pinned post-ApplyVerifiedBlock integration hook and failure-propagation rule must be implemented and reviewed before publication is possible;
- the one-block AppHash relationship and deterministic HND execution proof must be implemented and tested against the pinned v0.40.0 source;
- Genesis bootstrap, trust-root rotation, validator-set changes, and emergency recovery require explicit witnessed procedures;
- the proof retention and audit model must be frozen.

## Decision requested

Ratify or reject the network-global checkpoint scope and light-client-verification model before freezing the HREC wire schema or writing production code.

Until ratified and independently reviewed, this remains a proposal. No production anchor, signer release, public listener, token issuance, or real-value use is authorized.
