# HND application lifecycle boundary

Status: Python lifecycle model implemented and connected to the Go CometBFT v0.40.0 adapter.

## Lifecycle

LedgerApplication exposes:
- info(): committed height and app hash.
- check_tx(raw): canonical encoding, chain ID, and signature admission only.
- prepare_proposal(txs): ordered valid selection against isolated state.
- process_proposal(txs): deterministic validation of the complete proposal.
- finalize_block(txs): computes a candidate without durable writes.
- commit(): persists the finalized block atomically and verifies the resulting app hash.

The ABCI dispatcher adds Info, InitChain, Query, CheckTx, InsertTx, ReapTxs, PrepareProposal, ProcessProposal, FinalizeBlock, and Commit request mappings.

## Invariants

1. CheckTx and proposal preparation/validation do not mutate committed state.
2. Proposal retries begin from the same committed state.
3. FinalizeBlock does not persist.
4. Commit is unavailable without a finalized candidate.
5. A failed database write cannot advance the in-memory committed state.
6. Mempool contents are disposable and are not consensus state.
7. Transaction and block size limits are enforced before persistence.

## Verification

Python tests passed on commit d0832723ee533e7c27f47e62bcdedc7c5d1e3149, run 42361314253 (70 tests). The suite includes a SQLite trigger failure and a child process forcibly terminated during block insertion; reopening the database restores the original genesis state.

Three-validator signed transfer, account/ledger-info RPC queries, signed overspend filtering, post-transfer app-hash agreement, and restart recovery passed in run 42361234762. One-node restart passed in run 42361234790.

## Explicit limitations

Crash injection at other persistence boundaries, power-loss testing, historical queries, Merkle proofs, snapshots, state sync, vote extensions, and production multi-host operations are not implemented or not validated.
