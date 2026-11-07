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


## Verified update — checkpoint crash recovery (2026-11-07)

This addendum supersedes older evidence and status statements above where they conflict.

The latest code commit for the rollback-checkpoint recovery regression is `0aa49d823c252fc8214cd1ed9aa0f96fe4c551e8`. All four workflows completed successfully on that exact SHA:
- HND Python tests: run `42411996750`.
- CometBFT one-node restart: run `42411996862`.
- CometBFT three-validator integration: run `42411996702`.
- CometBFT four-validator liveness/recovery: run `42411996737`.

The subsequent documentation commit `d3fc4cd0770bcbc87436d3709a61e3d0650540d2` also passed all four exact-SHA workflows:
- HND Python tests: run `42412003076`.
- CometBFT one-node restart: run `42412003224`.
- CometBFT three-validator integration: run `42412003111`.
- CometBFT four-validator liveness/recovery: run `42412002973`.

The new restart regression exercises the distributed-commit failure window: SQLite has committed a block, the process stops before publishing the corresponding external checkpoint, and the chain is reopened. The local chain is correctly classified as `LOCAL_AHEAD_UNVERIFIED`; the startup-gate helper rejects operation instead of silently treating the local database as trusted. This is a deterministic process/reopen regression using the volatile in-memory test authority, not a production remote-authority integration.

The existing consensus matrix also records a four-validator partition/healing test: one validator was isolated while the other three retained quorum and advanced, then the isolated validator caught up after healing. That evidence is limited to separate processes/data directories on one CI runner; it does not prove multi-host or multi-operator behavior.

## Current security boundary — do not overclaim

- Signed checkpoint records, pinned-key verification, compare-and-swap contract, local-chain assessment, publication helpers, and a fail-closed exact-match helper exist.
- The checkpoint helper is **not wired into CometBFT startup or block commit**.
- The only authority implementation used in tests is volatile and in-memory. No independently operated durable authority, remote endpoint, credential, production signing-key custody, or validator-wide checkpoint policy is configured.
- Therefore external anti-rollback protection is **not implemented for production**, and no public deployment, issuance, or real-value use is authorized.
- The exact-match helper rereads the authority and local tip to reduce a read/assessment race, but it is not a lease or fencing mechanism and does not prevent the authority or local chain changing immediately after the helper returns.

## Next engineering gates

1. Implement and independently test a durable external authority with authenticated clients, monotonic CAS, idempotent retry, audit history, and outage semantics.
2. Define secure authority-key custody, rotation, revocation, and multi-validator checkpoint publication policy.
3. Design explicit recovery authorization for a local chain ahead of its last accepted checkpoint; verify every suffix block and CometBFT commit evidence before advancing the authority.
4. Wire the gate into the actual CometBFT lifecycle so no consensus writes can occur before successful verification and after an unacknowledged checkpoint update.
5. Test adversarial proposals, equivocation, delayed/reordered messages, Byzantine voting-power boundaries, power-loss durability, and independent multi-host operators.
6. Complete independent protocol, cryptographic, application-security, economic, and legal reviews before any public launch.


## Verified update — external authority contract and exact-SHA CI (2026-11-08)

The implementation-status refresh commit `338ffc32a0db05b7232086daaab3d366f6bb562c` completed all four workflows successfully on that exact commit:
- HND Python tests: run `42413770023`.
- CometBFT one-node restart: run `42413769994`.
- CometBFT three-validator smoke: run `42413770141`.
- CometBFT four-validator liveness/recovery: run `42413770170`.

The new design contract is documented in `docs/EXTERNAL_CHECKPOINT_AUTHORITY_CONTRACT.md` (documentation commit `6d92241551979a5453a926b1ae456fb0ba2ca330`). It specifies the required independent trust boundary, linearizable monotonic compare-and-swap, authenticated transport and authorization, KMS/HSM-backed signing-key custody, consensus-safe publication evidence, crash/recovery behavior, fencing requirements, and real-provider conformance tests.

This document is a specification, not an implemented service. No provider was selected or provisioned, and no credentials or signing secrets were added. The Go CometBFT adapter remains a transport adapter to the Python application; checkpoint startup and commit enforcement remain unwired. Production anti-rollback protection remains unimplemented and unclaimed.
