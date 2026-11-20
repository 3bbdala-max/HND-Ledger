# P0 Signer Fencing — Option A Prototype Decision Record

**Date:** 2026-11-20  
**Status:** OWNER RECOMMENDATION FOR DISPOSABLE PROTOTYPE ONLY — NOT PRODUCTION RATIFICATION  
**Baseline:** `phase-0.2-planning` at `113aa400cf0b3255a9123250a98b0eb543d1b9ac`  
**Design branch:** `work/p0-signer-fencing-design`  
**Tracking:** Issue #52; draft PR #53

## 1. Decision

Recommend **Option A — drain durably admitted signing operations before ownership-transfer commit** for the next disposable-key prototype.

This is a conservative prototype policy, not a claim that Option A is already implemented or independently security-approved. Production signing, real validator keys, public deployment, token issuance, and release remain blocked.

## 2. Why Option A for the prototype

Option A gives the prototype an explicit and inspectable ordering rule:

- A signing request is admitted only after a durable record binds its stable request ID, full signer identity scope, owner, fencing epoch, canonical sign-bytes digest, and H/R/S slot.
- A transfer request may begin while signing is in flight, but the new epoch cannot commit until every operation admitted under the old epoch reaches a durable terminal state.
- Signature bytes are releasable only after the exact signature result and corresponding anti-double-sign H/R/S state are durably committed.
- If a key operation may have occurred but its durable result is unknown, the operation becomes UNKNOWN. The transfer remains blocked until the same request ID is reconciled. No replacement request ID or conflicting signature is allowed.

The main trade-off is deliberate: a failed or unreachable signer may block ownership transfer indefinitely. For a safety-first prototype, loss of availability is preferable to committing a new owner while an old admitted operation may still release a signature.

## 3. Required prototype state machine

Each signer identity scope must have one durable ownership epoch and an operation ledger.

An operation moves through:

`RECEIVED -> ADMITTED -> KEY_OPERATION_PENDING -> COMMITTED`

Permitted terminal alternatives are:

- `SAFELY_ABORTED`: only when the key boundary proves that no signature was produced or released.
- `UNKNOWN_BLOCKED`: key operation or durable commit may have happened, but the exact result cannot yet be proven. This state is non-terminal for transfer purposes.

Transfer moves through:

`REQUESTED -> DRAINING -> COMMITTED(epoch + 1)`

Transfer must not reach COMMITTED while any old-epoch operation is ADMITTED, KEY_OPERATION_PENDING, or UNKNOWN_BLOCKED.

## 4. Required crash behavior

| Crash point | Required recovery |
|---|---|
| Before durable admission | No signature is authorized; request may be resubmitted under documented rules |
| After admission, before key operation | Reconcile the same request ID; prove safe abort or continue it |
| During/after key operation, before durable result | UNKNOWN_BLOCKED; keep transfer pending; reconcile the same request ID |
| After durable signature and H/R/S commit, before response | Return the exact committed result for the same request ID |
| After transfer commit | Reject every old-epoch request at the actual key-release boundary |

An UNKNOWN_BLOCKED operation must never be treated as safely aborted merely because a timeout elapsed or a process restarted.

## 5. Non-negotiable architecture boundary

The prototype must use disposable keys and a protected signing boundary. A validator host holding a raw local consensus private key cannot be considered fenced by a remote lease, database row, cached epoch, startup check, or preflight response.

The authority and key-release mechanism must ensure that transfer cannot commit around an admitted old-epoch operation. A local mutex, `flock`, or caller-side check is not distributed fencing.

## 6. Acceptance tests before advancing

1. **SIGN-WINS:** admit A's request; request transfer to B; prove B's epoch cannot commit until A's exact signature and H/R/S result are durable.
2. **TRANSFER-BEFORE-ADMISSION:** commit transfer first; prove A is rejected before key use.
3. **CRASH-AFTER-KEY:** crash after the key operation but before durable result; prove transfer remains blocked and same-request reconciliation is required.
4. **CRASH-AFTER-COMMIT:** crash after durable commit but before response; prove retry returns the exact committed result.
5. **UNKNOWN-NEVER-ABORT:** prove an ambiguous operation cannot be force-cleared by timeout, restart, or operator convenience.
6. **STALE-OWNER:** after transfer commits, prove A cannot release a signature, including after reconnect or snapshot restore.

