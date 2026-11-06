# WP4.14 — CometBFT Native Database Compatibility, ABCI Replay and Recovery Matrix Audit — 2026-11-07

**Repository:** `3bbdala-max/HND-Ledger`  
**Branch:** `phase-0.2-planning`  
**Reviewed branch head:** `082912126e919455c642d5c3f6607eb9cff11b9b`  
**Audit type:** Documentation-only source and test review  
**Disposition:** **NOT APPROVED for production recovery, native database migration, snapshot/state-sync recovery, or validator restart with unverified cross-store state.**

## 1. Executive finding

HND persists its own application height, application hash, ledger and evidence state. Its ABCI `Info` method returns the HND application's persisted height and app hash. This is a useful application-store recovery property, but it is not an independent reconciliation of HND state against CometBFT's native block store and state database.

The HND adapter's snapshot ABCI methods currently:
- return an empty snapshot list;
- reject offered snapshots;
- return an empty loaded chunk; and
- abort snapshot chunk application.

The existing tests verify these method responses, local HND restart behavior and a helper that compares replica fingerprints. They do not establish that a running pinned CometBFT v0.40.0 node can safely recover from deliberately divergent native CometBFT and HND application databases.

This is an **integration and operational recovery-evidence gap**. It is not proof that CometBFT v0.40.0 itself lacks native block replay, state recovery or database compatibility mechanisms. Those behaviors must be verified against the exact pinned CometBFT source/build and exercised with the HND ABCI application.

## 2. Source and test evidence

Reviewed:
- `hnd_v02/cometbft_v040_server.py`
- `hnd_v02/recovery_controls.py`
- `tests/test_v02_cometbft_v040_adapter.py`
- `tests/test_v02_recovery_controls.py`
- `scripts/cometbft_v040_single_node_smoke.py`
- `docs/WP4_14_COMETBFT_APPLICATION_RECOVERY_HEIGHT_RECONCILIATION_AUDIT_2026-11-05.md`
- `docs/WP4_14_COMETBFT_V040_EXACT_SOURCE_SCHEMA_AND_DEFAULT_PROFILE_AUDIT_2026-11-05.md`
- `docs/WP4_14_NETWORK_LIFECYCLE_UPGRADE_AND_RECOVERY_AUDIT_2026-11-05.md`
- `docs/WP4_14_DURABLE_STATE_FRESHNESS_ANTI_ROLLBACK_AND_COMETBFT_RECOVERY_RECONCILIATION_AUDIT_2026-11-07.md`

### 2.1 HND application recovery

The ABCI `Info` method forwards `application.info()` fields into `ResponseInfo.last_block_height` and `last_block_app_hash`. The HND application store loader verifies its local checksum, network/Genesis identity, ledger/evidence state and recomputed app hash.

The adapter's `main()` constructs the HND application and starts the gRPC server. It does not independently inspect the CometBFT native database before starting the ABCI service. The `--recovery` option asks HND to require an existing application state file; it is an explicit CLI flag, not evidence of a complete production launcher policy.

### 2.2 Snapshot/state-sync behavior

The adapter's snapshot methods are intentionally unsupported. The unit test asserts those exact responses. Consequently, HND application snapshot transfer/state sync is not implemented by this adapter.

Do not conflate:
- CometBFT native block/state database recovery;
- CometBFT block replay against an ABCI application;
- HND application's own durable-store restart;
- ABCI snapshot/state-sync transfer.

They are different recovery paths and need separate acceptance evidence.

### 2.3 Recovery controls

`recovery_controls.py` provides a bounded process-readiness wait that terminates a process on timeout without modifying caller-owned state, and a replica-convergence assertion comparing validator height, block hash and app hash fingerprints.

The corresponding tests cover timeout termination/state preservation and synthetic replica fingerprint divergence. These are useful controls, but they do not themselves read CometBFT's native database, authenticate a checkpoint, reconcile native/app heights, or prove safe CometBFT replay.

### 2.4 Existing smoke coverage

The single-node smoke starts a disposable CometBFT process with temporary data and a local HND ABCI service, then exercises transaction and account behavior. This demonstrates a useful live integration path. The reviewed recovery audit and test set do not establish the complete controlled crash/restart divergence matrix described below.

## 3. Recovery state model

A production recovery decision must consider at least these separately observed values:

| Layer | Required observations |
|---|---|
| CometBFT block store | last committed block height, block ID/hash, commit metadata |
| CometBFT state database | last block height, app hash, consensus/validator state and last results as exposed by the pinned version |
| HND application store | committed height, app hash, network/Genesis identity, config/profile identity, store schema |
| Independent trusted checkpoint | authenticated network identity, expected height and block/app commitments, monotonic freshness information |
| Signer anti-double-sign state | validator key identity, last signed height/round/step and protected monotonic recovery anchor |

