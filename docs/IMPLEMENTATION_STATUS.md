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
- CI for Python, Go tests/static analysis, one-node restart, and three-validator transfer/query/overspend/recovery.

## Verified evidence

- Python tests: run 42361150494 on commit 3b97907a9b484144e67a9386620fd30e0ad45a6c, success (69 tests).
- One-node CometBFT restart: run 42360867084 on commit 90f49448e553a0fae386b7dfc18c14e8f082d2a7, success.
- Three-validator signed transfer, RPC Query, overspend filtering, post-transfer app-hash comparison, and restart recovery: run 42360867085 on the same commit, success.
- Go adapter tests/static analysis: run 42359852685 on commit 1c62d3cad548315b8cecb811edd76ee6b93808af, success.

The SQLite failure-injection test forces an abort during block insertion. The test confirms no height, tip hash, balance, nonce, in-memory block, or database block row advances, then reopens the database and confirms the original genesis state is intact. This is not a full process-kill or power-loss campaign.

## Remaining work

- Process-level crash injection around FinalizeBlock/Commit and power-loss durability testing.
- Adversarial proposals, equivocation, partitions, delayed/reordered messages, and Byzantine voting-power tests.
- Snapshots, state sync, Query proofs, historical queries, and validator-set changes.
- Production key custody, validator admission, backup/restore, upgrades, monitoring, and incident response.
- Multi-host independently operated validators.
- Independent protocol, cryptographic, application security, economic, and legal review.

No public deployment, issuance, or real-value use should occur before these gates are complete.
