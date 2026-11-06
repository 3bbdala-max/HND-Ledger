# WP4.14 — VSP Runtime Enforcement Implementation Blueprint and Acceptance Plan

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Status:** Implementation blueprint; documentation-only  
**Decision:** VSP verification must be an unavoidable pre-start gate for the validator process, not merely an HND application-side check.  
**Release disposition:** NOT APPROVED for implementation completion, production validator operation, production signing or public launch.

## 1. Objective and scope

This blueprint translates the selected v0.2 governance model into an implementation sequence. It defines the security boundary, required inputs, validation order, fail-closed behavior, durable rollback protection, test strategy and release gates.

This is not an implementation. No source, tests, workflows, dependencies, configuration, Genesis, keys or runtime behavior were changed. The acceptance tests below are proposed and have not been run.

## 2. Critical architecture decision: gate CometBFT before process start

The validator consists of more than the HND ABCI application. CometBFT owns consensus networking, validator identity and consensus signing requests. An HND-side VSP check is insufficient if an operator can launch CometBFT directly, point it at an unchecked home, or connect it to a signer without the same authorization decision.

Required architecture:
1. A single supported validator launcher/supervisor performs preflight verification before starting either the HND ABCI application or CometBFT.
2. The launcher verifies the trust manifest, signed VSP, network identity, Genesis digests, software/profile identity, local validator identity, and durable anti-rollback state.
3. It verifies that the local CometBFT home/config/validator public identity matches the authorized VSP entry.
4. It starts the HND application and CometBFT only after all checks pass.
5. The supported deployment must prevent routine operators and service managers from bypassing the launcher. Direct CometBFT execution must be denied by OS/service permissions or an equivalent enforced deployment boundary.
6. The signer independently enforces its own validator-key, chain/Genesis, request and anti-double-sign policy. Launcher approval must not become a reusable bearer token that bypasses signer checks.
7. Any missing verifier, unreadable state, unavailable trust source, mismatch, timeout, or ambiguous result causes startup failure. There is no permissive fallback.

**Important:** a Python wrapper alone is not a security boundary if the service account can execute the CometBFT binary directly. The eventual implementation must include a tested OS/service execution boundary and document the exact threat model for root-level administrators.

## 3. Trusted inputs and artifact binding

The verifier must consume independently authenticated inputs:

| Input | Required binding |
|---|---|
| Trust manifest | Out-of-band pinned digest; three governance public keys; threshold; schema and sequence |
| Signed VSP | Canonical digest; two distinct authorized signatures; predecessor digest; sequence; activation height |
| HND Genesis | Exact chain ID and HND manifest digest |
| CometBFT Genesis | Exact full-file digest and parsed validator set/consensus parameters |
| CometBFT software | Exact source commit, build recipe identity and approved binary digest; a version tag alone is insufficient |
| Local validator identity | Local consensus public key/address maps to exactly one active VSP entry |
| Local profile/config | Consensus-affecting values match the approved CometBFT profile; local-only operational settings are separately validated |
| Anti-rollback state | Durable monotonic trust-manifest/VSP sequence and digest, protected from silent rollback |
| Signer policy | Exact validator key, chain context, Genesis identity and durable H/R/S anti-double-sign state |

No private key material is an input to the verifier. The verifier must never ask for or read governance or consensus private keys.

## 4. Validation order

The verifier should use a deterministic, auditable sequence. It must not start network listeners or consensus processes while validation is in progress.

1. Load a bounded-size trust manifest and VSP from configured paths or authenticated distribution sources.
2. Reject symlinks or unsafe file ownership/modes where the deployment threat model requires it; reject unexpected file types and excessive sizes.
3. Parse with a strict schema: reject unknown critical fields, duplicate keys, duplicate JSON members, unsupported versions and non-canonical encodings.
4. Re-encode canonical bytes and compare exact bytes/digest with the signed package.
5. Verify the independently pinned trust-manifest digest and its witness/bootstrap evidence.
6. Verify the VSP has the exact expected chain ID, HND Genesis digest and CometBFT Genesis/profile identity.
7. Verify monotonic sequence, predecessor digest, expiry/activation policy and durable anti-rollback record.
8. Verify at least two distinct valid governance signatures over the exact canonical package digest and domain-separated context.
9. Validate algorithm/key policy, public-key encoding, proof-of-possession/enrollment status and signature uniqueness.
10. Validate validator list: non-empty, deterministic ordering, unique public keys and derived addresses, positive bounded integer powers, exact total power, and no arithmetic overflow.
11. Parse the actual CometBFT Genesis using the exact pinned CometBFT version and compare the full approved validator roster, voting power and consensus parameters—not merely validator count.
12. Verify the local validator's consensus public key/address and configured signer identity match exactly one active VSP record.
13. Verify CometBFT binary/source identity and the classified consensus-profile digest.
14. Verify local operational configuration against separate hardening policy (bind addresses, peer allowlists, filesystem paths, service identity and permissions).
15. Verify signer endpoint identity and signer policy binding without disclosing private material.
16. Atomically persist the accepted trust/VSP sequence and digest using a rollback-resistant mechanism. A normal writable file plus an unkeyed hash is not sufficient evidence of anti-rollback protection.
17. Emit a redacted, structured audit event containing decision, digests, sequence, local validator identifier and reason code.
18. Only then release the service manager to start the HND application and CometBFT. Any post-check change to an authenticated input must invalidate the approval and abort startup.

