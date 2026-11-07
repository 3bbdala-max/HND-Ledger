# HND ABCI++ transport implementation plan

**Target:** CometBFT v0.40.0 (exact version pin)
**Decision:** use the official Go ABCI socket server as a thin transport adapter; keep transaction validation and state transitions in the Python HND application.
**Status:** architecture decision only. No ABCI server or CometBFT node has been implemented or run yet.

## Why this boundary

The v0.40.0 ABCI protobuf service includes the ABCI++ lifecycle and the v0.40 mempool methods `InsertTx` and `ReapTxs`. Its Go `types.Application` interface requires implementations for Info, Query, CheckTx, InsertTx, ReapTxs, InitChain, PrepareProposal, ProcessProposal, FinalizeBlock, ExtendVote, VerifyVoteExtension, Commit, and snapshot operations.

CometBFT provides an official Go socket server and serializes calls through its application mutex. A small Go adapter therefore avoids hand-implementing the protobuf socket framing and ensures the application implements the exact versioned interface. It must remain a transport adapter, not a second ledger implementation.

## Process topology

```
CometBFT v0.40.0
      |
      | official ABCI socket protocol (Unix domain socket preferred)
      v
HND Go ABCI adapter
      |
      | private local IPC, versioned request/response envelope
      v
Python HND application process
      |
      v
SQLite reference ledger
```

The Go adapter must bind only to a local Unix socket by default. It must not expose the Python IPC endpoint to the network. If TCP is ever required, authentication and transport encryption become mandatory.

## Responsibilities

### Go adapter

- Implement the exact `types.Application` interface from the pinned v0.40.0 module.
- Use CometBFT's official `abci/server.NewSocketServer`; do not reimplement protobuf framing.
- Translate ABCI request fields to a versioned private IPC envelope and translate deterministic results back.
- Maintain the mempool queue required by `InsertTx` and `ReapTxs`; enforce byte limits and never claim a transaction is committed merely because it entered the mempool.
- Preserve ABCI request order and fail closed on IPC protocol/version errors.
- Return explicit response codes for invalid transactions; do not turn ordinary invalid user input into an application-process crash.
- Return unsupported/empty snapshot responses until deterministic snapshot support is implemented.
- Disable vote extensions initially; verification behavior must be explicitly pinned and tested before enabling them.

### Python engine

- Own all transaction decoding, signature verification, nonce/balance rules, proposal selection, proposal validation, deterministic execution, app hash, and SQLite persistence.
- Implement a strict versioned IPC request schema; reject unknown fields, malformed hex/base64, oversized payloads, and unsupported protocol versions.
- Keep `FinalizeBlock` speculative and `Commit` durable.
- On startup, replay and verify the persisted chain before reporting its height or app hash.
- Never trust transaction validity decisions supplied by the Go adapter.

## Required method mapping

| ABCI v0.40.0 method | HND behavior |
|---|---|
| Info | Return committed height and app hash |
| Query | Initially support read-only account/balance and chain metadata paths; reject unknown paths |
| CheckTx | Weak mempool admission check; no nonce reservation |
| InsertTx | Insert into bounded in-memory mempool after validation |
| ReapTxs | Return ordered transactions bounded by requested max bytes |
| InitChain | Validate chain ID, genesis format, supply cap, initial allocations; initialize exactly once |
| PrepareProposal | Select deterministic valid transactions within request and HND limits |
| ProcessProposal | Validate the complete ordered proposal against committed state |
| FinalizeBlock | Execute decided transactions in memory and return per-transaction results plus app hash; no durable write |
| Commit | Atomically persist the finalized block and advance committed state |
| ExtendVote / VerifyVoteExtension | Disabled initially; no custom extension accepted |
| Snapshot methods | Explicitly report no snapshots until snapshot format and verification are implemented |

## Critical invariants and failure handling

1. All validators executing the same committed history must produce byte-identical app hashes.
2. PrepareProposal and ProcessProposal must not mutate committed state.
3. A candidate may be discarded after a proposal retry or process crash before Commit.
4. FinalizeBlock must not persist. Commit must persist before returning.
5. Startup Info must report the last successfully committed height, not a speculative height.
6. A failed IPC call during Commit must be treated as a fatal/recoverable node error, never as a successful commit.
7. CheckTx is not consensus validation. ProcessProposal and FinalizeBlock must independently enforce deterministic validity.
8. Mempool contents are disposable and must be revalidated after Commit; they are not ledger state.
9. The Go layer must not reimplement cryptographic or monetary rules.
10. The app hash must commit to all consensus-relevant state, including account balances and nonces, and genesis policy must be bound to the chain identity.

## Integration gates

- Build the adapter against the exact CometBFT v0.40.0 module and compile-time assert `var _ types.Application = (*HNDApp)(nil)`.
- Unit-test every ABCI method and malformed IPC cases.
- Run the official ABCI socket handshake against one local CometBFT node.
- Test InitChain, Info, CheckTx, InsertTx, ReapTxs, PrepareProposal, ProcessProposal, FinalizeBlock, Commit, restart, and replay.
- Inject crashes before FinalizeBlock, after FinalizeBlock but before Commit, and immediately after durable Commit.
- Run three independent nodes with separate data directories and validator keys; compare height, block hash, and app hash after every committed height.
- Exercise duplicate/replayed transactions, nonce gaps, insufficient funds, supply cap, overflow, oversized transactions/blocks, proposal reordering, restarts, and network partitions.
- Do not enable public peers, real-value transfers, validator rewards, or public token distribution before all gates and independent security/legal reviews pass.

## Source pinning

The adapter must be built from the tagged CometBFT v0.40.0 source and its ABCI interface, not from the moving `main` branch. v0.40.0 includes the `InsertTx` and `ReapTxs` methods and changes to the ABCI interface; compile-time interface assertion is mandatory.