All tests must use disposable keys and clearly label evidence as MODEL, UNIT, PROCESS, MULTI_HOST, KEY_BOUNDARY, or COMETBFT. No test may claim a stronger evidence level than the environment actually exercised.

## 7. Remaining independent approvals

This recommendation does not resolve production governance. Before production implementation or approval, independent protocol/security owners must ratify:

- authority replication and quorum/failover model;
- enrollment, transfer, takeover, revocation, and emergency recovery authority;
- key custody and non-bypassable release enforcement;
- durable operation-ledger and H/R/S recovery design;
- multi-host partition and disaster-recovery evidence;
- audit, monitoring, and incident-response requirements.

Option B is not selected for this prototype. It may be reconsidered only if a protected key service can demonstrate one genuinely linearizable signing/transfer boundary; wrapping a separate HSM call in an ordinary database transaction is not sufficient.

## 8. Model artifact and evidence status

A separate MODEL-only reference test file has been added:
`tests/test_p0_signer_option_a_model.py`.

It covers deterministic sign-wins/drain ordering, transfer-before-admission, UNKNOWN_BLOCKED after a simulated key operation, reconciliation using an externally supplied exact-result fixture, and request-ID idempotency/payload mutation rejection.

**Execution status:** NOT RUN in this work session. The file is source only; no test result is claimed. It uses in-memory state and synthetic byte markers, so even a passing run would establish MODEL behavior only. It does not demonstrate durable storage, cryptography, process-crash recovery, distributed coordination, a protected key boundary, or CometBFT integration.

## 9. SQLite persistence-model artifact and local check

Added `tests/test_p0_signer_option_a_sqlite_model.py`, a SQLite-backed, single-process MODEL-only prototype. It persists ownership epoch, transfer target, admitted operation identity, operation status, and synthetic result bytes. Its five test cases cover transfer drain across reopen, UNKNOWN_BLOCKED persistence/reconciliation across reopen, idempotent retry during drain, committed-result retry after reopen, and request-ID payload-reuse rejection.

A separate local Python/SQLite harness exercising the same five state-transition scenarios completed **5/5 passing** in this work session. This was not execution of the checked-in repository test file: the repository could not be cloned into the local runtime because outbound GitHub access was unavailable. The checked-in test file itself remains **NOT RUN**, and no GitHub Actions run was triggered. The local harness is supporting model evidence only, not repository CI evidence.

The SQLite model still has no real cryptographic key operation, no independent verification of reconciliation evidence, no durable external key-service journal, no multi-process/multi-host authority, no process-kill fault injection at the actual key boundary, no H/R/S consensus integration, and no CometBFT integration. SQLite transaction serialization in one local database does not prove distributed linearizability or production fencing.

## 10. Release gate

This record authorizes no production signing, no use of real keys or funds, no public network launch, no token issuance, and no merge to the main branch. The draft PR remains open for independent review. The next permitted engineering step is a disposable-key prototype and deterministic tests on the work branch, after review of this decision record.


## 11. Independent-connection contention cases (source added; not executed)

The SQLite test file now includes three additional MODEL-only cases using separate SQLite connections to the same database file:

- Admission-first: one connection durably admits an operation; another starts transfer; transfer commit remains blocked until the first connection commits the synthetic result.
- Transfer-first: one connection begins transfer; a second connection's new old-owner admission is rejected; after transfer commits, stale admission remains rejected.
- Writer-lock contention: a held `BEGIN IMMEDIATE` on one connection prevents a second connection from acquiring a writer transaction until the first rolls back.

