# P0 Signer Fencing Threat Model

**Status:** WORKING DRAFT — requires protocol/security review  
**Design contract:** [P0_SIGNER_FENCING_DESIGN_CONTRACT.md](P0_SIGNER_FENCING_DESIGN_CONTRACT.md)  
**Tracking:** [Issue #52](https://github.com/3bbdala-max/HND-Ledger/issues/52), [Draft PR #53](https://github.com/3bbdala-max/HND-Ledger/pull/53)

## 1. Protected assets

- Validator consensus private keys and any signing capability exposed by a signer service.
- Durable last-sign state: height, round, step, sign bytes, and signature/result identity.
- Current signer ownership and fencing epoch for each validator identity.
- Chain identity: network identifier, Genesis hash, validator public key.
- Authority credentials, enrollment/revocation records, and audit evidence.
- Integrity of CometBFT's proposal/vote signing behavior.

## 2. Security objectives

An attacker or fault must not be able to:
1. cause two distinct signer owners to release signatures concurrently for one validator identity;
2. make a signer with an obsolete epoch release a signature after a newer epoch is committed;
3. obtain conflicting signatures for a prohibited H/R/S state;
4. restore an old backup/snapshot and thereby restore old signing authority or anti-double-sign state;
5. bypass the guarded signer by causing CometBFT to fall back to a local FilePV;
6. replay, alter, or misbind a valid authorization to another chain, validator, request, or signing step;
7. turn an authority timeout, partition, stale read, or ambiguous commit into permission to sign.

Availability is secondary to consensus-signing safety: when the system cannot prove authorization, it must stop signing.

## 3. Adversary and fault model

Assume any of the following may occur independently or in combination:

- **Stale process:** an old signer remains alive after a new owner is activated.
- **Network partition:** old and new owners cannot communicate reliably; either side may retain local key access.
- **Concurrent clients:** two processes submit signing requests for the same validator.
- **Crash/restart:** signer, CometBFT, or authority crashes at any persistence/response boundary.
- **Replay:** a client replays a previously valid request or response.
- **Rollback:** an operator restores an older VM, filesystem, database, or backup.
- **Credential compromise:** an unauthorized client obtains a credential, or a credential is not revoked everywhere.
- **Operator error:** incorrect validator/Genesis enrollment, accidental key duplication, or unsafe recovery.
- **Authority failover:** replicas disagree, a stale replica is queried, quorum is lost, or a commit outcome is unknown.
- **Build/configuration error:** an unpinned or modified CometBFT binary bypasses the intended signer path.
- **Local fallback:** a stock CometBFT startup path creates or uses local FilePV state even though remote signing is expected.

The model does not assume that a hostname, PID, process lock, local clock, or signer-supplied epoch is trustworthy proof of exclusive ownership.

## 4. Trust boundaries

### B1 — CometBFT process to signer
The signer must authenticate and authorize every request. The transport connection alone does not establish ownership or release permission.

### B2 — Signer to authority
The authority must authenticate the signer instance and validate the exact chain, validator, epoch, and request context. Stale reads must not authorize signing.

### B3 — Authority replication and recovery
The authority's durable monotonic state is a root of trust. Replication, backup, restore, and disaster recovery must preserve the highest committed epoch and prevent resurrection of old ownership.

### B4 — Key custody
Possession of key material must not be equivalent to permission to sign. Key access must be mediated by the release authorization boundary.

### B5 — Build and deployment
Only the reviewed, pinned CometBFT/signer artifacts and configurations may be considered in scope. A stock CLI fallback or unreviewed binary invalidates the security claim.

### B6 — Operations and governance
Enrollment, revocation, takeover, emergency recovery, and key rotation require authenticated, auditable procedures. These policies remain unresolved until explicitly approved.

## 5. Required failure behavior

| Condition | Required signer behavior |
|---|---|
| Authority unreachable | Refuse to release signature |
| Authority response stale or unverifiable | Refuse to release signature |
| Ownership epoch mismatch | Refuse and record fenced-owner event |
| Unknown/ambiguous prior commit | Reconcile by request ID; do not create a new conflicting signature |
| Durable anti-double-sign state unavailable | Refuse to release signature |
| H/R/S conflict | Refuse and preserve existing committed state |
| Chain or Genesis mismatch | Refuse |
| Validator public-key mismatch | Refuse |
| Revoked signer identity | Refuse |
| Local FilePV fallback detected | Startup/test acceptance failure |
| Backup epoch lower than authority's committed epoch | Refuse recovery pending approved reconciliation |

## 6. Critical race to prove impossible

The implementation must specifically disprove this sequence:

1. Signer A owns epoch e and asks the authority to authorize request R.
2. Authority returns a positive response to A.
3. Ownership transfers and epoch e+1 for signer B is durably committed.
4. A, still alive or partitioned, releases signature R using the old positive response.

A design that checks ownership only at step 2 is insufficient. The architecture must couple the authoritative fencing decision to the actual key-release operation, or provide an equivalent cryptographic/linearizable mechanism that makes step 4 impossible after step 3.

The proof must include concurrency and crash behavior, not only sequential unit tests.

## 7. Out of scope / explicit assumptions to resolve

This draft does not choose:
- crash-fault versus Byzantine-fault tolerance for the authority;
- number and placement of authority replicas or quorum requirements;
- lease duration, clock assumptions, or takeover delay;
- human approval policy for ownership transfer;
- HSM, KMS, enclave, or isolated-process key custody;
- authority vendor or database technology;
- emergency override and disaster-recovery governance.

These are design inputs, not implementation details to guess.

## 8. Evidence required for a security claim

A future security review must receive:
- threat-model sign-off and documented assumptions;
- exact source commit and reproducible binary digests;
- proof or rigorous argument for the release-time fencing race;
- multi-host partition/takeover tests;
- crash-injection and anti-double-sign recovery evidence;
- stale backup/restore and authority failover evidence;
- local fallback negative tests against the pinned CometBFT build;
- key-custody, enrollment, revocation, audit, and operational procedures;
- independent review findings and remediation status.

A green unit test or a four-validator smoke test alone is not sufficient evidence of production signer safety.