No one layer is a substitute for the others. In particular, a locally recomputed unkeyed checksum proves internal consistency against accidental/tampered bytes only to its design limits; it does not prove that the state is the newest valid state.

## 4. Required recovery decision table

The following is a required future policy, not a claim that the current node implements it.

| Condition | Safe required disposition |
|---|---|
| Native CometBFT and HND heights/hashes match, trusted checkpoint matches | Continue only after all identity and signer checks pass |
| HND app is behind native committed state | Permit only the exact pinned CometBFT replay/reconciliation behavior after it is independently tested; verify final app hash and height |
| HND app is ahead of native CometBFT state | Halt and investigate; do not truncate or silently accept |
| Heights match but app hashes differ | Halt; do not sign or serve state-changing operations |
| HND store is older but internally valid | Reject against an authenticated freshness checkpoint; do not trust its checksum alone |
| CometBFT DB is older than HND state | Halt; require an authorized recovery procedure, never silently rewrite either store |
| HND state missing on established network | Fail closed; do not initialize empty state |
| Native CometBFT DB missing/corrupt | Follow a separately reviewed native DB restore/replay procedure; do not assume HND state can reconstruct CometBFT consensus state |
| Checkpoint unavailable or disagrees | Do not enable signing; enter an explicit recovery/quarantine state |
| Snapshot offered but HND snapshot support remains disabled | Reject; operator must use a supported, independently verified recovery path |

## 5. Native CometBFT database compatibility requirements

For every CometBFT binary upgrade or database restore, record and verify:
- exact CometBFT source commit, release/build inputs and binary digest;
- database backend and exact native store schema/version as implemented by that source;
- whether the target binary officially supports opening the source database directly;
- any required migration command, ordering, backup/restore constraints and compatibility window;
- whether block replay requires the ABCI app at a matching or earlier height;
- how last block height, app hash, validator set, consensus parameters and last results are reconciled;
- whether replay is deterministic and idempotent after interruption;
- whether the old binary can safely reopen a database already touched/migrated by the new binary.

No compatibility claim should be inferred from a matching semantic version string, successful process start, or a successful HND-only store load. If the exact upstream source does not document or test an upgrade path, treat the database as incompatible until a pinned-version test proves otherwise.

## 6. Required startup/recovery sequence

Before enabling network listeners or consensus signing on an established validator:

1. Verify independently provisioned trust roots and signed release/recovery manifest.
2. Verify exact CometBFT binary digest, source/build identity and approved native database compatibility.
3. Verify HND software, protocol, config, store schema and CometBFT profile identities.
4. Open the native CometBFT database in a controlled preflight/read-only inspection mode where supported; collect its committed recovery metadata without mutating it.
5. Load the HND application store with mandatory existing-state semantics; verify checksum, Genesis/network identity, schema, config/profile bindings and app hash.
6. Compare both stores to an authenticated monotonic checkpoint and to each other under the pinned CometBFT replay contract.
7. Verify signer identity and anti-double-sign state against its independent recovery anchor.
8. If a documented replay is required, run it in a controlled mode and verify the resulting height, block ID and app hash before serving/signing.
9. If any value is missing, stale, mismatched or unsupported, stop startup and preserve source artifacts for forensic recovery.
10. Enable listeners and signing only after all gates pass.

This sequence is a target design. The current adapter does not implement this complete cross-store startup gate.

## 7. Backup, restore and snapshot policy

A backup set must be a coordinated recovery artifact, not a random copy of individual files. It should bind:
- network and Genesis identity;
- HND config/protocol/store-schema digests;
- CometBFT binary/profile and native database version;
- native CometBFT state/block-store metadata;
- HND application height/app hash and state digest;
- validator identity and signer anti-double-sign recovery metadata references;
- capture time as operational metadata, not as the sole freshness proof;
- authenticated checkpoint and backup-manifest signatures.

Restore must occur into a separate staging location. Preserve original source directories read-only. Validate the backup manifest and checkpoint, perform any approved native DB migration on a copy, restore HND state, then run exact-version replay/reconciliation and independent verification. Do not combine a newer HND application store with an older CometBFT database or vice versa without a separately approved recovery/fork plan.

Since HND's current ABCI snapshot methods reject/abort snapshot transfer, no operator documentation should advertise HND ABCI snapshot-based state sync as available. A future snapshot implementation needs chunk integrity, manifest identity, size/resource bounds, resumability, atomic apply/commit, interruption recovery, anti-rollback and cross-validator verification.