These cases exercise SQLite's local database transaction boundary and independent-connection visibility. They do **not** constitute a barrier-controlled end-to-end race between an actual key operation and ownership transfer, process-kill fault injection, multi-process key custody, or multi-host linearizability. In particular, the lock-contention case uses a short SQLite busy timeout and checks the database's writer-lock behavior directly; it is not evidence of a distributed signer fence.

**Execution status:** The three new checked-in tests are **NOT RUN**. No GitHub Actions run was triggered. The earlier separate 5/5 equivalent local harness result applies only to the five prior state-transition scenarios and must not be extended to these additions or treated as execution of the repository test file.

**Next gate:** Run the exact repository test file in a controlled local environment, then add a deterministic process-level crash schedule around the key-operation/result-commit boundary. Keep the PR draft and production signing blocked.


## 12. Child-process exit and reopen case (source added; not executed)

Added one subprocess test to the SQLite model suite. A child Python process writes an operation's `KEY_OPERATION_PENDING` marker durably, then exits immediately via `os._exit` without closing the SQLite connection. The parent reopens the database and verifies that the pending state remains present and blocks ownership transfer.

This is process-level evidence for persistence of the already-committed pending marker across abrupt process exit. It does **not** simulate a cryptographic key operation occurring before the crash, prove whether a signature escaped the key boundary, or validate independent reconciliation evidence. It must not be described as a crash-after-key test.

**Execution status:** This subprocess test, like the three independent-connection additions, is **NOT RUN** in this work session. No manual Actions rerun was requested or performed. Any automatically triggered workflow result must be inspected against its exact head SHA and actual job steps before being treated as test evidence.


## 13. Unknown-state retry and reconciliation-conflict cases (source added; not executed)

Added two further MODEL-only tests:

- An `UNKNOWN_BLOCKED` request cannot be restarted as a fresh key operation and cannot be committed through the synthetic-signature path. It remains blocked pending reconciliation.
- Reconciliation of an already committed request is idempotent only for the exact previously stored result; conflicting result bytes are rejected.

These tests check state-machine behavior only. They do not authenticate the party supplying reconciliation evidence. The model's `reconcile_committed` method still accepts caller-supplied non-empty bytes as fixture evidence; a production implementation must replace this with independently verifiable evidence from the protected key boundary or a trusted durable key-service journal. Never treat caller-provided bytes as proof that a signature was or was not emitted.

**Execution status:** Both tests are added to the branch but **NOT RUN**. No manual workflow rerun was initiated.


## 14. Verifier-gated reconciliation interface (source added; not executed)

The SQLite model's reconciliation method now requires an injected verifier callable. The verifier receives the request ID, owner, epoch, payload digest, and exact evidence bytes. Reconciliation remains blocked unless the verifier returns the literal boolean `True`; the stored operation identity is read under the SQLite write transaction before verification and update. Two MODEL-only tests cover verifier rejection and binding the evidence check to the complete operation identity. Existing reconciliation tests now use explicit fixture verifiers.

This is an interface-level improvement, **not an implemented trust root**. The repository still contains no production verifier, protected-key-service protocol, authenticated journal, certificate/signature validation, anti-replay proof, or independent authority configuration. A test lambda returning `True` proves only that the state machine obeys its injected decision. It does not prove the decision is trustworthy. Calling arbitrary verifier code while holding a SQLite write transaction is also a prototype simplification and must not be carried into a production architecture without a bounded, authenticated protocol and concurrency review.

**Execution status:** The updated reconciliation tests and the complete 13-test SQLite file are **NOT RUN**. No Actions rerun was initiated. The branch remains a draft and no production signing or merge is authorized.


## 15. Verification outside the SQLite write lock (source added; not executed)

Moved the injected verifier call outside the SQLite `BEGIN IMMEDIATE` write transaction to avoid holding the database writer lock across potentially slow or remote verification. The model now reads the operation identity/state, asks the verifier to check the evidence against request ID, owner, epoch, digest, and result bytes, then opens a write transaction and rechecks the identity and state before committing. A changed identity or incompatible state fails closed.

