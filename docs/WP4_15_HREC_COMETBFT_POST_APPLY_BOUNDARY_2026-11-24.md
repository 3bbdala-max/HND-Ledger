# HREC / CometBFT v0.40.0 integration boundary audit

**Pinned source:** CometBFT v0.40.0 commit
`0880b4d378f347ab16e54ec677ff50d803f37d62`

**Status:** source-order audit complete; runtime hook not implemented.

## Confirmed block-commit order

In the pinned `consensus/state.go`, `finalizeCommit` performs these operations:

1. Writes `EndHeightMessage{height}` to the consensus WAL using `WriteSync`.
2. Calls `cs.blockExec.ApplyVerifiedBlock(...)`.
3. On return, records metrics.
4. Calls `cs.updateToState(stateCopy)`.
5. Calls `cs.updatePrivValidatorPubKey()`.

In the pinned `state/execution.go`, `BlockExecutor.applyBlock`:

1. Calls ABCI `FinalizeBlock`.
2. Persists the FinalizeBlock response.
3. Calls ABCI `Commit`, which is expected to persist application state.
4. Updates the CometBFT state and calls `blockExec.store.Save(state)`.
5. Returns the updated state to `finalizeCommit`.

Therefore ABCI `Commit` is too early for publishing the HREC checkpoint. The first candidate synchronous post-commit hook in the consensus path is immediately after `cs.updateToState(stateCopy)` in `finalizeCommit`, before the next consensus transition can proceed. The hook must be synchronous and fail closed; logging an asynchronous notification is not sufficient.

## Confirmed startup recovery order

In the pinned `consensus/state.go`, `State.OnStart`:

1. Opens the WAL.
2. Runs `catchupReplay(cs.Height)` until replay completes or startup returns an error.
3. Starts the event switch.
4. Starts the receive routine.

A supervisor pre-launch check alone is insufficient. WAL catch-up can apply a committed block after the supervisor has checked local databases but before consensus starts. A second mandatory HREC reconciliation hook is required after the WAL catch-up loop succeeds and before the event switch/receive routine starts.

## Required runtime integration

The reviewed integration must provide both:

- **Post-commit hook:** after `updateToState(stateCopy)`, synchronously confirm HND and CometBFT durable state, append/reconcile the HREC journal operation, publish the exact checkpoint to the independently administered remote monotonic anchor, and only then allow consensus to continue.
- **Post-replay startup hook:** after successful WAL catch-up in `OnStart`, compare HND state, CometBFT state, HREC journal, and remote checkpoint. Any mismatch, missing record, pending operation, timeout, or ambiguous result must prevent consensus startup.

The existing Python supervisor gate is only a pre-launch check. It does not yet implement the post-WAL-replay hook and must not be represented as sufficient by itself.

## Crash recovery implications

- Crash after the durable CometBFT/HND state save but before remote checkpoint publication leaves local state ahead of the remote anchor. Normal startup must quarantine. An explicit recovery operation must verify the committed block and both state stores before advancing the remote anchor.
- Crash after remote publication but before local journal finalization is reconciled by reading the remote anchor and matching the exact operation digest. A different digest at the same sequence is a hard conflict.
- A timeout after a remote write is an unknown outcome. Read the remote record and accept only the exact proposed successor; never submit a different successor.

## Remaining implementation gates

1. Add a pinned, reviewable CometBFT source patch or maintained fork for both synchronous hooks.
2. Define a local authenticated IPC contract between CometBFT and the HND recovery/checkpoint service; bind it to the pinned node process and reject unauthenticated callers.
3. Implement readers for the authoritative HND and CometBFT state stores.
4. Add the explicit Python recovery primitive in `hnd_v02/hrec_recovery.py`; still required: production HND/CometBFT state readers, authenticated IPC invocation, and process-kill fault injection for one-block-ahead and lost-response cases.
5. Add process-kill fault injection at every boundary and prove no next-height vote can be signed before checkpoint confirmation.
6. Run the full tests on the exact same source commit and retain successful CI evidence.

No production readiness or public network authorization is claimed.
