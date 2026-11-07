# HND-Ledger v0.2 — Reproducible test plan

## Evidence rule

A result is PASS only when the test, source commit, workflow run, and observed result are linked. Distinguish pass, fail, skipped, timed out, pending, and not run. Three processes on one CI runner are not independent operators.

## Verified CI evidence

- Python suite run 42362574022 on commit d81c8fb5033fec1b369658df5671c1e3e45bfdcf: PASS, 75 tests.
- One-node CometBFT restart run 42362573986 on commit d81c8fb5033fec1b369658df5671c1e3e45bfdcf: PASS.
- Three-validator transfer, Query, overspend filtering, app-hash comparison, and restart recovery run 42362574012 on commit d81c8fb5033fec1b369658df5671c1e3e45bfdcf: PASS.
- Go adapter tests/static analysis run 42359852685 on commit 1c62d3cad548315b8cecb811edd76ee6b93808af: PASS.

## Unit test coverage

Python tests cover canonical CBOR and base64, Ed25519 verification, chain separation, malformed encodings, replay, nonce gaps/conflicts/overflow, self-transfer, overspend, balance overflow, supply cap, duplicate transactions, atomic proposals, genesis validation/idempotence across restart, conflicting-genesis rejection across restart, atomic genesis marker persistence, state commitment coverage, block hashes, SQLite restore/replay, IPC validation, and read-only Query responses.

The dispatcher test confirms weak CheckTx accepts a well-formed signed overspend, while PrepareProposal filters it without changing committed state and still selects a valid following transaction.

Persistence tests include SQLite trigger aborts during block insertion and before/after insertion of the CometBFT genesis marker, plus child processes terminated inside uncommitted SQLite transactions. Reopening verifies rollback to the original genesis state with no partial block or marker. The suite also checks that a funded-genesis retry after restart is idempotent and a different genesis cannot mutate the persisted state.

Go tests cover IPC request correlation, malformed/mismatched responses, typed errors, partial writes, zero-progress writes, and loopback listener validation. Go static analysis runs in CI.

## Integration matrix

| ID | Scenario | Evidence |
|---|---|---|
| INT-01 | One-node CometBFT startup and block production | PASS, 42362573986 |
| INT-02 | One-node restart with persistent data | PASS, 42362573986 |
| INT-03 | Three validators reach common height | PASS, 42362574012 |
| INT-04 | Funded test genesis and signed transfer | PASS, 42362574012 |
| INT-05 | Matching balances, nonce, and state commitment | PASS, 42362574012 |
| INT-06 | Matching post-transfer CometBFT app hash at H+1 | PASS, 42362574012 |
| INT-07 | Restarted validator retains transfer and state | PASS, 42362574012 |
| INT-08 | Account and ledger-info queries through all three RPC endpoints | PASS, 42362574012 |
| INT-09 | Signed overspend passes weak CheckTx but is filtered before proposal commit on all validators | PASS, 42362574012 |

| INT-10 | Identical funded-genesis retry after application restart | PASS, 42362574022 |
| INT-11 | Conflicting funded-genesis request rejected after restart without state mutation | PASS, 42362574022 |
| INT-12 | Non-canonical base64 genesis payload rejected without writing marker or allocations | PASS, 42362574022 |

## Remaining adversarial and operational tests

Process-kill/power-loss tests at other boundaries, conflicting proposals, equivocation, replayed votes, network partitions/healing, Byzantine voting-power scenarios, validator crash after signing, validator-set updates, state sync, snapshot integrity, database rollback detection, backup/restore, multi-host deployment, mempool flooding, per-peer quotas, CPU/memory exhaustion, and crash injection around every SQLite commit boundary.
