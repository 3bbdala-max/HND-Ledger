# WP4.14 — Signer Authorization TOCTOU and Signature-Release Linearization Audit

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Review type:** Static source and test review; documentation-only.  
**Change boundary:** No source, tests, workflow, signer process, keys, or runtime settings changed.

## 1. Executive determination

The offline anti-rollback reference model exposes a `signing_allowed(host_id)` predicate. That predicate is a point-in-time readiness check, not a durable authorization capability and not an atomic gate around a consensus signature.

The method separately reads the anchor record, validates its status and MAC, looks up a local generation, hashes that generation, and finally checks whether the host epoch is current. The anchor can be fenced or its record can change after the readiness check returns and before a caller performs a signing operation.

More importantly, the reviewed model is not called by the CometBFT FilePV or remote-signer signature-release path. It is explicitly an offline synthetic model with in-memory state and a fixed test-only MAC key. It must not be connected to a real signer.

**Disposition: Critical integration gap remains open.** No production signing authorization, anti-rollback enforcement, or signer failover is approved by this audit.

## 2. Direct source observations

Reviewed files:

- `hnd_v02/anti_rollback_reference.py` (blob SHA `041ae09e97c37d77dea77def911653803503b31b`)
- `tests/test_v02_anti_rollback_reference.py` (blob SHA `7ab7f7dc7eae47fdb7b84d24711593652ac768ed`)
- `scripts/cometbft_v040_remote_signer_process_probe.go`
- `scripts/cometbft_v040_noise_remote_signer_helper.go`
- `.github/workflows/hnd-v02-tests.yml`

### 2.1 The readiness predicate is observational

`OfflineAntiRollbackModel.signing_allowed()`:

1. reads the current anchor record;
2. returns false unless the record is COMMITTED;
3. validates network/Genesis/validator/signer identity, schema and synthetic MAC;
4. reads the generation from the model's local in-memory map;
5. hashes the generation and compares it with the anchored digest;
6. checks the host identity and cached host epoch against the anchor's current host epoch;
7. returns a boolean.

Those operations are not one atomic transaction with a subsequent signature. The method returns no unforgeable, one-use authorization token and reserves no signing sequence at the anchor.

### 2.2 Fencing does not retroactively cancel an already returned boolean

The synthetic anchor serializes each individual read, host check and compare-and-swap under its own lock. That protects each operation's internal state transition. It does not hold the lock across the caller's later signing operation.

A possible interleaving is:

- Host A calls `signing_allowed(A)`; it reads a COMMITTED record and passes the host-epoch check.
- The method returns `True`.
- A takeover fences Host A and advances the epoch to Host B.
- Host A, having retained the earlier boolean, proceeds to call a signer unless a separate signature-release gate rechecks/fences the operation atomically.

This is a source-derived race scenario, not a reproduced exploit. The reviewed tests cover stale-host rejection when the model is called after takeover; they do not test a retained `True` result followed by takeover and a subsequent signature attempt.

### 2.3 The reference model is not connected to signing

The module header explicitly states that it is an offline synthetic protocol model using an in-memory anchor and a fixed synthetic MAC key, and must never be connected to CometBFT, a signer, filesystem, HSM, TPM, KMS or network service.

The inspected remote-signer process probes exercise CometBFT v0.40.0 signer behavior and temporary state. They do not call `OfflineAntiRollbackModel.signing_allowed()`, obtain an anchor authorization, or enforce a shared fencing epoch at signature release.

### 2.4 Test and CI boundary

The anti-rollback reference tests include:
- anchor compare-and-swap concurrency in the synthetic in-memory model;
- old-host rejection after takeover;
- stale model-instance rejection after fencing;
- prepared-versus-committed readiness behavior;
- ambiguous commit reconciliation and synthetic restore checks.

