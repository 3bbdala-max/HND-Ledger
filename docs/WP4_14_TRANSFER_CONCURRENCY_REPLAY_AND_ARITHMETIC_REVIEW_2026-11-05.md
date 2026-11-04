# HND v0.2 — Transfer concurrency, replay, arithmetic, and deterministic-state review

**Date:** 2026-11-05  
**Workstream:** WP4.14 — Adversarial transfer and state-transition review  
**Branch:** `phase-0.2-planning`  
**Status:** Documentation-only static review. No application code or workflow files changed.

## 1. Executive result

The ABCI application serializes its own state-changing and read methods with a process-local re-entrant lock. Its block execution path applies transactions in a deterministic sequence to temporary ledger copies, and the ledger rejects duplicate transaction IDs, stale nonces, overspending, malformed amounts, and unknown recipients. The current design therefore has useful protections against ordinary replay and conflicting same-account spends when all operations pass through one correctly configured ABCI application.

However, this review found important boundaries that must not be mistaken for complete concurrency or distributed-safety guarantees:

1. The standalone `HNDLedger` itself has no internal lock. Concurrent direct calls to `apply_transaction` are not proven safe.
2. The transaction maximum `max_amount` is supplied separately at process startup, is not included in the Genesis manifest/hash, and is not carried in the ABCI application Genesis payload. Validators configured with different values can disagree about whether the same otherwise-valid transaction is acceptable.
3. Amount and supply values use Python arbitrary-precision integers. The code does not define a protocol-wide maximum supply or portable cross-language integer bound.
4. Existing tests cover sequential replay/conflict behavior and a 2,000-transfer sequence, but the inspected test files do not establish a concurrent stress test, cross-process race test, or heterogeneous-configuration consensus test.

## 2. Source reviewed

Current `phase-0.2-planning` versions of:

- `hnd_v02/ledger.py`
- `hnd_v02/transaction.py`
- `hnd_v02/abci_app.py`
- `hnd_v02/cometbft_v040_server.py`
- `tests/test_v02_ledger.py`
- `tests/test_v02_transaction_envelope.py`
- `tests/test_v02_abci_app.py`

This is static source and test-definition inspection. No test command was run for this report.

## 3. Existing protections observed

### 3.1 Transaction replay and same-account ordering

- A transaction ID is derived from the signed transaction's unsigned payload fields.
- The ledger rejects an already accepted transaction ID.
- Each sender must use the exact expected nonce; accepted transactions increment that sender's nonce.
- The transaction signature binds sender, recipient, amount, network ID, protocol version, and nonce.
- Unknown senders and recipients are rejected; self-transfers are rejected.
- Amount must be an exact positive integer, must not exceed the configured `max_amount`, and must not exceed the sender's balance.

These controls make a previously accepted transaction fail on replay and make two different transactions competing for the same sender nonce conflict when applied in sequence.

### 3.2 ABCI application serialization

The ABCI application wraps `check_tx`, proposal methods, `finalize_block`, `commit`, and account queries with a single `threading.RLock`. `finalize_block` requires the next height and refuses a second pending block before the previous pending block is committed. It executes the decided transaction list in order against temporary ledger copies; only a successful transaction advances the candidate state. `commit` persists and publishes the pending state while holding the same lock.

This is a process-local serialization mechanism for calls through that application instance. It is not a distributed lock, and it does not protect callers that directly share a standalone `HNDLedger` instance outside the ABCI wrapper.

### 3.3 Deterministic block handling

- Transaction byte payloads are required to be canonical JSON objects.
- A block is limited to 1,000 transactions by the application.
- `process_proposal` validates the ordered transaction list against a clone of the committed ledger without mutating committed state.
- `finalize_block` uses ordered execution and records per-transaction success/failure.
- Snapshots are reconstructed from Genesis and transaction history rather than accepting serialized balances as authoritative.

These are meaningful local determinism controls, but do not alone prove that every validator runs with identical protocol configuration or software.

## 4. Findings requiring remediation or explicit protocol decisions

