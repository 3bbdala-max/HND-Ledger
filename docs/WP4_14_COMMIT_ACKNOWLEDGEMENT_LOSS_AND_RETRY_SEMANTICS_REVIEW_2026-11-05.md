# HND v0.2 — Commit acknowledgement-loss and retry semantics review

**Date:** 2026-11-05  
**Workstream:** WP4.14 — ABCI commit durability and retry behavior  
**Branch:** `phase-0.2-planning`  
**Status:** Documentation-only static review. No source, test, or workflow files changed.

## 1. Executive result

The HND application separates block execution from durable commitment:

- `FinalizeBlock` creates one in-memory pending candidate at exactly `last_committed_height + 1`.
- `Commit` writes that candidate to the application store before publishing it as the in-memory committed state.
- If the write fails before replacement, the pending candidate remains available for an in-process retry.
- If the process restarts after the replacement became visible, the store loader can recover the new height, ledger, and app hash.

The inspected implementation does **not** define an idempotent repeated-`Commit` contract. After a successful commit, a second call has no pending block and raises `ABCIApplicationError`. The ABCI `Commit` request itself carries no height or operation identifier with which the application could distinguish a duplicate acknowledgement from an invalid call.

This is not, by itself, proof of a CometBFT protocol defect: the pinned CometBFT process may not retry a completed ABCI Commit RPC in the way a generic RPC client might. The repository evidence inspected here does not establish the exact behavior when the application has durably replaced its state file but the Commit response is lost before CometBFT receives it.

## 2. Source and tests reviewed

At the reviewed branch head:

- `hnd_v02/abci_app.py`
  - `finalize_block()` rejects a second pending block and requires the next committed height.
  - `commit()` writes the pending state, updates in-memory committed fields, then clears `_pending`.
  - `_load_store()` restores the persisted committed height and app hash.
- `hnd_v02/cometbft_v040_server.py`
  - ABCI `Commit()` delegates to `application.commit()` and maps errors to gRPC `FAILED_PRECONDITION`.
- `tests/test_v02_abci_app.py`
  - `test_commit_storage_failure_leaves_old_committed_state`
  - `test_restart_after_durable_replace_recovers_committed_height_and_hash`
  - `test_commit_persists_and_updates_committed_state`
- `tests/test_v02_cometbft_v040_adapter.py`
  - adapter-level FinalizeBlock/Commit lifecycle test.

Static inspection only. No test command was run.

## 3. What the existing tests establish

1. A failure injected at `os.replace` leaves the previous state file and in-memory committed position unchanged; the pending candidate can then be retried in the same process.
2. If the real `os.replace` succeeds and the test raises immediately afterwards, a newly constructed application reads the new height, app hash, balance, and nonce from the state file.
3. Normal successful Commit persists the candidate and advances the application height.
4. The application refuses a new FinalizeBlock while an earlier candidate remains pending.

These tests cover useful local state transitions. They do not run a real CometBFT process through a lost Commit response and restart.

## 4. Identified evidence and contract gaps

### 4.1 Repeated Commit is not idempotent

After a successful call, `_pending` is cleared. Calling `commit()` again raises “no finalized block is awaiting Commit”. The transport exposes this as a failed precondition.

There is no stored last-commit acknowledgement record or request identity in the HND application interface. Because the ABCI Commit request has no block height field, a safe duplicate-call policy cannot be added by guessing that every no-pending call is a retry.

### 4.2 A response-loss boundary is not tested end-to-end

The existing restart test simulates process loss after replacement, but it does not run CometBFT, lose the actual gRPC response, restart both processes, and inspect native CometBFT height/hash alongside HND height/hash.

The important question is not merely whether the HND state file is readable. It is whether the pinned CometBFT v0.40.0 node and HND application converge on the same committed block after this precise interruption, without reapplying transactions or advancing the application twice.

### 4.3 Post-replace directory-fsync failure is a separate uncertain outcome

If replacement succeeds but the subsequent directory fsync raises, the in-memory HND height is not advanced and `_pending` remains. A same-process retry rewrites the pending candidate. After process restart, however, the visible destination may contain either the previous or replacement state depending on the actual filesystem/power-loss outcome. The application store checksum detects malformed/tampered data, but is not an independent rollback anchor.

This path must be tested separately from a failure before replacement.

## 5. Required integration acceptance matrix

Run against the exact pinned CometBFT v0.40.0 binary. Preserve native logs, ABCI request/response traces, HND store hashes, and both systems' heights/app hashes.

| ID | Fault injection | Required outcome |
|---|---|---|
| COMACK01 | Normal FinalizeBlock and Commit | Native CometBFT and HND committed height/app hash agree |
| COMACK02 | Kill the ABCI application after state replacement but before the Commit response is delivered | On restart, establish the exact CometBFT handshake/replay behavior; no duplicate transaction effects |
| COMACK03 | Drop the Commit response while keeping the application process alive | Observe whether the pinned CometBFT retries; if it does, verify the documented duplicate-call behavior |
| COMACK04 | Restart both processes after COMACK02 | Both stores converge to one identical committed height/hash; no silent reset or truncation |
| COMACK05 | Fail before `os.replace`, then retry in the same process | Old committed state remains authoritative until retry succeeds |
| COMACK06 | Fail directory fsync after successful replace | Treat outcome as uncertain; restart and reconcile against native CometBFT state, not an assumed old/new result |
| COMACK07 | Send a second Commit after a successful Commit without a new FinalizeBlock | Confirm the intended protocol behavior; do not silently acknowledge an unknown duplicate |
| COMACK08 | Commit an empty block, then repeat the fault scenarios | Height still advances exactly once even when the ledger state hash itself is unchanged |

## 6. Recommended disposition

1. Do not change `commit()` to blindly return the previous app hash whenever no pending block exists. That would hide invalid call sequences and cannot identify which block is being acknowledged.
2. First establish the pinned CometBFT v0.40.0 behavior for lost Commit responses and restart/replay using the integration matrix above.
3. If the integration contract requires idempotent acknowledgement, design it around a verifiable commit position and app hash, with an explicit protocol state machine. Do not infer a duplicate solely from the absence of `_pending`.
4. Preserve the existing rule that application state is written before in-memory committed fields are published.
5. Keep cross-store reconciliation and independent anti-rollback checkpoints as separate release gates.

## 7. Release boundary

The repository demonstrates local retry after a pre-replace storage failure and local restart recovery after a visible replacement. It does not yet demonstrate end-to-end CometBFT behavior under Commit response loss. No claim is made here that CometBFT retries Commit, or that it does not. Production validator recovery remains unverified until the pinned-binary integration scenarios are executed and reviewed.
