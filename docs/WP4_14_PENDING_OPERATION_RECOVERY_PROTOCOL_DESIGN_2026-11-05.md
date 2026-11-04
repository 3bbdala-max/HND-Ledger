# HND v0.2 — Pending-operation recovery protocol design

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Status:** Design proposal only; not an implementation or production authorization  
**Related model:** `hnd_v02/anti_rollback_reference.py`  
**Safety boundary:** Synthetic in-memory reference model only. No production signer, private key, HSM/KMS, durable database, filesystem transaction, or live network is connected.

## 1. Purpose and non-goals

Define deterministic decisions for a signing-state operation that may have stopped between preparation and commitment, including a lost reply and process restart. The design prevents a timeout, missing local cache, or predecessor record from being interpreted as proof that an operation was committed or safely aborted.

This document does not implement crash recovery, establish a durable trust anchor, authorize signing, or claim protection against a host administrator or Byzantine storage provider.

## 2. Terms and invariants

- **Operation ID:** globally unique identifier for one state transition. It must never be reused with a different payload.
- **Transaction digest:** digest over the immutable operation identity and payload fields, excluding the transition status.
- **Prepared payload:** the complete generation/state snapshot plus its manifest, bound to the operation ID, transaction digest, predecessor digest, chain/genesis/validator/signer identities, and schema version.
- **Trusted anchor:** an independently protected, authenticated, monotonic authority. A same-host file or a digest supplied by the caller is not an independent anchor.
- **Committed:** the trusted anchor durably records the operation as committed, with matching operation ID, transaction digest, state digest, sequence, and identity context.

The following invariants are mandatory:

1. A PREPARED record never authorizes signing.
2. A timeout or lost response is an unknown outcome, not a failure and not a commit.
3. Only a matching COMMITTED record read from the trusted anchor can resolve an operation as committed.
4. A COMMITTED record with a missing, corrupt, or mismatched durable generation snapshot does not authorize signing; isolate the signer and require recovery review.
5. PREPARED state cannot be silently replaced by its predecessor, and the predecessor is not restore authorization while a newer operation is pending.
6. No automatic abort, rollback, re-sign, or new operation ID is permitted to resolve ambiguity.
7. Repeating a commit request is permitted only as an idempotent retry for the exact same verified prepared payload and operation digest.

## 3. Deterministic decision table

| Anchor observation | Local durable payload | Decision | Signing |
|---|---|---|---|
| Matching COMMITTED operation and matching state digest/context | Present and verified | Mark operation committed; append reconciliation evidence | Disabled until all startup checks complete |
| Matching COMMITTED operation | Missing, corrupt, or digest mismatch | Quarantine; preserve evidence; supervised recovery required | Disabled |
| Matching PREPARED operation | Present and verified | Remain pending; commit may be retried only under the same operation ID and exact payload after policy checks | Disabled |
| Matching PREPARED operation | Missing or corrupt | Quarantine; do not commit, abort, or restore predecessor automatically | Disabled |
| Anchor unavailable or read times out | Any | Outcome unknown; retry read with bounded backoff; remain blocked | Disabled |
| Operation ID absent from anchor | Any | Absence alone is not proof of safe abort; compare durable journal and anchor sequence under recovery procedure | Disabled |
| Operation ID exists with conflicting digest or identity | Any | Integrity incident; quarantine and preserve both records | Disabled |
| Anchor sequence/predecessor does not match expected transition | Any | Stale/conflicting transition; stop and escalate | Disabled |

## 4. State-resolution procedure

1. Start in **RECOVERY_LOCKED**. Do not expose a signing endpoint or load a signing key.
2. Read the trusted anchor through an authenticated, independently protected channel. Validate schema, MAC/signature, network ID, genesis hash, validator ID, signer ID, sequence, and monotonicity.
3. Read the durable operation journal and generation snapshot. Verify canonical encoding, operation ID, transaction digest, state digest, predecessor digest, schema, and manifest authentication.
4. Query the anchor's operation record by operation ID. Do not infer state from the latest record alone if the anchor supports a durable operation history.
5. Apply the decision table exactly. Any missing, conflicting, unavailable, or unverifiable evidence leaves the signer blocked.
6. If COMMITTED is confirmed, verify the complete committed generation snapshot against the anchor. Only then may startup continue to the separate signer-readiness gate.
7. If PREPARED is confirmed, keep signing disabled. A commit retry requires the complete original prepared payload and the same operation digest. No replacement payload is allowed.
8. Record the decision, evidence hashes, timestamps, operator identities, and outcome in a tamper-evident audit domain separate from the signer host.

## 5. Commit retry versus abort

A commit retry and an abort are different state transitions:

- **Commit retry:** idempotently asks the anchor to complete the exact operation already prepared. It must not alter the operation ID, state digest, sequence, predecessor, or identity context.
- **Abort:** would require a separately designed, authenticated, monotonic terminal state and a defined rule for whether the sequence can be reused. The current reference model has no abort protocol. Therefore abort is unsupported; absence of local payload, timeout, or anchor unavailability must never be treated as an abort.

