# HREC checkpoint publication boundary — integration proposal

**Status:** Source-grounded integration proposal; no runtime hook is implemented or approved.
**Pinned CometBFT:** v0.40.0, commit `0880b4d378f347ab16e54ec677ff50d803f37d62`.
**Existing policy/design:** DEC-HREC-01 and HREC-CP-01 remain normative inputs.
**Purpose:** Define where a cross-store checkpoint may be published without racing HND ABCI Commit against CometBFT native-state persistence.

## 1. Finding

The HND Python ABCI adapter cannot safely publish the independent cross-store checkpoint from its `Commit` handler.

The pinned CometBFT v0.40.0 execution order is:

1. `consensus.State.finalizeCommit` saves the decided block and commit to the native block store.
2. It synchronously writes and fsyncs the consensus WAL `EndHeight` record.
3. It calls `BlockExecutor.ApplyVerifiedBlock`.
4. `BlockExecutor.applyBlock` calls ABCI `FinalizeBlock`.
5. CometBFT saves the `FinalizeBlock` response.
6. It calculates the next CometBFT state.
7. `BlockExecutor.Commit` calls ABCI `Commit`; the HND adapter calls `HNDABCIApplication.commit()`, which durably writes the HND state.
8. Only after ABCI Commit succeeds does CometBFT set `state.AppHash` from the FinalizeBlock response and call `state.Store.Save(state)`.
9. `ApplyVerifiedBlock` returns successfully only after this native state save and the remaining apply path complete. Consensus then updates its in-memory state and schedules the next round.

The upstream source explicitly notes that the block's AppHash does not reflect the current block's transactions until the next block. It also documents the crash window in which the block and WAL EndHeight have been saved but ApplyBlock has not completed; restart may apply the already-stored block during ABCI handshake.

## 2. Mandatory publication rule

**The recovery checkpoint MUST NOT be prepared, committed, or acknowledged from inside the HND ABCI `Commit` handler.**

At that point:
- HND application state may already be durable;
- CometBFT's native state database may not yet have saved the corresponding updated state/AppHash;
- a block in the native block store or an EndHeight WAL record alone does not prove successful application and native-state completion.

The earliest acceptable publication point is after the pinned CometBFT `ApplyVerifiedBlock` operation returns successfully, and after the publisher independently reads and verifies:
- the native CometBFT state-store height and AppHash;
- the native block-store height, full block, and commit evidence;
- the HND durable `Info.last_block_height` and `Info.last_block_app_hash`;
- exact chain/Genesis/config and pinned build identities;
- the deterministic HND execution result for the authenticated block.

The publisher must not infer CometBFT native state from the ABCI Commit response. In v0.40.0, `ResponseCommit` contains retain-height information; the CometBFT state AppHash is taken from `FinalizeBlock` and saved after ABCI Commit.

## 3. Candidate integration boundary

The pinned v0.40.0 source exposes a concrete, auditable integration route, although no HREC hook is implemented yet:

- `consensus/state.go`: after `cs.blockExec.ApplyVerifiedBlock(...)` returns nil, before `cs.updateToState(...)` and `cs.scheduleRound0(...)`.
- `consensus/state_ingest.go`: after `cs.blockExec.ApplyVerifiedBlock(...)` returns nil, before `cs.updateToState(...)` and `cs.scheduleRound0(...)`.
- `blocksync/reactor.go`: after `r.blockExec.ApplyVerifiedBlock(...)` returns nil, before the block-sync loop continues.

All three normal committed-block paths must call the same HREC publisher helper. If publication fails, the existing call path must panic/stop before advancing to the next round or accepting more blocks. The supervisor must then keep restart quarantined until the same operation ID, anchor outcome, and both stores are reconciled.

The existing CometBFT interfaces make a read-only evidence collector feasible:
- `state.Store.Load()` reads the persisted native state; `LoadValidators(height)` reads the validator set.
- `state.BlockStore.LoadBlockMeta(height)`, `LoadBlock(height)`, and `LoadBlockCommit(height)` expose the stored block identity, full block, and commit.
- `proxy.AppConns` already exposes `Query() AppConnQuery`; `AppConnQuery.Info()` returns the ABCI application height and latest persisted app hash. `node/node.go` currently passes only `proxyApp.Consensus()` to `NewBlockExecutor`, so a small optional `BlockExecutorWithAppQuery(proxyApp.Query())` option is needed for the collector.

The proposed patch should add one shared post-apply collector/publisher method to `BlockExecutor`, configured with the read-only query connection and a checkpoint publisher interface. The three call sites invoke it only after `ApplyVerifiedBlock` succeeds. The collector independently rereads native state, block metadata/full block/commit, validator set, and HND Info; it does not trust the in-memory state argument alone. The independent anchor still verifies the signed-header trust path and deterministic HND execution from the recoverable predecessor snapshot.

