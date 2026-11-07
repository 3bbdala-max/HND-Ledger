# ABCI local adapter status

## Architecture

CometBFT v0.40.0 communicates with a thin Go ABCI socket adapter. The Go adapter delegates HND application methods to a Python process over a private Unix-domain JSONL IPC socket. Python owns transaction validation, state transitions, state commitments, and SQLite persistence.

## Implemented ABCI methods

- Info: committed height and app hash.
- InitChain: validates HND-LOCAL-V2 and a bounded canonical JSON/CBOR genesis envelope. Genesis state and CometBFT marker are persisted atomically.
- Query: read-only latest-state paths /hnd/v1/info and /hnd/v1/account; proofs and historical heights are rejected.
- CheckTx: encoding, chain ID, and signature admission only.
- InsertTx / ReapTxs: bounded disposable in-memory mempool.
- PrepareProposal / ProcessProposal: deterministic proposal selection and full state-dependent validation.
- FinalizeBlock: candidate calculation without durable writes.
- Commit: persists the finalized block and evicts included mempool transactions.

Unsupported snapshot, state-sync, and vote-extension methods fail closed.

## Transport controls

- Python IPC is Unix-domain only, mode 0600, 1 MiB frame cap, strict JSON envelope, duplicate-key rejection, and sequential handling on the SQLite-owning thread.
- Go ABCI listener is restricted to loopback TCP addresses.
- Go IPC client handles partial writes and zero-progress write errors.

## Verified integration

On commit 90f49448e553a0fae386b7dfc18c14e8f082d2a7:
- One-node block production and restart recovery: run 42360867084, success.
- Three-validator funded genesis, signed transfer, RPC Query, overspend filtering, post-transfer app-hash comparison, and restart recovery: run 42360867085, success.
- Python tests: run 42360867069, success.

The three-validator run committed a signed transfer at height 4. All ledgers agreed on balances, nonce, and state commitment 78b774640f86986f70e5528d94aee5e8aa56fa5b79320dc6bc99b50b1bfa5438. Account and ledger-info queries returned committed state on all three nodes. A correctly signed 800,000-unit spend from an account holding 750,000 passed weak CheckTx admission but was excluded by PrepareProposal; no validator committed it and balances/nonces remained unchanged. All CometBFT header app hashes matched at height 5. After validator 0 restarted, it retained the valid transfer and matching app hash.

## Compatibility and remaining work

Pre-v3 state roots are incompatible with the current v3 commitment format. Crash injection, Query proofs and historical reads, snapshots/state sync, adversarial consensus testing, mempool resource-exhaustion testing, and production validator/key-management procedures remain open.
