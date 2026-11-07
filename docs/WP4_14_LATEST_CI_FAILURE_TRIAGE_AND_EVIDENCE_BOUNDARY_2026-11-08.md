# WP4.14 — Latest CI Failure Triage and Evidence Boundary

**Inspection date:** 2026-11-08  
**Branch:** `phase-0.2-planning`  
**Inspected branch HEAD:** `a3c41b24d7ee6cdd08f4f7ac2abfb9857ceaa7fc`  
**Run:** `42338348291`  
**Review type:** GitHub Actions metadata, job-step inspection, workflow/source inspection  
**Change type:** Documentation only  
**Disposition:** Confirmed failure location; root cause not established

## 1. Executive summary

The latest workflow run for the inspected branch HEAD completed with **failure**. The failure is isolated to the CometBFT integration job at the step named:

`Run HND four-replica P2P equivocation evidence integration`

The preceding pinned CometBFT Byzantine prevote/evidence regression step passed. All later steps in that job were skipped because the integration step failed. The HND unit-test job passed, including the isolated cross-language VSP JCS compatibility spike.

This report does not infer the underlying cause from the failed step label. A step-level failure is confirmed; a specific assertion, exception, or protocol defect is **not** confirmed by the metadata inspected here.

## 2. Exact commit-bound run evidence

- Branch HEAD: `a3c41b24d7ee6cdd08f4f7ac2abfb9857ceaa7fc`
- Run ID: `42338348291`
- Run URL: https://github.com/3bbdala-max/HND-Ledger/actions/runs/42338348291
- Overall status/conclusion: `completed / failure`

### Job: `hnd-v02-tests`

Conclusion: **success**.

The following steps completed successfully:
- Install hash-verified isolated JCS spike dependency.
- Install integrity-locked independent JavaScript JCS comparator.
- Generate pinned CometBFT v0.40.0 Python bindings.
- Run isolated VSP JCS cross-language compatibility spike.
- Run isolated v0.2 tests.

This is evidence that the named CI steps passed on this exact commit. It is not an approval of the VSP candidate as a frozen protocol specification.

### Job: `cometbft-single-node-smoke`

Conclusion: **failure**.

| Step | Result |
|---|---|
| Build pinned CometBFT binary | success |
| Remote-only CLI rejects missing signer without generating local consensus keys | success |
| Pinned CometBFT Byzantine prevote equivocation/evidence regression | success |
| HND four-replica P2P equivocation evidence integration | **failure** |
| Validator signer anti-double-sign and all subsequent probes | skipped |

The failed integration step is run by:

`python scripts/cometbft_v040_hnd_p2p_evidence_integration.py --cometbft-source ...`

## 3. What the integration script is intended to prove

Static inspection of the script shows that it:
1. Starts four separate HND ABCI application processes on loopback ports.
2. Patches the pinned CometBFT Byzantine test in a disposable source checkout so its ABCI application connections point to those four HND replicas.
3. Runs the upstream Byzantine prevote-equivocation test against that setup.
4. Queries all four replicas and checks evidence-journal equality, application-hash equality, and matching heights.
5. Checks that one duplicate-vote evidence record is recorded and account balances remain unchanged.
6. Restarts one HND application process and checks restoration of its evidence journal, app hash, and height.

These are intended assertions, not a claim that each assertion was reached or passed in the failed run.

## 4. Root-cause status

**Confirmed:** the integration step exited unsuccessfully.

**Not established from the inspected job-step metadata:**
- whether the subprocess failed during Go test execution;
- whether the four replicas diverged in journal, app hash, or height;
- whether the evidence count/type assertion failed;
- whether the restart/restore assertion failed;
- whether a transient port/process/readiness issue occurred.

No root-cause label should be assigned until the failed step's complete stdout/stderr is inspected and the first causal error is identified. The large raw job-log response could not be safely retrieved in this inspection, so this report deliberately does not fabricate an error message.

## 5. Required triage sequence

1. Retrieve the failed step's complete log using a bounded log/artifact retrieval method; identify the earliest causal error, not merely the final Python exception.
2. Preserve the exact failing commit and record the failing assertion or subprocess return code.
3. Determine whether the failure is deterministic by analyzing existing evidence only; do not rerun CI or modify workflow/source as part of this report.
4. Map the failure to one layer: CometBFT test patch, ABCI transport/process lifecycle, evidence delivery, replica convergence, or restart persistence.
5. Propose the smallest isolated correction and its regression test. Any source, test, or workflow modification requires separate explicit authorization.
6. After an authorized correction, require a new run whose `head_sha` exactly matches the corrected commit; do not transfer success from another commit.

## 6. Safety and release disposition

- No source code, test, workflow, dependency, validator configuration, or key material was changed by this report.
- No CI rerun was requested or triggered.
- The JCS compatibility spike passed in the HND test job on this commit; this does not freeze or approve VSP.
- The four-replica P2P evidence integration is currently a confirmed CI blocker.
- Signer anti-double-sign, remote-signer, single-node ABCI, four-validator, and subsequent recovery probes were skipped in this run; their status is **not tested in this run**, not failed individually.
- No public launch, production signing, token issuance, or production-readiness approval is granted.
