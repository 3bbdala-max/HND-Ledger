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

On commit 90f49448e553a0fae386b7dfc18c14e8f082d2a7:
- Python tests: run 42360867069, success.
- One-node CometBFT restart: run 42360867084, success.
- Three-validator signed transfer, RPC Query, overspend filtering, post-transfer app-hash comparison, and restart recovery: run 42360867085, success.

The three-validator integration checked sender balance 750,000, recipient balance 250,000, sender next nonce 1, and state commitment 78b774640f86986f70e5528d94aee5e8aa56fa5b79320dc6bc99b50b1bfa5438. It then submitted a validly signed 800,000-unit spend from the sender using nonce 1. CheckTx admitted its encoding/signature; PrepareProposal excluded it because the committed balance was only 750,000. All three ledgers retained the original balances and nonce and did not include the invalid transaction in any committed block. RPC queries confirmed state on all three nodes. Validator 0 restarted and retained the valid transfer and app hash.

Go adapter tests/static analysis passed on commit 1c62d3cad548315b8cecb811edd76ee6b93808af, run 42359852685. No Go adapter code changed in the subsequent Python/query integration work.

## Remaining work

- Crash injection at FinalizeBlock/Commit and SQLite persistence boundaries.
- Adversarial proposals, equivocation, partitions, delayed/reordered messages, and Byzantine voting-power tests.
- Snapshots, state sync, Query proofs, historical queries, and validator-set changes.
- Production key custody, validator admission, backup/restore, upgrades, monitoring, and incident response.
- Multi-host independently operated validators.
- Independent protocol, cryptographic, application security, economic, and legal review.

No public deployment, issuance, or real-value use should occur before these gates are complete.
