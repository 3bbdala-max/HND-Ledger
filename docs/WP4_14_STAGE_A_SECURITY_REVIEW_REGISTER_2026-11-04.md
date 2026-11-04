# HND v0.2 — WP4.14 Stage A security review register

**Date:** 2026-11-04  
**Status:** Internal design review checklist; NOT an independent security audit or approval  
**Branch:** `phase-0.2-planning`  
**Scope:** Threat-model completeness and decision closure before a synthetic anti-rollback reference model

## 1. Review disposition

The current WP4.14 architecture and anti-rollback ADR establish a sound design direction: caller-supplied digests and same-host manifests are not independent trust anchors; signing must fail closed when state or anchor status is uncertain; and state transitions need monotonic, authenticated, serialized commitment.

This review register does **not** certify the design as secure. It identifies decisions and evidence that must be completed by an independent reviewer before Stage A can exit. No production implementation is authorized.

## 2. Stage A findings

| ID | Topic | Current finding | Required closure evidence |
|---|---|---|---|
| A01 | Attacker boundary | Ordinary host, local files, backups and caller-supplied digests are treated as attacker-controlled | Independent reviewer validates privileged-host, physical, insider, and supply-chain assumptions |
| A02 | Anchor compromise | Loss/control of the anchor is acknowledged but response is not yet a complete incident protocol | Document compromise indicators, isolation, quorum recovery, re-provisioning, and governance authority |
| A03 | First-time enrollment | Initial trusted state and first sequence are not yet specified end-to-end | Dual-control enrollment ceremony; authenticated validator/chain binding; out-of-band verification; immutable enrollment audit |
| A04 | State transition atomicity | PREPARED/COMMITTED is a protocol outline, not a proven implementation | Formal state machine, crash-point analysis, idempotent operations, anchor CAS semantics, and fault-injection evidence |
| A05 | Concurrent restore / split brain | Single-generation intent is stated, but lease/fencing and stale-host behavior need exact semantics | Anchor-issued fencing generation or equivalent; old host denied after restore; two-node race test |
| A06 | Anchor outage / partition | Fail-closed policy is stated; recovery and quorum-loss operating procedure is open | Explicit availability policy, RTO/RPO, witness quorum rules, partition behavior, and signed runbook |
| A07 | Anchor disaster recovery | Backup/recovery of anchor metadata and trust roots is not fully specified | Separate custody, threshold recovery, anti-rollback of anchor backups, root rotation, and witnessed restore drill |
| A08 | Schema migration | Unknown schemas fail closed; approved migration semantics remain open | Versioned migration policy preserving monotonic state; no downgrade; synthetic migration tests |
| A09 | Cryptographic agility | Digest/signature/MAC algorithms and domain separation are deferred | Approved algorithm suite, key separation, rotation and deprecation plan, canonical serialization test vectors |
| A10 | CometBFT semantics | Height/round/step binding is required but exact FilePV state interpretation and upgrade compatibility need verification | Source-pinned mapping to CometBFT v0.40.0 state fields and compatibility review for future versions |
| A11 | Backup authenticity | Authenticated encrypted backup is required; recovery-factor custody and restore quorum need operational detail | Key separation, threshold policy, factor-loss response, manifest format, and tamper tests |
| A12 | Audit independence | Separate security-domain logging is required but trust and retention model remain open | Append-only/tamper-evident sink, time-source assumptions, retention, access and export controls |
| A13 | Operator separation | Two-person approval is specified at a high level | Role matrix, separation-of-duty enforcement, break-glass procedure, revocation and periodic access review |
| A14 | Vendor/provider assumptions | No HSM/TPM/witness model has been selected | Comparative evaluation with explicit security claims, failure semantics, support lifecycle and exit plan |

## 3. Mandatory state-machine invariants

Before a reference implementation can be accepted, the protocol specification must make these invariants executable:

1. Exactly one committed successor may extend a given committed predecessor for a validator identity.
2. Every state generation is immutable once written; a new generation is written separately.
3. The previous committed generation remains available until the new generation and anchor commitment have been read back and verified.
4. PREPARED, timeout, unknown acknowledgement, anchor partition, or reconciliation state never enables signing.
5. An anchor operation ID is idempotent for an identical request and rejects reuse with different content.
6. A restored host must obtain a newer fencing generation; an older host must be unable to sign even if it later reconnects.
7. Anchor state loss or corruption does not permit re-enrollment from a local backup alone.
8. Initial enrollment, trust-root rotation, and schema migration require explicit dual control and append-only audit evidence.
9. A rollback of the anchor's own backup/history must be detectable or prevented by a separately protected recovery mechanism.
10. No code path regenerates anti-double-sign state or silently downgrades its schema during recovery.

## 4. Required independent-review questions

The reviewer must answer and record evidence for:

- Can an attacker with full ordinary host administrator/root access replace state, manifests, local trust roots, process binaries, and cached anchor responses?
- What exact capability remains outside that attacker boundary?
- Does the anchor bind the complete canonical state digest, chain/validator context, sequence, predecessor, and transaction status atomically?
- What happens if the anchor acknowledges COMMIT but the response is lost?
- Can two hosts race to restore or commit from the same predecessor?
- How is the old host fenced after restore, including after a network partition heals?
- How is the anchor itself backed up, restored, rotated, and recovered without reintroducing rollback?
- What are the safe outcomes for loss of one or more recovery factors, quorum, hardware, or witness operators?
- Which guarantees are provided by the selected hardware/service and which are only application assumptions?
- Does the protocol remain safe across CometBFT upgrades and state-schema migrations?

A reviewer must explicitly identify residual risks and any conditions under which the stated guarantees do not hold.

## 5. Stage A exit criteria

Stage A is not complete until all of the following are present:

- independent reviewer identity, scope, date, findings, and disposition;
- approved attacker model and explicit excluded threats;
- signed decision records for custody model, anchor model, transaction protocol, bootstrap ceremony, quorum, backup and recovery;
- formal transition table covering normal commit, retry, crash, partition, restore, anchor loss, migration, and key rotation;
- approved operational roles, dual-control matrix, incident runbooks, RTO/RPO and retention policy;
- explicit approval to proceed to a synthetic-only reference model.

An internal document update or green CI run does not substitute for independent security review.

## 6. Safe next engineering activity

While independent review is pending, the only permitted engineering preparation is a deterministic, offline, synthetic reference model with:
- fake validator identities and non-production test keys;
- no network listener or remote signing endpoint;
- no HSM/KMS/cloud credentials;
- no access to real validator homes or production backups;
- test-only anchor abstraction clearly labelled as simulated;
- negative tests for state transitions, idempotency, rollback, concurrent operations, fencing, and crash recovery.

The reference model must not be described as proof of hardware monotonicity or production custody security.

## 7. Current status

**Stage A: open — internal review register prepared; independent review not performed.**  
**Stage B: not started.** It may begin only as a synthetic offline reference model under the constraints above and after the project explicitly records the review disposition required by the plan.

No production key generation, custody provisioning, real signing, public network deployment, token issuance, sale, or exchange activity is authorized. G2–G4 remain closed.
