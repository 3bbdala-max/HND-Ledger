# HND v0.2 — WP4.14 implementation readiness and verification plan

**Date:** 2026-11-04  
**Branch:** `phase-0.2-planning`  
**Status:** Planning artifact only — independent review and design decisions are prerequisites  
**Scope:** Validator consensus-key custody, anti-double-sign state, signer identity, backup and recovery  
**Safety boundary:** This plan creates no keys, credentials, backups, cloud resources, HSM objects, or production signing capability.

## 1. Purpose

Translate the WP4.14 architecture proposal into a reviewable implementation sequence and a testable acceptance matrix. The existing four-validator CI is useful evidence for local crash-stop recovery, but it does not implement production custody. The current Go signer helpers are explicitly disposable integration-test programs; their temporary FilePV keys, local sockets, and test-supplied state digests must not be treated as a production custody boundary.

## 2. Current baseline and evidence boundary

The current test code provides these limited mechanisms:

- The Unix process probe creates disposable FilePV material in a temporary directory and uses a private Unix socket. Its source comments explicitly say the socket is unencrypted and the probe is not production key custody.
- The Noise helper authenticates a peer identity for the test transport and checks a supplied SHA-256 digest of the anti-double-sign state before loading FilePV in recovery mode.
- The recovery supervisor enforces a bounded readiness deadline and terminates a disposable process on timeout; replica convergence compares height, block hash, and application hash.
- WP4.13 CI passed the enumerated local integration cases. This is a test result, not independent assurance of key custody, hardware security, filesystem crash consistency, or Byzantine fault tolerance.

**Critical limitation:** a digest passed to a test process by the same orchestrator is not an independently trusted rollback anchor. An attacker able to replace both the state file and the expected digest can defeat that comparison. A production design needs a separately protected trust anchor and a documented monotonicity guarantee.

## 3. Architecture decisions required before implementation

| Decision | Required decision record | Minimum acceptance criterion |
|---|---|---|
| Consensus key custody | HSM/KMS, dedicated offline signer, or other reviewed custody model | Key non-exportability or approved offline ceremony; documented algorithms and CometBFT compatibility |
| Anti-double-sign state | Storage format, update transaction, durability and rollback anchor | Fail closed on missing/corrupt/stale state; independently detect rollback; no implicit state regeneration |
| Trust-anchor custody | HSM monotonic counter, separately protected state service, or equivalent | Attacker controlling ordinary signer host cannot rewrite both state and trusted version |
| Signer authentication | Noise peer pinning, mTLS, or reviewed transport | Explicit non-empty allowlist; mutual identity verification; rotation procedure |
| Backup encryption | Independent encryption key and recovery quorum | Backup and recovery factors separated; dual control; tamper-evident manifest |
| Restore authority | Named roles, threshold and approvals | No single routine operator can authorize and execute a complete restore alone |
| Key lifecycle | Enrollment, rotation, revocation, emergency removal | Chain-height activation and governance process defined before consensus-key rotation |
| Operations | Audit retention, incident response, RTO/RPO | Tested runbooks and accountable operators identified |

No vendor or algorithm is selected by this plan. Selection requires independent security and operational review against the pinned CometBFT release and deployment environment.

## 4. Proposed implementation sequence

### Stage A — independent review and decision freeze

1. Have an independent security specialist review the threat model, key inventory, signer trust boundaries, rollback assumptions and restore ceremony.
2. Select a custody model and document HSM/KMS/offline-signer guarantees, including failure modes and export restrictions.
3. Define the trust anchor for anti-double-sign monotonicity. A same-host hash file or caller-supplied digest is not sufficient.
4. Approve role separation, dual control, recovery quorum, backup retention, RTO/RPO and incident authority.
5. Record explicit approval before any production adapter or key-generation procedure is implemented.

**Exit condition:** signed architecture decision record and threat-model review. Until then, no production custody implementation. The offline synthetic model described in Stage B may be used as a bounded planning/test artifact while this review is pending; it does not constitute Stage A approval.

### Stage B — deterministic local reference model

A bounded offline synthetic reference model has been implemented on `phase-0.2-planning`, and its dedicated model test suite passed in CI. This records completion of that limited model activity only; it does not mean the full C01–C18 matrix has passed or that Stage A has exited.

The model remains software-only: use synthetic keys and disposable state. It must have no network signing endpoint, cloud integration, HSM credentials, production key import/export, or access to real chain funds.

Required properties:

- Typed manifest binds chain ID, Genesis hash, network ID, validator public-key fingerprint, signer identity, state schema/version, last signed height/round/step, and backup sequence.
- Canonical serialization and explicit schema versioning.
- Authenticated manifest verification using a test-only trust root that is clearly labelled as non-production.
- Atomic state update protocol with crash-injection points before write, during write, after fsync, and after rename.
- Restore verifier rejects unknown schema, mismatched identities, mismatched chain context, stale backup sequence, bad authentication, and any missing recovery factor.
- The reference model never creates a new anti-double-sign state during recovery when an existing state is missing or invalid.

