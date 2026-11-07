# HND v0.2 implementation status

Status: deterministic Python ledger integrated with CometBFT v0.40.0 for controlled local CI; not production-ready.

## Implemented

- Ed25519 transaction signing/verification and sender-key binding.
- Canonical CBOR, strict transaction schema, chain-ID binding, and domain-separated hashes.
- Account balances, sequential uint64 nonces, self-transfer rejection, insufficient-funds checks, overflow protection, and supply-cap invariant.
- Deterministic blocks, parent linkage, state commitments, SQLite persistence, and replay verification.
- State commitment v3 commits chain ID and supply cap as well as account balances/nonces. Pre-v3 local database roots are incompatible.
- Funded development genesis via bounded canonical JSON/CBOR allocation envelope. Genesis state and CometBFT marker are persisted atomically.
- Python ABCI lifecycle: Info, InitChain, Query, CheckTx, InsertTx, ReapTxs, PrepareProposal, ProcessProposal, FinalizeBlock, Commit.
- Query paths /hnd/v1/info and /hnd/v1/account, latest-state only, no proofs or historical reads.
- Bounded JSONL IPC over Unix socket; strict envelope checks, duplicate-key rejection, 1 MiB frame limit, socket mode 0600.
- Go CometBFT v0.40.0 adapter; partial-write handling; loopback-only ABCI listener.
- CI for Python, Go tests/static analysis, one-node restart, and three-validator transfer/query/recovery.

## Verified evidence

- Python tests: run 42360521258 on commit a6c5250905d0861c5d3a62dd766d957742080b1c, success.
- One-node CometBFT restart: run 42360521260 on the same commit, success.
- Three-validator signed transfer, Query RPC on all validators, post-transfer app-hash comparison, and validator restart recovery: run 42360521298 on the same commit, success.
- Go adapter tests/static analysis: run 42359852685 on commit 1c62d3cad548315b8cecb811edd76ee6b93808af, success.

The three-validator integration checked sender balance 750,000, recipient balance 250,000, sender next nonce 1, and state commitment 78b774640f86986f70e5528d94aee5e8aa56fa5b79320dc6bc99b50b1bfa5438. The RPC account and ledger-info queries returned committed values on all three nodes. After restarting validator 0, its database retained the transfer, balances, nonce, and matching app hash.

## Remaining work

- Crash injection at FinalizeBlock/Commit and SQLite persistence boundaries.
- Adversarial proposals, equivocation, partitions, delayed/reordered messages, and Byzantine voting-power tests.
- Snapshots, state sync, Query proofs, historical queries, and validator-set changes.
- Production key custody, validator admission, backup/restore, upgrades, monitoring, and incident response.
- Multi-host independently operated validators.
- Independent protocol, cryptographic, application security, economic, and legal review.

No public deployment, issuance, or real-value use should occur before these gates are complete.
