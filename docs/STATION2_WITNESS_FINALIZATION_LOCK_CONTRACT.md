# Station 2 — Witness Finalization Lock Contract

Status: DRAFT — implementation and independent review required
Applies to: `station2-witness-backend-interface`
Scope: witness ACK issuance, pending-operation exclusion, etcd finalization, recovery

## 1. Security objective

The witness MUST NOT issue an ACK for a second activation while an earlier ACK remains unresolved. An ACK is an immutable statement about one activation; it is not permission to advance another activation or to start the network.

The lock is a safety invariant, not a timeout lease. Expiry, process restart, loss of a response, or operator intervention MUST NOT release it.

## 2. Required durable witness state

The witness backend MUST persist one globally exclusive unresolved-operation record, transactionally with the receipt and counter:

- `activation_id`
- `activation_digest`
- `receipt_digest`
- exact immutable signed receipt
- `witness_id`
- `config_epoch`
- `witness_counter`
- `anchor_checkpoint_digest` and `anchor_sequence`, when anchor binding is integrated
- state: `ACK_ISSUED`, `ETCD_FINALIZED`, `COMPLETED`, or `ABORTED`
- terminal evidence digest, when terminal

The backend MUST enforce at most one operation in `ACK_ISSUED` or `ETCD_FINALIZED`. This invariant MUST be enforced in the durable transaction, not only in an in-memory coordinator lock.

## 3. ACK issuance

For `acknowledge(activation_id, activation_digest)`:

1. Validate identifiers and digest using strict types and canonical formats.
2. Begin a serializable/linearizable write transaction.
3. If the same activation ID and digest already own the unresolved slot, return the exact original receipt and counter.
4. If the activation ID exists with a different digest, reject as conflict.
5. If another activation owns the unresolved slot, reject with a stable pending-operation error; do not allocate a counter or sign.
6. Otherwise allocate the next counter, create the immutable receipt, persist the receipt and unresolved slot atomically, and commit.
7. Only after durable commit may the receipt be returned.

No wall-clock expiry or automatic stale-lock deletion is permitted.

## 4. Binding to the anchor

Before etcd finalization is authorized, the finalizer MUST verify the witness receipt and query the independent anchor's current state. The anchor checkpoint MUST commit to the exact `activation_id`, `activation_digest`, `receipt_digest`, witness identity, configuration epoch, counter, network identity, genesis identity, and predecessor checkpoint.

The finalizer MUST reject if the anchor is unavailable, behind, ahead in a conflicting way, or cannot prove that the exact checkpoint is current. A signed historical proof alone is insufficient.

The witness lock MUST retain the exact anchor checkpoint identity associated with the receipt. Re-ACK or recovery MUST NOT create a replacement receipt or advance the counter for the same activation.

## 5. etcd finalization evidence

The witness MUST NOT mark an operation complete merely because the coordinator supplies a boolean or an untrusted digest.

Completion requires independently verifiable evidence that the exact etcd intent is `finalized`, including:

- etcd cluster/deployment identity pinned by witness policy
- exact intent key and activation ID
- activation digest and exact witness receipt digest
- finalized state
- etcd transaction/revision evidence sufficient for the configured read/consistency policy

Preferred implementation: the witness-side completion verifier performs an authenticated read of the authoritative etcd record using read-only credentials and validates the full canonical record. If a signed finalizer attestation is used instead, its key, role, revocation, and binding to the exact etcd cluster and record MUST be independently governed; it MUST NOT be the witness or anchor key.

After verifying evidence, the witness atomically changes `ACK_ISSUED` to `ETCD_FINALIZED`, storing the evidence digest. A separate idempotent operation changes `ETCD_FINALIZED` to `COMPLETED` only after the anchor and witness records agree on the same activation and checkpoint.

## 6. Crash and retry rules

- Crash before ACK commit: no receipt may have escaped; retry may issue the first receipt.
- Crash after ACK commit but before response: retry returns the exact original receipt.
- Crash before etcd CAS: retain the lock; retry the same activation only.
- etcd CAS succeeds but response is lost: read the same intent key and accept only an exact finalized record.
- etcd is finalized but witness completion was not recorded: reconcile the exact etcd record and complete the same operation; do not issue another ACK.
- Anchor or etcd unavailable: retain the lock and fail closed.
- Any identity, digest, counter, epoch, or checkpoint mismatch: quarantine; do not guess or repair automatically.

