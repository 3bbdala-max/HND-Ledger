# Station 2 Witness Security Contract

Status: design baseline for implementation and review. This document is not a production approval, security certification, or authorization to activate a network.

Baseline reviewed: `phase-0.2-planning` at the time this branch was created.
Related tracking: GitHub issue #61.

## 1. Scope

This contract defines the security properties required of the Station 2 activation witness. It does not change Config-v1 owner decisions DEC-01 through DEC-14, CometBFT consensus parameters, tokenomics, or activation policy.

The existing SQLite witness store and its HTTPS/mTLS endpoint remain reference-only. A production deployment MUST NOT select them as its independent witness.

## 2. Threat model

The witness design must account for:

- Loss of a process, host, disk, or one witness node.
- Network partition and loss of quorum.
- Concurrent acknowledgement requests for the same activation.
- A client timing out after the witness has durably committed an acknowledgement.
- Reuse of an activation ID with a different activation digest.
- Restoration of a stale database or snapshot, including restoration of every replica to an older common snapshot.
- Compromise, rotation, or revocation of a signing key.
- Misconfiguration that points validators or the supervisor at an untrusted witness identity or configuration epoch.
- Compromise or operational control shared between the witness, etcd cluster, and validator hosts.

Out of scope for this contract alone: protection against a fully compromised trusted deployment authority or a colluding quorum of all independent witness operators. Those require separate governance and key-custody controls.

## 3. Required trust and failure-domain separation

A production witness MUST be separately administered from:

1. The Station 2 etcd cluster.
2. The CometBFT validator hosts and their operators.
3. The deployment identity that can change validator startup configuration.

A proposed baseline is at least three witness members distributed across three independently administered failure domains, with acknowledgement requiring a durable majority commit. This is a design target, not proof that three virtual machines or three cloud zones are independent. The deployment review must document ownership, administrators, cloud/account boundaries, network paths, backup operators, and common-mode failure risks.

If the configured quorum is unavailable, the witness MUST reject or remain unavailable. It MUST NOT issue an acknowledgement from a minority or fall back to SQLite.

## 4. Durable acknowledgement invariants

For each activation ID:

- The first accepted request binds exactly one activation digest, witness identity, configuration epoch, and monotonically increasing counter.
- The immutable record and its signed receipt are committed durably before a successful response is returned.
- A retry with the same activation ID and digest returns the exact original receipt, including the original counter and signature.
- Reuse of the activation ID with a different digest or incompatible epoch is rejected as a conflict.
- Concurrent requests cannot allocate multiple counters or conflicting receipts for the same activation ID.
- Counter allocation and receipt persistence are one atomic quorum operation.
- A response timeout is treated as an unknown outcome. The caller reconciles by reading/retrying the same activation ID and digest; it never creates a replacement activation ID to bypass uncertainty.

A receipt signature proves that a configured key signed a commitment. It does not, by itself, prove quorum durability, freshness, or resistance to rollback.

## 5. Anti-rollback and disaster recovery

Consensus replication alone is insufficient against restoration of every replica to a common stale snapshot.

Before production use, the design MUST provide an independently protected monotonic checkpoint or anchor that is outside the witness cluster's ordinary snapshot/restore authority. The anchor must bind at least the witness identity, configuration epoch, highest committed counter, and a digest of the committed log/checkpoint.

Recovery MUST:

1. Establish the identity and trust roots of the restored witness.
2. Read and verify the independent monotonic anchor.
3. Prove the restored log/checkpoint is not older than the anchor.
4. Reject recovery if the counter or checkpoint regresses, conflicts, or cannot be verified.
5. Require a documented, separately authorized recovery procedure for anchor loss; no automatic reset to counter zero is allowed.

The exact anchor technology and custody model remain an infrastructure decision. A second database under the same administrators and backup credentials does not satisfy independence.

## 6. Signing-key custody and trust configuration

- Private signing keys MUST NOT be stored in the witness SQLite/database files or ordinary application configuration.
- Production signing should use a protected key service or hardware-backed custody appropriate to the deployment threat model.
- Public-key fingerprints, witness ID, configuration epoch, and trust roots MUST be pinned in separately protected deployment configuration.
- Trust configuration MUST NOT be learned from the receipt being verified.
- Rotation must define activation time, overlap, old-receipt verification, revocation, emergency replacement, and recovery. Historical receipts must remain verifiable under the documented trust history.
- Key export and backup permissions must be separated from ordinary witness database administration.

## 7. Software boundary and backend interface

The HTTPS/mTLS service MUST depend on a narrow witness-store interface rather than the concrete `SQLiteActivationWitnessStore` class.

The interface must provide:

- `acknowledge(activation_id, activation_digest) -> immutable signed receipt`
- A readiness/capability report identifying backend type, durability mode, quorum status, witness identity, and configuration epoch.
- An explicit production-capability assertion that cannot be supplied by the SQLite reference backend.

Production startup MUST reject a backend that reports reference/development capability, lacks quorum, lacks a verified anti-rollback checkpoint, or cannot access protected signing-key custody.

SQLite remains available only for local development and tests. It must be clearly labelled and impossible to select through production configuration.

## 8. Failure and adversarial test requirements

The production backend is not acceptable until automated tests demonstrate:

- Idempotent retries return byte-identical receipts across process restart and leader change.
- Conflicting activation-ID reuse is rejected.
- Concurrent acknowledgements preserve unique monotonic counters and immutable records.
- A lost response after quorum commit is reconciled without issuing a second receipt.
- Loss of one member and leader transfer preserve safety and availability where quorum remains.
- Loss of quorum prevents acknowledgement and causes startup to fail closed.
- Stale snapshot restore, whole-cluster rollback, counter regression, and anchor mismatch are detected and rejected.
- Backup restoration succeeds only when it is consistent with the independent anchor.
- Key rotation, revocation, unknown key, wrong witness ID, and wrong configuration epoch are handled as specified.
- etcd timeout/ambiguous-commit recovery remains bound to the same activation ID and digest.
- CI evidence identifies the exact candidate commit SHA and includes test logs/artifacts.

Tests using mocks or a single-host SQLite database are useful unit tests but do not satisfy production quorum, failure-domain, or anti-rollback acceptance.

## 9. Rollout gates

1. Review and approve this threat model and trust-boundary design.
2. Select and document actual witness operators, infrastructure, quorum topology, anti-rollback anchor, key custody, backup/restore, monitoring, and incident response.
3. Refactor the service to the backend interface while retaining SQLite only for development.
4. Implement the production backend and independent anchor integration.
5. Add the adversarial tests above and obtain green CI on the exact candidate SHA.
6. Conduct an independent security review and operational recovery exercise.
7. Only then assess Station 2 exit criteria. This document grants no merge, production activation, public launch, or consensus certification approval.

## 10. Explicit non-claims

Passing this contract's software tests does not establish regulatory approval, independent security certification, production readiness of the full network, or safety of token issuance. Those require separate evidence and review.
