# P0 Signer Fencing — Concurrency, Crash, and Recovery Test Plan

**Status:** TEST SPECIFICATION — NOT IMPLEMENTED; NOT EXECUTED; NOT PRODUCTION APPROVED  
**Date:** 2026-11-20  
**Design branch:** `work/p0-signer-fencing-design`  
**Tracking issue:** #52  
**Related design:** `P0_SIGNER_FENCING_DESIGN_CONTRACT.md`, `P0_SIGNER_FENCING_THREAT_MODEL.md`, `P0_SIGNER_RELEASE_INTERFACE_CONTRACT.md`  
**Baseline under review:** `phase-0.2-planning` (record the exact SHA at each test execution)

## 1. Purpose

Define deterministic acceptance tests for the P0 signer-fencing gap before implementation. The tests must establish that a stale signer cannot release a consensus signature after ownership moves, that conflicting H/R/S requests cannot both be released, and that crashes, retries, failover, or restore cannot roll back signer authority or anti-double-sign state.

This document adds test specifications only. It does not select a production authority, database, quorum, lease duration, key-custody vendor, hardware root, or takeover policy.

## 2. Safety boundary

- Use disposable validator keys, synthetic chain identities, isolated processes, and isolated test networks only.
- Never use production validator keys, production credentials, real funds, or a public network.
- Do not connect `OfflineAntiRollbackModel`, its synthetic MAC key, or its in-memory anchor to a real signer.
- Same-host `flock`, process-local mutexes, cached epochs, startup checks, and caller-side readiness booleans are not distributed fencing evidence.
- Do not treat a model/unit test as proof of actual CometBFT key-release enforcement.
- Keep production signing disabled until the key-custody and release-boundary design is independently approved.

## 3. Test layers and evidence labels

Every result must carry exactly one primary evidence label:

| Label | Environment | What it can establish |
|---|---|---|
| MODEL | Pure reference/state-machine model | State transition logic only |
| UNIT | Component tests with controlled fakes | Local component behavior only |
| PROCESS | Separate OS processes and independent state handles | Process races and persistence behavior on one host |
| MULTI_HOST | Separate hosts/VMs with real network partition controls | Cross-host fencing and takeover behavior |
| KEY_BOUNDARY | Actual protected key service/HSM or equivalent boundary | Whether stale authorization can be prevented at the cryptographic operation |
| COMETBFT | Exact pinned CometBFT v0.40.0 source/build and adapter | Whether every production-shaped proposal/vote reaches the guarded path |

A test cannot claim a stronger label than the environment it exercised. Passing MODEL/UNIT/PROCESS tests does not imply MULTI_HOST, KEY_BOUNDARY, or COMETBFT acceptance.

## 4. Common fixture and evidence

Each test fixture must define:
- synthetic `network_id`, Genesis hash, validator public key, and signer identity;
- two independently started signer instances A and B;
- authority state with a durable epoch and explicit owner;
- disposable key material held only by the test key boundary;
- deterministic barriers/fault hooks at each operation boundary;
- a durable request ID and canonical sign-bytes digest;
- a record of every signature-release attempt, successful release, rejection, and durable H/R/S transition.

Each report must record:
1. test ID and specification revision;
2. exact repository commit SHA;
3. exact CometBFT source revision and binary digest when applicable;
4. authority/key-service build or image digest;
5. environment and evidence label;
6. command and configuration;
7. fault/barrier position;
8. expected and observed outcomes;
9. signer epoch/owner before and after;
10. H/R/S and request-ID ledger before and after;
11. signature verification result using the disposable validator public key;
12. logs/audit event identifiers, with secrets redacted.

## 5. Mandatory test cases

### Group A — ownership and stale signer fencing

| ID | Scenario | Procedure | Required result |
|---|---|---|---|
| FENCE-01 | Two owners contend | A and B concurrently request ownership for the same full identity scope and expected epoch | Exactly one linearizable ownership transition wins; one current epoch/owner is observable |
| FENCE-02 | Stale owner after committed transfer | A owns epoch e; transfer to B commits epoch e+1; A submits a fresh signing request | A is rejected at the actual key-release boundary; no signature is emitted |
| FENCE-03 | Partitioned stale owner | A is isolated from authority; B takes over under the approved policy; A later reconnects | A remains fenced; reconnecting or presenting cached authorization cannot restore signing |
| FENCE-04 | Retained positive preflight response | A obtains any permitted preflight/readiness response; B's transfer commits; A then requests a signature | The old response cannot authorize release; the key boundary rejects A |
| FENCE-05 | Delayed/replayed authorization | Delay an authorization response until after epoch advancement, then replay it | Rejected as stale/replayed; no signature release |
| FENCE-06 | Identity-scope substitution | Reuse an authorization across a different network, Genesis, validator key, signer instance, or request digest | Reject before key operation; audit the mismatch |

### Group B — signature/transfer race and anti-double-sign

