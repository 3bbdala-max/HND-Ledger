# HND-Ledger v0.2 — Reproducible test plan

## Evidence rule

A result is PASS only when the test, source commit, workflow run, and observed result are linked. Distinguish pass, fail, skipped, timed out, pending, and not run. Three processes on one CI runner are not independent operators.

## Verified CI evidence

Baseline on commit 1c62d3cad548315b8cecb811edd76ee6b93808af:
- Python suite run 42359852666: PASS.
- Go adapter tests/static analysis run 42359852685: PASS.
- One-node CometBFT restart run 42359852690: PASS.
- Three-validator signed-transfer integration run 42359852656: PASS.

Strengthened integration on commit a6c5250905d0861c5d3a62dd766d957742080b1c:
- Python suite run 42360521258: PASS.
- One-node CometBFT restart run 42360521260: PASS.
- Three-validator signed transfer, RPC queries, app-hash comparison, and restart recovery run 42360521298: PASS.

The three-validator run committed one signed transfer at height 4, checked all local ledger balances and nonces, queried account and ledger info through each node's CometBFT RPC, compared the post-transfer CometBFT header app hash at height 5, restarted validator 0, and verified the persisted transfer, balances, nonce, and common app hash.

## Unit test coverage

Python tests cover canonical CBOR, Ed25519 verification, chain separation, malformed encodings, replay, nonce gaps/conflicts/overflow, self-transfer, overspend, balance overflow, supply cap, duplicate transactions, atomic proposals, genesis validation/idempotence, atomic genesis marker persistence, state commitment coverage, block hashes, SQLite restore/replay, IPC validation, and read-only Query responses.

Go tests cover IPC request correlation, malformed/mismatched responses, typed errors, partial writes, zero-progress writes, and loopback listener validation. Go static analysis runs in CI.

## Integration matrix

| ID | Scenario | Evidence |
|---|---|---|
| INT-01 | One-node CometBFT startup and block production | PASS, 42360521260 |
| INT-02 | One-node restart with persistent data | PASS, 42360521260 |
| INT-03 | Three validators reach common height | PASS, 42360521298 |
| INT-04 | Funded test genesis and signed transfer | PASS, 42360521298 |
| INT-05 | Matching balances, nonce, and state commitment | PASS, 42360521298 |
| INT-06 | Matching post-transfer CometBFT app hash at H+1 | PASS, 42360521298 |
| INT-07 | Restarted validator retains transfer and state | PASS, 42360521298 |
| INT-08 | Account and ledger-info queries through all three CometBFT RPC endpoints | PASS, 42360521298 |

## Remaining adversarial and operational tests

Conflicting proposals, equivocation, replayed votes, network partitions/healing, Byzantine voting-power scenarios, validator crash after signing, validator-set updates, state sync, snapshot integrity, database rollback detection, backup/restore, multi-host deployment, mempool flooding, per-peer quotas, CPU/memory exhaustion, and crash injection around SQLite commit.
