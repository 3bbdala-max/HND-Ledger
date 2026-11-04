# HND v0.2 — WP4.14 Independent Security Reviewer Handoff

**Prepared:** 2026-11-04  
**Repository:** `3bbdala-max/HND-Ledger`  
**Review branch:** `phase-0.2-planning`  
**Reviewed branch head:** `0ba697857fd4cfe3e31c37dcc0d0c894a7648759`  
**CI run:** [41907600792](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41907600792) — completed successfully  
**Main branch at handoff:** `3f0a71e27924954f27813ec68e483ecf159461e5` (not modified)  
**Document status:** Reviewer briefing package only. It is not an audit, certification, approval, or closure of Stage A.

## 1. Purpose and requested engagement

This package gives an independent security reviewer a bounded, evidence-linked starting point for WP4.14: validator consensus-key custody, anti-double-sign state integrity, anti-rollback, backup, and recovery.

The requested work is an independent assessment of the threat model and proposed architecture, including explicit findings, residual risks, and a disposition against the Stage A exit criteria. The reviewer should be competent in validator signing systems, distributed consensus operations, cryptographic key custody, and crash-consistent state/recovery design. The reviewer must be independent of the implementation and must disclose relevant conflicts.

**No reviewer has yet been engaged or has issued an opinion.** The repository's internal register is a checklist, not an independent audit.

## 2. Exact review baseline and evidence

Review the repository at commit `0ba697857fd4cfe3e31c37dcc0d0c894a7648759`, not an unpinned moving branch.

The latest CI run for that exact commit is run [41907600792](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41907600792):
- `hnd-v02-tests`: success.
- `cometbft-single-node-smoke`: success.
- The integration job includes the private four-validator network scenario, remote-signer outage/recovery, authenticated Noise remote-signer integration/recovery, anti-double-sign state rejection probes, and the CometBFT integration checks recorded in the CI job.
- The run is automated test evidence for the specified CI environment only. It is not proof of production BFT safety/liveness, hardware security, independent monotonicity, or production key custody.

A prior timing-sensitive 2/2 partition test was corrected by waiting for all four replicas' height/block-hash fingerprints to stabilize for five seconds before starting the no-quorum observation window. The follow-up run [41897803356](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41897803356) passed. The reviewer should inspect the test and decide whether its assumptions and observation window are adequate; passing CI does not remove the need for that assessment.

## 3. Primary artifacts to inspect

1. `docs/WP4_14_STAGE_A_SECURITY_REVIEW_REGISTER_2026-11-04.md` — 14 open review topics, mandatory invariants, reviewer questions, and Stage A exit criteria.
2. `docs/WP4_14_ADR_ANTI_ROLLBACK_TRUST_ANCHOR_2026-11-04.md` — proposed external monotonic trust-anchor contract; no vendor selected and no implementation approved.
3. `docs/WP4_14_KEY_CUSTODY_BACKUP_RECOVERY_DESIGN_2026-11-04.md` — custody, backup, and recovery design assumptions.
4. `docs/WP4_14_IMPLEMENTATION_READINESS_AND_TEST_PLAN_2026-11-04.md` — staged plan and C01–C18 verification matrix.
5. `docs/WP4_14_CI_TECHNICAL_ACCEPTANCE_EVIDENCE_2026-11-04.md` — recorded CI evidence and explicit limitations.
6. `docs/PHASE_0.2_PLAN.md` — overall phase status and stage boundaries.

The reviewer should inspect relevant source code and tests at the pinned commit rather than relying only on these summaries.

## 4. Required review questions

The review must address, at minimum:

