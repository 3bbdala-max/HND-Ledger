# HND v0.2 — CI coverage, trigger, and release-gate audit

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Review type:** static workflow review plus inspection of the latest GitHub Actions run; documentation-only  
**Workflow:** `.github/workflows/hnd-v02-tests.yml`

## 1. Latest CI evidence

The latest run inspected for the current branch head was:

- Run: [41975196036](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41975196036)
- Tested commit: `f340e4e8a06452a39e96ae79a17095a6b1aa82f6`
- Event: push to `phase-0.2-planning`
- Result: `success`
- Jobs: `hnd-v02-tests` and `cometbft-single-node-smoke`; both completed successfully.

The job-step records for this run show success for all listed steps, including:
- isolated v0.2 Python test command;
- pinned CometBFT v0.40.0 build and Byzantine prevote equivocation regression;
- HND P2P evidence integration;
- validator signer anti-double-sign smoke;
- remote-signer protocol conformance and process-isolated probes;
- authenticated Noise remote-signer and unauthorized-peer rejection probe;
- vote-withholding probe;
- anti-double-sign persistence across restart;
- missing and substituted anti-double-sign state rejection in recovery mode;
- single-node ABCI smoke;
- four-validator Genesis/identity preflight and network integration;
- external remote-signer outage/recovery and authenticated Noise recovery.

This is concrete CI evidence for the exact run and commit above. It is not evidence for tests absent from the workflow command, nor a production security certification.

## 2. Python test-suite coverage gap

The workflow's `Run isolated v0.2 tests` command explicitly runs these modules:

- `tests.test_v02_transaction_envelope`
- `tests.test_v02_genesis_manifest`
- `tests.test_v02_ledger`
- `tests.test_v02_blocks`
- `tests.test_v02_abci_app`
- `tests.test_v02_cometbft_v040_adapter`
- `tests.test_v02_four_abci_replica_evidence`
- `tests.test_v02_four_replica_state_convergence`
- `tests.test_v02_tcp_peer_relay`

The current command does **not** list:
- `tests.test_v02_anti_rollback_reference`
- `tests.test_v02_recovery_controls`

Consequently, the latest green CI run does not prove that either omitted module was executed by the isolated Python test step. In particular, the anti-rollback reference-model tests are not part of the current explicit test command, despite earlier evidence documentation describing them as included. That earlier statement must not be carried forward as a claim about this workflow configuration or the latest run without a run-specific log proving otherwise.

The remote-signer process probes in the second job are separate integration checks. They do not execute the omitted Python reference-model/recovery-control modules and do not provide an independent durable monotonic trust anchor.

## 3. Workflow trigger boundary

The workflow currently declares:
- `push` on `phase-0.2-planning`;
- `pull_request` targeting `main`.

It does not declare a pull-request trigger targeting `phase-0.2-planning`. Thus a pull request whose base is the planning branch is not covered by this workflow's declared PR trigger. Pushes to the planning branch are tested, and pull requests targeting main are configured to be tested.

This review did not inspect or certify repository branch-protection/ruleset settings. A green workflow run alone does not prove that merges are blocked when required checks are missing or failing.

## 4. Release pipeline boundary

The inspected workflow is a test workflow. It does not define a separate release/deployment job, signed release artifact, reproducible binary attestation, SBOM publication, provenance attestation, or production deployment approval step.

This is not necessarily a defect for a planning branch, but it means the current workflow is not a complete production release pipeline. No production credentials, live key material, deployment or token issuance should be inferred from the successful CI result.

## 5. Recommended CI corrections (not applied)

1. Add `tests.test_v02_anti_rollback_reference` to the isolated Python test command, or explicitly classify it as a separate required job.
2. Add `tests.test_v02_recovery_controls` if these recovery gates are intended to be maintained and regression-tested in CI.
3. Decide whether pull requests targeting `phase-0.2-planning` should trigger this workflow; if yes, add that base branch to the PR trigger.
4. Inspect and document branch protection/rulesets so required checks are enforced on the intended protected branch.
5. Keep test evidence tied to the exact commit SHA and run ID; update acceptance reports when the workflow test matrix changes.
6. Before a production release pipeline is authorized, define separate gates for signed artifacts, provenance/SBOM, independent security approval, configuration/genesis pinning, and deployment authorization. These are not supplied by this workflow.

## 6. Release disposition

| Area | Current evidence/status |
|---|---|
| Latest planning-branch CI run | Passed, run 41975196036 on commit f340e4e8a06452a39e96ae79a17095a6b1aa82f6 |
| Listed isolated v0.2 tests | Passed in latest run |
| Listed CometBFT/remote-signer integration probes | Passed in latest run |
| Anti-rollback reference Python module | Not listed in current workflow command; not proven by this run |
| Recovery-controls Python module | Not listed in current workflow command; not proven by this run |
| PR trigger targeting planning branch | Not configured |
| Required-check branch protection | Not assessed |
| Signed release/provenance/deployment pipeline | Not present in inspected workflow |
| Production security/release approval | Not established |

**Disposition:** CI is green for the workflow's declared steps on the inspected commit, but test-matrix completeness and release governance remain open. Keep production release gates closed until the missing test coverage is deliberately resolved, trigger/branch-protection expectations are confirmed, and the separate production approval requirements are met.

No workflow, source, test, branch-protection, or release configuration was changed. No new tests were run by this static audit. This report records observed CI evidence and configuration gaps only; it is not a security certification or launch approval.
