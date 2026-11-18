# P0 Signer Fencing and Signature-Release Design Contract

**Status:** DESIGN CONTRACT — NOT IMPLEMENTED, NOT REVIEWED, NOT PRODUCTION-APPROVED  
**Baseline branch:** `phase-0.2-planning`  
**Baseline commit:** `1c94234ac36a4d6e43ac32d42bb948fbf3ac4a7f`  
**Work branch:** `work/p0-signer-fencing-design`  
**Tracking issue:** [#52](https://github.com/3bbdala-max/HND-Ledger/issues/52)

## 1. Purpose and non-goals

Define the security boundary required before a HND validator signer may release a consensus signature. The design must fence a stale signer even when that process remains alive, is partitioned from the network, or reconnects after ownership has moved.

This document does not implement a signer, select a production database/vendor, define quorum policy, authorize deployment, or permit use of real validator keys or funds.

## 2. Security invariants

1. **Single current owner:** For each signer identity scope, the authority exposes at most one current fencing epoch.
2. **Monotonic fencing:** A successfully committed ownership transfer strictly increases the epoch. Epochs never decrease or get reused after restart, restore, failover, or disaster recovery.
3. **Release-time authorization:** Every proposal/vote signature is authorized at the signature-release boundary against the current owner and epoch. Startup authorization and cached leases alone are insufficient.
4. **Stale-owner rejection:** A signer holding an older epoch cannot release a signature after a newer epoch is committed, even if it is healthy and can reach its local key.
5. **Durable anti-double-sign:** H/R/S state and the request identity are durably serialized with signature release. Conflicting requests must never produce a second signature.
6. **Fail closed:** If current ownership, epoch freshness, authority consistency, or durable signing state cannot be proven, no signature is released.
7. **Identity binding:** Authorization is bound to chain/network identity, Genesis hash, validator public-key identity, signer instance identity, and the exact signing request.
8. **No implicit recovery:** Restoring an old signer database, VM snapshot, backup, or host image must not restore signing authority.

## 3. Identity and request scope

The protocol must define canonical encodings and domain separation for:

- `network_id`
- `genesis_hash`
- `validator_pubkey` (canonical CometBFT key type and bytes)
- `signer_id` and enrolled signer instance / key-custody identity
- `fencing_epoch` (unsigned, strictly monotonic)
- CometBFT signing tuple: height, round, step/type
- canonical sign-bytes digest and request identifier
- authority transaction / decision identifier

No request may be authorized by matching only a validator name, process ID, hostname, or client-supplied epoch.

## 4. Ownership state machine (abstract)

The authority must provide linearizable transitions equivalent to:

- `UNENROLLED -> OWNED(epoch=1, owner=A)`: only after explicit validator/signer enrollment and identity verification.
- `OWNED(e, A) -> OWNED(e+1, B)`: atomic transfer; the new epoch becomes authoritative only after durable commit.
- `OWNED(e, A) -> OWNED(e+1, A)`: explicit recovery/re-enrollment when policy requires invalidating old sessions; never silently reuse e.
- `OWNED -> UNAVAILABLE/UNKNOWN`: inability to prove authority state. This is not permission to continue signing.
- `REVOKED`: signer identity is denied; re-enrollment requires a new auditable authorization path.

The final protocol must specify how leases, renewal, expiry, quorum, operator approval, and takeover interact. No lease duration or quorum rule is assumed here. Wall-clock expiry alone is not a fencing mechanism.

## 5. Signature-release transaction

A compliant signer must execute a single serialized release protocol for every proposal/vote:

1. Authenticate the caller and verify its enrolled signer identity.
2. Canonicalize the chain/Genesis/validator identity and CometBFT sign-bytes; compute the request digest.
3. Obtain a fresh, authoritative decision for the exact current owner and fencing epoch. A cached startup result is not acceptable.
4. Compare the request against durable H/R/S anti-double-sign state.
5. Atomically persist an intent/decision sufficient to recover after a crash. The design must explain how authority ownership and local durable signer state are coordinated without a split-brain window.
6. Produce the deterministic signature using the protected key.
7. Durably commit the signature and resulting H/R/S state before returning success.
8. Return a response bound to the committed request/decision identifier. Retries of the same request return the same committed result; conflicting requests are rejected.

**Critical unresolved design point:** a remote authority check followed by an independent local signature operation has a TOCTOU gap unless the authority participates in, or cryptographically fences, the actual release operation. The implementation must prove why an old signer cannot pass step 3 and release after a newer ownership transfer commits.

If the architecture cannot provide that proof, it is not an acceptable fencing design.

## 6. Crash and retry semantics

The implementation must define durable behavior at each fault boundary:

- before authority decision;
- after ownership decision but before local intent;
- after durable intent but before key operation;
- after signature creation but before durable commit;
- after durable commit but before response delivery;
- during authority failover or ownership transfer.

Timeouts are ambiguous outcomes, not implicit failures. A retry must query/reconcile the same request identifier and may not generate a conflicting signature. Recovery must never roll H/R/S or fencing epoch backward.

## 7. Authority requirements

The production authority must be independently administered from validator hosts and provide:

- linearizable compare-and-swap / transaction semantics for ownership and epoch changes;
- durable monotonic state across replica failover and disaster recovery;
- authenticated, mutually authorized clients and explicit enrollment/revocation;
- auditable ownership transitions and signature-release decisions;
- a defined backup/restore procedure that cannot resurrect stale epochs;
- fail-closed behavior for partitions, quorum loss, stale reads, and ambiguous commits;
- independently reviewable operational controls and threat model.

An in-memory synthetic anchor, SQLite reference implementation, validator-local database, advisory file lock, or ordinary eventually consistent read is not sufficient evidence of a production authority.

## 8. Mandatory test matrix

All tests must use disposable keys and isolated test networks. Each result must identify the exact source commit and binary digest.

| Scenario | Required outcome |
|---|---|
| Two hosts contend for one validator | One committed current epoch; loser cannot sign |
| Transfer while old host is partitioned | New owner can proceed only after committed transfer; old owner remains fenced |
| Old host reconnects | Every signing request from old epoch is rejected |
| Same H/R/S and identical request retry | Same committed signature/result; no second state transition |
| Conflicting sign bytes at same H/R/S | Rejected; no conflicting signature released |
| Concurrent proposal/vote requests | Serialized with protocol-correct H/R/S rules |
| Authority unavailable or stale | No signature released |
| Crash at every boundary in §6 | Recovery is deterministic; no double-sign or epoch rollback |
| Restore stale backup/snapshot | Old epoch cannot regain authority |
| Authority failover / disaster recovery | Highest committed epoch and anti-double-sign checkpoint preserved |
| Unauthorized, revoked, or rotated signer | Rejected and auditable |
| CometBFT integration | Exact pinned v0.40.0 build invokes the protected release path; no FilePV fallback |

CI must run the relevant test steps on the exact commit under review. A workflow run that fails before job steps execute is an infrastructure block, not a passing or failing test result.

## 9. Implementation sequence and gates

1. **Protocol review:** ratify identity scope, ownership transitions, lease/takeover policy, failure model, and operational authority.
2. **Threat model:** enumerate partitions, Byzantine/stale clients, operator error, backup restore, process cloning, compromised hosts, and authority failover.
3. **Interface contract:** specify typed request/response schemas, canonical serialization, authentication, idempotency, errors, and audit events.
4. **Single-validator prototype:** disposable key only; demonstrate release-time fencing and crash-safe H/R/S behavior.
5. **Multi-host fault injection:** prove stale-owner rejection and no split-brain across real process/network boundaries.
6. **CometBFT integration:** pinned source/build; no local FilePV creation or fallback; prove every proposal/vote reaches the guarded signer.
7. **Four-validator regression:** run the existing four-validator remote-only harness plus the new fencing tests.
8. **Independent security review:** review source, threat model, key custody, operations, and evidence before any production approval.

## 10. Explicitly unresolved decisions

These must be resolved by protocol/security review before implementation chooses a mechanism:

- authority replication and consensus model;
- ownership lease and renewal semantics, if any;
- who may initiate or approve takeover;
- signer host and key custody model (HSM/remote KMS/isolated process);
- how the fencing decision is coupled atomically to key release;
- durable anti-double-sign record format and recovery protocol;
- emergency recovery and disaster-recovery governance;
- audit retention, monitoring, and incident response.

Do not silently choose defaults for these decisions in code.

## 11. Current evidence boundary

The repository contains experimental remote-signer helpers and a four-validator harness. Same-host `flock` is not distributed fencing. The synthetic anti-rollback reference is not a production authority and is not wired into the signer signature-release path. Existing startup authorization does not prove release-time authorization.

This contract records required design and acceptance criteria only. It is not evidence that any of the above controls have been implemented or tested.
