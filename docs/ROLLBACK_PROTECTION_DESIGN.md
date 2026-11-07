# Rollback protection design — HND-Ledger v0.2

Status: design decision; implementation and adversarial verification are NOT complete.

## Problem

The SQLite chain replays and validates its stored blocks and checks a chain-tip commitment. That commitment and its version marker are stored in the same SQLite database. Restoring an older, internally consistent database snapshot can therefore restore a valid older chain and its matching older tip metadata. The current in-database checks cannot distinguish that rollback from a legitimate historical database.

## Security objective

When an operator configures an independent trusted checkpoint authority, reopening a database whose height or block hash is older than the latest accepted checkpoint must fail closed. A checkpoint must bind at least:

- protocol/domain identifier: `HND-ROLLBACK-CHECKPOINT-V1`
- chain ID
- genesis hash
- committed block height
- committed block hash
- application state commitment
- monotonically increasing checkpoint sequence
- checkpoint format version

All integer fields use strict unsigned-integer validation (booleans are not integers for this protocol). Hashes and identifiers have fixed lengths. The signed payload uses one canonical encoding and domain separation.

## Trust boundary

The trusted checkpoint authority MUST be outside the rollback domain of the SQLite database and its ordinary backups. Examples of acceptable future integrations are a separately administered append-only checkpoint service, a remote service with enforced monotonic compare-and-swap/versioning, or a hardware-backed monotonic counter with a separately protected signing key.

A sidecar file on the same disk, a second table in SQLite, or a signing key stored beside the database is NOT an independent anti-rollback authority. Such mechanisms may detect accidental mismatch but cannot protect against an attacker restoring all local files together.

The checkpoint signing private key must never be stored in the chain database, repository, CI logs, or ordinary application configuration. Validators should verify checkpoints using a pinned public key or authenticated authority identity. Key rotation requires an explicit, auditable transition signed by the old authority and accepted by policy; silent key replacement is rejected.

## Commit ordering and crash semantics

SQLite and an independent checkpoint authority do not share an atomic transaction. The implementation must not hide this distributed-commit boundary.

The initial strict mode will:
1. Validate the currently accepted external checkpoint against the database's genesis and tip before serving consensus or accepting writes.
2. Commit a block to SQLite using the existing transaction.
3. Submit the new checkpoint with a monotonic compare-and-swap against the prior sequence and prior checkpoint hash.
4. Mark the chain operational only after the external authority confirms acceptance.

If the process crashes or the authority is unavailable between steps 2 and 3, the local database may be ahead of the external checkpoint. On restart, the system must enter a recovery-required state and refuse consensus writes. It may advance the external checkpoint only through an explicit recovery procedure that verifies the entire database suffix from the last accepted checkpoint, validates all blocks and state commitments, and records an auditable recovery event. It must never silently lower the checkpoint to match an older database.

If the external checkpoint is ahead of the local database, the database is rolled back or incomplete. Normal startup must refuse service. Recovery must restore a database containing the checkpointed block or perform a separately designed trusted state-sync process; it must not accept the older local tip.

## Multi-validator rules

All validators must agree on the same chain ID, genesis hash, checkpoint authority identity, and checkpoint policy. A validator must not independently advance a shared checkpoint unless the authority protocol explicitly supports consensus-safe compare-and-swap. The preferred model is an independently operated checkpoint service that accepts only a checkpoint already committed by the consensus network and verifies the relevant CometBFT commit evidence, rather than trusting an arbitrary single validator's request.

Checkpoint cadence, finality depth, and whether the authority anchors every block or periodic finalized heights must be explicit policy. Periodic checkpoints permit rollback within the unanchored interval and must not be described as zero-window protection.

## Required adversarial tests before implementation can be called verified

