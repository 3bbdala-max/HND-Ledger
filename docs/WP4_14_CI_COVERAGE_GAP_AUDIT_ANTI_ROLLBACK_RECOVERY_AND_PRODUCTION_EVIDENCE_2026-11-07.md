# WP4.14 — CI Coverage Gap Audit: Anti-Rollback, Recovery and Production Evidence

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Baseline commit:** `b74b8d152e16995da5d0fc2d15db21a3afa22f60`  
**Review type:** Static workflow and test-source inspection  
**Change type:** Documentation only  
**Disposition:** Findings and proposed acceptance gates; no workflow or test changes authorized or made

## Current status update (2026-11-07)

The earlier static finding that the explicit CI command omitted
`tests.test_v02_anti_rollback_reference` and
`tests.test_v02_recovery_controls` has been closed by a later workflow
revision. The current `.github/workflows/hnd-v02-tests.yml` explicitly lists
both modules in the isolated v0.2 test command (lines 46–47), and separately
runs the VSP JCS compatibility spike.

Workflow run `42337449661` on commit
`22249843cf3a65ac6dd55bda9328f96261f579ff` completed the
`hnd-v02-tests` job successfully. Its log records **221 tests passed** in
17.888 seconds, including tests from both anti-rollback and recovery-controls
modules. The same workflow run also completed the CometBFT smoke job
successfully.

The earlier sections below are retained as the historical static audit at
the time it was written; they are not the current CI status. The synthetic
anti-rollback model remains offline and synthetic, so passing its tests is
not evidence of production anchor-to-signer enforcement or distributed
fencing.

## 1. Executive finding

The current GitHub Actions workflow runs a defined set of HND v0.2 unit/integration modules and a long CometBFT smoke sequence. The workflow's explicit Python test command does **not** include:

- `tests.test_v02_anti_rollback_reference`
- `tests.test_v02_recovery_controls`

Both test modules exist in the repository and contain useful negative/reference-model tests. Their existence is not evidence that the current CI workflow executes them.

This is a coverage gap in the configured test command, not proof that either module fails. This review did not execute tests and did not change the workflow.

## 2. Exact workflow scope observed

File: `.github/workflows/hnd-v02-tests.yml`

The `hnd-v02-tests` job invokes `python -m unittest -v` with these explicit modules:

1. `tests.test_v02_transaction_envelope`
2. `tests.test_v02_genesis_manifest`
3. `tests.test_v02_ledger`
4. `tests.test_v02_blocks`
5. `tests.test_v02_abci_app`
6. `tests.test_v02_cometbft_v040_adapter`
7. `tests.test_v02_four_abci_replica_evidence`
8. `tests.test_v02_four_replica_state_convergence`
9. `tests.test_v02_tcp_peer_relay`

The command does not use test discovery (such as `unittest discover`) and does not list the two modules named above. Therefore they are not selected by this explicit invocation.

The downstream `cometbft-single-node-smoke` job depends on `hnd-v02-tests` and then performs a sequence of CometBFT source build, equivocation/evidence, signer, remote-signer, single-node ABCI and multi-validator smoke operations. A successful downstream job would still not imply that omitted Python modules were executed.

## 3. What the omitted modules actually test

### 3.1 `tests.test_v02_anti_rollback_reference`

The module describes itself as synthetic offline anti-rollback reference-model tests. The inspected cases include:

- normal prepare/commit/restore behavior;
- prepared state not enabling signing;
- preservation of the last committed record during a pending prepare;
- ambiguous commit reconciliation by operation ID;
- anchor outage fail-closed behavior;
- dual-control restore;
- rejection of an older unanchored generation;
- corruption and identity mismatch rejection;
- unsupported anchor schema rejection;
- host fencing and takeover;
- concurrent compare-and-swap behavior;
- idempotent retries and conflicting operation-ID reuse;
- stale predecessor and predecessor-digest rejection;
- HRS numeric-width and step constraints.

