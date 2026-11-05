# HND v0.2 — Mempool restart and uncommitted transaction durability review

**Date:** 2026-11-05  
**Workstream:** WP4.14 — Transaction admission and restart semantics  
**Branch:** `phase-0.2-planning`  
**Status:** Documentation-only static review. No source, test, or workflow files changed.

## 1. Executive result

The adapter explicitly uses CometBFT's normal **Flood Mempool**. It does not enable the ABCI application-mempool mode because the HND core does not implement an `InsertTx/ReapTxs` transaction queue.

HND's `check_tx()` maintains an in-process ledger view to validate sequential pending nonces and balances. That view is not persisted. It is reconstructed from the committed ledger at application startup and reset to the committed ledger after each successful Commit.

Consequently, a transaction accepted by `CheckTx` but not yet included in a committed block is **not a durable transaction**. It may disappear from the node's mempool after restart. This is expected mempool behavior, not loss of committed ledger state. A client that needs eventual delivery must retain the signed transaction and rebroadcast it until it observes committed inclusion or a definitive rejection/expiry condition.

The repository's current tests cover mempool-view isolation and reset after Commit, but do not directly state or test the restart contract for a transaction accepted by CheckTx and not yet finalized.

## 2. Source and tests reviewed

At the reviewed branch head:

- `hnd_v02/abci_app.py`
  - `check_tx()` clones and advances `_mempool_ledger` in memory.
  - `__init__()` rebuilds `_mempool_ledger` from `_committed_ledger`.
  - `commit()` resets `_mempool_ledger` to the newly committed ledger.
- `hnd_v02/cometbft_v040_server.py`
  - `CheckTx()` delegates to HND application validation.
  - `InsertTx()` is disabled and returns code 1.
  - `ReapTxs()` returns an empty list.
  - The adapter comment explicitly states that normal Flood Mempool is pinned and app-mempool mode is not enabled.
- `tests/test_v02_abci_app.py`
  - CheckTx updates only the mempool view.
  - sequential pending nonces are accepted.
  - failed and duplicate CheckTx do not corrupt the view.
  - restart discards uncommitted finalized state.
  - Commit resets the mempool view.
- `tests/test_v02_cometbft_v040_adapter.py`
  - adapter CheckTx and app-mempool-disabled behavior.

Static inspection only. No test command was run.

## 3. Transaction lifecycle and durability boundary

| Stage | Meaning | Durable in HND application store? |
|---|---|---|
| Client signs transaction | Client has a signed transaction | Only if client retains it |
| CometBFT CheckTx accepts | Node admission checks passed | No |
| HND mempool view advances | In-process nonce/balance admission view advances | No |
| FinalizeBlock executes transaction | Candidate block result is computed | Not until Commit |
| Commit succeeds | Candidate ledger and height are persisted | Yes, subject to storage/platform durability assumptions |

A CheckTx success response must not be described to clients as final settlement, irreversible acceptance, or a guarantee of inclusion.

## 4. Restart behavior

On application restart:

1. HND loads the last committed application store.
2. It restores the committed ledger, evidence journal, height, and app hash.
3. It reconstructs the mempool admission view from that committed ledger.
4. Transactions that were only pending in memory are absent from HND's reconstructed view.
5. CometBFT's Flood Mempool behavior is owned by the pinned CometBFT implementation; the HND adapter does not provide a durable transaction queue or app-mempool recovery mechanism.

Clients and external relayers should therefore retain signed transaction bytes and rebroadcast after reconnect/restart, using transaction identity and account nonce to determine whether a transaction is still pending, already committed, or rejected. Rebroadcast must not create a new signature or increment the nonce blindly.

## 5. Evidence gap and acceptance tests

The inspected test suite does not directly encode the HND-side restart contract for CheckTx-only transactions. Add tests only after explicit authorization to modify tests.

| ID | Scenario | Required outcome |
|---|---|---|
| MEMRST01 | Accept one transaction via CheckTx, restart HND before FinalizeBlock | Committed balance, nonce, height, and app hash remain unchanged; mempool view returns to committed state |
| MEMRST02 | Accept sequential nonce N and N+1, restart before block inclusion | Both pending admissions are absent after restart; committed nonce remains N |
| MEMRST03 | Rebroadcast the original signed transaction after restart | CheckTx accepts it if still valid against committed state |
| MEMRST04 | Commit the transaction, restart, then rebroadcast the same signed bytes | CheckTx rejects it as already applied/nonce stale; committed balance changes exactly once |
| MEMRST05 | Commit transaction N, then rebroadcast transaction N+1 that had only been pending | N+1 is accepted only if its nonce and balance remain valid against the new committed state |
| MEMRST06 | Restart CometBFT and HND together with a non-empty Flood Mempool | Record actual pinned-binary mempool recovery behavior; do not assume pending transactions survive |
| MEMRST07 | Client loses CheckTx response and rebroadcasts same signed bytes | Duplicate handling is deterministic; no duplicate ledger effect |
| MEMRST08 | Client loses Commit/query response after inclusion | Client can query committed height/account/transaction evidence and reconcile before constructing a new transaction |

For MEMRST06, test the exact CometBFT v0.40.0 binary and configuration. The application-level tests alone cannot establish CometBFT mempool persistence.

## 6. Recommended client contract

A client or relayer should:

1. Persist the signed transaction bytes locally before broadcast.
2. Treat CheckTx success as node admission only.
3. Re-broadcast the exact same signed bytes after connection loss or node restart while the transaction remains unresolved.
4. Query committed account nonce/state and transaction inclusion evidence before creating a replacement transaction.
5. Never interpret a timeout as proof of rejection or proof of commitment.
6. Create a new transaction with a new nonce only after reconciling the prior transaction's outcome.

This client-side retention requirement is operationally important because the HND application does not persist a pending transaction queue.

## 7. Release boundary

The current architecture has a clear committed-state durability boundary and an intentionally volatile mempool-admission view. That is acceptable if documented and supported by client rebroadcast behavior. It is not acceptable to advertise CheckTx acceptance as durable payment/transfer acceptance.

This review does not claim that CometBFT Flood Mempool loses transactions on every restart; it states that HND does not persist them and that exact pinned-binary restart behavior must be verified separately. No source or tests were changed, and no tests were run.