- Restore an older but internally consistent SQLite snapshot while retaining the latest external checkpoint: startup must fail closed.
- Restore both SQLite and its local sidecar while retaining the independent checkpoint: startup must fail closed.
- Submit a checkpoint with a lower sequence: authority rejects it.
- Submit same sequence with a different payload/hash: authority rejects it.
- Submit wrong chain ID or genesis hash: verifier rejects it.
- Tamper with signature, canonical encoding, state commitment, or checkpoint domain: verifier rejects it.
- Crash after SQLite commit but before external checkpoint acknowledgement: startup enters recovery-required state, never silently accepts or rewinds.
- Crash after external acknowledgement but before local acknowledgement: retry is idempotent and cannot create a second conflicting checkpoint.
- Concurrent checkpoint attempts: compare-and-swap permits one successor only.
- Authority outage: node fails closed for writes and reports an explicit degraded/recovery state.
- Key rotation and revoked/unknown key: rejected unless the explicit transition policy validates.
- Two independent operators restore backups and verify the same accepted checkpoint and chain tip.

## Scope decision

No checkpoint provider, credential, remote endpoint, or hardware trust anchor is currently configured. Therefore no external anti-rollback guarantee is claimed and no local sidecar will be misrepresented as protection. The next implementation step is a provider-neutral checkpoint interface plus a deterministic test authority; production integration remains blocked until an independent authority and key custody model are selected and configured.

## Current verified boundary

The latest verified code commit before this design note is `166231c251dbcb181e52dd65af0cdda191f3fb64`. Four exact-commit workflows passed: HND Python tests `42401814429`, one-node CometBFT `42401814447`, three-validator CometBFT `42401814426`, and four-validator liveness/recovery `42401814441`. This evidence does not include external rollback protection.


## Signed checkpoint primitives — implemented, not integrated

On code commit `be1e5725707861b7996ea6b1bfeb2b939653a127`, the provider-neutral record module now includes:

- Canonical CBOR checkpoint payloads with fixed domain and version.
- Strict uint64 and 32-byte hash validation; booleans are rejected as integers.
- Ed25519 signing and verification with an explicitly pinned 32-byte public key.
- A signed envelope with its own domain separator; payload, envelope, signer identity, and signature are validated before use.
- A provider-neutral `CheckpointAuthority` protocol with read and compare-and-swap operations.
- A volatile, lock-protected in-memory authority test double covering first acceptance, successor monotonicity, replay/conflict rejection, and competing updates.

All four exact-commit CI workflows passed on `be1e5725707861b7996ea6b1bfeb2b939653a127`: Python `42402800672`, one-node `42402800686`, three-validator `42402800837`, and four-validator liveness/recovery `42402800633`.

This does NOT yet provide a production authority. The in-memory test double is volatile and is not an anti-rollback trust anchor. The checkpoint contract is not yet wired into chain startup, block commit, or recovery. No external endpoint, credential, durable monotonic store, production signing-key custody, or multi-validator checkpoint policy is configured. Therefore production rollback protection remains unimplemented and unclaimed.


## Local-tip reconciliation — implemented as a pure fail-closed assessment

On commit `6f093fc69a899244eb3f840f13eae3efb008c6a1`, the checkpoint primitives were verified by all four CI workflows. A follow-up implementation now adds a pure local-tip assessment:

- `MATCH`: chain ID, genesis hash, height, block hash, and application hash all match; this is the only relation marked as write-eligible by the assessment.
- `LOCAL_BEHIND`: local database is below the trusted height; writes are not eligible.
- `LOCAL_AHEAD_UNVERIFIED`: local database is ahead; the suffix is not presumed valid and requires explicit verification/recovery; writes are not eligible.
- `DIVERGED`: height matches but block or application commitment differs; writes are not eligible.
- `UNANCHORED`: no trusted checkpoint exists; writes are not eligible.

The signing domain separator is also corrected to use a literal zero byte rather than the printable characters backslash-x-zero-zero.

This is a comparison primitive only. It is not yet wired into `LocalChain`, CometBFT startup, or block commit. It does not establish that an ahead suffix descends from the checkpoint; a future recovery procedure must replay and verify that suffix and require explicit authorization. No production anti-rollback guarantee is claimed.


## Checkpoint ancestry assessment

The local-tip assessment now accepts optional local block and application commitments at the trusted checkpoint height. For a local database ahead of the trusted checkpoint:
- Missing ancestor commitments remain unverified and fail closed.
- A mismatch in either ancestor commitment is classified as divergence.
- Matching ancestor commitments establish that the checkpoint appears in the locally replayed chain, but do not authorize writes: the suffix still requires explicit verification and recovery.