| ID | Scenario | Procedure | Required result |
|---|---|---|---|
| RACE-01 | Transfer wins serialization | Pause A before the release linearization point; commit transfer to B; resume A | A is rejected; B alone may sign under the new epoch |
| RACE-02 | Sign wins serialization | Allow A's complete signing transaction to linearize before transfer; then transfer to B | A's result is durably committed and returned consistently; transfer occurs only in the protocol-defined order; no overlapping ownership result |
| RACE-03 | Transfer during in-flight signature | Race transfer against a request already inside the protected signing boundary | Exactly one serializable order is recorded; no signature from A may be released after the transfer's committed fencing point |
| HRS-01 | Same H/R/S, same request retry | Submit identical request ID and canonical payload repeatedly, including concurrently | One durable signing result; retries return the identical committed result or a defined reconciliation outcome |
| HRS-02 | Same H/R/S, conflicting payload | Submit different canonical sign bytes for the same prohibited H/R/S | Conflict rejected; no second conflicting signature |
| HRS-03 | Concurrent proposal/vote sequence | Submit valid and conflicting proposal/vote requests concurrently for one validator | State transitions follow pinned CometBFT v0.40.0 rules; no prohibited double-sign |
| HRS-04 | Request-ID payload mutation | Reuse a committed request ID with altered sign bytes or identity | Reject; never reinterpret the old request ID as a new operation |
| HRS-05 | Out-of-order/lower H/R/S | Submit lower or invalidly regressed H/R/S after a higher state is committed | Reject; durable H/R/S checkpoint never decreases |

### Group C — crash, timeout, and idempotent reconciliation

Inject a process kill, power-loss simulation, or controlled exception at each boundary. The test harness must distinguish a crash before the key operation from a crash after the key operation.

| ID | Fault boundary | Required result after restart/reconciliation |
|---|---|---|
| CRASH-01 | Before authority decision | No signature; same request may be safely attempted according to the contract |
| CRASH-02 | After authority decision, before durable signing intent | No signature may be assumed; reconcile the same request ID and authority decision |
| CRASH-03 | After durable intent, before key operation | Recover intent without releasing a conflicting signature; same request ID remains authoritative |
| CRASH-04 | During/after key operation, before durable signature/state commit | Outcome is UNKNOWN until proven; fail closed; never issue a conflicting signature |
| CRASH-05 | After durable signature and H/R/S commit, before response | Retry returns the exact committed signature/result; no second reservation or signature |
| CRASH-06 | After response delivery | Durable state matches the delivered response; replay is idempotent |
| CRASH-07 | Authority commit timeout with unknown outcome | Reconcile the same transaction/request ID; do not create a new ownership or signing request to bypass uncertainty |
| CRASH-08 | Signer restart with stale local cache | Fresh authority/key-boundary state wins; cached epoch or H/R/S cannot authorize signing |

**Global rule:** timeout is not proof of failure. An UNKNOWN outcome blocks new conflicting signing until the original request is reconciled.

### Group D — authority durability, failover, and restore

| ID | Scenario | Procedure | Required result |
|---|---|---|---|
| DUR-01 | Authority replica failover | Commit an epoch/H/R/S update, fail over, then query and sign | Highest committed epoch and signing checkpoint remain authoritative |
| DUR-02 | Stale replica read | Force a stale replica/read path during takeover | Stale data cannot authorize signature release |
| DUR-03 | Quorum/authority outage | Remove the authority's ability to prove a linearizable current state | Fail closed; no signature released |
| DUR-04 | Stale backup restore | Restore a backup predating a committed transfer | Restored service cannot lower epoch or resurrect the old owner |
| DUR-05 | VM/process snapshot rollback | Restore an old signer image/state after transfer | Old signer remains fenced at the independent key boundary |
| DUR-06 | Disaster-recovery exercise | Recover authority under the approved recovery procedure | Highest committed epoch and H/R/S checkpoint are preserved or signing remains blocked pending witnessed reconciliation |
| DUR-07 | Concurrent restore and takeover | Race recovery/restore against a new ownership transfer | No rollback, duplicate current owner, or ambiguous permission to sign |

### Group E — key custody, revocation, and bypass

| ID | Scenario | Procedure | Required result |
|---|---|---|---|
| KEY-01 | Raw-key isolation | Inspect validator host files, environment, process configuration, and backups | If remote custody is claimed, no usable consensus private key is available on validator hosts |
| KEY-02 | Revoked signer | Revoke A, retain its process and credentials, then request signing | Rejected at the release boundary and auditable |
| KEY-03 | Credential rotation | Rotate signer credentials while an old session remains open | Old credential/session cannot release signatures after the defined revocation point |
| KEY-04 | Direct local FilePV bypass | Attempt direct local FilePV signing and fallback paths | No unguarded path can release a signature; startup/test acceptance fails if fallback exists |
| KEY-05 | Alternate endpoint bypass | Attempt every configured signer endpoint and recovery path | All signing paths enforce the same ownership/H/R/S gate |
| KEY-06 | Key-service restart | Restart the protected key service with pending and committed requests | Durable state is recovered; unknown outcomes remain blocked and reconcilable |

### Group F — pinned CometBFT integration

