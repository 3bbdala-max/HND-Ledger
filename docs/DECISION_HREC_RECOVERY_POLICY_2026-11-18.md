# HND v0.2 — HND/CometBFT Recovery Policy Decision

**Decision ID:** DEC-HREC-01  
**Date:** 2026-11-18  
**Scope:** Engineering recovery policy for HND application state and the pinned CometBFT v0.40.0 native stores.  
**Disposition:** Approved as the implementation direction under the project's delegated execution authority. This is not a cryptographic signature, production approval, or launch authorization.

## Decision

Adopt a **quarantine-first, independently checkpointed recovery policy**.

A height or hash mismatch is never resolved automatically during ordinary node startup. The node starts in an isolated recovery state with consensus signing, ABCI/public listeners, and transaction admission disabled. It may leave quarantine only after the HND state, CometBFT native state, chain identity, and independently authenticated checkpoint have been reconciled.

Deterministic CometBFT replay is permitted only as an explicit recovery operation, not as an implicit startup fallback. It is eligible only when all of the following hold:

1. The pinned CometBFT v0.40.0 binary/source identity and HND network/Genesis identity match the approved release.
2. An independently administered, authenticated, rollback-resistant checkpoint establishes the expected chain identity, committed position, block identity, HND app hash, and predecessor relationship.
3. The native CometBFT store is proven to be the trusted source for the missing application transitions; the replay input is contiguous and verifiable from the last authenticated HND checkpoint to the independently anchored target.
4. Replay runs in quarantine with signing and listeners disabled, and every replayed transition is deterministic and checked against the expected final HND app hash.
5. The resulting HND and CometBFT positions and hashes are reread and match the authenticated checkpoint before a separate activation gate can enable service.

If any prerequisite is absent, ambiguous, unavailable, stale, or inconsistent, replay is prohibited. Recovery requires a separately authorized and witnessed restore procedure. No automatic truncation, reset, regeneration of established-chain state, downgrade, or fallback to a convenient older backup is allowed.

## Required outcomes

| Condition | Required disposition |
|---|---|
| Fresh Genesis ceremony with no prior committed state | Explicit first-boot path only; distinct from restart/recovery |
| HND and CometBFT positions and hashes match the independent checkpoint | Continue to the separate startup authorization gate |
| HND is behind CometBFT | Quarantine; checkpoint-gated deterministic replay may be invoked explicitly |
| HND is ahead of CometBFT | Quarantine; no automatic HND rollback |
| Same height but different app hash or block identity | Quarantine; reject silent acceptance |
| HND state missing on an established chain | Quarantine; no empty-state initialization |
| CometBFT native store missing, stale, or older than the checkpoint | Quarantine; witnessed restore only |
| Independent checkpoint unavailable, stale, or ambiguous | Quarantine; no replay, listener, or signing |
| Replay result differs from the authenticated target | Quarantine and preserve all evidence |

## Implementation constraints

- The independent checkpoint must be administered outside the validator host's ordinary writable disk, backups, and operator credentials. A local checksum, SQLite file on the validator host, CI artifact, or adjacent digest is not sufficient.
- The checkpoint must bind network ID, Genesis hash, protocol/config identity, HND committed height and app hash, CometBFT committed height and block identity, monotonic sequence, predecessor digest, and operation identity.
- Checkpoint advancement must be linearizable, durable before acknowledgement, idempotent by operation ID, and recoverable after ambiguous timeouts without issuing a conflicting successor.
- The recovery operation must preserve original stores and logs; it must not destroy evidence or mutate the only available backup.
- No fixed replay-height allowance, byte limit, quorum, lease duration, hardware root, service vendor, or operator identity model is invented by this decision. Those require separate measured and reviewed contracts.
- The production signer-release anti-rollback authority remains a separate control. Passing recovery reconciliation does not itself authorize validator signing.

## Acceptance evidence

Implement and execute HREC01–HREC09 and FRESH-01–FRESH-14 against the exact pinned CometBFT v0.40.0 build, using disposable keys and state. Capture native CometBFT state, HND Info height/app hash, authenticated checkpoint contents and sequence, process/listener/signing state, recovery logs, and final state hashes. Include crash injection and ambiguous checkpoint outcomes.

CI evidence must show actual test steps executed on the exact tested commit. A zero-step Actions failure is an infrastructure block, not a test result. Do not weaken tests or workflows to obtain a passing status.

## Release boundary

This decision resolves the recovery-policy direction only. It does not claim implementation, test completion, independent security review, production readiness, public-network approval, real-fund safety, token issuance approval, or exchange readiness. Production signing and public service remain disabled until all relevant gates are independently verified.
