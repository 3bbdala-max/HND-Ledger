# HND-Ledger v0.2 — Reproducible test plan

**Status:** executable unit and integration tests exist and pass in controlled CI. The broader adversarial consensus matrix remains incomplete.

## 1. Evidence rule

A test is PASS only when its executable test, fixture, command, environment, and observed result are tied to an exact source commit. Distinguish passed, failed, skipped, timed out, pending, and not run. A local CI cluster must not be described as independent multi-operator decentralization.

## 2. Verified CI baseline

On commit `1c62d3cad548315b8cecb811edd76ee6b93808af`:

- Python test workflow [42359852666](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42359852666): success.
- Go adapter tests and static analysis [42359852685](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42359852685): success.
- One-node CometBFT block production and restart [42359852690](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42359852690): success.
- Three-validator CometBFT integration [42359852656](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42359852656): success.

The three-validator integration uses funded test-only genesis allocations and one Ed25519-signed transfer. It verifies all three local ledgers, post-transfer application hashes, the CometBFT header app hash at H+1, and validator-0 restart recovery with the committed transfer, balances, and nonce retained.

## 3. Implemented transaction and state tests

The executable Python suite covers:
- Canonical CBOR, valid Ed25519 signatures, tampered signatures, sender/public-key binding, and wrong chain IDs.
- Invalid base64, malformed transaction encodings, invalid amount and nonce types, and bounded transaction batches.
- Self-transfer rejection, insufficient funds, recipient overflow, nonce overflow, stale/replayed nonce, and conflicting same-nonce spends.
- Duplicate transaction rejection and atomic proposal execution.
- Weak CheckTx admission separated from state-dependent proposal validation.
- Genesis allocation ordering, uniqueness, supply cap, idempotent InitChain retry, conflicting genesis rejection, and atomic persistence of genesis state plus marker.
- State commitments that change when chain ID or supply cap changes.
- Deterministic block hashing, parent linkage, corruption detection, canonical storage validation, and replay after restart.

The Go suite covers IPC request/response correlation, malformed or mismatched responses, typed remote errors, partial writes, and zero-progress write rejection. Static analysis is also run.

## 4. Implemented integration tests

| ID | Scenario | Evidence/status |
|---|---|---|
| INT-01 | One-node CometBFT startup and block production | PASS, run 42359852690 |
| INT-02 | One-node restart with persistent CometBFT and SQLite data | PASS, run 42359852690 |
| INT-03 | Three local validators reach a common chain height | PASS, run 42359852656 |
| INT-04 | Funded test genesis and signed transfer through CometBFT RPC | PASS, run 42359852656 |
| INT-05 | All three HND ledgers agree on post-transfer balances, nonce, and state commitment | PASS, run 42359852656 |
| INT-06 | All three CometBFT nodes agree on the post-transfer header app hash at H+1 | PASS, run 42359852656 |
| INT-07 | Restarted validator retains the transfer, balances, nonce, and matching app hash | PASS, run 42359852656 |

These are integration tests on one CI runner, not adversarial multi-host tests.

## 5. Remaining adversarial and operational tests

- Conflicting proposals at the same height/round and proposer equivocation.
- Duplicate, delayed, reordered, and replayed consensus messages.
- Network partitions, packet loss, node downtime, and partition healing.
- Byzantine voting power scenarios under CometBFT's documented fault assumptions.
- Validator key persistence, anti-double-sign behavior, key rotation, and validator-set changes.
- Crash injection immediately before and after SQLite commit, process termination during block persistence, and recovery from interrupted writes.
- Database rollback detection, backup/restore, state sync, snapshot integrity, and software upgrade compatibility.
- Mempool flooding, per-peer quotas, CPU/memory exhaustion, and malformed input under sustained load.
- Multi-host and independently operated validator deployment.

## 6. Release gates

1. Freeze versioned protocol and genesis formats with test vectors.
2. Complete adversarial and crash-injection tests.
3. Define validator admission, key custody, upgrades, backup, and incident response.
4. Run multi-host tests with network faults and independent operators.
5. Complete independent protocol, cryptographic, and application security reviews.
6. Complete economic and jurisdiction-specific legal review before public issuance or distribution.
