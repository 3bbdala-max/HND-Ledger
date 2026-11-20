# Protected Key-Service Protocol Contract (Design Only)

**Status:** DESIGN PROPOSAL — NOT IMPLEMENTED, NOT SECURITY-APPROVED  
**Scope:** Disposable-key prototype interface between signer authority and protected key service.  
**Branch:** `work/p0-signer-fencing-design`

This document specifies a fail-closed request and evidence contract. It does not authorize production keys, real funds, public deployment, token issuance, or release.

## 1. Security boundary

The protected key service is the only component permitted to access the private signing key. Validator hosts and orchestration services submit requests; they never receive raw private-key material. A database lease, cached epoch, caller-side mutex, or preflight authorization is not a fence unless the protected key-release boundary enforces it atomically.

The service identity, authority identity, and trust configuration must be authenticated. A production design requires mutually authenticated transport (or an equivalent authenticated channel), explicit authorization, pinned trust roots, rotation and revocation procedures, and independently protected audit records.

## 2. Canonical request envelope

Every signing request carries these fields:

| Field | Requirement |
|---|---|
| protocol_version | Explicit version; unknown versions rejected |
| request_id | Globally unique stable idempotency identifier |
| signer_id | Stable validator/signer identity scope |
| owner_id | Current authorized owner |
| epoch | Monotonically increasing fencing epoch |
| key_id | Exact key identity, not a caller-selected alias |
| domain | Protocol and chain domain separator |
| sign_bytes_digest | Digest of canonical bytes, algorithm and encoding fixed by protocol |
| h_r_s | Exact height, round, step tuple where applicable |
| authority_proof | Authenticated authorization bound to signer_id, owner_id, epoch and request |
| caller_nonce | Replay-resistant request nonce or sequence |

The service recomputes the canonical digest from the supplied canonical sign bytes. It must not trust a caller-provided digest without recomputation. Any mismatch, omitted mandatory field, duplicate field, non-canonical encoding, or unsupported algorithm is rejected.

## 3. Service journal and state machine

The service maintains an independently protected durable journal. A journal entry binds the complete request identity, authorization context, key identity, and terminal outcome.

States:

- `RECEIVED`: authenticated request durably recorded.
- `EXECUTING`: the protected signing operation may have started.
- `SIGNED`: exact signature result and verifiable attestation durably recorded.
- `REJECTED`: request rejected before any signing side effect.
- `UNKNOWN`: outcome cannot be proven; no new signing operation is permitted for this request.

Allowed transitions are deliberately narrow:

`RECEIVED -> EXECUTING -> SIGNED`

`RECEIVED -> REJECTED`

`EXECUTING -> UNKNOWN`

`UNKNOWN -> SIGNED` only by retrieving and validating the original durable outcome, never by blindly signing again.

A service must persist the request identity before beginning the key operation, and persist the exact outcome and attestation before returning success. If the outcome cannot be durably recorded, it must fail closed and expose UNKNOWN rather than claim success or safe abort.

## 4. API operations

### PrepareSign / SignOnce

Input: canonical request envelope.

Behavior:
1. Authenticate caller and authority proof.
2. Validate signer, owner, epoch, key, domain, nonce, H/R/S and canonical digest.
3. Look up request_id.
4. If it exists with identical complete identity, return its stored state/outcome; do not execute a second key operation.
5. If it exists with any differing identity field, reject as an idempotency conflict.
6. Atomically verify the active owner and epoch at the protected key boundary, reserve the request, and durably journal it before key use.
7. Execute only the authorized operation and persist its exact result and attestation before success response.

The check of owner/epoch and authorization to release a signature must share one non-bypassable serialization boundary with ownership transfer. A check performed only by the caller is insufficient.

### GetOutcome

Input: request_id plus authenticated caller identity.

Output: journal state and, for SIGNED, the exact signature plus service attestation. The response must bind request_id, signer_id, owner_id, epoch, key_id, domain, sign_bytes_digest, H/R/S, signature digest, service identity, journal sequence, and protocol version.

No response may imply that UNKNOWN means no signature was produced.

### TransferFence

