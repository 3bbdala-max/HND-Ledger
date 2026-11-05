# HND v0.2 — remote signer anti-rollback implementation boundary audit

**Workstream:** WP4.14 — validator signer safety and recovery  
**Review date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Review type:** static source/test/design review; documentation-only  
**Scope:** distinguish implemented CometBFT signer integration evidence from the offline anti-rollback reference model and the proposed durable recovery protocol.

## 1. Executive finding

The repository contains two different levels of work that must not be conflated:

1. A four-validator integration harness exercises a controlled remote-signer outage/restart path. It moves a validator consensus key and signing-state file into a temporary signer-owned directory, observes state advancement, stops the signer, and restarts it with a digest captured by the harness. It also checks selected key-file digests across a node restart and optionally probes unauthorized Noise identities.
2. `hnd_v02/anti_rollback_reference.py` is explicitly an **offline synthetic reference model**. Its `SyntheticAnchor` is in-memory, uses a fixed synthetic MAC key, and provides no durable trust anchor. It is not wired into the production CometBFT remote-signer process or the HND ABCI application.

The reference model tests meaningful state-machine properties, including fail-closed behavior, host fencing, monotonic HRS transitions, stale local backup rejection, anchor outage, lost commit reply reconciliation, and model restart with a pending operation. However, these are tests of the synthetic model, not proof that a production signer uses an independent monotonic checkpoint or durably commits anti-double-sign state before releasing a signature.

**Production anti-double-sign protection and production key custody remain unproven.** Do not enable real-value validator signing on the strength of the current harness or synthetic model alone.

## 2. What the integration harness demonstrates

The existing remote-signer integration audit records that the harness:
- moves the validator consensus private key and signing-state file into a temporary signer-owned directory;
- applies restrictive file modes in the controlled test setup;
- observes signing-state advancement after a signer operation;
- stops the signer and restarts it using a captured post-stop state digest;
- exercises Unix-socket or Noise transport depending on the external signer binary;
- optionally probes an unauthorized Noise identity and expects a rejection marker;
- checks validator consensus-key and P2P node-key file digests across a node restart.

This is useful controlled integration evidence, but it does not demonstrate:
- that a production signer independently authenticates the supplied recovery digest;
- rejection of an older but valid signing-state snapshot;
- exclusive ownership when two signer processes start concurrently;
- crash safety at every persistence boundary;
- atomic durable intent/checkpoint advancement before signature release;
- Unix socket owner/mode and unauthorized local UID rejection;
- production identity issuance, revocation, rotation, or key custody.

A digest is an integrity fingerprint. It is not an anti-rollback trust anchor unless its expected value is authenticated and protected outside the attacker's rollback domain.

## 3. Synthetic reference model: implemented properties and limits

Source: `hnd_v02/anti_rollback_reference.py`.

Implemented in the offline model:
- thread-safe in-memory compare-and-swap transitions;
- PREPARED state disables signing;
- exact operation ID/payload retry semantics;
- operation-ID reuse with conflicting payload is rejected;
- monotonic sequence, predecessor digest, and H/R/S progression checks;
- stale host epoch is fenced at the anchor transition boundary;
- a pending PREPARED operation prevents restoring the previous committed generation;
- anchor outage fails closed;
- lost commit reply can be reconciled by operation ID;
- a stale local backup cannot replace a newer anchored generation;
- model restart with a pending operation and missing generation data remains blocked;
- historical operation outcomes are represented in an operation map.

Hard limitations:
- anchor records, operation history, host fencing, and generations are in memory;
- fixed synthetic MAC key is embedded in the model and is not a production secret;
- no durable write-ahead log, fsync protocol, hardware-backed monotonic counter, external database, or independently administered anchor exists;
- the model is not connected to the CometBFT remote signer;
- no signature-release path is gated by this model in the production node;
- no production operator authentication, authorization, or dual-control workflow is enforced by an external trusted service.

Therefore the model demonstrates protocol logic only. It does not supply a production security boundary.

## 4. Previously identified model edge cases

The pending-operation recovery design already records two additional static-review findings:

### 4.1 Multiple unresolved PREPARED operations

A new operation ID can be accepted while the current anchor record is PREPARED under a different operation ID. This can create multiple unresolved operations, contrary to the single-pending-operation protocol.

Required behavior: reject a new operation while the current record is PREPARED; permit only an exact retry or the exact PREPARED-to-COMMITTED transition for that same operation.