## 8. Required integration and negative test matrix

These are acceptance requirements, not tests claimed to have run.

| ID | Scenario | Required evidence/result |
|---|---|---|
| DBREC-01 | Fresh chain, commit multiple blocks, clean restart | Native/HND heights and app hashes reconcile exactly |
| DBREC-02 | Kill node during block commit | Restart/replay reaches one deterministic committed state; no double application |
| DBREC-03 | HND app store one height behind native CometBFT state | Exact v0.40.0 replay behavior captured; final app hash matches |
| DBREC-04 | HND app store ahead of native CometBFT state | Fail closed; no truncation or silent signing |
| DBREC-05 | Same height, different app hash | Fail closed |
| DBREC-06 | Restore older valid HND store with newer native DB | Independent freshness check detects rollback |
| DBREC-07 | Restore older native DB with newer HND store | Startup blocked; no automatic reconciliation that discards committed state |
| DBREC-08 | Missing HND store on established-chain restart | Fail closed regardless of accidental omission of recovery flag in production launcher |
| DBREC-09 | Missing/corrupt native CometBFT DB | Documented recovery only; no HND-only reconstruction claim |
| DBREC-10 | Open database with unsupported CometBFT binary version | Reject before mutation or use explicitly tested upstream migration |
| DBREC-11 | Crash during native DB migration | Original backup remains intact; partial target is not accepted |
| DBREC-12 | Crash during HND restore/migration | Partial HND state is rejected; source remains intact |
| DBREC-13 | Checkpoint is older than local committed state | Halt/quarantine; never lower monotonic anchor |
| DBREC-14 | Checkpoint is newer than both local stores | Refuse signing; recover only from authenticated data reaching checkpoint |
| DBREC-15 | Checkpoint unavailable or signature invalid | Fail closed |
| DBREC-16 | Four validators restore independently | Equal height, block ID/hash and app hash before signing |
| DBREC-17 | One validator restores a stale but checksummed backup | That validator is rejected; other validators remain unaffected |
| DBREC-18 | Snapshot offer to current HND adapter | Explicit rejection observed; no false claim of state sync |
| DBREC-19 | Future snapshot with corrupt/missing chunk | Reject atomically; no partial state becomes active |
| DBREC-20 | Future snapshot with wrong network/config/profile digest | Reject before apply |
| DBREC-21 | Signer anti-double-sign state is older than chain checkpoint | Signing disabled pending authorized signer recovery |
| DBREC-22 | Restore after protocol upgrade activation | Exact target schema/protocol/profile and activation identity required |

Run these against the exact pinned CometBFT binary and at least four independent validator instances. Preserve raw native logs, database inspection output, ABCI Info responses, block IDs, app hashes, checkpoint signatures, signer state observations and final process status. The test harness must deliberately create divergence; simply restarting four nodes from identical temporary directories is insufficient.

## 9. CI observation during this audit

At the time of inspection:
- Workflow run: [42304601956](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42304601956)
- Commit: `082912126e919455c642d5c3f6607eb9cff11b9b`
- Branch head: same commit.
- `hnd-v02-tests`: completed successfully.
- `cometbft-single-node-smoke`: in progress.
- Active step: **Build pinned CometBFT binary**.
- Subsequent Byzantine/evidence, signer, remote-signer, single-node and multi-validator smoke steps were still pending at inspection.

This is a live workflow observation, not a final result. It does not establish DBREC-01–DBREC-22. No success/failure conclusion is made for the in-progress CometBFT job.

## 10. Decision register and release gate

| Control | Current assessment |
|---|---|
| HND local store integrity/restart | Implemented and unit-tested within application scope |
| Cross-store native CometBFT/HND startup reconciliation | Not established by inspected HND startup path |
| Independent authenticated monotonic recovery checkpoint | Design requirement; production implementation not established |
| HND ABCI snapshot/state-sync | Explicitly unsupported |
| Native CometBFT DB version compatibility matrix | Not established by repository evidence reviewed |
| Crash-injected coordinated native/app restore | Not demonstrated |
| Four-validator stale backup rejection before signing | Not demonstrated |
| Production restore runbook and drill | Not certified |

**Decision: NOT APPROVED for production validator recovery, CometBFT native database migration, snapshot/state-sync recovery, or public-network operation.**

The next safe sequence is to obtain an exact upstream CometBFT v0.40.0 database/replay compatibility statement from pinned source, specify an authenticated cross-store checkpoint format, then implement and run the DBREC matrix only after explicit owner authorization for source and test changes.

No source, tests, workflow, live state, native database or signer state was changed by this audit.
