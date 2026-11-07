# HND-Ledger v0.2 — Reproducible test plan

## Evidence rule

A result is PASS only when the test, source commit, workflow run, and observed result are linked. Distinguish pass, fail, skipped, timed out, pending, and not run. Three processes on one CI runner are not independent operators.

## Verified CI evidence

- Python suite run 42361314253 on commit d0832723ee533e7c27f47e62bcdedc7c5d1e3149: PASS, 70 tests.
- One-node CometBFT restart run 42361234790 on commit f08e0e053920a989b8b7b200c4ee856d6cefee54: PASS.
- Three-validator transfer, Query, overspend filtering, app-hash comparison, and restart recovery run 42361234762 on the same commit: PASS.
- Go adapter tests/static analysis run 42359852685 on commit 1c62d3cad548315b8cecb811edd76ee6b93808af: PASS.

## Unit test coverage

Python tests cover canonical CBOR, Ed25519 verification, chain separation, malformed encodings, replay, nonce gaps/conflicts/overflow, self-transfer, overspend, balance overflow, supply cap, duplicate transactions, atomic proposals, genesis validation/idempotence, atomic genesis marker persistence, state commitment coverage, block hashes, SQLite restore/replay, IPC validation, and read-only Query responses.

The dispatcher test confirms weak CheckTx accepts a well-formed signed overspend, while PrepareProposal filters it without changing committed state and still selects a valid following transaction.

Persistence tests include a SQLite trigger abort during block insertion and a child process terminated from inside an uncommitted SQLite block insert. Reopening the database recovers the original genesis state and no partial block.

Go tests cover IPC request correlation, malformed/mismatched responses, typed errors, partial writes, zero-progress writes, and loopback listener validation. Go static analysis runs in CI.

## Integration matrix

| ID | Scenario | Evidence |
|---|---|---|
| INT-01 | One-node CometBFT startup and block production | PASS, 42361234790 |
| INT-02 | One-node restart with persistent data | PASS, 42361234790 |
| INT-03 | Three validators reach common height | PASS, 42361234762 |
| INT-04 | Funded test genesis and signed transfer | PASS, 42361234762 |
| INT-05 | Matching balances, nonce, and state commitment | PASS, 42361234762 |
| INT-06 | Matching post-transfer CometBFT app hash at H+1 | PASS, 42361234762 |
| INT-07 | Restarted validator retains transfer and state | PASS, 42361234762 |
| INT-08 | Account and ledger-info queries through all three RPC endpoints | PASS, 42361234762 |
| INT-09 | Signed overspend passes weak CheckTx but is filtered before proposal commit on all validators | PASS, 42361234762 |

## Remaining adversarial and operational tests

Process-kill/power-loss tests at other boundaries, conflicting proposals, equivocation, replayed votes, network partitions/healing, Byzantine voting-power scenarios, validator crash after signing, validator-set updates, state sync, snapshot integrity, database rollback detection, backup/restore, multi-host deployment, mempool flooding, per-peer quotas, CPU/memory exhaustion, and crash injection around every SQLite commit boundary.