The implementation must document the atomicity and crash semantics of step 16. It must not claim rollback resistance until an external monotonic anchor or an equivalently justified protected mechanism is implemented and tested.

## 5. Configuration classification and consistency

Do not hash every TOML field indiscriminately. Build a version-specific allowlist from the exact CometBFT v0.40.0 source/config schema and classify each field as:

- consensus-critical: affects block validity, evidence, validator set, consensus safety/liveness or deterministic acceptance;
- security-critical operational: affects authentication, peer identity, network exposure, signer routing or filesystem trust;
- local-only operational: paths, logging and resource settings that do not alter consensus semantics.

Unknown fields or newly introduced CometBFT fields must fail review rather than silently default to local-only. A CometBFT upgrade requires a new schema/profile review and new expected source/binary identities.

## 6. Durable anti-rollback requirements

The VSP/trust-manifest sequence and digest must survive process restart, host reboot and ordinary backup/restore without accepting an older authorization state.

Minimum properties:
- monotonic sequence bound to chain ID and Genesis identity;
- atomic compare-and-advance semantics;
- integrity and authenticity rooted outside the mutable application directory;
- no automatic recreation when state is missing, corrupt or unreadable;
- explicit recovery requiring the approved governance/recovery ceremony;
- detection of restoring an older disk snapshot;
- signer H/R/S anti-double-sign state remains separate and cannot be reset by VSP rotation;
- crash tests around every persistence boundary.

If the selected platform cannot provide a defensible monotonic anchor, production approval remains blocked. Do not label a local JSON file, filesystem timestamp or unkeyed checksum as a hardware-backed anti-rollback control.

## 7. Implementation work packages

| Work package | Deliverable | Exit evidence |
|---|---|---|
| VSP-IMPL-01 | Strict canonical schema/parser | Duplicate-member, canonicalization, size and schema tests |
| VSP-IMPL-02 | Trust-manifest and 2-of-3 signature verifier | Positive/negative signature vectors and domain-separation tests |
| VSP-IMPL-03 | Genesis and validator-roster binding | Exact full Genesis digest and parsed roster comparison |
| VSP-IMPL-04 | CometBFT build/profile identity | Immutable source commit and binary digest verification |
| VSP-IMPL-05 | Pre-start launcher gate | Demonstrated no process/listener starts on any rejected input |
| VSP-IMPL-06 | OS/service bypass prevention | Service-account and direct-binary bypass tests |
| VSP-IMPL-07 | Durable anti-rollback store | Crash, reboot, snapshot-restore and corruption tests |
| VSP-IMPL-08 | Signer-side independent enforcement | Wrong validator/network/VSP/HRS requests rejected |
| VSP-IMPL-09 | Redacted audit and operator diagnostics | No secret leakage; stable reason codes |
| VSP-IMPL-10 | Independent security review | Findings resolved and signed review record |

Do not combine these into one large unreviewable change. Each work package needs a narrow implementation, tests, code review and evidence record. Any consensus-critical behavior change requires explicit owner-approved design and test vectors before source changes.

## 8. Acceptance tests — proposed, not executed

