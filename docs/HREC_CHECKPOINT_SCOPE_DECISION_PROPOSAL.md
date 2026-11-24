# HREC checkpoint scope — decision proposal

**Status:** Proposed architecture decision; requires protocol-owner ratification and independent security review.
**Related draft:** `HREC_CHECKPOINT_PROTOCOL_V1_DRAFT.md`
**Target:** HND v0.2 / pinned CometBFT v0.40.0.
**No implementation authorization is granted by this proposal.**

## Recommendation

Use one **network-global checkpoint stream per HND network and Genesis identity**, not one competing global sequence per validator.

The checkpoint represents a finalized chain position, not the health or local disk state of an individual validator. The anchor must accept an advancement only when the submitted CometBFT commit/header evidence is independently verified against the trusted validator-set history for that network. A caller's assertion, local HND database, local CometBFT database, or app-hash value by itself is insufficient.

## Why network-global

A per-validator global sequence creates competing writers: validators naturally observe and persist different heights at different times. A lagging but healthy validator could be blocked from advancing its own checkpoint by another validator's later height, or a single validator could accidentally become the network's freshness authority.

A network-global checkpoint avoids that split-brain authority. All validators compare their local state against the same authenticated chain checkpoint. A lagging validator remains quarantined from signing until it has safely caught up and reconciled.

## Required verification model

The anchor is a monotonic checkpoint store plus a verifier. It is not a consensus engine and must not invent finality.

For each proposed advancement, the verifier must validate, using the exact pinned CometBFT v0.40.0 semantics:
- chain ID and Genesis/trust-root identity;
- header height, block ID, and commit linkage;
- commit signatures and voting power against the correct validator set;
- validator-set transitions from the last trusted checkpoint;
- application-hash field semantics and the exact relationship between the header and HND application state;
- monotonic height and valid adjacent/trust-bounded light-client verification rules.

The precise proof object, trusted validator-set transition algorithm, trust period, clock/drift policy, and treatment of skipped heights must be specified against the pinned CometBFT source and independently reviewed before implementation. This document does not assert those details are already implemented.

## Local node recovery remains separate

The global checkpoint proves an authenticated chain position. It does not prove that a particular validator's local HND or CometBFT database is intact.

Each node must, while quarantined:
1. read and authenticate the current network checkpoint;
2. inspect its local HND and CometBFT state without enabling signing or listeners;
3. compare heights, block identity, app-hash semantics, and network/config identities;
4. remain quarantined on missing, stale, ahead, or inconsistent state;
5. replay only from a separately verified source under DEC-HREC-01, then prove exact equality with the checkpoint;
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
- the exact HND app-hash versus CometBFT header-height mapping must be verified from v0.40.0 source;
- Genesis bootstrap, trust-root rotation, validator-set changes, and emergency recovery require explicit witnessed procedures;
- the proof retention and audit model must be frozen.

## Decision requested

Ratify or reject the network-global checkpoint scope and light-client-verification model before freezing the HREC wire schema or writing production code.

Until ratified and independently reviewed, this remains a proposal. No production anchor, signer release, public listener, token issuance, or real-value use is authorized.
