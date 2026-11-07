# HND-Ledger architecture

Status: describes the v0.2 local implementation as of 2026-11-07. Experimental; not production-ready.

## Components

1. CometBFT v0.40.0 owns P2P communication, validator voting, proposal rounds, and block consensus.
2. Go ABCI adapter implements the pinned CometBFT application interface and exposes a loopback TCP ABCI socket.
3. Python ABCI dispatcher and application validate HND requests, manage the disposable mempool, validate proposals, finalize candidates, and commit blocks.
4. Private IPC is bounded hnd-ipc/1 JSONL over a Unix-domain socket, mode 0600.
5. Python ledger core implements Ed25519 signatures, canonical CBOR, account state, nonces, supply cap, deterministic blocks, and state commitments.
6. SQLite is a per-validator local store. Each validator process has its own database; databases are not shared.

## Transaction and commit flow

1. A client creates a canonical transaction and signs it with Ed25519.
2. CometBFT RPC submits the transaction to a node.
3. CheckTx verifies canonical encoding, chain ID, and signature; it does not reserve nonce or balance.
4. The bounded mempool stores pending transactions.
5. PrepareProposal selects an ordered valid subset.
6. ProcessProposal validates the complete proposal against committed state.
7. FinalizeBlock computes a speculative candidate in memory.
8. Commit atomically appends the block to SQLite and advances committed state.
9. On restart, Python reloads genesis and replays every committed block, checking canonical encoding, signatures, parent links, state commitments, and block hashes.

## Genesis

CometBFT InitChain accepts the fixed local chain ID and a bounded canonical JSON v2 envelope containing Base64 canonical-CBOR allocations. The state snapshot, genesis hash, and CometBFT genesis marker are written in one SQLite transaction. Funded allocations used by CI are test-only, not a public issuance policy.

## Read-only queries

- /hnd/v1/account: latest balance and next nonce for a 32-byte account ID.
- /hnd/v1/info: chain ID, height, state commitment, supply cap, total supply, and account count.
- No historical reads or proofs.

## Consensus evidence and limitations

One-node restart and three-validator signed-transfer/query/restart tests passed in CI. The three validators used separate node homes and application databases but ran on one CI runner. This does not establish independent operators, multi-host resilience, or Byzantine fault tolerance under adversarial conditions.

Wallet/key custody, public account API/explorer, validator admission and key rotation, snapshots/state sync, validator-set updates, query proofs, adversarial consensus tests, crash injection, multi-host deployment, independent security review, economic design, and legal review remain incomplete.
