# WP4.14 — CI Acceptance Evidence

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Reviewed commit:** `15157e5fbea1c0bd603f22f3a8b640f62eef82c9`  
**Workflow run:** [42321741346](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42321741346)  
**Conclusion:** SUCCESS — both required jobs completed successfully.

## 1. Executed test evidence

### Isolated HND v0.2 tests

Job: `hnd-v02-tests`  
Result: SUCCESS  
Test runner output: **221 tests passed** (17.694 seconds).

The workflow includes transaction envelope, Genesis, ledger, blocks, ABCI application, CometBFT adapter, four-replica evidence, state convergence, TCP peer relay, anti-rollback reference, and recovery-control test modules.

### CometBFT integration

Job: `cometbft-single-node-smoke`  
Result: SUCCESS

The completed job includes successful steps for:

- Building CometBFT from pinned source commit `0880b4d378f347ab16e54ec677ff50d803f37d62`.
- CometBFT Byzantine prevote equivocation/evidence regression.
- HND four-replica P2P equivocation evidence integration.
- CometBFT validator signer anti-double-sign smoke test.
- Remote-signer protocol conformance and process-isolated probes.
- Authenticated Noise remote-signer integration and unauthorized-peer rejection.
- Vote-withholding probe.
- Anti-double-sign persistence across signer restart.
- Rejection of missing or substituted signer recovery state, for both remote-signer helper paths.
- Single-node ABCI integration.
- Four-validator Genesis and identity preflight.
- Private four-validator network integration.
- Four-validator external remote-signer outage/recovery integration.
- Four-validator authenticated Noise remote-signer integration and recovery.

The final authenticated Noise integration step completed successfully; the entire job and workflow then completed successfully.

## 2. What this evidence establishes

For this exact commit and the workflow environment, the declared 221-test HND suite and all configured CometBFT integration steps passed. The four-validator integration fixtures exercised remote signing, signer outage/restart, recovery-state checks, and network/application convergence within the test harness.

## 3. What this evidence does not establish

This CI run is not a production certification or independent security audit. In particular, it does not close the previously documented issues:

- The signer probes and network fixtures do not prove safe simultaneous signing by two independent signer processes/hosts, nor do they establish a production-grade distributed single-writer lease or linearized authorization boundary.
- The four-validator fixture configures the remote signer for validator 4; it does not prove mandatory remote signing and downgrade resistance for every production validator.
- The anti-rollback reference remains an offline synthetic model and is not a hardware-backed production anchor.
- The VSP/JCS candidate is not frozen, approved, or enforced by an unavoidable runtime verifier.
- The insecure ABCI gRPC transport remains loopback-only; loopback containment is not TLS, mutual authentication, or local process authorization.
- A fully hashed transitive dependency lock, SBOM, signed build provenance, deployment controls, production monitoring, and backup/restore drills remain outstanding.
- No real production validator keys, production chain, public release, or deployment were used.

## 4. Acceptance decision

**CI acceptance for the tested `phase-0.2-planning` commit: PASS.**

**Production readiness: NOT APPROVED.**

The successful run closes the outstanding CI execution question for commit `15157e5fbea1c0bd603f22f3a8b640f62eef82c9`; it does not close the separate architecture, governance, operational, or independent-review gates listed above.
