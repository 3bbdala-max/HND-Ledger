# WP4.15 — Anti-Rollback Reference Model, Signer Release Boundary, and Production Gate

**Inspection date:** 2026-11-08  
**Branch:** `phase-0.2-planning`  
**Inspected HEAD:** `8af21620cb5a5df9649b770bf2e7e0fa96694a81`  
**Review type:** Static source review and exact-commit CI evidence reconciliation  
**Change type:** Documentation only  
**Disposition:** Reference-model and smoke-test evidence is positive for the exercised cases; production signing authorization remains unapproved.

## 1. Exact-commit CI evidence

GitHub Actions run `42418415505` targets the exact inspected HEAD `8af21620cb5a5df9649b770bf2e7e0fa96694a81` and completed with conclusion `success`.

Both jobs completed successfully:

- `hnd-v02-tests`: all listed steps succeeded, including installation of the isolated JCS dependencies, the cross-language compatibility spike, and the v0.2 test suite.
- `cometbft-single-node-smoke`: all listed steps succeeded, including signer anti-double-sign smoke, process-isolated remote signer probes, same-host FilePV single-writer lock contention, Noise remote-signer authentication/recovery probes, and four-validator integration scenarios.

This is evidence for the exact workflow and scenarios that ran on this SHA. It is not evidence that every production topology, operating system, storage failure mode, hardware security boundary, or hostile-host scenario has been tested.

## 2. Static source boundary

The inspected `hnd_v02/anti_rollback_reference.py` declares itself an offline synthetic model. Its module-level contract explicitly excludes production trust-anchor use and connection to CometBFT, signers, filesystem, HSM, TPM, KMS, or network services.

The implementation confirms that boundary:

- `SyntheticAnchor` stores its record, operation map, host epoch, and active-host identity in process memory.
- Its compare-and-swap operation is protected by an in-process Python lock; this is not a durable, independently administered anchor.
- Record authentication uses a fixed synthetic MAC key whose value is embedded in the test module and explicitly labelled test-only.
- `OfflineAntiRollbackModel.signing_allowed(host_id)` reads the anchor, validates the synthetic record and generation digest, and returns a boolean.
- That boolean is a point-in-time observation. It is not itself an atomic authorization operation coupled to the actual FilePV or remote-signer signature release.

The reference model is useful for state-machine testing, but none of these properties should be represented as production key custody or production anti-rollback enforcement.

## 3. Security interpretation of current passing probes

The exact-HEAD workflow's successful steps provide useful regression evidence for the named cases:

1. A same-host single-writer lock rejects the tested competing FilePV signer process scenario.
2. Remote-signer protocol and process-isolation probes pass for their configured test environment.
3. The tested anti-double-sign persistence and crash/recovery sequences pass.
4. The tested authenticated Noise peer and unauthorized-peer rejection scenarios pass.
5. The tested four-validator remote-signer integrations and outage-recovery scenarios pass.

The correct claim is that these named test scenarios passed on commit `8af21620cb5a5df9649b770bf2e7e0fa96694a81`. They do not establish that the production signer has a durable fencing authority shared across independent hosts, or that a stale host is unable to release a signature after a failover race.

## 4. Remaining signature-release race to close

A production design must not implement authorization as:

1. signer asks an external guard whether signing is currently allowed;
2. guard returns `true`;
3. failover or fencing occurs;
4. the old signer releases a signature using the earlier result.

The authorization decision and signature release need one enforceable serialization boundary. A stale host must be rejected at the point where the signing operation is committed, not merely at an earlier health/readiness check.

Required properties for a production design:

- **Durable monotonic fencing epoch:** allocated by a trust anchor that survives process and host restart and cannot be rolled back by restoring an ordinary local backup.
- **Single authoritative writer:** a stale or partitioned host cannot obtain a valid signing authorization after a newer epoch is committed.
- **Atomic release semantics:** the signer or trusted signing service validates the current fencing epoch and anti-double-sign HRS at the signature-release boundary.
- **Crash consistency:** power loss between durable state commit and signature response must reconcile by stable operation identity without permitting a conflicting second signature.
- **Identity binding:** anchor state is bound to chain ID, Genesis hash, validator identity, signer identity, and the expected software/configuration profile.
- **Fail-closed behavior:** anchor unavailability, ambiguous commit, missing state, identity mismatch, or recovery uncertainty prevents signing.
- **Independent recovery controls:** restoration requires separately administered dual control and a documented, tested recovery ceremony.

A local mutex or lock file is a useful same-host concurrency control, but it is not a substitute for distributed fencing across independent hosts.

## 5. Required evidence before production approval

The following artifacts are still required and must be independently reviewed:

| Gate | Required evidence | Current disposition |
|---|---|---|
| Durable anchor | Threat model, implementation, durability guarantees, rollback resistance, and failure semantics | OPEN |
| Cross-host fencing | Adversarial partition/failover tests proving stale-host signature denial | OPEN |
| Atomic signer integration | Source-level proof and tests that fencing and HRS checks guard actual signature release | OPEN |
| Crash/restart | Power-loss and ambiguous-response tests against durable production state | OPEN |
| Key custody | Separate custody domains, access controls, audit trail, backup and restore evidence | OPEN |
| Recovery ceremony | Witnessed dual-control restore drill and rollback/compromise procedure | OPEN |
| Runtime enforcement | Unavoidable pre-start gate before both HND ABCI and CometBFT launch | OPEN |
| Independent review | External security review of signer, anchor, storage, and operations | OPEN |

## 6. Safe next implementation sequence

No production implementation change is authorized by this review. The next engineering sequence should be:

1. Write a concrete production threat model and select the anchor trust boundary (for example, a separately administered service or hardware-backed mechanism); do not assume a particular vendor or hardware.
2. Specify the signer request/commit/release protocol, including fencing epoch, HRS, operation ID, idempotency, and ambiguous-result reconciliation.
3. Define how the selected mechanism prevents a stale host from signing after failover, including network partitions and restored snapshots.
4. Build adversarial tests against a disposable synthetic environment first; do not use real validator keys.
5. Integrate only after design review, then require exact-commit CI and an independent security review.
6. Keep the pre-start VSP/profile verifier and signer authorization as separate mandatory gates, both fail-closed.

## 7. Scope and decision

This report adds documentation only. It does not modify source code, tests, workflows, dependencies, Genesis, keys, validator configuration, or protocol rules. It does not trigger a CI rerun or authorize a production deployment.

**Decision:** The current CI evidence is a positive regression result for the tested scenarios. The offline anti-rollback model and passing signer smoke tests are not sufficient to close the production anti-rollback/signature-release gate. No public launch, production signing, token issuance, or production-readiness approval is implied.