- **Attacker boundary:** Can a fully compromised ordinary validator host replace state, local trust roots, process binaries, backups, cached anchor responses, or orchestration inputs? What capability is explicitly outside this boundary?
- **Anchor semantics:** Does the independent anchor authenticate and monotonically bind the complete canonical state digest, chain/genesis context, validator and signer identities, schema, height/round/step, predecessor, operation ID, and transaction status?
- **Atomicity and crash consistency:** What happens at every crash point, including after anchor acknowledgement but before the caller receives it? Are retries idempotent? Can any ambiguous PREPARED or reconciliation state enable signing?
- **Concurrency and fencing:** Can two hosts restore or commit from the same predecessor? How is the old host fenced after restore and after a partition heals?
- **Anchor compromise and availability:** What are the isolation, quorum, recovery, re-enrollment, and governance procedures after anchor compromise, loss, corruption, outage, or partition?
- **Backup and disaster recovery:** Are backup authenticity, encryption-key separation, recovery-factor custody, anchor-history rollback, restore quorum, and witnessed recovery adequately specified?
- **CometBFT semantics:** Are the exact FilePV/priv-validator state fields and signing-step semantics mapped correctly for the pinned CometBFT v0.40.0 version? Are upgrade and migration risks addressed?
- **Operations and governance:** Are dual control, operator separation, audit independence, time-source assumptions, retention, emergency access, and revocation enforceable rather than merely procedural?
- **Cryptography and providers:** Are canonical serialization, domain separation, algorithms, key separation, rotation, provider guarantees, and failure semantics sufficiently specified without relying on unverified vendor claims?

## 5. Mandatory invariants to challenge

The reviewer must assess whether the design can enforce all ten invariants in the Stage A register, especially:
1. One committed successor per committed predecessor and validator identity.
2. Immutable state generations; previous committed generation retained until successor and anchor commitment are read back and verified.
3. PREPARED, timeout, unknown acknowledgement, partition, and reconciliation never authorize signing.
4. Idempotent operation IDs; conflicting reuse is rejected.
5. Restored hosts obtain a newer fencing generation; stale hosts cannot sign after reconnecting.
6. Anchor loss/corruption cannot be bypassed by local-backup-only re-enrollment.
7. Enrollment, trust-root rotation, and schema migration require dual control and append-only audit evidence.
8. Rollback of anchor backup/history is detectable or prevented by a separately protected mechanism.
9. No recovery path silently regenerates or downgrades anti-double-sign state.

If an invariant cannot be guaranteed under the stated attacker model, the reviewer must state the limitation and propose a safe disposition; do not silently weaken the requirement.

## 6. Required reviewer deliverable

Please return a signed report containing:

- reviewer identity, qualifications, organization (if applicable), independence/conflict disclosure, review date, exact commit SHA, and scope;
- artifacts and source/test paths inspected, plus methodology and any tests independently reproduced;
- finding register with severity, affected component, exploit preconditions, impact, evidence, and remediation;
- explicit answers to the questions in section 4 and disposition for every A01–A14 item;
- invariant-by-invariant result: satisfied, not satisfied, or not demonstrated, with evidence;
- residual risks, excluded threats, assumptions, and any compensating controls;
- a clear Stage A recommendation: approve with stated conditions, reject, or more evidence required;
- cryptographically signed report or another verifiable approval record accepted by project governance.

A generic statement such as “looks secure” or a CI badge is not an acceptable review deliverable.

## 7. Stage boundaries and prohibited actions pending approval

- **Stage A:** OPEN until the independent review and required signed architecture decisions are complete and accepted.
- **Stage B:** bounded offline synthetic reference model implemented; its dedicated tests passed in CI. This is not full C01–C18 completion and does not close Stage A.
- **Stages C/D:** NOT AUTHORIZED / NOT STARTED. No live HSM/KMS/provider integration or supervised production-like disaster-recovery rehearsal is authorized by this handoff.
- **Release gates G2–G4:** CLOSED.

Do not generate production keys, introduce provider credentials, connect real custody services, enable production signing, deploy a public network, issue/sell/list a real-value token, or move this work to `main` based on this document or the green CI result.

## 8. Acceptance and change control

The reviewer should report against the pinned commit. Any material code or design change during review must be separately identified and the affected review areas re-evaluated. Review closure requires explicit project-governance acceptance of the signed findings and decision records; this handoff itself grants no authorization.

---
**Boundary statement:** This document organizes evidence and requests independent scrutiny. It does not claim that an audit has occurred, that WP4.14 is production-ready, or that any legal, regulatory, operational, or release approval has been obtained.
