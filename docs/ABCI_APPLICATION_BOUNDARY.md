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

Python tests passed on commit a6c5250905d0861c5d3a62dd766d957742080b1c, run 42360521258. One-node restart passed in run 42360521260. Three-validator signed transfer, account/ledger-info RPC queries, post-transfer app-hash agreement, and restart recovery passed in run 42360521298.

## Explicit limitations

Historical queries, Merkle proofs, snapshots, state sync, vote extensions, crash injection at every persistence boundary, and production multi-host operations are not implemented or not validated.