New tests cover missing ancestry evidence, matching ancestry, block-hash mismatch, application-hash mismatch, and partial ancestor input. This remains a pure assessment API, not an integrated startup/recovery implementation.


## LocalChain ancestry accessor and assessment integration

Commit `40c622b296fc81d2ee5b40c8d565d45cf418179c` adds `LocalChain.checkpoint_ancestor_commitments(height)`. It returns the genesis hash plus genesis app commitment at height zero, or the replay-verified block hash and state root at a positive height. It rejects boolean, negative, and future heights.

A cross-module test now feeds those actual locally replayed ancestor commitments into `assess_local_tip` for a chain that is ahead of the trusted checkpoint. Matching ancestry still produces `LOCAL_AHEAD_UNVERIFIED`; it does not enable writes. This is still not an external authority integration or a recovery authorization mechanism.


## Idempotent compare-and-swap retry semantics

The authority contract and in-memory test double now treat an exact retry of a checkpoint already accepted as success. This models a lost acknowledgement after durable acceptance: retrying the same signed payload with the original compare-and-swap expectation returns success without advancing sequence again. A different candidate using that stale expectation remains rejected. This is a test-double contract guarantee only; durable provider behavior must be independently implemented and verified.


## Authenticated authority read and local assessment

A composition helper now reads the checkpoint through the provider-neutral authority interface, verifies the signed record against the pinned public key, and assesses the local chain tip. Its fail-closed rules are explicit:
- A valid exact match can be write-eligible at the assessment layer.
- A missing record is UNANCHORED and not write-eligible.
- A malformed record or untrusted signature raises a checkpoint error.
- An authority outage raises a checkpoint error and is never converted into an unanchored fallback.

The helper is not yet called by CometBFT startup or block commit. The current authority implementation remains a volatile test double; this is not production anti-rollback protection.


## Checkpoint publication helper — provider-neutral, not atomic with SQLite

A publication helper now verifies the candidate signature, reads and authenticates the current authority record, validates strict successor monotonicity, and performs compare-and-swap. If CAS reports false, it rereads the authority: an exact candidate already present is treated as an idempotent success; a different latest record is a conflict. Read/CAS failures and unknown outcomes fail closed.

Important boundary: the helper cannot make a local SQLite block commit and a remote authority update atomic. It must be called only after the local consensus commit, and a crash/outage in between still leaves a recovery-required state. It is not wired into CometBFT commit or startup and has only been exercised against the volatile test authority.


Additional reconciliation coverage: a test authority now commits a candidate but reports a false CAS result. The publisher rereads the authority, finds the exact signed candidate, and resolves the result as success. This covers an ambiguous response distinct from an exception/timeout.


## LocalChain authority assessment integration

A new `assess_local_chain` helper composes the verified local chain commitments, independent authority read, pinned-key signature verification, and checkpoint ancestry lookup. It is an explicit helper only; it is not automatically invoked by the CometBFT process.

Integration tests cover:
- Exact genesis checkpoint match.
- A local database behind the accepted checkpoint.
- A local database ahead of the checkpoint whose replayed ancestry matches (still recovery-required).
- A locally valid but divergent history whose block/state commitment at the trusted height differs (rejected).

Authority outages, invalid signatures, missing checkpoints, and wrong response types remain fail-closed. No production authority provider or startup enforcement is configured.


## Publication bound to the replay-verified local tip

The provider-neutral publication path now has an additional composition helper, `publish_local_chain_checkpoint`. Before attempting authority CAS, it verifies that the signed candidate's chain ID, genesis hash, height, block hash, and application-state commitment exactly match the supplied replay-verified `LocalChain` tip. Tests reject a validly signed candidate with a wrong height, block hash, or application hash, and reject an untrusted signer.

This helper still must be called after the corresponding consensus commit. It does not independently prove CometBFT finality, does not authenticate the caller to a remote service, and does not provide atomicity between SQLite and the external authority. It is not wired automatically into ABCI commit. Production anti-rollback remains unimplemented.