If the original prepared payload is unavailable after restart, the operation cannot be safely committed from the current model. The correct outcome is quarantine and supervised recovery, not reconstruction from the previous committed record.

## 6. Durable implementation requirements (not yet implemented)

Before any production implementation, the design must specify and independently review:

- A write-ahead operation journal and immutable generation snapshot.
- Atomic durability semantics (for example, database WAL with documented fsync guarantees, or a carefully specified write-temp/fsync/atomic-rename/directory-fsync protocol).
- A trusted anchor outside the ordinary signer host's administrative failure domain, with authenticated monotonic reads and compare-and-swap writes.
- An operation-history lookup that survives restart and distinguishes PREPARED, COMMITTED, and any future explicitly approved terminal state.
- Crash/fault injection at every persistence boundary, including power loss, torn writes, stale replicas, delayed replies, duplicate requests, and anchor failover.
- Host fencing and split-brain prevention across recovery operators and signer instances.
- Dual-control approval for quarantine release, restore, and any future abort ceremony.
- Tamper-evident audit export to a separate security domain.
- A documented threat model, RTO/RPO, operator runbook, and independent security review.

A successful fsync or database commit on the signer host alone does not create an independent anti-rollback guarantee.

## 7. Required verification matrix for a future implementation

| ID | Fault injection | Required result |
|---|---|---|
| R01 | Crash before journal durability | No commit; signer remains blocked |
| R02 | Crash after journal durability but before anchor PREPARED | Reconcile journal/anchor; no signing |
| R03 | Crash after anchor PREPARED | Pending state; no automatic abort or predecessor restore |
| R04 | Crash after anchor COMMITTED but before response | Read-by-operation-ID confirms matching commit; otherwise remain blocked |
| R05 | Commit reply lost repeatedly | Idempotent retry only for identical payload |
| R06 | Payload missing after restart while PREPARED | Quarantine; no commit or automatic restore |
| R07 | Payload modified but operation ID unchanged | Digest mismatch; quarantine |
| R08 | Anchor unavailable | Outcome unknown; signing disabled |
| R09 | Anchor returns conflicting operation digest | Integrity incident; quarantine |
| R10 | Anchor says COMMITTED but snapshot is absent | No signing; supervised recovery |
| R11 | Old host resumes after takeover | Fenced host cannot write or sign |
| R12 | Two operators attempt conflicting recovery actions | Dual-control and monotonic transition prevent split-brain |

Each test must capture the exact anchor response, journal/snapshot hashes, process state, signer-listener state, and audit event. Test results must be produced by an authorized environment; this document does not claim any of these future tests have run.

## 8. Current reference-model gap and scope

The current `SyntheticAnchor` is explicitly in-memory and non-durable. The model keeps a latest record, a last-committed pointer, and an in-memory operation map. A newly constructed model can lose its generation cache even if the same synthetic anchor object remains available. The existing restart test correctly verifies fail-closed behavior in that limited simulation.

The current model does **not** provide a durable journal, durable generation snapshot, independent trust anchor, restart-safe operation history, abort state, crash-consistent filesystem/database protocol, or production signer isolation. The design above must not be read as evidence that these mechanisms exist.

## 9. Acceptance gates

- **Gate A:** independent reviewer approves threat model, anchor independence, durability model, and operator authority.
- **Gate B:** durable protocol and schema are implemented in an isolated non-production environment.
- **Gate C:** the complete R01–R12 fault-injection matrix passes and evidence is retained.
- **Gate D:** supervised disaster-recovery rehearsal and independent sign-off.

Until all required gates are independently satisfied, Stage A remains open, production signing remains prohibited, and no release or custody guarantee is claimed.


## 10. Additional code-review finding: prevent a second PREPARED operation

A review of the current in-memory reference implementation identified a state-machine gap requiring correction before the next test cycle:

- `SyntheticAnchor.compare_and_swap` handles a retry or COMMITTED transition for an existing operation ID.
- For a previously unseen operation ID, it checks the current sequence, predecessor digest, HRS progression, and that the proposed record begins as PREPARED.
- It does not currently reject a new operation merely because the current anchor record is already PREPARED under a different operation ID.

Consequently, a second operation may be prepared on top of an unresolved PREPARED record. The operation history can then contain multiple unresolved operations, while the latest anchor record points only to the newest one. That is inconsistent with the single-pending-operation decision model in this document.

**Required correction:** before accepting a new operation ID, the anchor must reject the transition whenever its current record is PREPARED. The only permitted transition out of that state is the matching operation's idempotent retry or its exact PREPARED-to-COMMITTED transition. Do not add implicit abort or supersession.

**Required regression test:** prepare operation A; attempt to prepare operation B with a distinct ID and a strictly advancing HRS; assert B is rejected, the current anchor record remains A/PREPARED, operation A remains queryable, the last committed pointer is unchanged, and signing remains disabled. Then verify that A can be committed or reconciled through the existing permitted path.

**Evidence status:** this is a source-review finding, not a test result. The correction and regression test are pending; no claim is made that the current implementation already enforces this rule.