A dedicated regression test is specified in the design document. This review does not claim that correction has been implemented.

### 4.2 Historical COMMITTED result versus current signing state

The operation-history APIs can return an old COMMITTED operation even after a newer operation has advanced the latest anchor record. The design distinguishes historical operation outcome from current-state authorization. The signing gate independently reads the latest anchor, but callers must not mistake a historical COMMITTED result for permission to sign now.

Required behavior: current-state confirmation must compare the latest anchor record's operation ID, sequence, transaction digest, state digest, and identity context. If the anchor is unavailable, current-state status remains unknown/blocked.

These findings are specific to the synthetic reference model and do not establish that a production signer is vulnerable through this model; the model is not wired into that signer.

## 5. Test coverage and execution status

The repository includes `tests/test_v02_anti_rollback_reference.py`, with cases covering normal prepare/commit/restore, PREPARED signing lock, ambiguous commit reconciliation, anchor outage, dual control, stale restore rejection, corrupted generation, identity/schema checks, host fencing, concurrent prepare CAS, operation ID idempotency/conflict, predecessor digest, HRS progression/regression, stale backup rejection, and pending-operation restart behavior.

The prior audit records that this test module is **not listed in the current CI workflow**. The earlier required local command is:

```bash
python -m pip install -r requirements.txt
python -m unittest -v tests.test_v02_anti_rollback_reference
```

This review did not execute that command. Passing results must not be claimed until run in an authorized environment and recorded.

The test module remains synthetic-model coverage even if it passes. It cannot substitute for remote-signer process-level negative tests.

## 6. Required production acceptance gates (not run)

1. **RS-PROD-01 — stale-state rollback:** restore an older valid signing-state snapshot while the independent anchor remains advanced; signer must refuse to start and must not emit a signature.
2. **RS-PROD-02 — concurrent signer exclusion:** start two signer processes against the same validator key/state; exactly one may acquire the signing lease/lock, and the losing process must not sign.
3. **RS-PROD-03 — crash boundaries:** inject process termination/power-loss simulation before, during, and after intent persistence, signature generation, state persistence, and response delivery; demonstrate no conflicting signature can be released after recovery.
4. **RS-PROD-04 — authenticated monotonic checkpoint:** substitute, replay, truncate, or roll back the checkpoint; reject unless independently authenticated and monotonic.
5. **RS-PROD-05 — exact request replay:** replay identical and conflicting sign requests across restart; preserve the pinned CometBFT H/R/S anti-double-sign rules.
6. **RS-PROD-06 — socket authorization:** unauthorized local UID/process cannot connect to or control the Unix signer socket; verify owner and mode.
7. **RS-PROD-07 — Noise identity lifecycle:** reject unknown, revoked, and expired identities; test trust-root rotation and auditability.
8. **RS-PROD-08 — key/state binding:** reject a key or state snapshot transplanted from another validator, signer identity, chain, or Genesis.
9. **RS-PROD-09 — independent anchor failure:** unavailable, stale, inconsistent, or failover anchor leaves signing disabled.
10. **RS-PROD-10 — recovery audit trail:** produce an authenticated record of signer identity, software version, H/R/S, checkpoint digest, recovery decision, and operator authorization without exposing private key material.

## 7. Release disposition

| Control | Status |
|---|---|
| Controlled remote-signer outage/restart harness | Implemented as test integration evidence |
| Signing-state file changes across operation | Observed in controlled harness |
| Harness-provided post-stop digest on restart | Implemented in test path |
| Synthetic anti-rollback state machine | Implemented as offline reference model |
| Synthetic model test coverage | Present; CI inclusion gap previously recorded; not run in this audit |
| Independent durable monotonic anchor | Not implemented |
| Production signer integration with anti-rollback model | Not implemented |
| Stale valid state rejection by production signer | Not demonstrated |
| Concurrent signer exclusion | Not demonstrated |
| Crash-boundary anti-double-sign proof | Not demonstrated |
| Production signer key custody/authorization | Not demonstrated |

**Final disposition:** the current work is valuable design and test scaffolding, not production anti-double-sign certification. Keep production validator signing disabled until the independent durable anchor, signer integration, concurrent exclusion, rollback rejection, crash-boundary tests, and operator/key-custody controls are implemented and independently reviewed.

No source, test, workflow, signer key, or runtime configuration was changed. No tests were executed during this review. This report is not a security certification or launch approval.
