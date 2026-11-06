# WP4.14 — Remote Signer CI Execution Evidence and Production Boundary

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Reviewed commit:** `5c18ae194b77080673fb1fb3491ad0167d646622`  
**Workflow run:** `42313807802`  
**Review type:** CI evidence reconciliation and static source-boundary review  
**Status:** CI run completed successfully; production signer approval remains blocked.

## 1. Executive result

GitHub Actions run `42313807802`, attached to the exact reviewed commit, completed with conclusion `success`.

Both jobs completed successfully:

- `hnd-v02-tests`
- `cometbft-single-node-smoke`

The CometBFT job completed the following relevant steps:

- pinned CometBFT Byzantine prevote equivocation regression;
- HND four-replica P2P equivocation evidence integration;
- CometBFT validator signer anti-double-sign smoke test;
- remote-signer protocol conformance probe;
- process-isolated remote-signer probe;
- authenticated Noise remote-signer integration and unauthorized-peer rejection;
- connected remote-signer vote-withholding probe;
- remote-signer anti-double-sign persistence across restart;
- rejection of missing anti-double-sign state in recovery mode;
- rejection of substituted anti-double-sign state;
- single-node ABCI integration;
- four-validator Genesis and identity preflight;
- private four-validator network integration;
- four-validator external remote-signer integration and outage recovery;
- four-validator authenticated Noise remote-signer integration and recovery;
- rejection of missing and substituted Noise anti-double-sign state.

This is concrete, successful CI execution evidence for the test harness at the reviewed commit. It supersedes earlier notes that described this run as still in progress.

## 2. What the passing run establishes

Within the disposable CI environment, the workflow successfully exercised:

1. CometBFT v0.40.0 integration against the repository's HND application.
2. Four-validator private-network startup and integration.
3. Remote signer connectivity through the tested CometBFT private-validator protocol paths.
4. A signer refusing a conflicting vote at the same height/round/step while permitting an identical retry.
5. Persistence of the tested signer state across a process restart, including reuse of the prior signature and rejection of a conflicting request.
6. Recovery-mode rejection when the anti-double-sign state file is absent or its digest does not match the expected test digest.
7. Noise transport integration, including the tested unauthorized-peer rejection path.
8. Four-validator outage/recovery scenarios in the test harness.

The workflow step names and successful conclusions are evidence that these commands completed successfully. They do not independently certify every internal property beyond the assertions implemented by those probes.

## 3. Source-level limits that remain material

The reviewed test helpers explicitly identify themselves as disposable/test-only or use temporary local resources:

- `scripts/cometbft_v040_remote_signer_process_probe.go` describes a private temporary Unix socket and states that the probe tests process separation and protocol behavior, not authenticated network transport or production key custody.
- `scripts/cometbft_v040_noise_remote_signer_helper.go` describes itself as a persistent Noise-authenticated remote signer for disposable integration tests, using loopback endpoints and ephemeral identities, and says never to use it in production.
- The process probe creates temporary key and state files and tests CometBFT FilePV behavior. It is not evidence of an independently administered hardware-backed or durable monotonic trust anchor.
- The recovery digest is supplied to the test helper by the harness. A SHA-256 comparison proves equality with that supplied value; it does not prove that the value is authenticated and protected outside the signer's rollback domain.

Therefore, passing CI does **not** establish:

- production key generation, custody, HSM/keystore integration, or dual-control;
- independent durable monotonic anti-rollback anchoring;
- safe exclusion of two separately launched production signer instances sharing the same validator identity;
- power-loss safety at every write/sign/response boundary;
- production Noise identity issuance, revocation, rotation, and operator authorization;
- production deployment hardening, monitoring, backup/restore drills, or incident response;
- independent third-party security review.

## 4. Evidence classification

| Area | Current evidence | Disposition |
|---|---|---|
| HND v0.2 reference test job | Successful on reviewed commit | CI pass |
| CometBFT integration job | Successful on reviewed commit | CI pass |
| Four-validator network harness | Successful workflow step | Test integration pass |
| Remote signer protocol probes | Successful workflow steps | Test integration pass |
| Same-H/R/S conflict rejection and identical retry across restart | Assertions in disposable process probe; workflow step passed | Test evidence, not production certification |
| Noise unauthorized-peer probe | Successful workflow step | Test evidence, not production identity lifecycle certification |
| Independent durable monotonic anchor | Not established by these probes | Open production blocker |
| Production custody and operational controls | Not established by these probes | Open production blocker |
| Independent security review | Not evidenced by this workflow | Open release gate |

## 5. Required next validation

Before production signer approval, retain the passing CI run as a baseline and add separately reviewed evidence for:

1. A real independent monotonic checkpoint whose trust domain is separate from signer-local storage.
2. A stale-but-valid state rollback attempt against the signer while the checkpoint remains advanced.
3. Two concurrent signer processes attempting to use the same validator identity and state.
4. Crash/power-loss injection around signing intent persistence, signature creation, durable state update, and response delivery.
5. Authenticated checkpoint substitution/replay rejection, not merely a digest mismatch against a harness-supplied value.
6. Production identity lifecycle, local socket authorization, key custody, audit trail, backup, and recovery controls.
7. Reproducible build and binary provenance for the exact signer deployed.

These are acceptance requirements, not claims that the tests have already been implemented or run.

## 6. Release disposition

**CI status:** PASS for workflow run `42313807802` on commit `5c18ae194b77080673fb1fb3491ad0167d646622`.

**Production signer status:** NOT APPROVED.

**Network launch status:** NOT APPROVED.

This report records successful automated integration evidence without upgrading test-only helpers into production security claims. No source code, test code, workflow, key material, or runtime configuration was changed by this report. No production key was generated or used.