This reduces lock-hold risk in the prototype; it does not solve distributed races or establish a trusted verifier. Production still needs an authenticated, replay-resistant evidence protocol and a protected key boundary. The verifier implementation remains absent.

**Execution status:** The full 13-test SQLite file, including the verifier-gated cases and this lock-boundary refactor, is **NOT RUN**.

## 16. CI observation for the preceding commit

GitHub Actions created run `44801387264` for preceding commit `7aa2cf1f80291f9a001255a68def3b5dbb3aaefc`. The `hnd-v02-tests` job completed with `failure`; `cometbft-single-node-smoke` completed with `skipped`. Both jobs reported **zero steps**, so this is not evidence of a test assertion failure or of test execution. The run is not for the current source commit `2679d360b614b2ead08f2ed3ab6ba67399629a49`. No manual rerun was initiated.


## 17. Separate external-key-journal crash-recovery model (source added; not executed)

Added `IndependentKeyJournalModel`, backed by a second SQLite database separate from the ownership/operation database. Its `execute_once` operation binds a request ID to owner, epoch, and payload digest; a retry with the same identity returns the one persisted synthetic result, while reuse with a different identity is rejected.

Added a subprocess test that:
1. Durably admits a request and marks `KEY_OPERATION_PENDING` in the main database.
2. Writes a synthetic result to the separate key-journal database.
3. Exits abruptly with `os._exit` before the main database records the result.
4. Reopens both databases, confirms the main request is still pending, retrieves the journal result, and verifies the evidence against request ID, owner, epoch, and digest.
5. Retries the journal request and confirms it returns the exact same result with one journal row, then reconciles the main database and completes the ownership transfer.

This is a more faithful crash-window **model** than the earlier pending-marker-only test. It demonstrates a possible recovery protocol when an independent journal durably records an idempotent operation before the caller crashes. It still uses two local SQLite files on one machine, synthetic result bytes, and a test verifier that reads the model journal. It does not establish cryptographic signing, remote durability, tamper resistance, authenticated service identity, multi-host consistency, key isolation, or a production-grade exactly-once guarantee. The journal itself is not independently protected against an attacker who can alter its database.

**Execution status:** The new subprocess crash-recovery test and the full SQLite model test file are **NOT RUN**. No manual Actions rerun was initiated.



## 18. Protected key-service protocol contract (design added; not implemented)

Added `docs/P0_PROTECTED_KEY_SERVICE_PROTOCOL_CONTRACT.md`. It specifies a design-only request envelope, durable key-service journal states, `SignOnce` and `GetOutcome` behavior, transfer fencing, attestation-bound reconciliation, anti-replay and anti-rollback requirements, and a crash/partition failure matrix.

The contract requires the protected key boundary to serialize epoch authorization and signature release with ownership transfer. It explicitly rejects caller-supplied bytes, timeouts, ordinary database rows, and cached leases as proof. UNKNOWN remains blocked unless the exact original outcome is recovered and authenticated.

This is a written contract only. No service implementation, authenticated transport, key custody, cryptographic attestation, journal protection, anti-rollback mechanism, multi-host consistency, or real key-boundary test has been added. The contract does not establish exactly-once execution or production readiness.

**Execution status:** Documentation-only change. No test was run by this documentation change. The existing SQLite model suite remains unexecuted in the repository environment.


## 19. CI observation for protocol-contract commit

GitHub Actions run `44802206935` was associated with the protocol-contract commit `02599868441135a7a5debb5176ed556b9d065707`. The `hnd-v02-tests` job completed with `failure`; `cometbft-single-node-smoke` completed with `skipped`. The job response contained no step records, so this observation does not identify a test assertion failure and does not prove that repository tests executed. No manual rerun was initiated.

The failure is associated with this exact commit and must not be represented as a failure of the newly written protocol document's content. The CI initialization/configuration failure remains unresolved pending actionable job logs or step-level evidence.
