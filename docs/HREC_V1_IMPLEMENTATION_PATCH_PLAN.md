# HREC v1 implementation patch plan

**Status:** Engineering patch plan only. Not an implementation contract, source patch, or production approval.  
**Target:** HND v0.2 with the exact CometBFT v0.40.0 source commit `0880b4d378f347ab16e54ec677ff50d803f37d62`.  
**Design inputs:** DEC-HREC-01, HREC-CP-01, HREC checkpoint protocol draft, scope proposal, AppHash semantics note, publication-boundary proposal, and [canonical encoding / operation-ID proposal](HREC_CANONICAL_ENCODING_OPERATION_ID_PROPOSAL.md).  
**Release boundary:** No signer, public listener, transaction admission, token issuance, or real-value operation is authorized.

## 1. Purpose and implementation gate

This plan translates the existing design into a bounded source-patch sequence. It does not resolve the protocol-owner decisions listed in the protocol draft. In particular, implementation MUST NOT begin until canonical encoding, operation-ID preimage, Genesis bootstrap, trust-root lifecycle, snapshot retention, anchor service identity/administration, and validator-set transition policy are frozen and independently reviewed.

The first code target is a version-pinned CometBFT fork/patch, not the Python ABCI adapter alone. The HND ABCI `Commit` handler is not a valid publication hook.

## 2. Required component boundaries

Keep five responsibilities separate:

1. **Local evidence collector (CometBFT process):** read-only collection of the just-applied block, commit, validator set, native state, and HND `Info`; it does not decide trust.
2. **Independent proof verifier (anchor service):** verifies the trusted light-client path, full block identity, predecessor state/snapshot, and deterministic HND transition. It does not trust caller assertions or local database claims.
3. **Checkpoint publisher client:** performs idempotent PREPARE/COMMIT and operation-status reads using one deterministic operation ID.
4. **Startup quarantine/reconciliation coordinator:** reads the committed checkpoint and pending operation state before any replay, listener, transaction admission, or signer can be enabled.
5. **Activation gate:** remains separate. A matching checkpoint is necessary but does not itself authorize service or signing.

Do not reuse `RemoteMonotonicAnchor` as the HREC protocol. Its existing trust-manifest/VSP sequence-and-digest contract is a different namespace and does not provide HND/CometBFT recovery semantics.

## 3. CometBFT source patch surface

Pin the fork to the exact upstream v0.40.0 commit above and record the resulting fork commit and binary digest.

### 3.1 Read-only query connection

Add an optional `AppConnQuery` dependency to `BlockExecutor`, wired from `proxyApp.Query()` in `node/node.go` through a narrowly scoped constructor option (candidate name: `BlockExecutorWithAppQuery`).

Requirements:

- The query connection is read-only and used only for `Info()` evidence.
- Missing query wiring is a construction/startup error when HREC enforcement is enabled; it must not silently disable checkpointing.
- The returned HND height and app hash are observations to compare with independently verified evidence, not cryptographic proof.
- Keep HREC-disabled development/test configurations explicit and impossible to confuse with an approved validator profile.

### 3.2 Shared post-apply method

Add one shared method to the pinned `BlockExecutor` boundary, conceptually:

```go
PublishVerifiedHRECCheckpoint(ctx, height) error
```

The method must:

1. Load the durable CometBFT state from `state.Store.Load()`.
2. Load block metadata, full block, and commit for exactly `height` from the native block store.
3. Load the validator set needed to bind the signed header and commit evidence.
4. Query HND `Info()` and require the application height to equal the applied block height.
5. Check native state height/AppHash against the HND post-commit state using the pinned v0.40.0 semantics.
6. Construct a canonical evidence envelope containing chain/Genesis/config/build identities, full BlockID including PartSetHeader, signed-header/commit references, HND post-state hash, predecessor checkpoint digest, and content-addressed references to all proof and snapshot material.
7. Derive the deterministic operation ID from the frozen canonical preimage. No timestamp, random nonce, local validator identity, or mutable operation status may enter that preimage.
8. Call the publisher's PREPARE operation, reconcile any timeout by querying the same operation ID, then COMMIT the exact prepared digest.
9. On timeout or unknown outcome, query the same operation ID and latest checkpoint. Never generate a replacement ID or assume a timeout means failure.
10. Return success only after an exact COMMITTED outcome is confirmed. Any mismatch, unavailable anchor, stale response, or ambiguous outcome returns a fatal error.

