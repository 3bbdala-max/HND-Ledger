# HND v0.2 — WP4.14 / CI technical acceptance evidence report

**Date:** 2026-11-04  
**Branch:** `phase-0.2-planning`  
**Tested commit:** `1610824860081bd803a1b87fa3b89237b36f6ed1`  
**CI run:** [41890718611](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41890718611)  
**Overall result:** SUCCESS — both jobs completed successfully  
**Purpose:** Record the exact automated evidence for this commit. This is an internal test-evidence report, not an independent audit or production approval.

## 1. Run disposition

GitHub Actions run 41890718611 completed with conclusion `success`.

| Job | Result |
|---|---|
| `hnd-v02-tests` | Success |
| `cometbft-single-node-smoke` | Success |

The tested branch head was `1610824860081bd803a1b87fa3b89237b36f6ed1`. At report preparation, `phase-0.2-planning` still pointed to that commit. The `main` branch remained at `3f0a71e27924954f27813ec68e483ecf159461e5`; no merge to main was performed.

## 2. Successful automated checks

The isolated v0.2 job successfully installed its dependencies, generated pinned CometBFT v0.40.0 Python bindings, and ran the isolated v0.2 test suite. This includes the offline synthetic anti-rollback reference-model tests already present in the branch.

The CometBFT integration job successfully completed all listed steps, including:

- Pinned CometBFT Byzantine prevote equivocation/evidence regression.
- HND four-replica P2P equivocation evidence integration.
- Validator signer anti-double-sign smoke and remote-signer protocol conformance.
- Process-isolated remote-signer probe.
- Authenticated Noise remote-signer integration and unauthorized-peer rejection.
- Connected remote-signer vote-withholding probe.
- Anti-double-sign persistence across restart.
- Rejection of missing or substituted anti-double-sign state in recovery mode, including the Noise helper path.
- Single-node ABCI integration smoke test.
- Four-validator Genesis and identity preflight.
- Private four-validator network integration smoke test.
- Four-validator external remote-signer integration and outage recovery.
- Four-validator authenticated Noise remote-signer integration and recovery.

All steps reported by the two jobs completed with `success`; no failed steps were reported in this run.

## 3. What this result establishes

For the exact tested commit and the CI environment, the recorded automated test commands completed successfully. The run provides reproducible CI evidence for the listed isolated tests, CometBFT v0.40.0 integration probes, four-validator local test harness, remote-signer transport/recovery probes, and synthetic anti-rollback reference-model suite.

## 4. What this result does not establish

This green CI run does **not** establish:

- production-grade Byzantine fault tolerance, partition safety, or liveness under arbitrary network conditions;
- production key custody, HSM/TPM/KMS security, hardware monotonicity, or independent anti-rollback trust;
- filesystem/database crash consistency under all power-loss and storage failure modes;
- independent security audit completion or closure of WP4.14 Stage A review findings;
- operational readiness, governance approval, jurisdiction-specific legal clearance, or permission to issue, sell, list, or transfer a real-value token.

The four-validator integration is a controlled CI test, not a public distributed network. The remote-signer helpers and credentials remain test-only. The anti-rollback model is synthetic and offline; it is not a real trust anchor.

## 5. WP4.14 disposition

- **Stage A — independent security review:** OPEN. The internal review register is a checklist, not an independent review.
- **Stage B — synthetic reference model:** automated test suite passed in this CI run. This does not imply Stage A has been independently approved or that a production trust anchor exists.
- **Stages C and D:** NOT AUTHORIZED / NOT STARTED. No provider credentials, live HSM/KMS, production keys, or production signing endpoint are to be introduced.
- **Release gates G2–G4:** remain closed. No public launch or real-value activity is authorized.

## 6. Next controlled actions

1. Preserve this report and the CI run as evidence for the tested commit.
2. Obtain an independent security review addressing the WP4.14 Stage A register and record reviewer identity, scope, findings, and disposition.
3. Close architecture decisions only with documented evidence; keep the trust-anchor/provider choice open until reviewed.
4. Do not proceed to live custody integration, production key generation, or deployment until the required independent approvals are recorded.

---
This report records automated test evidence only. It is not a security certification, audit opinion, legal opinion, or production-readiness declaration.
