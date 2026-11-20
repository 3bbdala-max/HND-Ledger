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

## 8. Release gate

This record authorizes no production signing, no use of real keys or funds, no public network launch, no token issuance, and no merge to the main branch. The draft PR remains open for independent review. The next permitted engineering step is a disposable-key prototype and deterministic tests on the work branch, after review of this decision record.