A transfer request carries signer_id, current owner, target owner, current epoch, next epoch, and authenticated authority proof.

The authority must stop admitting new old-epoch operations and wait until every previously admitted operation is in a proven terminal state. UNKNOWN is not terminal. The protected key boundary must atomically activate the next epoch and reject every old-epoch release, including after reconnect, restart, failover, or snapshot restore.

The exact ordering mechanism must be selected and proven for the actual deployment topology. A remote lease plus an independent HSM call is not sufficient. If no single linearizable boundary can be established, the transfer protocol must remain blocked.

## 5. Attestation and reconciliation

Reconciliation accepts only an attestation authenticated by the configured key-service identity and validated against the full original request identity. The verifier checks:
- trusted service identity and certificate/key status;
- attestation signature and protocol version;
- request_id, signer_id, owner_id, epoch, key_id and domain;
- canonical sign-bytes digest and H/R/S;
- journal sequence and anti-replay constraints;
- exact signature bytes or an authenticated proof of a pre-key rejection.

Caller-supplied bytes, a database row, a log message, or a timeout is not proof. Missing, malformed, stale, conflicting, unverifiable, or rollback-suspect evidence leaves the request UNKNOWN and transfer blocked.

## 6. Replay, rollback, and key lifecycle

The implementation must define durable monotonic journal sequence numbers, anti-replay nonces, epoch monotonicity, backup/restore rules, rollback detection, service-key rotation, revocation, disaster recovery, and audit retention. Restoring an older snapshot must never reactivate an old owner or permit an old request to release a signature.

The journal's integrity and availability must be protected independently from the caller and ordinary validator host. The threat model must include compromise of the caller, host, database administrator, service operator, network, backup pipeline, and recovery process.

## 7. Crash and partition matrix

| Failure point | Required behavior |
|---|---|
| Before durable RECEIVED | No key operation authorized; retry may use the same request ID |
| After RECEIVED, before EXECUTING | Recover same request; prove no side effect before rejecting or continuing |
| During key operation | Mark/retain UNKNOWN; prohibit a fresh signing attempt |
| After signature, before outcome persistence | UNKNOWN; recover exact result from protected key boundary or block indefinitely |
| After durable SIGNED, before response | GetOutcome returns the exact stored result |
| Caller crashes before main-ledger commit | Retrieve the same attested outcome; do not sign again |
| Service unavailable or partitioned | Fail closed; transfer cannot pass unresolved operations |
| Journal corruption, rollback, or attestation failure | UNKNOWN; quarantine and block transfer pending independent recovery |
| Transfer races with admission/release | One proven serialization boundary decides the winner; otherwise block |

## 8. Required contract tests

Before any prototype can progress beyond MODEL, add deterministic tests for:
1. same request ID and identical payload returns the same stored outcome;
2. same request ID with changed owner, epoch, key, domain, digest or H/R/S is rejected;
3. stale epoch and revoked authority are rejected at the key boundary;
4. replayed nonce and rolled-back journal sequence are rejected;
5. UNKNOWN never triggers a second key operation;
6. absent, invalid, stale, or conflicting attestation cannot reconcile;
7. transfer cannot commit while old-epoch operations are unresolved;
8. after transfer, an old owner cannot release a signature after restart or restore;
9. crash at every row in the failure matrix recovers the exact outcome or remains blocked;
10. independent multi-host race and partition tests exercise the real protected boundary.

Label evidence accurately as MODEL, UNIT, PROCESS, MULTI_HOST, KEY_BOUNDARY, or COMETBFT. A local model test must never be described as proof of production fencing.

## 9. Explicit non-claims and release gate

This contract is design-only. No authenticated service, cryptographic attestation, protected journal, HSM integration, distributed linearizability proof, anti-rollback implementation, multi-host test, or CometBFT integration is supplied by this document.

Do not claim absolute exactly-once execution across distributed systems. The target is an idempotent request identity, durable outcome retrieval, and a separately proven key-release/transfer serialization boundary. Until independent security review and the required evidence exist, use disposable keys only and keep production signing, real funds, public release, token issuance, and merge blocked.
