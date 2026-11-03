# HND v0.2 — WP4.8 CometBFT validator signer guard

**Date:** 2026-11-04  
**Workstream:** WP4.8 — validator signing-state and same-HRS conflict checks  
**Status:** Implemented and CI-verified for the pinned CometBFT v0.40.0 FilePV signer  
**Branch:** `phase-0.2-planning`

## 1. Purpose and responsibility boundary

CometBFT owns validator consensus signing. HND's ABCI application validates HND transactions and deterministic application state; it must not create its own competing consensus signer or implement a parallel consensus protocol.

This work adds a disposable Go smoke test that imports the exact pinned CometBFT v0.40.0 `privval.FilePV` implementation. It tests the local file-backed validator signer guard, rather than a reimplementation in Python.

## 2. Implementation

Added:

- `scripts/cometbft_v040_privval_signing_smoke.go`
- A CI step named `Run pinned CometBFT validator signer anti-double-sign smoke test` in `.github/workflows/hnd-v02-tests.yml`

The test creates disposable private-validator key and state files in a temporary directory, runs the signer checks, and removes the temporary directory when complete. It prints only a success marker; it does not print or upload private keys.

## 3. Tested cases

The pinned CometBFT FilePV smoke test verifies:

1. A first prevote at height 10, round 1 is signed.
2. Retrying the same height/round/type and same block is accepted and reuses the persisted signature.
3. A different block ID at the same height/round/type is rejected.
4. After loading FilePV again from the same key and last-sign-state files, the original vote can be retried with the same signature, while the conflicting block remains rejected.
5. Height and round regressions are rejected.
6. Advancing the HRS step from prevote to precommit at the same height/round is accepted for the same block; a conflicting precommit after a signer reload is rejected.
7. A proposal is signed, an identical retry is accepted with the persisted signature, and a conflicting proposal at the same height/round is rejected both before and after signer reload.

The smoke test uses the CometBFT v0.40.0 implementation in:
- `privval/file.go`: `FilePVLastSignState.CheckHRS`, `SignVote`, `SignProposal`, and persistent `saveSigned`.
- `privval/file_test.go`: upstream tests for same-HRS retries and conflicting votes/proposals.

Pinned source references:
- https://github.com/cometbft/cometbft/blob/v0.40.0/privval/file.go
- https://github.com/cometbft/cometbft/blob/v0.40.0/privval/file_test.go

## 4. CI evidence

**Tested commit:** `027a0db12ac391462ff97027df138491a3e83102`  
**GitHub Actions run:** https://github.com/3bbdala-max/HND-Ledger/actions/runs/41723251514  
**CometBFT:** v0.40.0  
**Workflow conclusion:** `success` for both `hnd-v02-tests` and `cometbft-single-node-smoke`.

Observed CI evidence:

- `Ran 133 tests` — Python suite passed.
- `COMETBFT_V040_PRIVVAL_SIGNER_GUARD_OK` — FilePV signer guard smoke test passed.
- `COMETBFT_V040_SINGLE_NODE_SMOKE_OK` — single-node application integration and restart passed.
- `COMETBFT_V040_3_1_PARTITION_OK` — three-validator quorum advanced while one validator remained isolated and unchanged.
- `COMETBFT_V040_2_2_PARTITION_OK` — neither half advanced during the 12-second observation window.
- `COMETBFT_V040_PARTITION_RECONNECTION_OK` — both partition scenarios reconverged after reconnection.
- `COMETBFT_V040_FOUR_VALIDATOR_NETWORK_OK` — four-validator integration and prior crash-stop/restart catch-up passed.

## 5. Security scope and limitations

This test demonstrates selected behavior of CometBFT's local FilePV signer implementation for conflicting messages at the same height/round/type, height/round regressions, and persistence of its last-sign-state across reload.

It does **not** establish:

- Byzantine fault tolerance or consensus safety under arbitrary malicious validators.
- Safety under 1/3 or more malicious voting power.
- Correctness or security of remote signers, HSM integrations, multi-operator key custody, or external signing services.
- Protection if an operator deletes, rolls back, or maliciously replaces both a signing key and its last-sign-state.
- DDoS resistance, censorship resistance, WAN reliability, or long-duration partition safety.
- Slashing/evidence policy or validator governance.

The 3/1 and 2/2 partition tests remain controlled local integration tests; they are not a Byzantine consensus proof. Independent review of the CometBFT integration and operational key management remains mandatory before any public or financial use.

## 6. Next work

Proceed to adversarial consensus-message/fault-injection tests on the four-validator harness, then design remote-signer/key-custody requirements and snapshot/state-sync support. Keep these as separate gates; do not treat a passing FilePV smoke test as a complete security audit.

---
This is bounded engineering test evidence only. It is not a security certification, financial-product approval, or release authorization.