| ID | Scenario | Required result |
|---|---|---|
| VSP-RUN-T01 | Valid canonical VSP with two distinct valid signatures | Preflight passes |
| VSP-RUN-T02 | Only one valid signature | Reject; no process starts |
| VSP-RUN-T03 | Two signatures from same key | Reject |
| VSP-RUN-T04 | Unknown or retired governance key | Reject |
| VSP-RUN-T05 | Modified VSP after signing | Reject digest/signature |
| VSP-RUN-T06 | Duplicate JSON member | Reject |
| VSP-RUN-T07 | Non-canonical serialization | Reject |
| VSP-RUN-T08 | Oversized or malformed profile | Reject safely |
| VSP-RUN-T09 | Wrong chain ID | Reject |
| VSP-RUN-T10 | Wrong HND Genesis digest | Reject |
| VSP-RUN-T11 | Wrong CometBFT Genesis full-file digest | Reject |
| VSP-RUN-T12 | Same validator count but substituted public key | Reject |
| VSP-RUN-T13 | Voting power differs from approved roster | Reject |
| VSP-RUN-T14 | Duplicate validator consensus key/address | Reject |
| VSP-RUN-T15 | Local node key not present in active VSP | Reject |
| VSP-RUN-T16 | Local signer key differs from local VSP entry | Reject |
| VSP-RUN-T17 | CometBFT binary digest differs | Reject |
| VSP-RUN-T18 | CometBFT source commit differs | Reject |
| VSP-RUN-T19 | Consensus-critical config field differs | Reject |
| VSP-RUN-T20 | Unknown consensus config field appears after upgrade | Block pending schema review |
| VSP-RUN-T21 | VSP sequence rollback | Reject |
| VSP-RUN-T22 | Predecessor digest mismatch | Reject |
| VSP-RUN-T23 | Anti-rollback state missing/corrupt | Fail closed; no auto-reset |
| VSP-RUN-T24 | Restore old disk snapshot | Detect rollback and reject |
| VSP-RUN-T25 | Crash during sequence advance | Recover old or new complete state, never partial |
| VSP-RUN-T26 | Direct CometBFT binary invocation by routine service account | Denied |
| VSP-RUN-T27 | Launcher verification failure | Neither HND nor CometBFT process starts |
| VSP-RUN-T28 | Authenticated profile changes after preflight | Startup aborts or re-verifies before use |
| VSP-RUN-T29 | Signer receives wrong chain/Genesis/validator context | Reject signing request |
| VSP-RUN-T30 | VSP rotation attempts to reset signer H/R/S | Reject |
| VSP-RUN-T31 | Trust source unavailable | Fail closed |
| VSP-RUN-T32 | Two distribution channels disagree | Halt activation |
| VSP-RUN-T33 | Audit log inspection for secrets | No private key, seed or credential leakage |
| VSP-RUN-T34 | Four independent deployment hosts start same authorized VSP | Exact profile agreement, independent host evidence |
| VSP-RUN-T35 | One host/operator/network fault | Remaining network behavior matches the approved fault model |

These are required acceptance criteria. They are not existing test results.

## 9. Rollout and rollback policy

- Implement and test in disposable local fixtures first.
- Add negative tests before enabling the gate in any shared environment.
- Use a non-production canary with disposable identities and no real funds or production keys.
- Require independent review of the launcher bypass boundary and anti-rollback mechanism.
- Production rollout requires an authenticated initial trust ceremony, independent validator operators, signed release artifacts, deployment monitoring, recovery drills and an explicit release approval.
- Rollback must never reduce trust-manifest/VSP sequence or signer H/R/S state. If a software rollback is necessary, it must still load the latest authorized trust state and be compatible with the active network profile; otherwise halt.

## 10. Current evidence versus remaining work

Established by repository audits:
- current HND Genesis manifest does not authenticate the complete CometBFT validator roster;
- current startup does not bind a complete HND application-config digest and CometBFT profile digest;
- current CometBFT test build selects a release tag and logs resolved source identity without enforcing a reviewed expected commit/binary digest;
- local four-validator tests use disposable temporary identities and do not establish production trust-root or independent operator deployment.

Not established:
- a VSP parser/verifier in runtime;
- an unavoidable CometBFT pre-start gate;
- OS/service prevention of direct-binary bypass;
- production governance keys or witnessed trust-root ceremony;
- external monotonic anti-rollback storage;
- production HSM/KMS signer enforcement;
- independently operated validator infrastructure.

## 11. Decision

**Selected architecture:** strict VSP verification before validator startup, enforced at the process/service boundary and independently reinforced by the signer. Bind the VSP to HND Genesis, CometBFT Genesis, exact software build/profile identity, local validator key and durable monotonic trust state.

**Implementation order:** schema/parser → signature/trust verifier → Genesis/roster binding → build/profile identity → pre-start launcher and OS boundary → anti-rollback → signer enforcement → independent review.

**Status: NOT APPROVED** for production validator operation, production signing, token issuance or public launch. The current change is documentation only; no code or tests were modified and none of the proposed VSP runtime acceptance tests were executed.

---
This blueprint is an engineering plan, not a security certification or launch authorization.