The startup WAL-replay path in `consensus/replay.go` uses `ApplyBlock`, not `ApplyVerifiedBlock`. It MUST NOT automatically publish each replayed block. Recovery replay remains quarantined and is reconciled by the explicit DEC-HREC-01 recovery coordinator after the complete replay target has been verified.

This requires a version-pinned CometBFT patch/fork and a reviewed publisher interface. It is not present in the current Python ABCI server. The exact source diff, build identity, all three call-site tests, and failure propagation must be reviewed and pinned before implementation.

A polling sidecar without an explicit completion signal is not approved by this proposal. It could observe a partially completed cross-store transition and cannot infer from blockstore height or WAL EndHeight alone that the native state save completed.

## 4. Crash and unknown-outcome behavior

| Crash/failure boundary | Required recovery behavior |
|---|---|
| Before blockstore save | No checkpoint advancement; retain prior anchor |
| After blockstore save but before EndHeight WAL fsync | No checkpoint advancement; use pinned CometBFT restart semantics under quarantine |
| After EndHeight WAL fsync but before/during ABCI FinalizeBlock | No checkpoint advancement; startup remains quarantined until exact replay/reconciliation |
| After HND durable Commit but before CometBFT state Store.Save | No checkpoint advancement; do not treat HND state as a completed cross-store point |
| After CometBFT state Store.Save but before ApplyVerifiedBlock returns | No checkpoint advancement until the completion boundary is proven; on restart re-read and reconcile |
| After ApplyVerifiedBlock returns but before PREPARE | Both local stores are durable; publish only after independent reread and proof verification |
| After PREPARE but before COMMIT | Query the same operation ID; keep the node quarantined until exact pending outcome is reconciled |
| COMMIT durable but response lost | Query the same operation ID and exact latest checkpoint; never create a new operation ID |
| Anchor unavailable/conflicting | Stop/quarantine before the next consensus round; no signer/listener release |

A publication timeout is an unknown outcome. The publisher must query the same deterministic operation ID and exact payload. It must never advance with a different successor or infer failure from a timeout. If publication is unavailable or conflicting after local commit, the CometBFT process must not schedule another consensus round; the supervisor must stop it or keep it quarantined, and restart must not re-enable consensus until the anchor outcome and both stores are reconciled.

For a network-global checkpoint, the operation ID should be deterministically derived from the chain namespace, predecessor checkpoint digest, signed block identity, and successor HND app hash (using a frozen canonical preimage). This allows independent validators to propose the same semantic transition idempotently. The exact derivation remains a protocol-freeze decision. It must be based on a canonical preimage shared by every validator so two validators proposing the same network transition do not create different operation IDs.

## 5. Required cross-store consistency checks

For a successful application of block height `h`, the publisher must confirm:
- HND `Info.last_block_height == h`;
- HND `Info.last_block_app_hash == A[h]`;
- CometBFT native state `LastBlockHeight == h`;
- CometBFT native state `AppHash == A[h]`;
- native block store contains the exact committed block `B[h]` and commit evidence;
- signed header `H[h]` verifies against the trusted light-client state;
- `H[h].AppHash == A[h-1]`;
- the full block `B[h]` matches the signed BlockID including PartSetHeader;
- deterministic HND execution from the complete predecessor state at `h-1` over all state-affecting inputs in `B[h]` derives exactly `A[h]`;
- chain ID, Genesis hash, HND protocol config/build, and CometBFT release/profile identities match the approved values.

The local CometBFT state AppHash and HND Info are cross-store consistency observations. The independent proof is the combination of trusted signed-header verification, full block validation, authenticated predecessor state, and deterministic HND execution.

## 6. Implementation gate

Before writing the callback or publisher:
1. Review DEC-HREC-01 and HREC-CP-01 as controlling project decisions.
2. Freeze the one-block AppHash relationship and deterministic execution evidence in `HREC_COMETBFT_V0400_APPHASH_SEMANTICS.md`.
3. Specify the shared publisher helper and all three normal `ApplyVerifiedBlock` call sites (`consensus/state.go`, `consensus/state_ingest.go`, and `blocksync/reactor.go`), failure propagation, process-stop/quarantine behavior, and recovery-on-restart path.
4. Specify read-only native-state inspection and HND state observation, including `Store.Load`, `BlockStore` metadata/block/commit reads, `LoadValidators`, `AppConnQuery.Info`, and how those reads are authenticated and protected from TOCTOU.
5. Freeze deterministic operation-ID preimage and concurrent-validator publication semantics.
6. Add fault injection at every boundary in section 4 and run on the exact pinned CometBFT v0.40.0 build.
7. Obtain independent security review of the patch, publisher, anchor service, and threat boundary.

No source, test, workflow, CometBFT runtime, ABCI endpoint, signer, trust root, or persistent store is changed by this proposal. Production signing and public service remain disabled.