The method must not publish from `FinalizeBlock`, HND ABCI `Commit`, a background poller, or an unverified sidecar.

### 3.3 Mandatory normal-apply call sites

Invoke the shared method only after successful `ApplyVerifiedBlock`, before the caller advances state or accepts another block:

- `consensus/state.go`: after `cs.blockExec.ApplyVerifiedBlock(...)` succeeds and before `cs.updateToState(...)` / `cs.scheduleRound0(...)`.
- `consensus/state_ingest.go`: after `cs.blockExec.ApplyVerifiedBlock(...)` succeeds and before state advancement / next-round scheduling.
- `blocksync/reactor.go`: after `r.blockExec.ApplyVerifiedBlock(...)` succeeds and before the block-sync loop continues.

All three paths must use the same method and identical failure semantics. A missing call site is a release-blocking defect.

### 3.4 Failure propagation

A publisher error is not a recoverable warning. The process must not schedule another consensus round, accept another committed block, or release any listener/signer path.

The patch must use an explicit fatal-stop path whose behavior is tested for each call site. Do not rely on a log message, ignored error, best-effort goroutine, or a panic that a supervisor might recover from and restart without quarantine.

The supervisor's restart policy must enforce quarantine before re-entry. A process restart must not bypass unresolved PREPARED/COMMITTED operation reconciliation.

### 3.5 WAL replay exclusion

`consensus/replay.go` uses `ApplyBlock` during WAL replay. It must not call the normal post-`ApplyVerifiedBlock` publisher and must not publish each replayed block automatically.

Replay remains inside startup quarantine. After replay reaches its exact target, the recovery coordinator independently verifies both stores and reconciles the same checkpoint/operation state. Only the separate activation gate may authorize normal service.

## 4. Publisher interface contract

The client boundary needs typed operations equivalent to:

- `ReadLatest(network_id, genesis_hash)`
- `Prepare(operation_id, predecessor_sequence, predecessor_digest, canonical_payload)`
- `ReadOperation(operation_id)`
- `Commit(operation_id, prepared_payload_digest)`

Required server outcomes must distinguish:

- exact operation already PREPARED;
- exact operation already COMMITTED;
- predecessor/sequence conflict;
- operation ID reused with different payload;
- another operation reserved the same predecessor;
- unauthenticated or unauthorized caller;
- stale/rolled-back replica;
- unavailable or unknown outcome.

The server must enforce linearizable compare-and-publish, durable acknowledgement, read-after-write visibility, immutable payload digest, idempotency, and append-only audit. PREPARED/COMMITTED lifecycle state belongs in a separate operation record; it must never be hashed into the immutable checkpoint payload.

A timeout is always an unknown outcome. The caller queries the same operation ID and retries only an exact idempotent operation after proving the observed state permits it.

## 5. Canonical operation identity: freeze before code

The protocol draft currently leaves the exact preimage unresolved. A candidate semantic input set is:

- fixed domain-separation label and schema version;
- network ID, chain ID, and Genesis hash;
- predecessor checkpoint sequence and digest;
- proof header height and canonical complete BlockID;
- predecessor HND app hash and derived successor HND app hash;
- protocol configuration digest and exact HND build identity.

The final encoding must be deterministic, length-delimited, versioned, and independently test-vector verified across at least two implementations. Do not include wall-clock time, local validator ID, random data, request ordering, or PREPARED/COMMITTED state. The final field set and encoding are protocol decisions, not implementation guesses.

Concurrent validators proposing the same network transition must derive byte-identical operation IDs and payload digests. The anchor must reject two different successors for one predecessor and return the exact prior result for an idempotent duplicate.

## 6. Startup quarantine and reconciliation

Before CometBFT replay or any service activation:

