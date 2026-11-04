# HND v0.2 — Concurrency, host fencing, and signer-readiness review

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Status:** Static source review and test specification only  
**Reviewed source:** `hnd_v02/anti_rollback_reference.py` and `tests/test_v02_anti_rollback_reference.py`  
**Safety boundary:** Offline synthetic model only. No production signer or distributed anchor is connected.

## 1. Scope

Reviewed the anchor lock, compare-and-swap transition, host epoch fencing, model-level prepare/commit sequencing, and `signing_allowed` read path. Existing tests were inspected but not executed during this review.

## 2. Positive controls observed

1. `SyntheticAnchor.compare_and_swap` holds the anchor lock while checking availability, host identity/epoch, sequence, predecessor digest, HRS progression, and applying the record transition. The state transition itself is atomic within this in-memory object.
2. `fence_host` increments the epoch and changes the active host while holding the same lock used by compare-and-swap.
3. `prepare` and `commit` perform an anchor-side host/epoch check before their transition. Even if the model's earlier host check becomes stale, the anchor-side compare-and-swap rejects the stale epoch.
4. Existing tests cover simultaneous prepare attempts from a shared predecessor, stale host rejection, stale model instances, fencing at the compare-and-swap boundary, and a stale host attempting to commit after takeover.

These controls establish only in-process behavior of this synthetic anchor. They do not establish distributed consensus, durable fencing, or protection against a compromised anchor host.

## 3. Findings

### T01 — Signer-readiness check has a time-of-check/time-of-use race

`signing_allowed` reads the latest anchor record, validates it, reads the local generation, and then checks whether the host is current. These reads are not one atomic authorization operation.

Two relevant interleavings are possible:

- The method reads committed record A. Another valid operation commits record B. The first method can still return `True` based on its earlier snapshot of A.
- The method confirms that host H is current. A takeover fences H immediately after that check. The method can still return `True` to its caller.

**Impact:** a boolean readiness result can become stale before the caller uses it. The method is a snapshot check, not a linearizable authorization to perform a particular signing operation.

**Required design:** move the final authorization decision to a trusted signing boundary that atomically validates the current anchor version and host fencing token for the specific signing request. Use a short-lived, single-use authorization bound to the exact network/genesis/validator/signer identity, HRS, state/commit digest, operation ID, and anchor sequence. The signer must reject stale sequence or epoch tokens at the point of use. If the anchor cannot provide an atomic or equivalent fenced authorization primitive, fail closed and do not claim race-free signing.

A repeated check immediately before signing narrows but does not eliminate the race unless the signer/anchor protocol makes the check and use indivisible or cryptographically binds the authorization to a monotonic fencing token enforced by the signer.

### T02 — A later PREPARED operation can invalidate an earlier readiness snapshot

The anchor currently permits a new operation ID to be prepared after a previous operation is COMMITTED. Once the new PREPARED record becomes the latest anchor record, `signing_allowed` should return false for a fresh read. However, a concurrent caller that already read the previous COMMITTED record can still finish its readiness check and return true.

This is the concrete record-transition version of T01. It also reinforces the already documented rule that a PREPARED record disables signing immediately.

**Required regression test:** pause a readiness check after it reads committed A; prepare B so B becomes the latest PREPARED anchor record; resume the check. The current implementation may return true from the stale A snapshot. The corrected authorization design must reject the request because B is now latest and PREPARED.

### T03 — Host fencing is atomic at anchor transition, not at external signing use

The anchor prevents an old epoch from changing its state after takeover. The model's `signing_allowed` check, however, only samples host-current status. It does not issue a fencing token that an external signer must enforce for every signing operation.

**Required design:** the signer must persist or otherwise enforce the greatest accepted epoch and reject all lower epochs. Epoch acquisition, takeover, and signing authorization must have a defined linearization point. Merely checking `host_is_current` in application code is insufficient for an external signing process.

### T04 — The synthetic concurrency test does not prove distributed race safety

The existing simultaneous-prepare test coordinates two readers and checks that one compare-and-swap wins. This is useful evidence for the in-memory lock/CAS behavior, but it does not test process crashes, separate anchor replicas, network partitions, delayed authorization, or a signer using a stale readiness result.

**Required expansion:** add deterministic interleaving tests for readiness versus commit, readiness versus takeover, and authorization versus actual signer use. A future distributed implementation also needs multi-process and fault-injection tests against its real anchor and signer boundary.

## 4. Required regression tests

| ID | Controlled interleaving | Required result |
|---|---|---|
| TST01 | Readiness reads committed A; B becomes PREPARED before readiness returns | No authorization for A |
| TST02 | Readiness validates old host epoch; takeover occurs before signing use | Signer rejects old epoch |
| TST03 | Authorization issued for sequence N; anchor advances to N+1 before use | Signer rejects stale sequence |
| TST04 | Anchor unavailable during final authorization | Unknown/blocked; no signing |
| TST05 | Two concurrent transitions race at CAS | At most one transition succeeds from a given predecessor |
| TST06 | Old host resumes after takeover and presents a previously issued token | Token rejected by signer-side epoch enforcement |
| TST07 | PREPARED transition races with signing authorization | PREPARED state wins or authorization is otherwise atomically ordered; no ambiguous permission |
| TST08 | Host takeover races with a new operation transition | Anchor enforces one monotonic order; stale epoch cannot commit |

The tests must use barriers/hooks at explicit decision boundaries, not timing sleeps. They must record the anchor sequence, epoch, operation ID, signer decision, and whether any signature operation was actually reached.

## 5. Recommended implementation order

1. Define a linearizable authorization contract for the signer, including exactly when an authorization becomes valid and invalid.
2. Bind authorization to operation ID, anchor sequence, host epoch, identity tuple, HRS, and state digest.
3. Enforce the monotonic epoch and sequence at the signer boundary, not only in the model caller.
4. Ensure PREPARED immediately blocks new authorization and invalidates any authorization not yet consumed.
5. Implement deterministic interleaving tests TST01–TST08.
6. Repeat the tests against the actual multi-process/durable implementation with crash, partition, failover, and delayed-message injection.

## 6. Evidence and release status

This review did not modify source code and did not execute tests. T01–T04 are source-review findings; TST01–TST08 are proposed regression tests, not test results.

The existing in-memory lock and fencing tests are useful model-level controls but are not evidence of production-grade distributed fencing or race-free signing. Production signing, custody, and release authorization remain prohibited until the signer-boundary protocol is implemented, independently reviewed, and verified.