**Scope limitation:** these are tests of a synthetic reference model and its synthetic anchor. They do not prove that production CometBFT signing is wired to a durable independent anchor, that a real signer refuses to sign after restore ambiguity, or that host fencing is enforced across actual processes and machines.

### 3.2 `tests.test_v02_recovery_controls`

The inspected cases include:

- readiness timeout terminates a process without touching a fixture state file;
- a ready process is not terminated;
- replica convergence rejects divergent application hashes;
- replica convergence rejects height/block-hash mismatch.

**Scope limitation:** these tests exercise recovery-control helpers and fixture data. They do not constitute a full production backup/restore drill, real database crash-recovery test, independent anchor recovery test, or four-validator network recovery proof.

## 4. CI status evidence must remain commit-specific

At inspection time, the branch HEAD was `b74b8d152e16995da5d0fc2d15db21a3afa22f60`. The workflow run for that exact commit was:

- Run ID: `42313567312`
- `hnd-v02-tests`: completed / success
- `cometbft-single-node-smoke`: in progress
- The active CometBFT job step was `Run pinned CometBFT Byzantine prevote equivocation and evidence regression`.
- Later steps, including four-validator network integration and external/Noise remote-signer recovery, were still pending at the time of inspection.

Thus the HND test job success applies only to the nine explicitly listed modules. It does not cover the two omitted modules. The CometBFT job was not yet complete, so no final smoke result is asserted here.

## 5. Recommended CI acceptance plan (not applied)

Before treating anti-rollback/recovery regression coverage as part of the required CI baseline:

1. Run both omitted modules explicitly in a controlled CI change, or adopt repository-wide discovery only after confirming discovery does not execute unsafe, environment-dependent, or intentionally excluded tests.
2. Preserve separate labels/reporting for synthetic reference-model tests and real CometBFT integration tests.
3. Add a CI summary that lists the exact modules and test counts executed; avoid relying on a broad “tests passed” label.
4. Add real integration tests only where a production implementation exists. Do not convert synthetic tests into claims of production enforcement.
5. Require negative tests for missing anchor, stale generation, mismatched network/Genesis/validator/signer identity, ambiguous commit, process takeover, and recovery-state substitution at the actual signer boundary.
6. Require crash/restart tests against the real persistence implementation and prove that failure leaves signing disabled.
7. Require a multi-validator recovery drill with independently captured height, block ID, app hash, validator identity and signer anti-double-sign state.
8. Bind every CI result to the exact commit SHA and retain logs/artifacts needed to reproduce the result.

A future workflow change requires separate explicit authorization. No workflow edit is included in this report.

## 6. Evidence classification

| Claim | Current evidence | Correct classification |
|---|---|---|
| Nine named HND test modules passed on latest commit | Latest workflow job completed successfully | Verified for that job/commit |
| Anti-rollback reference-model module is in repository | Source file inspected | Verified existence; not run by current explicit workflow command |
| Recovery-controls module is in repository | Source file inspected | Verified existence; not run by current explicit workflow command |
| Production anti-rollback is enforced end-to-end | No evidence from these synthetic modules | Not established |
| Production recovery and backup restore are safe | No production drill evidence in this workflow | Not established |
| Four-validator and remote-signer smoke passed on latest commit | Latest CometBFT job still in progress at inspection | Not established |

## 7. Disposition and next gate

**Finding CI-COV-01 — Medium:** the explicit HND unit-test command omits two existing anti-rollback/recovery test modules.

**Finding CI-COV-02 — High:** synthetic reference-model test success, even if later run, must not be represented as proof of production signer/anchor enforcement.

**Finding CI-COV-03 — High:** latest-commit CometBFT integration evidence remains incomplete until the job finishes and its final steps/conclusion are inspected.

Next safe gate: obtain owner authorization for a narrowly scoped workflow change that adds the two modules and makes the executed test inventory explicit. Separately, continue the real signer/anchor integration and recovery work only under its own source-change approval.

No source code, tests, workflows, dependency pins, validator settings, keys, or production configuration were modified by this audit.
