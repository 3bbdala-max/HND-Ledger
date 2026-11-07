# HND-Ledger Version 0.2 — Reproducible Test Plan

**Status:** Test specification only; no executable tests are claimed by this document.
**Scope:** Deterministic local ledger first. Distributed consensus and multi-validator claims remain gated.

## 1. Evidence rule

A test is PASS only when its executable test, fixture, command, environment, and captured result are committed or otherwise reproducibly archived. A design checklist or simulated narrative is not a test result. Never report a test as passed merely because its expected behavior is documented.

Each test record must include:
- stable test ID;
- exact software/runtime and dependency versions;
- deterministic fixture and seed where applicable;
- command used to run the test;
- expected result and observed result;
- exit code and artifact/log reference;
- commit SHA containing the tested code.

## 2. Local transaction validation

| ID | Scenario | Required outcome |
|---|---|---|
| TX-001 | Valid canonical transaction and signature | Accept once |
| TX-002 | Modified signed payload | Reject; state unchanged |
| TX-003 | Wrong network identifier | Reject; state unchanged |
| TX-004 | Sender does not match signing key | Reject; state unchanged |
| TX-005 | Zero, negative, malformed, or overflowing amount | Reject; state unchanged |
| TX-006 | Stale or repeated nonce | Reject; state unchanged |
| TX-007 | Future nonce / skipped sequence | Apply the explicitly selected protocol rule |
| TX-008 | Insufficient balance | Reject; state unchanged |
| TX-009 | Repeated transaction identifier | Reject duplicate |
| TX-010 | Same transaction submitted concurrently | At most one acceptance |
| TX-011 | Replay on a different network | Reject |
| TX-012 | Malformed or oversized input | Reject safely without crash or unbounded resource use |

## 3. State-transition invariants

- Rejected transactions cause no partial state mutation.
- Account balances never become negative.
- Total supply changes only through explicitly authorized genesis/issuance/burn rules.
- All arithmetic uses bounded integer smallest units; overflow is rejected.
- Transaction application is deterministic for identical prior state and ordered inputs.
- A block is committed atomically or not committed at all.

## 4. Block and persistence tests

| ID | Scenario | Required outcome |
|---|---|---|
| BLK-001 | Valid parent link and next height | Accept |
| BLK-002 | Wrong parent or height | Reject |
| BLK-003 | Tampered block contents/hash | Reject |
| BLK-004 | Invalid transaction commitment | Reject |
| BLK-005 | Duplicate transaction in block | Reject |
| BLK-006 | Invalid state transition | Reject; prior state unchanged |
| DB-001 | Restart after valid commit | Recover identical state |
| DB-002 | Truncated record | Detect corruption; do not silently accept |
| DB-003 | Interrupted write | Recover last valid committed state |
| DB-004 | Corrupted snapshot | Reject or rebuild from validated ledger |
| DB-005 | Ledger/state mismatch | Detect and fail closed or rebuild deterministically |

## 5. Validator and consensus gate

No distributed-validator test is meaningful until a consensus protocol is selected and specified, including validator admission, quorum, fault assumptions, proposal/vote formats, timeouts, finality, equivocation handling, and partition recovery.

After that gate, tests must include:
- independent processes with independently generated validator keys;
- verified distinct operator/process identities and network endpoints;
- valid quorum and insufficient-quorum cases;
- duplicate vote and replay rejection;
- conflicting proposals at the same height/round;
- double-sign/equivocation evidence and deterministic response;
- Byzantine and offline validator cases within the documented fault model;
- network delay, loss, reordering, and partition/rejoin;
- restart and state synchronization;
- safety checks that no two conflicting blocks are finalized;
- liveness checks only under explicitly stated synchrony and availability assumptions.

A local process simulation must be labelled simulation, not independent decentralization.

## 6. Release gates

1. Protocol decisions are approved and versioned.
2. Implementation and dependency manifest are committed.
3. Unit, integration, and adversarial tests are executable in clean CI.
4. Reproducible local-ledger results are archived.
5. Consensus is separately specified and threat-modelled before coding.
6. Multi-validator tests run across independent processes/operators and produce verifiable evidence.
7. Independent security review and jurisdiction-specific legal review precede any public deployment or token-related activity.

## 7. Current status

At the time this plan is added, the repository is a documentation baseline. No executable implementation, CI test run, independent validator deployment, or production audit is asserted.