| ID | Severity | Finding | Required control |
|---|---|---|---|
| CONC01 | Critical | `max_amount` is a CLI/process configuration value, not committed in the Genesis manifest or ABCI Genesis payload. Different validator settings can produce different transaction validity decisions. | Move every consensus-critical monetary parameter into a versioned, authenticated protocol configuration bound to Genesis; reject startup on mismatch. |
| CONC02 | High | Standalone `HNDLedger.apply_transaction` has no internal synchronization. | Make the ledger explicitly single-thread-confined or add an internal lock / atomic state-transition contract; test simultaneous conflicting submissions. |
| CONC03 | High | No protocol-wide upper bound is defined for `total_supply`, allocation amounts, or balances. Python integers do not overflow, but other implementations may use bounded integer types. | Define portable integer widths and maximum supply; reject out-of-range Genesis, transfers, and state values identically in every implementation. |
| CONC04 | High | ABCI's process-local lock does not protect multiple application processes sharing the same state file. No file-lock or single-writer deployment invariant is implemented here. | Enforce one application process per state directory or add an OS-level single-writer/locking design and crash-safe tests. |
| CONC05 | Medium | Existing replay/conflict tests are sequential. They do not establish behavior under true concurrent calls or races between independent application instances. | Add barrier-synchronized concurrency tests and multi-process tests; assert one valid spend, one nonce advance, and invariant preservation. |
| CONC06 | Medium | `max_amount` is only a per-transaction cap; it is not a maximum supply or a guarantee against configuration drift. | Document distinct meanings and test both configuration identity and monetary bounds. |
| CONC07 | Medium | The app accepts transaction byte lists up to 1,000 items and a caller-provided proposal byte budget; no aggregate protocol-wide economic limit is defined here. | Bind byte and transaction limits to the versioned consensus configuration and test identical rejection at all validators. |
| CONC08 | Medium | A transfer's recipient must already be registered from Genesis; no account-creation path exists. | Explicitly decide whether this is a deliberate closed account registry or design a deterministic registration operation. |

## 5. Required acceptance tests (not yet executed)

- **TCON01 — Same nonce race:** submit two differently signed transfers from one sender with the same nonce concurrently. Exactly one may commit.
- **TCON02 — Same transaction replay race:** submit identical signed bytes concurrently. At most one acceptance/commit may occur.
- **TCON03 — Conflicting recipients:** same sender and nonce, different recipients and amounts; all validators must select the same committed result for the same decided block.
- **TCON04 — Direct ledger concurrency:** either prove/document single-thread confinement or demonstrate safe concurrent `apply_transaction` behavior.
- **TCON05 — Multi-process state directory:** two processes must not silently overwrite each other's committed state.
- **TCON06 — Configuration mismatch:** start two nodes with different `max_amount` values and confirm startup fails before consensus, after the parameter is bound to Genesis.
- **TCON07 — Numeric boundaries:** test zero, negative, maximum allowed, one above maximum, maximum supply, and out-of-range allocation values.
- **TCON08 — Long sequence and restart:** execute a large deterministic sequence, persist, restart, replay, and compare balances, nonces, total supply, and application hash.
- **TCON09 — Proposal order:** permute conflicting transactions and verify the documented ordered-execution semantics; no node may independently reorder the decided block.
- **TCON10 — Cross-implementation vectors:** run identical Genesis and transaction vectors through at least two independent implementations and compare accept/reject decisions and state hashes.

## 6. Recommended implementation order

1. Resolve **CONC01 first**: consensus-critical configuration must be identical and authenticated before validator agreement can be relied upon.
2. Specify portable integer bounds and maximum supply; include them in the versioned Genesis/protocol configuration.
3. Establish a single-writer guarantee for the state directory and a thread-safety contract for the standalone ledger.
4. Add the concurrency, configuration-mismatch, numeric-boundary, and multi-process acceptance tests.
5. Run the tests in the authorized Python 3.12 environment and record exact commit, command, and output. Do not infer test success from test definitions.

## 7. Evidence and release boundary

- No test command was executed during this review.
- No application code or CI workflow was modified.
- This report does not establish formal determinism, distributed race safety, or production readiness.
- Public network, token distribution, and production release gates remain **CLOSED**.
