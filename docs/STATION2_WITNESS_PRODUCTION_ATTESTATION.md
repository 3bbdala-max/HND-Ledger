# Station 2 Witness Production Attestation

Status: admission-control contract only. This document does not certify a deployment or authorize production activation.

## Why a signed attestation is required

A backend's own capability flags are not evidence. Any Python object can claim that it has quorum, an independent anchor, and protected key custody. The HTTPS witness service therefore rejects production startup unless it receives a short-lived Ed25519 attestation verified against a public key pinned in deployment configuration.

The pinned attestor public key MUST be provisioned independently of the witness process and its ordinary configuration-management credentials. The witness process MUST NOT generate the attestation or control the attestor private key.

## Signed payload

Schema: `hnd.station2.witness-production-attestation.v1`

The signed canonical JSON payload contains exactly:

- `schema`
- `backend`
- `witness_id`
- `config_epoch`
- `quorum_id`
- `anchor_id`
- `signing_key_ref`
- `review_reference`
- `issued_at`
- `expires_at`

The signature is Ed25519 over:

```text
"HND-STATION2-WITNESS-PRODUCTION-ATTESTATION-V1" || 0x00 || canonical_json(payload)
```

Canonical JSON is ASCII UTF-8, sorted keys, no insignificant whitespace, and rejects non-finite numbers. The signature is base64 encoded and must be canonical.

The attestation is valid for no more than 90 days. Startup rejects expired attestations, attestations issued more than 60 seconds in the future, malformed signatures, unknown attestor keys, mismatched backend identity, or a mismatch between the capability backend name and the signed backend name.

## Identity binding

The backend must expose immutable identity values matching the signed payload: backend name, witness ID, configuration epoch, quorum ID, independent anchor ID, and protected signing-key reference.

## Required review before issuing an attestation

The attestor must independently verify and retain evidence for:

1. Actual witness member count, quorum configuration, member identities, and linearizable durable commit behavior.
2. Separate ownership, administrators, credentials, accounts, and recovery authority from Station 2 etcd and validator infrastructure.
3. Independent anti-rollback anchor operation and recovery, including whole-cluster stale restore tests.
4. Hardware-backed or protected signing-key custody, access logging, rotation, revocation, and recovery.
5. Backup/restore drills, incident response, monitoring, and access review.
6. Exact software release commit SHA, reproducible build or artifact digest, and adversarial test evidence.
7. Independent security review reference and unresolved findings.

The attestation verifier proves that a trusted key signed a bounded statement and that the running backend identity matches it. It does NOT independently prove the truth of the review, the security of the infrastructure, or the honesty of the attestor. The public key's custody and the attestation issuance process are separate trust decisions.

## Operational rule

No production attestation may be issued for the current SQLite reference backend, a mock, a single-host etcd instance, or an anchor under the same administrative/backup domain. Until a real independent quorum, anchor, and protected key provider exist and have been reviewed, production startup must remain blocked.
