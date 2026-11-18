# P0 Signer Release Interface Contract

**Status:** DESIGN CONTRACT — proposed interface and security boundary; not implemented  
**Tracking:** [Issue #52](https://github.com/3bbdala-max/HND-Ledger/issues/52)  
**Related:** P0_SIGNER_FENCING_DESIGN_CONTRACT.md, P0_SIGNER_FENCING_THREAT_MODEL.md

## 1. The decisive architectural constraint

A fencing token checked by a validator process before it uses a locally held private key does **not** fence that process after a network partition. The process may retain the key and continue signing from a cached positive response.

Therefore:

> No validator host that can continue using a raw consensus private key locally may be considered fenced solely because a remote lease, epoch, database row, or authorization check changed.

A valid design must make the actual cryptographic signing operation conditional on current fencing state at a boundary the stale host cannot bypass. Acceptable design families for evaluation are:

- **Remote key custody:** validator hosts never receive the consensus private key; every signature is produced by an independently controlled signing service/HSM that enforces current ownership and anti-double-sign state at the operation boundary.
- **Hardware-enforced fencing:** key operations require a non-bypassable hardware or service authorization that invalidates old owners and cannot be rolled back with the validator host.
- **Other formally equivalent design:** only if a security proof and multi-host partition tests demonstrate that a stale host cannot release a signature after transfer.

A remote check followed by local signing is explicitly not an acceptable implementation.

## 2. Logical interface boundary

The following is a language-neutral contract. Names and serialization are illustrative and must be mapped to the pinned CometBFT v0.40.0 interfaces during implementation.

### Signer identity

`SignerIdentity` must bind:

- protocol/network ID;
- Genesis hash;
- canonical CometBFT public-key type and public-key bytes;
- validator address derived from that key;
- enrolled signer/key-custody identity;
- signer software and policy version where required.

### Ownership token

`OwnershipToken` must be authority-issued and cryptographically authenticated. It contains:

- identity scope digest;
- strictly increasing fencing epoch;
- current owner identity;
- authority transaction/decision ID;
- policy version;
- expiry only if the approved protocol uses leases.

A token supplied by the caller is a claim, not proof. The key-release boundary must validate it against current authoritative state or use an equivalent non-bypassable hardware-enforced mechanism. Expiry based only on a local clock is not fencing.

### Signing request

`SignRequest` contains:

- request ID (stable across retries);
- SignerIdentity;
- OwnershipToken reference;
- CometBFT chain ID;
- exact canonical sign bytes or canonical protobuf request;
- height, round, step/type;
- request digest with domain separation.

The server must independently derive/check H/R/S and request digest from canonical sign bytes. It must not trust caller-supplied H/R/S metadata alone.

### Signing response

`SignResponse` contains:

- request ID;
- signer identity digest;
- committed fencing epoch;
- H/R/S tuple;
- sign-bytes digest;
- signature and public-key identity;
- durable anti-double-sign record/commit ID;
- authority decision ID;
- outcome classification.

The response must be authenticated and bound to the exact request. No signature may be returned before required durable state has committed.

## 3. Required operations

### Enroll

`EnrollSigner(identity, key_custody_reference, policy)`

- Explicitly enrolls one validator public key and its key-custody reference.
- Rejects duplicate or ambiguous validator identity enrollment.
- Records authenticated operator/approval evidence.
- Does not accept private key material through ordinary API payloads.

### AcquireOrTransferOwnership

`AcquireOrTransferOwnership(identity, requested_owner, expected_epoch, approval_evidence)`

- Executes a linearizable ownership transition.
- Returns the committed new epoch and decision ID.
- Requires explicit policy for current owner liveness, lease expiration, quorum, and human approval.
- Does not imply that an old signer is fenced until the key-release boundary enforces the new epoch.

### Sign

`Sign(SignRequest) -> SignResponse`

For every request, the key-release boundary must:

1. authenticate the caller and signer identity;
2. verify chain ID, Genesis, validator public key, request ID, canonical sign bytes, and H/R/S;
3. establish current ownership/fencing epoch at the actual signing boundary (not only at process startup or client preflight);
4. serialize access to durable anti-double-sign state for this validator;
5. reject stale ownership, conflicting H/R/S, replay with altered payload, revoked identity, and unknown/ambiguous durable outcomes;
6. persist enough durable intent to recover safely;
7. perform the protected key operation;
8. durably commit the exact signature and resulting H/R/S state;
9. return the authenticated response only after durable commit.

The implementation must explain and prove how steps 3–8 avoid a race with a concurrent ownership transfer. If the authority and key operation are separate systems, a transaction/cryptographic enforcement mechanism must close that gap. A plain read followed by a local key call does not.

### GetStatus

`GetStatus(identity)`

- Returns current authoritative epoch/owner and durable H/R/S checkpoint.
- Distinguishes current authorization from historical request outcome.
- A historical successful request is never, by itself, current permission to sign.

### Reconcile

`Reconcile(request_id)`

- Resolves a timeout or lost response using the same stable request ID.
- Returns the exact committed result, a definite not-committed result, or UNKNOWN/BLOCKED.
- UNKNOWN/BLOCKED must not trigger a fresh signature attempt with a new request ID.

### Revoke

`RevokeSigner(identity, signer_instance, reason, approval)`

- Revokes the relevant signer instance/credential.
- Invalidates all sessions/tokens at the release boundary.
- Produces an auditable decision.
- Defines key rotation/re-enrollment separately.

## 4. Outcome model

The API must use explicit outcomes, not ambiguous booleans:

| Outcome | Meaning | Caller action |
|---|---|---|
| COMMITTED | Signature and anti-double-sign state durably committed | Accept exact response |
| REPLAY_SAME | Same request ID and identical canonical payload already committed | Return same committed result |
| REJECT_STALE_OWNER | Caller epoch/owner is no longer current | Stop signer; no retry with old token |
| REJECT_CONFLICT | H/R/S already committed with conflicting sign bytes | Halt and raise safety incident |
| REJECT_IDENTITY | Chain/Genesis/key/signer identity mismatch or revoked | Stop and alert |
| NOT_COMMITTED | Authority proves no signature was committed | Retry only under documented idempotency rules |
| UNKNOWN_BLOCKED | Commit/sign outcome cannot be established | Do not sign; reconcile same request ID |
| UNAVAILABLE | Required authority/key custody/durable store unavailable | Fail closed |

Errors must not leak private key material, credentials, or sensitive signing state.

## 5. H/R/S and idempotency rules

- One durable serialization domain exists per validator key identity.
- Exact retries are keyed by request ID plus canonical payload digest.
- Reuse of a request ID with different payload is rejected.
- H/R/S progression follows the exact pinned CometBFT v0.40.0 LastSignState/PrivValidator semantics; this document does not redefine consensus rules.
- A lower H/R/S, same H/R/S with conflicting sign bytes, or invalid step transition is rejected.
- A higher H/R/S cannot be committed while an earlier operation has an unresolved outcome unless the approved CometBFT semantics explicitly permit safe reconciliation.
- Persisted signature bytes and state are bound to chain ID, Genesis, validator key, and signer identity.
- Recovery from backup cannot reduce either fencing epoch or anti-double-sign state.

## 6. CometBFT adapter requirements

The adapter must be built against the repository's pinned CometBFT v0.40.0 source and prove:

- every proposal and vote signing request reaches the guarded Sign operation;
- no local FilePV is generated, opened, or used as a fallback;
- startup fails if remote signer identity or policy is missing;
- reconnect and retry paths preserve the same request identity;
- response verification checks the expected validator public key and request;
- signer failure does not cause the node to silently switch signing backends.

The exact pinned source integration must be inspected before choosing method signatures. This document does not assert that the current repository already has this adapter.

## 7. Mandatory acceptance tests

1. **Partition after authorization:** old signer obtains any preflight response, is partitioned, ownership transfers, then old signer attempts a new signature. The key-release boundary must reject it.
2. **Partition during signing:** transfer races an in-flight signature. Exactly one serializable outcome is allowed and is recorded; no stale signature is released after transfer commit.
3. **Two owners:** concurrent owners contend for one validator. One current epoch only; stale owner cannot use a copied token.
4. **Raw-key isolation:** validator host filesystem, process memory, backup, and environment do not contain a usable consensus private key when remote custody is claimed.
5. **Bypass test:** direct local FilePV access and unguarded signing path are absent or denied.
6. **Same request retry:** same request ID and payload returns the same committed signature.
7. **Altered retry:** same request ID with altered bytes is rejected.
8. **Crash before durable intent:** no signature response; safe retry/reconciliation.
9. **Crash after signature but before commit:** recovery cannot emit a conflicting signature; ambiguous result is blocked until reconciled.
10. **Crash after commit before response:** same request returns exact committed signature.
11. **Authority outage / stale replica:** no signature released.
12. **Revocation / key rotation:** old instance and credential cannot sign after revocation boundary.
13. **Snapshot rollback:** restoring an old signer or key-service snapshot cannot regain ownership or lower H/R/S.
14. **Pinned CometBFT regression:** all tests run against exact source and binary digests.

Every test report must include exact commit SHA, build digest, test command, result, and whether the test exercised a model, local process, real multi-host deployment, or hardware-backed key boundary. These evidence classes must not be conflated.

## 8. Implementation decision gate

Before code is written, reviewers must select and approve:

- key custody model and whether validator hosts ever possess raw consensus keys;
- authoritative fencing enforcement point;
- atomicity model between ownership transfer, signing, and durable H/R/S state;
- authority replication/failure model;
- lease/takeover/approval policy;
- recovery, backup, disaster-recovery, and key-rotation procedures;
- audit and incident-response requirements.

Until those decisions are approved, implementation must remain a disposable prototype with synthetic keys and no production claims.
