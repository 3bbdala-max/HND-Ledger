# WP4.6 — ABCI Genesis Identity Negative Tests

**Status:** Implemented and CI-verified  
**Target branch:** `phase-0.2-planning`  
**Tested commit:** `b89b99abc4c9193c0235b3f5ff52833ef9c0b91e`  
**Consensus engine:** CometBFT v0.40.0

## 1. Purpose

This work package adds negative-path checks at the HND ABCI initialization boundary. The tests ensure that an application instance refuses to initialize when the CometBFT chain identity or the independently pinned HND Genesis manifest identity does not match its configured expectation.

## 2. Tests added

In `tests/test_v02_cometbft_v040_adapter.py`:

1. **Wrong CometBFT chain ID:** calls the adapter's `InitChain` with an attacker-selected chain ID. The call must raise the expected chain-ID mismatch error and must not create the application state file.
2. **Wrong pinned Genesis hash:** supplies the correct manifest with an all-zero Genesis hash. The call must raise the Genesis hash mismatch error and must not create the application state file.

The no-state-file assertions matter: rejection must happen before initialization writes persistent application state.

## 3. CI evidence

GitHub Actions run [41246122343](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41246122343) completed with conclusion **success** for commit `b89b99abc4c9193c0235b3f5ff52833ef9c0b91e`.

Both workflow jobs passed:

- `hnd-v02-tests`: isolated v0.2 tests, including the two new negative InitChain tests.
- `cometbft-single-node-smoke`: pinned CometBFT build, single-node integration, four-validator Genesis/identity preflight, and full private four-validator integration smoke test.

## 4. Security meaning and limits

These tests verify two specific initialization identity checks. They do **not** prove resistance to malicious validators, equivocation, network partition attacks, Sybil attacks, denial of service, key compromise, or arbitrary Byzantine behavior. The four-validator test remains a local crash-stop/restart integration test, not a Byzantine fault-tolerance proof or an independent security audit.

## 5. Current decision

- The chain-ID and pinned-Genesis mismatch negative cases are covered and CI-passing.
- The private four-validator integration remains CI-passing at the recorded revision.
- Production deployment, public token issuance, real-value transfers, and public release remain blocked pending broader adversarial testing, durable storage and key-management engineering, independent security review, governance, and jurisdiction-specific legal review.
- All changes remain on `phase-0.2-planning`; `main` is not modified.

---
This report records engineering test evidence only. It is not a security certification, financial-product approval, or release authorization.