These tests establish properties of the reference model only. The current `.github/workflows/hnd-v02-tests.yml` isolated v0.2 test command does not list `tests.test_v02_anti_rollback_reference` or `tests.test_v02_recovery_controls`. The current remote-signer process probes do not close the missing anchor-to-signature-release integration.

## 3. Required production invariant

The security invariant must be stronger than “the host checked readiness recently”:

> Every signature release must be linearized against the current authenticated signer authorization, validator identity, chain/Genesis identity, anti-double-sign state and active fencing epoch. A fenced or stale host must be unable to release a signature, even if it obtained a prior readiness result.

A correct design must define the linearization point and prove that no signature can escape after authorization has been revoked or superseded.

## 4. Candidate enforcement patterns (not selected)

The production design must select and independently review one enforceable pattern, such as:

1. **Signer-side authoritative gate:** the component holding the non-exportable consensus key performs the current epoch/anchor check and signature operation as one serialized operation, refusing stale epochs.
2. **Anchor-issued one-use signing authorization:** a trusted authority atomically reserves the next H/R/S transition and issues a cryptographically bound, short-lived, one-use authorization that the signer validates and consumes. Replay, duplicate use and ambiguous completion must be handled.
3. **Fenced signer ownership with durable lease semantics:** the signer service itself enforces a monotonic fencing token on every request, and old owners cannot access the key after takeover. Lease expiry alone is insufficient without enforcement at the key boundary.

A caller-side boolean, cached health status, periodic polling, host-local mutex, PID lock, or orchestrator lease is not sufficient unless the actual signature-producing boundary enforces it.

## 5. Required tests before any production signer integration

| ID | Scenario | Required result |
|---|---|---|
| AUTH-TOCTOU-01 | Host A obtains readiness=true; Host B fences A before A requests a signature | A's signature request is rejected |
| AUTH-TOCTOU-02 | Fencing occurs while A's signing request is queued | Exactly one linearized outcome; no post-fence A signature |
| AUTH-TOCTOU-03 | Two hosts concurrently request the same next H/R/S | One authorized owner; no duplicate/conflicting signature release |
| AUTH-TOCTOU-04 | Authorization response is delayed or replayed after epoch increment | Reject stale/replayed authorization |
| AUTH-TOCTOU-05 | Anchor becomes unavailable between readiness and signature request | Fail closed at the signer boundary |
| AUTH-TOCTOU-06 | Signer process crashes after reservation but before response | Idempotent reconciliation; no unsafe H/R/S reset |
| AUTH-TOCTOU-07 | Signer crashes after signature generation but before durable state/acknowledgement | Recover without releasing a conflicting signature |
| AUTH-TOCTOU-08 | Old process remains alive after takeover | Key boundary rejects old fencing epoch |
| AUTH-TOCTOU-09 | Identity, chain, Genesis, signer key or state digest differs | Reject before signature release |
| AUTH-TOCTOU-10 | Concurrent retry of same operation ID | Idempotent result or explicit rejection; never a second independent reservation |

Tests must run against the actual signer/key boundary and a durable independently administered anchor implementation. In-memory unit tests are supplementary, not acceptance evidence.

## 6. Evidence required for closure

- A reviewed architecture showing where the consensus private key is held and where authorization is enforced.
- An independently administered, durable, authenticated monotonic anchor with explicit fencing semantics.
- A single-writer/linearization proof for every signature-release path, including retry and crash recovery.
- Process-level multi-host tests for all AUTH-TOCTOU cases above.
- Evidence that CometBFT cannot bypass the gate through local FilePV, an alternate signer endpoint, recovery mode, or stale process.
- Independent security review and signed test/release evidence tied to immutable source and binary identities.

## 7. Decision

**OPEN — NOT APPROVED.**

This audit identifies a concrete boundary between a successful readiness check and a later signature operation. It does not assert that a production exploit has been demonstrated. The reference model remains offline and synthetic; no production signer integration is present or authorized. Do not enable production signing, validator failover, or public network launch on the strength of this model.
