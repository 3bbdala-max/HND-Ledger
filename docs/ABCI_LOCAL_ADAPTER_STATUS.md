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

## Verified baseline

The one-node and three-validator integrations passed on commit 1c62d3cad548315b8cecb811edd76ee6b93808af (runs 42359852690 and 42359852656). The three-validator test committed a signed transfer at height 4, compared local state commitments and CometBFT app hashes at header height 5, restarted validator 0, and verified its persisted transfer, balances, nonce, and matching app hash.

Python Query unit tests passed on commit a6c5250905d0861c5d3a62dd766d957742080b1c (run 42360521258). The new end-to-end CometBFT RPC Query check is still being validated and must not be treated as passed until its workflow completes successfully.

## Compatibility and remaining work

Pre-v3 state roots are incompatible with the current v3 commitment format. Crash injection, Query RPC verification, Query proofs and historical reads, snapshots/state sync, adversarial consensus testing, mempool resource-exhaustion testing, and production validator/key-management procedures remain open.