## 7. Abort semantics

There is no timeout-based abort and no operator-only unlock.

An explicit abort is permitted only through a separately specified, authenticated terminal transition proving that:
1. the exact activation is terminally aborted in the authoritative activation store;
2. the anchor records a matching abort/tombstone for the same activation and receipt/checkpoint;
3. the witness persists the same terminal evidence digest;
4. the activation ID, receipt, and counter remain permanently consumed and cannot be reused.

Until this abort protocol is implemented and independently reviewed, an unresolved operation remains locked.

## 8. API contract

The witness store interface SHOULD expose operations equivalent to:

- `acknowledge(activation_id, activation_digest) -> immutable receipt`
- `read_pending_activation() -> immutable pending record or null`
- `confirm_activation_finalized(activation_id, activation_digest, evidence) -> terminal record`
- `reconcile_pending_activation() -> explicit state/result`

The exact API shape may differ, but the security invariants above MUST remain. The finalizer MUST enforce anchor verification inside the finalization boundary; a coordinator-only check is insufficient.

## 9. Authorization

The remote anchor service MUST map each authenticated client certificate identity to an immutable principal ID, an explicit role, and exact allowed namespace/operation sets. Certificate pinning and mTLS authenticate a peer; they do not authorize every route.

The v1 reference roles are constrained as follows:

- `witness`: exactly the `activation-witness` namespace; read and compare-and-advance only there.
- `trust-manifest-authority`: exactly `trust-manifest`; read and compare-and-advance only there.
- `vsp-profile-authority`: exactly `vsp-profile`; read and compare-and-advance only there.
- `finalizer`: read-only on explicitly assigned namespaces; no mutation.
- `recovery`: no v1 authority because v1 defines no recovery route.
- `operator`: no direct read, mutation, key use, or recovery privilege.

Authorization MUST be checked on every request, including route, namespace, operation, and certificate revocation state. The reference implementation's registry supports live fingerprint revocation and atomic old-to-new fingerprint rotation; production MUST govern registry updates through a separately administered control plane with append-only audit, approval, and key-rotation evidence. Rotation MUST preserve or reduce the prior principal's authority; it MUST NOT silently broaden namespace or operation scope.

A witness client MUST NOT act as a finalizer or recovery authority. A finalizer MUST NOT mutate any anchor namespace. An operator MUST NOT gain authority by possessing a valid client certificate. Unknown, revoked, cross-role, and cross-namespace requests MUST fail closed.

## 10. Required tests

- `LOCK-01`: second distinct activation is rejected while first is unresolved; counter unchanged.
- `LOCK-02`: retry of same ID/digest returns byte-identical receipt and counter.
- `LOCK-03`: same ID with different digest is rejected.
- `LOCK-04`: concurrent distinct ACK requests cannot both acquire the unresolved slot.
- `LOCK-05`: process restart preserves the unresolved slot.
- `LOCK-06`: etcd finalization without independently verified evidence cannot release the lock.
- `LOCK-07`: exact etcd-finalized record permits idempotent reconciliation.
- `LOCK-08`: conflicting or rolled-back etcd record causes quarantine.
- `LOCK-09`: anchor unavailable or checkpoint mismatch retains the lock.
- `LOCK-10`: no timeout or operator-only path releases the lock.
- `LOCK-11`: explicit abort requires matching terminal evidence from activation store, anchor, and witness.
- `AUTH-01`: authenticated but unauthorized client cannot mutate a namespace or call a privileged route.
- `AUTH-02`: a witness client cannot act as recovery authority or finalizer.

Each test MUST assert durable state, counter, receipt identity, anchor state, and etcd intent state—not merely an HTTP status or raised exception.

## 11. Production admission

SQLite and the reference HTTPS server remain development/test implementations. They MUST NOT satisfy production admission. Production requires independently administered monotonic state, protected key custody, anti-rollback evidence, durable audit, role-based authorization, and reproducible crash/recovery tests against the actual backend.

This document defines requirements; it does not claim that any implementation or test has passed.
