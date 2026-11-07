# HND application lifecycle boundary

**Status:** implemented as a local Python lifecycle model; not an ABCI++ transport or CometBFT integration.

## Purpose

The HND state machine must not persist speculative proposal state. Proposal preparation and validation may run repeatedly for different candidate blocks. Only the decided block's commit phase may advance durable application state.

## Implemented API

`LedgerApplication` in `src/hnd_ledger/application.py` exposes:

- `info()`: committed height and state commitment.
- `check_tx(raw)`: weak mempool admission check for canonical encoding, chain ID, and signature only; deliberately does not reject state-dependent balance/nonce conditions or mutate state.
- `prepare_proposal(raw_transactions)`: build an ordered valid selection against an isolated state copy, bounded by transaction-count and byte limits.
- `process_proposal(raw_transactions)`: deterministically validate the complete proposal against committed state.
- `finalize_block(raw_transactions)`: calculate the resulting application hash in memory and retain one pending finalized candidate.
- `commit()`: persist the finalized transactions through the local chain's atomic append operation and verify the resulting application hash.

## Invariants

1. `check_tx`, `prepare_proposal`, and `process_proposal` never mutate committed state or write a block. CheckTx is intentionally weaker than block execution because nonce and balance validity depend on ordered state.
2. A proposal retry starts from the same committed state; a rejected or abandoned candidate cannot leak balances or nonces.
3. `finalize_block` does not persist data.
4. A second finalization or proposal preparation while a finalized candidate awaits commit is rejected.
5. `commit` is unavailable without a finalized candidate.
6. Transaction count and encoded transaction byte limits are enforced before execution.
7. State transition rules remain in the existing HND protocol/state modules; the lifecycle facade does not implement a second set of transaction rules.

## Verification

- `tests/test_application.py` adds coverage for persistence boundaries, abandoned candidates, proposal retry isolation, weak CheckTx behavior, sequential nonces, wrong chain IDs, commit/finalize preconditions, and stale-candidate rejection.
- GitHub Actions run [42344679339](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42344679339), on exact code commit `29ae7ec7bee8cbea8b11469407ec48ab7be006a6`, completed successfully: **38 tests passed**.
- A prior CI run failed because a test incorrectly expected weak CheckTx to reject a well-formed transaction with insufficient funds. The test was corrected to reflect the intended mempool/consensus boundary; the subsequent 38-test run passed.
- Candidate discard tests simulate loss of in-memory process state; they are not full CometBFT crash/recovery tests.

## Explicit limitations

- No ABCI protobuf service, socket transport, CometBFT process, CometBFT mempool, validator set, or distributed consensus is implemented here.
- This facade models the application lifecycle only. A real adapter must map the exact CometBFT v0.40.0 ABCI++ request/response types and prove restart/commit semantics.
- The current `LocalChain` is a single-process SQLite reference store, not a production multi-node database.
