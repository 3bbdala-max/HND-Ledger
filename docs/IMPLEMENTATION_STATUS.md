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
- CI for Python, Go tests/static analysis, one-node restart, and three-validator transfer/query/overspend/recovery; bounded mempool capacity and committed-entry eviction are covered by unit tests.

## Verified evidence

- Python tests: run 42365173568 on commit 294c27db92655adbced5eac65fc9c813f216020a, success (76 tests). Adds mempool item/byte-cap, duplicate-accounting, and post-commit capacity-release coverage.
- One-node CometBFT restart: run 42365173534 on the same commit, success.
- Three-validator signed transfer, RPC Query, overspend filtering, post-transfer app-hash comparison, and restart recovery: run 42365173545 on the same commit, success.
- Go adapter tests/static analysis: run 42359852685 on commit 1c62d3cad548315b8cecb811edd76ee6b93808af, success; CometBFT workflows above also rebuilt and exercised the adapter.
- Go adapter tests/static analysis: run 42359852685 on commit 1c62d3cad548315b8cecb811edd76ee6b93808af, success.

The test suite includes SQLite trigger failures and child-process termination during block insertion and during both pre- and post-insert portions of the funded-genesis marker transaction. Reopening the database verifies transaction rollback, the original genesis snapshot, and absence of partial block or marker state. It also verifies that identical funded-genesis retries remain idempotent after restart, conflicting genesis is rejected without state mutation, and non-canonical base64 encodings are rejected. The mempool tests additionally verify item/byte caps, duplicate submissions not inflating byte accounting, and capacity reuse after committed transactions are evicted. These are targeted process-crash and input-canonicalization tests, not a complete power-loss or adversarial-network campaign.

## Remaining work

- Process-level crash injection at other FinalizeBlock/Commit and database boundaries; power-loss durability testing.
- Adversarial proposals, equivocation, partitions, delayed/reordered messages, and Byzantine voting-power tests.
- Snapshots, state sync, Query proofs, historical queries, and validator-set changes.
- Production key custody, validator admission, backup/restore, upgrades, monitoring, and incident response.
- Multi-host independently operated validators.
- Independent protocol, cryptographic, application security, economic, and legal review.

No public deployment, issuance, or real-value use should occur before these gates are complete.
