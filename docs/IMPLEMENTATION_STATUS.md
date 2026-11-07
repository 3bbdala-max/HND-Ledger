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
- CI for Python, Go tests/static analysis, one-node restart, three-validator transfer/query/overspend/recovery, and four-validator quorum liveness/recovery.
- Bounded mempool capacity, committed-entry eviction, and state-aware CheckTx RECHECK.

## Verified evidence

All four current integration/test workflows passed on commit `a76cee10eabafc7d27f36dbd66910f0f7feea790`:
- Python suite run `42368248628`: success, 77 tests.
- One-node CometBFT restart run `42368248709`: success; node resumed block production after restart, advancing from height 2 to 3.
- Three-validator integration run `42368248612`: success; signed transfer committed at height 4; all validators agreed on balances, nonce, and app hash; signed overspend was filtered; restarted validator retained the transfer and recovered.
- Four-validator liveness run `42368248630`: success; validators 1, 2, and 3 advanced to at least height 5 while validator 0 was offline; validator 0 restarted and caught up; all four app hashes matched at height 5 (`2FA595F9328078EB77A6EE62BDAD3743D619B1371BB82DD78AD0D98FAECC03A9`).
- Go adapter tests/static analysis run `42359852685` on commit `1c62d3cad548315b8cecb811edd76ee6b93808af`: success.

The dispatcher distinguishes new CheckTx submissions from CometBFT RECHECK. New submissions retain weak admission semantics; RECHECK validates against the latest committed state so stale balance/nonce transactions are rejected. Regression tests prove rejection after a balance-changing commit, acceptance of a still-valid transaction, rejection of unsupported CheckTx types, and no state mutation during recheck.

The test suite includes SQLite trigger failures and child-process termination during block insertion and during both pre- and post-insert portions of the funded-genesis marker transaction. Reopening the database verifies transaction rollback, the original genesis snapshot, and absence of partial block or marker state. These are targeted process-crash tests, not a complete power-loss campaign.

The four-validator test demonstrates quorum liveness for a single stopped validator in a four-validator testnet and recovery/catch-up after restart. It does not test a network partition, independent operators, separate hosts, or Byzantine behavior.

## Remaining work

- Network partition/healing, adversarial proposals, equivocation, delayed/reordered messages, and Byzantine voting-power tests.
- Process-level crash injection at other FinalizeBlock/Commit and database boundaries; power-loss durability testing.
- Snapshots, state sync, Query proofs, historical queries, and validator-set changes.
- Production key custody, validator admission, backup/restore, upgrades, monitoring, and incident response.
- Multi-host independently operated validators.
- Independent protocol, cryptographic, application security, economic, and legal review.

No public deployment, issuance, or real-value use should occur before these gates are complete.
