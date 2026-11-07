# HND-Ledger v0.2 — Reproducible test plan

## Evidence rule

A result is PASS only when the test, source commit, workflow run, and observed result are linked. Distinguish pass, fail, skipped, timed out, pending, and not run. Three processes on one CI runner are not independent operators.

## Verified CI evidence

- Python suite run 42365173568 on commit 294c27db92655adbced5eac65fc9c813f216020a: PASS, 76 tests. Includes mempool item/byte limits, duplicate accounting, and capacity release after Commit.
- One-node CometBFT restart run 42365173534 on the same commit: PASS.
- Three-validator transfer, Query, overspend filtering, app-hash comparison, and restart recovery run 42365173545 on the same commit: PASS.
- Go adapter tests/static analysis run 42359852685 on commit 1c62d3cad548315b8cecb811edd76ee6b93808af: PASS.

## Unit test coverage

Python tests cover canonical CBOR and base64, Ed25519 verification, chain separation, malformed encodings, replay, nonce gaps/conflicts/overflow, self-transfer, overspend, balance overflow, supply cap, duplicate transactions, atomic proposals, genesis validation/idempotence across restart, conflicting-genesis rejection across restart, atomic genesis marker persistence, state commitment coverage, block hashes, SQLite restore/replay, IPC validation, and read-only Query responses.

The dispatcher tests confirm weak CheckTx accepts a well-formed signed overspend, while PrepareProposal filters it without changing committed state and still selects a valid following transaction. CheckTx RECHECK is state-aware: after a block commits, stale transactions that no longer satisfy balance/nonce rules are rejected, while still-valid transactions are retained; recheck does not mutate committed state. Mempool tests cover item and byte ceilings, duplicate submissions without double-counting bytes, capacity rejection, and capacity reuse after Commit evicts included transactions.

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
| INT-13 | Mempool item/byte caps, duplicate accounting, and committed-entry capacity release | PASS, 42365173568 |\n| INT-14 | CheckTx RECHECK rejects stale balance/nonce transactions after commit without mutating state | PASS, 42365759445 |

## Latest exact-commit CI evidence

All three required workflows completed successfully on code commit `c91bb1478a50da0bd3c7c59c6b46c4bdb1bc897f`:
- Python tests run `42365922063`: PASS (77 tests).
- One-node CometBFT startup, block production, restart, and recovery run `42365922052`: PASS.
- Three-validator integration run `42365922077`: PASS; all three validators completed the integration job, including signed transfer, state/app-hash consistency, Query, overspend filtering, and validator-0 restart recovery.

The earlier all-green baseline on commit `05f4449c052a0e869dd1c6f18f5da67d88c24532` is retained as historical evidence: Python run `42365759445` (77 tests), one-node run `42365759497`, and three-validator run `42365759520`.

## Remaining adversarial and operational tests

Process-kill/power-loss tests at other boundaries, conflicting proposals, equivocation, replayed votes, network partitions/healing, Byzantine voting-power scenarios, validator crash after signing, validator-set updates, state sync, snapshot integrity, database rollback detection, backup/restore, multi-host deployment, mempool flooding, per-peer quotas, CPU/memory exhaustion, and crash injection around every SQLite commit boundary.
