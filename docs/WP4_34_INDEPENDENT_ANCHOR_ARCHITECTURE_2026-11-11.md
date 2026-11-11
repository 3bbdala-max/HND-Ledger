# WP4.34 — Independent Monotonic Anchor Architecture — 2026-11-11

**Status:** Recommended architecture for implementation planning; not deployed or production-approved.
**Base commit:** f75350689cece28e253c94b8b6b338096c2c789b

## Recommended architecture

Use a dedicated three-or-more-member etcd cluster as the linearizable transactional state engine, operated in a separate administrative and failure domain from HND validators. Pair it with a separately administered witness service or hardware-backed monotonic witness that retains the accepted cluster identity, epoch, and latest committed checkpoint digest.

Important: etcd snapshots alone do not prevent rollback. Restoring every member from an old snapshot can roll back the entire cluster. The independent witness is mandatory to detect and reject that condition.

## Atomic state model

Store the active profile artifact reference and both anti-rollback namespace records in one etcd transaction. Compare the complete expected current tuple and atomically write:
- active profile content-addressed reference and digest;
- trust-manifest sequence and digest;
- VSP-profile sequence and digest;
- activation intent identifier, activation height, and transaction generation.

Use transaction compare clauses on generation and every expected key revision/value. Never implement activation as sequential writes.

The witness checkpoint binds cluster identity, generation, transaction revision, and SHA-256 digest of the complete active tuple. Report success only after the quorum-backed transaction and independent witness acknowledgement both complete. If the witness is unavailable, stale, or ahead, fail closed.

## Trust separation

- At least three etcd members across documented independent failure domains.
- Dedicated service identities and mTLS, pinned CA, rotation and revocation procedure.
- Separate administrators for HND validators, anchor cluster, and witness.
- Witness state cannot be restored solely from anchor backups or credentials.
- No validator-local SQLite/file/environment override for accepted sequence.
- Only the activation service may access anchor write APIs.

## Failure and recovery rules

| Condition | Required behavior |
|---|---|
| Anchor quorum unavailable | Refuse activation and startup |
| Witness unavailable or behind | Refuse activation and startup |
| Witness ahead of restored anchor | Quarantine; no automatic rollback or reseed |
| Concurrent activation | Exactly one CAS wins; others receive conflict |
| Crash after commit, before response | Reconcile exact intent and witness checkpoint; return idempotent result only on exact match |
| Crash before commit | No state change; retry from authenticated expected state |
| Backup restore | Verify cluster identity and witness checkpoint before serving; reject stale restore |
| Credential rotation | Dual-trust bounded overlap, explicit revocation and audit |

## Required verification

1. Competing CAS writers: exactly one successor wins.
2. Leader crashes before/during/after commit: linearizable recovery.
3. Network partitions: loss of quorum and stale minority reads fail closed.
4. Restore an older snapshot: witness detects it and service remains unavailable.
5. Witness outage after anchor commit: no success until reconciliation.
6. Crash after commit but before response: idempotent recovery by intent ID.
7. Certificate rotation/revocation: revoked credentials cannot write.
8. Profile bytes, both monotonic namespaces, and activation generation change atomically.
9. Independent review of witness protocol and threat model.

## Scope boundary

This document does not add an etcd dependency, deploy infrastructure, provision keys, create operator identities, or claim production guarantees. Those require infrastructure ownership and independent security review. SQLite remains test/reference-only.

## Implementation order

1. Specify witness protocol and whole-cluster rollback/disaster-recovery threat model.
2. Implement an etcd-backed MonotonicStateAnchor adapter and atomic activation backend over the same transaction boundary.
3. Build a disposable three-member test cluster and fault-injection suite.
4. Enforce startup authorization before any ABCI/CometBFT process or listener exists.
5. Obtain independent review and owner approval before production deployment.

## Station 2 gate

The independent anchor gate remains OPEN until cluster and witness are deployed in separate trust domains and every required test passes on a commit-bound CI run. This architecture recommendation is not acceptance evidence.