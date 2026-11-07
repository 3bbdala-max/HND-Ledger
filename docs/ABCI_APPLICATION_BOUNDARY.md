# HND application lifecycle boundary

**Status:** implemented as a local Python lifecycle model; not an ABCI++ transport or CometBFT integration.

## Purpose

The HND state machine must not persist speculative proposal state. Proposal preparation and validation may run repeatedly for different candidate blocks. Only the decided block's commit phase may advance durable application state.

## Implemented API

`LedgerApplication` in `src/hnd_ledger/application.py` exposes:

- `info()`: committed height and state commitment.
- `check_tx(raw)`: validate one transaction against committed state without reserving a nonce or mutating state.
- `prepare_proposal(raw_transactions)`: build an ordered valid selection against an isolated state copy, bounded by the current transaction-count and byte limits.
- `process_proposal(raw_transactions)`: deterministically validate the complete proposal against committed state.
- `finalize_block(raw_transactions)`: calculate the resulting application hash in memory and retain one pending finalized candidate.
- `commit()`: persist the finalized transactions through the local chain's atomic append operation and verify the resulting application hash.

## Invariants

1. `check_tx`, `prepare_proposal`, and `process_proposal` never mutate committed state or write a block.
2. A proposal retry starts from the same committed state; a rejected or abandoned candidate cannot leak balances or nonces.
3. `finalize_block` does not persist data.
4. A second finalization or proposal preparation while a finalized candidate awaits commit is rejected.
5. `commit` is unavailable without a finalized candidate.
6. Transaction count and encoded transaction byte limits are enforced before execution.
7. State transition rules remain in the existing HND protocol/state modules; the lifecycle facade does not implement a second set of transaction rules.

## Verification added

`tests/test_application.py` covers:
- No durable write before commit.
- Abandoned candidate leaves committed state unchanged.
- Proposal retries do not mutate committed state.
- Invalid proposal and CheckTx rejection are read-only.
- Commit/finalize lifecycle preconditions.

These are automated tests awaiting a successful CI run on the exact commit. The test that discards a candidate simulates loss of the in-memory process state; it is not a full CometBFT crash/recovery test.

## Explicit limitations

- No ABCI protobuf service, socket transport, CometBFT process, mempool, validator set, or distributed consensus is implemented here.
- This facade models the application lifecycle only. A real adapter must map the exact CometBFT v0.40.0 ABCI++ request/response types and prove restart/commit semantics.
- The current `LocalChain` is a single-process SQLite reference store, not a production multi-node database.