| ID | Scenario | Required result |
|---|---|---|
| CBFT-01 | Version/source pin | Test records prove exact CometBFT v0.40.0 source revision and build digest |
| CBFT-02 | Proposal path | Every proposal signing request reaches the guarded signer boundary |
| CBFT-03 | Vote path | Every prevote/precommit signing request reaches the guarded signer boundary |
| CBFT-04 | No FilePV fallback | No local FilePV is created, opened, or silently selected |
| CBFT-05 | Restart/reconnect | Retry/reconnect preserves request identity and reconciles ambiguous outcomes |
| CBFT-06 | Four-validator remote-only regression | Existing four-validator harness passes with disposable keys and guarded signers |
| CBFT-07 | Negative bypass suite | Deliberately misconfigured/unavailable guard causes refusal to sign, not fallback |


## 5.1 First implementation-ready acceptance test — reject a transferred epoch

**Test ID:** FENCE-00  
**Priority:** P0  
**Status:** SPECIFIED ONLY — NOT IMPLEMENTED OR EXECUTED

**Given:** Validator signer A previously owned epoch e, and the ownership transfer to signer B at epoch e+1 is durably committed.

**When:** A submits a signing request using its old ownership/epoch e.

**Then:**
1. The signer service rejects the request at the protected signing/release boundary.
2. No signature is produced or released.
3. No new H/R/S signing record is committed for the rejected request.
4. The rejection is recorded with the request ID and stale epoch, without exposing secret key material.

**Pass condition:** The test verifies all four outcomes using disposable test keys and confirms that the current owner remains B at epoch e+1.

**Fail condition:** Any signature is produced/released by A, any signing state is committed for the rejected request, or the old epoch is accepted.

**Minimal test setup:** Create A and B with disposable keys; commit transfer A/e → B/e+1; submit one signing request from A/e; assert rejection, zero released signatures, and unchanged current ownership.

This is the first practical acceptance test only. Do not modify production code or keys as part of this specification step.

## 6. Required deterministic race schedules

The harness must provide explicit barriers rather than relying on timing or sleeps.

**Schedule S1 — transfer before release**
1. A owns epoch e.
2. A submits request R and pauses immediately before the key-release linearization point.
3. B commits ownership epoch e+1.
4. Resume A.
5. Assert A is rejected and the key boundary records zero released signatures for R.

**Schedule S2 — release before transfer**
1. A owns epoch e.
2. A enters the protected release transaction and obtains the protocol's serialization position.
3. Pause B's transfer until A's transaction reaches its defined durable completion point.
4. Complete A's request and commit its H/R/S result.
5. Commit B's transfer to epoch e+1.
6. Assert the audit log proves this order and there is no overlap or second owner at epoch e.

**Schedule S3 — stale authorization retained**
1. A obtains a preflight response while epoch e is current.
2. B commits epoch e+1.
3. A submits the old response with a new signing request.
4. Assert rejection at the cryptographic key boundary.

**Schedule S4 — unknown signature outcome**
1. A begins request R.
2. Inject a crash after the key operation may have occurred but before durable acknowledgement.
3. Restart the service and call Reconcile(R) using the same request ID.
4. Assert either the exact committed signature is returned or signing remains UNKNOWN_BLOCKED; no new conflicting signature is generated.

## 7. Acceptance gates

- **Gate 0 — specification review:** test owners and security reviewers agree on identity scope, serialization point, fault hooks, and expected outcomes. No mechanism-specific policy is silently assumed.
- **Gate 1 — model/unit:** state-machine and idempotency tests pass. This is design feedback only.
- **Gate 2 — process:** independent processes reproduce and then prevent stale FilePV/shared-state behavior in disposable fixtures.
- **Gate 3 — multi-host:** partition, takeover, reconnect, failover, and restore tests pass across separate hosts.
- **Gate 4 — key boundary:** stale owners cannot obtain signatures from the actual protected key operation after transfer.
- **Gate 5 — CometBFT:** exact pinned v0.40.0 adapter paths and no-fallback checks pass.
- **Gate 6 — independent review:** security reviewer accepts the architecture, operational controls, evidence, and residual risks.

No gate may be skipped by substituting a lower evidence class. A green CI status is not sufficient if the required test steps did not execute.

## 8. Stop conditions

Stop the test run and preserve evidence if:
- two distinct signatures verify for a prohibited identical H/R/S;
- a stale/revoked signer releases any signature;
- epoch or H/R/S decreases after restart, failover, or restore;
- a timeout is treated as permission to issue a new conflicting request;
- an unguarded FilePV or alternate signing path is found;
- the test accidentally uses non-disposable keys or a non-isolated network.

Any such result is a security failure for the tested layer. Do not weaken assertions, remove tests, or change workflow gates to obtain a pass.

## 9. Execution status

At creation, all cases above are **SPECIFIED / NOT EXECUTED**. This file does not claim an implementation exists or that any test has passed. The first executable work should be a disposable test harness for S1–S4 and HRS-01/HRS-02, followed by process-level tests. Multi-host and key-boundary acceptance remains blocked until the production-equivalent authority and custody design is selected and independently reviewed.
