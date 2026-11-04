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

## 10. CI evidence update — 2026-11-05

The GitHub Actions run [41918181895](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41918181895) completed with **success** for both jobs on the exact branch head `afd6d17fac73a266a0e7ade2521363efb9615dca`:

- `hnd-v02-tests`: success.
- `cometbft-single-node-smoke`: success, including the private four-validator network, external remote-signer outage/recovery, authenticated Noise remote-signer integration/recovery, and rejection of missing or substituted anti-double-sign state in the exercised recovery paths.

This is evidence for the named CI scenarios on this commit only. The recovery helper's expected state digest is supplied by the test orchestrator; it is not an independent monotonic trust anchor. The test therefore does not satisfy C08/C09 as production-grade rollback protection, and does not establish crash-consistent storage, HSM guarantees, or independent custody assurance.

Repository boundary check at this update: `phase-0.2-planning` points to `afd6d17fac73a266a0e7ade2521363efb9615dca`; `main` remains at `3f0a71e27924954f27813ec68e483ecf159461e5`. No merge or production action was performed.

**Disposition unchanged:** Stage A remains OPEN pending a qualified independent review and signed decisions. Stage C/D and G2–G4 remain closed.


## 11. CI evidence update — 2026-11-05 (anchor outage after commit)

The GitHub Actions run [41921054546](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41921054546) completed with **success** on branch commit `c387b67923ce194d44623fed425f15914affa6aa`. Both jobs passed:

- `hnd-v02-tests`: success.
- `cometbft-single-node-smoke`: success.

The added synthetic test `test_anchor_outage_after_commit_disables_signing_and_restore` first commits a state, then makes the synthetic anchor unavailable. It asserts that signing is disabled and restore raises `AnchorUnavailable`; after the anchor is made available again, it checks that the committed anchor record is unchanged and that restore can proceed.

This is a bounded in-memory reference-model test. It does not simulate power loss, durable storage, an independently administered monotonic anchor, or production key custody. It is evidence for the tested fail-closed behavior only; it does not close C08/C09 or C10/C11.

Repository boundary check: `phase-0.2-planning` points to `c387b67923ce194d44623fed425f15914affa6aa`; `main` remains at `3f0a71e27924954f27813ec68e483ecf159461e5`. No merge or production action was performed.

**Disposition unchanged:** Stage A remains OPEN pending qualified independent review and signed decisions. Stage C/D and G2–G4 remain closed.


## 12. CI scope correction — 2026-11-05

A subsequent audit of `.github/workflows/hnd-v02-tests.yml` found that the `hnd-v02-tests` job's explicit `python -m unittest` command does **not** include `tests.test_v02_anti_rollback_reference`. Therefore, the successful workflow run [41921054546](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41921054546) does not establish that either `test_anchor_outage_after_commit_disables_signing_and_restore` or the later C08 stale-local-backup test was executed by CI. The same limitation applies to the other tests in that module unless they are invoked elsewhere.

A local execution attempt was also unavailable because the environment could not resolve `github.com` to clone the repository. Accordingly, the two new reference-model tests are **committed but not yet execution-verified**. Do not count them as passed tests or as CI evidence.

The workflow file was not modified. Before relying on these tests, they must be run in an authorized test environment or included in a separately reviewed CI change. This correction supersedes any implication in the preceding CI evidence entry that the new anti-rollback unit test itself was covered by that run.

**Disposition:** C08 remains unverified; the additional C14 synthetic-anchor outage test remains unverified. The successful CI run remains valid only for the commands and scenarios actually listed in the workflow. Stage A remains OPEN; no production or release gate changes.


## 13. Required execution command for the synthetic anti-rollback test module

Until the workflow is changed through a separately reviewed and authorized CI change, execute the module explicitly from the repository root in a Python 3.12 environment after installing the pinned project requirements:

```bash
python -m pip install -r requirements.txt
python -m unittest -v tests.test_v02_anti_rollback_reference
```

The module currently contains 30 test methods, including the C08 stale-local-backup scenario, the synthetic anchor-outage-after-commit scenario, rejection of unsupported anchor schema versions, and C10/C11 model checks for retaining the last committed record during PREPARED and reconciling an ambiguous commit. These tests are committed but remain unverified by execution: the current workflow's explicit unittest list omits this module. Record the exact commit SHA, Python version, command, complete test output, and environment identity with any future execution evidence. A successful run of the repository's existing workflow is not a substitute for this command.

This section is an execution instruction only. It is not evidence that the command has been run or passed.


## 14. Synthetic PREPARED/COMMITTED retention update — 2026-11-05

The offline model now keeps a separate in-memory pointer to its last COMMITTED anchor record while a newer operation is PREPARED. The current operation remains PREPARED, so signing_allowed continues to fail closed; the previous committed record is retained for model inspection rather than being overwritten as the only committed reference.

Two dedicated tests were added:
- test_c10_pending_prepare_preserves_last_committed_record: confirms that a pending prepare does not erase the previous committed record and does not enable signing.
- test_c11_ambiguous_commit_retains_new_committed_record: confirms that a simulated lost reply after the in-memory commit can be reconciled by operation ID and that the committed pointer advances to the new record.

These are in-memory state-machine tests only. They do not simulate filesystem write ordering, fsync, atomic rename, power loss, durable transaction logs, or a separately administered trust anchor. They do not establish C10/C11 production acceptance. The dedicated test module still requires explicit execution using the command in Section 13; the existing workflow does not run it.


## 15. C10 restore-boundary clarification — 2026-11-05

A further synthetic test, `test_c10_previous_committed_record_is_not_a_restore_authorization_during_pending_prepare`, records an important boundary in the current model. While a newer operation is PREPARED, `read_last_committed()` still exposes the preceding COMMITTED record for inspection, but `restore()` continues to consult the current anchor record and rejects restoring that earlier generation. Signing also remains disabled while the pending operation is unresolved.

This is intentional fail-closed behavior for the present reference model. Retaining the prior record is **not** an abort, rollback, or recovery protocol. No operation currently resolves or safely abandons a PREPARED transaction after a crash or ambiguous outcome. Designing such a protocol requires explicit state-transition rules, durable atomicity, restart/reconciliation semantics, and independent review; it must not be inferred from the retained pointer.

The dedicated anti-rollback test module now contains 31 test methods. All 31 remain committed but unverified by execution until the exact module is run using the command in Section 13 in an authorized Python 3.12 environment. The existing workflow's explicit test list still omits this module. No workflow file was changed.

**Disposition:** C10/C11 remain synthetic-model work, not production acceptance. Stage A remains OPEN; Stage C/D and G2–G4 remain closed.
