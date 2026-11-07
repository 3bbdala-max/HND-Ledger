# HND-Ledger v0.2 — Reproducible test plan

## Evidence rule

A result is PASS only when the test, source commit, workflow run, and observed result are linked. Distinguish pass, fail, skipped, timed out, pending, and not run. Three or four processes on one CI runner are not independent operators.

## Verified CI evidence

- Python suite run 42368248628 on commit a76cee10eabafc7d27f36dbd66910f0f7feea790: PASS (77 tests).
- One-node CometBFT restart run 42368248709 on the same commit: PASS; node advanced from height 2 to 3 after all processes restarted with persistent data.
- Three-validator integration run 42368248612 on the same commit: PASS; signed transfer, Query, overspend filtering, matching app hashes, and validator-0 restart recovery.
- Four-validator liveness run 42368248630 on the same commit: PASS; validators 1–3 advanced from height 3 to at least height 5 while validator 0 was offline; restarted validator 0 caught up; all four app hashes matched at height 5.
- Go adapter tests/static analysis run 42359852685 on commit 1c62d3cad548315b8cecb811edd76ee6b93808af: PASS.

## Unit test coverage

Python tests cover canonical CBOR and base64, Ed25519 verification, chain separation, malformed encodings, replay, nonce gaps/conflicts/overflow, self-transfer, overspend, balance overflow, supply cap, duplicate transactions, atomic proposals, genesis validation/idempotence, conflicting-genesis rejection, atomic genesis marker persistence, state commitment coverage, block hashes, SQLite restore/replay, IPC validation, and read-only Query responses.

The dispatcher tests confirm weak CheckTx accepts a well-formed signed overspend, while PrepareProposal filters it without changing committed state and still selects a valid following transaction. CheckTx RECHECK is state-aware: after a block commits, stale transactions that no longer satisfy balance/nonce rules are rejected, while still-valid transactions are retained; recheck does not mutate committed state. Mempool tests cover item and byte ceilings, duplicate submissions without double-counting bytes, capacity rejection, and capacity reuse after Commit evicts included transactions.

Persistence tests include SQLite trigger aborts during block insertion and before/after insertion of the CometBFT genesis marker, plus child processes terminated inside uncommitted SQLite transactions. Reopening verifies rollback to the original genesis state with no partial block or marker. The suite also checks that a funded-genesis retry after restart is idempotent and a different genesis cannot mutate the persisted state.

Go tests cover IPC request correlation, malformed/mismatched responses, typed errors, partial writes, zero-progress writes, and loopback listener validation. Go static analysis runs in CI.

## Integration matrix

| ID | Scenario | Evidence |
|---|---|---|
| INT-01 | One-node CometBFT startup and block production | PASS, run 42368248709, commit a76cee10 |
| INT-02 | One-node restart with persistent data and resumed block production | PASS, run 42368248709, commit a76cee10 |
| INT-03 | Three validators reach common height | PASS, run 42368248612, commit a76cee10 |
| INT-04 | Funded test genesis and signed transfer | PASS, run 42368248612, commit a76cee10 |
| INT-05 | Matching balances, nonce, and state commitment | PASS, run 42368248612, commit a76cee10 |
| INT-06 | Matching post-transfer CometBFT app hash | PASS, run 42368248612, commit a76cee10 |
| INT-07 | Restarted validator retains transfer and state | PASS, run 42368248612, commit a76cee10 |
| INT-08 | Account and ledger-info queries through all three RPC endpoints | PASS, run 42368248612, commit a76cee10 |
| INT-09 | Signed overspend admitted by weak CheckTx but filtered before proposal commit on all validators | PASS, run 42368248612, commit a76cee10 |
| INT-10 | Identical funded-genesis retry after application restart | PASS, run 42362574022 |
| INT-11 | Conflicting funded-genesis request rejected after restart without state mutation | PASS, run 42362574022 |
| INT-12 | Non-canonical base64 genesis payload rejected without writing marker or allocations | PASS, run 42362574022 |
| INT-13 | Mempool item/byte caps, duplicate accounting, and committed-entry capacity release | PASS, run 42365173568 |
| INT-14 | CheckTx RECHECK rejects stale balance/nonce transactions after commit without mutating state | PASS, Python regression suite run 42365922063 |
| INT-15 | Four-validator quorum continues with one validator stopped; restarted validator catches up and all app hashes agree | PASS, run 42368248630, commit a76cee10; common height 5, app hash 2FA595F9328078EB77A6EE62BDAD3743D619B1371BB82DD78AD0D98FAECC03A9 |

## Latest exact-commit CI evidence

All four workflows completed successfully on code commit `a76cee10eabafc7d27f36dbd66910f0f7feea790`:
- Python tests run `42368248628`: PASS (77 tests).
- One-node CometBFT restart run `42368248709`: PASS.
- Three-validator integration run `42368248612`: PASS; signed transfer, RPC queries, overspend filtering, state/app-hash consistency, and restart recovery.
- Four-validator liveness run `42368248630`: PASS; three validators continued producing blocks while the fourth was stopped, and the restarted validator caught up with matching app hash.

## Remaining adversarial and operational tests

Network partition and healing (distinct from process shutdown), conflicting proposals, equivocation, replayed votes, Byzantine voting-power scenarios, validator crash after signing, validator-set updates, state sync, snapshot integrity, database rollback detection, backup/restore, multi-host deployment, mempool flooding, per-peer quotas, CPU/memory exhaustion, and crash injection around every SQLite commit boundary remain unverified.