### Stage C — adapter contract and isolated hardware evaluation

Only after Stage A approval, define a narrow signer-provider interface and run a vendor evaluation in a separate sandbox. Use vendor test/simulation mode first. Do not place provider credentials in this repository or CI.

The adapter contract must state:

- accepted key algorithms and key identifiers;
- exact signing message/domain and chain-context checks;
- monotonic-state read/write semantics and atomicity guarantees;
- authentication, authorization, rate limiting and audit events;
- timeout, retry, throttling, outage and failover behavior;
- key non-exportability claims and vendor backup/restore semantics;
- how key rotation and revocation affect validator identity.

### Stage D — supervised disaster-recovery rehearsal

A supervised rehearsal must use a non-production test environment and synthetic assets. Restore into an isolated target with signing disabled. Verify the manifest, chain context, validator identity, state monotonicity, audit record and dual approvals. Re-enable test signing only after an independent reviewer signs off the rehearsal record.

## 5. Verification matrix

Every negative test must fail closed and must not generate replacement signing state.

| ID | Scenario | Expected result | Evidence |
|---|---|---|---|
| C01 | Missing anti-double-sign state | Startup/restore rejected | Error code and unchanged filesystem |
| C02 | Truncated or malformed state | Rejected before signer endpoint opens | Process exit and no listener |
| C03 | Corrupt backup ciphertext | Authentication/decryption failure | No partial restore |
| C04 | Modified manifest | Signature/MAC verification failure | Audit event |
| C05 | Wrong chain ID or Genesis hash | Restore rejected | Context mismatch reason |
| C06 | Wrong validator public-key fingerprint | Restore rejected | Identity mismatch reason |
| C07 | Wrong signer transport identity | Connection rejected | Authenticated peer evidence |
| C08 | Stale backup sequence / rollback | Rejected against independent monotonic anchor | Anchor read and rejected sequence |
| C09 | State and caller-supplied digest both replaced | Must still be rejected by independent trust anchor | Demonstration that anchor is outside attacker-controlled host |
| C10 | Crash before atomic commit | Previous committed state remains valid | Crash-injection result |
| C11 | Crash after durable commit | New committed state is recoverable | fsync/transaction evidence |
| C12 | Missing one recovery factor | Restore denied | Approval/quorum audit record |
| C13 | Single operator attempts dual-control action | Denied | Identity and authorization audit |
| C14 | HSM/KMS unavailable or throttled | Fail closed; no local private-key fallback | Outage log and no signature |
| C15 | Credential rotation/revocation | Old credential rejected; authorized new identity accepted | Rotation event trail |
| C16 | Restore into wrong validator home | Rejected; no signing | Identity binding evidence |
| C17 | Two restored instances attempt same validator identity | Split-brain prevented by operational control | Isolation/lease evidence |
| C18 | Recovery followed by restart and catch-up | State remains monotonic; no conflicting signature | Signer state and chain evidence |

## 6. Required audit events

At minimum, record: key enrollment; public fingerprint and key-version changes; signer-policy changes; operator authentication and elevation; backup creation, retrieval and deletion; manifest verification; restore request, approval and completion; monotonic-anchor reads/writes; signer start/stop; rejected identity or rollback attempts; rotation, revocation and emergency isolation.

Logs must be append-only or tamper-evident, timestamped, access-controlled, and exported to a separate administrative/security domain. Never log private keys, recovery shares, passwords, API tokens, or decrypted backup contents.

## 7. Release gates

- **G-WP4.14-A — Review:** threat model and architecture independently reviewed.
- **G-WP4.14-B — Decisions:** custody provider/model, trust anchor, roles, backup policy and restore ceremony approved.
- **G-WP4.14-C — Reference model:** synthetic-only tests C01–C18 pass in CI where applicable.
- **G-WP4.14-D — Adapter evaluation:** isolated provider test and failure-mode evidence reviewed.
- **G-WP4.14-E — DR rehearsal:** supervised isolated restore passes with signed evidence and independent sign-off.

Passing these gates would establish only the stated scope. It would not by itself establish legal compliance, full protocol security, public-launch readiness, or authorization to handle real value.

## 8. Explicit non-goals

This work item does not generate or store production keys, configure a live HSM/KMS, create cloud accounts, enable production signing, modify mainnet/production configuration, or authorize token issuance, sale, exchange listing, or public launch. No real key material or credentials may be committed to GitHub, uploaded to ChatGPT, or placed in ordinary CI secrets as a shortcut.

## 9. Current disposition

**WP4.14 remains design/review only. Stage B's bounded synthetic reference model and its dedicated CI tests are complete; Stage A remains open pending independent security review.** The next legitimate action is independent review and approval of Stage A decisions. No Stage C adapter/provider integration, production key creation, or signer deployment may begin before the required approvals. G2–G4 remain closed.