1. Force the process into a non-signing, non-listening, no-transaction-admission quarantine state.
2. Authenticate the anchor service and read the latest checkpoint plus pending operation state.
3. Verify network, chain, Genesis, HND build/config, CometBFT build/profile, schema, and trust-root identities.
4. Inspect local HND and CometBFT stores read-only.
5. If a PREPARED or unknown operation exists, query and reconcile that same operation ID. Never supersede it merely because the original publisher process disappeared.
6. If local stores are behind, ahead, missing, stale, or inconsistent, follow DEC-HREC-01 exactly. No automatic rollback, empty-state initialization, convenient older backup, or unverified replay.
7. If replay is permitted, perform it while quarantined and verify the exact final state against the authenticated checkpoint.
8. Require a separate activation authorization after reconciliation. Checkpoint equality alone does not release signing or listeners.

Every OS/service launch route must be shown to pass this gate. A coordinator that is merely called by the preferred startup script is insufficient if another launch path can bypass it.

## 7. Fault-injection and acceptance matrix

Run all cases against the exact pinned CometBFT fork commit and HND build, with disposable keys and stores. Capture the exact SHA, binary digests, HND height/hash, CometBFT state height/AppHash, block ID, operation ID, anchor state, logs, process state, and listener/signer state.

| Boundary / fault | Required assertion |
|---|---|
| Before blockstore save | Prior checkpoint remains latest |
| After blockstore save, before WAL EndHeight fsync | No checkpoint advancement |
| After WAL EndHeight fsync, before/during FinalizeBlock | Quarantine; no publication |
| After HND durable Commit, before CometBFT state Store.Save | No checkpoint advancement |
| After native Store.Save, before ApplyVerifiedBlock returns | No publication until completion boundary is proven |
| After ApplyVerifiedBlock returns, before PREPARE | Re-read both stores; publish only exact evidence |
| PREPARE durable, response lost | Same operation ID reads as PREPARED; no new ID |
| Before COMMIT | Remain quarantined until exact operation is reconciled |
| COMMIT durable, response lost | Same operation ID reads as COMMITTED; exact payload required |
| Anchor unavailable or stale replica | Fatal stop/quarantine; no next round |
| Conflicting operation for same predecessor | Reject; preserve prior committed checkpoint |
| Same operation ID, altered payload | Fatal conflict |
| Two validators publish same transition | One exact network-global transition; duplicate is idempotent |
| Validator-set transition / wrong trust root | Light-client verification rejects |
| Wrong PartSetHeader or block body | Full-block identity verification rejects |
| Wrong predecessor snapshot or HND execution input | Deterministic replay mismatch rejects |
| WAL replay | No automatic per-block checkpoint publication |
| Startup with pending PREPARED operation | No signing/listener until same operation reconciled |
| Every normal apply path | All three call sites enforce the same fatal behavior |

Acceptance requires actual executed test steps and retained logs on the exact commit. A workflow with zero steps, missing runner, skipped job, or unavailable logs is infrastructure-blocked evidence, not a passing or failing test assertion.

## 8. Ordered implementation stages

**Stage A — protocol freeze:** ratify network-global scope, canonical payload encoding, operation-ID test vectors, Genesis bootstrap, trust-root and validator-set policy, snapshot retention, service identity/administration, and disaster-recovery ceremony.

**Stage B — anchor service:** implement and independently test typed HREC records, linearizable PREPARE/COMMIT, idempotent reads, anti-rollback restore, authentication/authorization separation, and append-only audit. No validator integration yet.

**Stage C — CometBFT patch:** add query wiring, shared evidence collector/publisher, all three normal-apply call sites, explicit fatal propagation, and pinned build identity. Keep replay excluded.

**Stage D — startup gate:** enforce quarantine before every startup/replay/service path; reconcile latest checkpoint and pending operations; prove no bypass path exists.

**Stage E — integration proof:** fault-inject the complete matrix, run HREC01–HREC09 and FRESH-01–FRESH-14 on exact commits, verify exact SHA attribution, and obtain independent security review.

**Stage F — separate release decision:** only after all prior gates pass may a distinct, explicit release review consider any signer or public-service activation. This plan itself grants no such approval.

## 9. Current repository status and non-claims

At the time this plan is authored, the HREC branch contains design documents only. It has no implemented HREC publisher hook, independent recovery anchor, startup quarantine/reconciliation integration, or passing exact-SHA HREC integration suite.

This plan does not claim that the project is production-ready, that recovery works, or that CI has passed. It does not authorize source/runtime changes, workflow edits, CI reruns, merge, signing, public exposure, or token issuance.

