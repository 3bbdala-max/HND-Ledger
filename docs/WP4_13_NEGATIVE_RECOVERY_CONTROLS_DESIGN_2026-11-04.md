# WP4.13 — Negative Recovery Controls Design (2026-11-04)

**Target branch:** `phase-0.2-planning`  
**Baseline commit reviewed:** `18ba780686730a9a90ddb1ebe50b8af62438b0d5`  
**Status (updated 2026-11-04):** NC-1 signer-state substitution and NC-2 validator-identity substitution are implemented and passed in CI run `41881433042` on commit `66dd05d86c3fc60c4869feb1e42a243da407d15c`. NC-3 bounded recovery-timeout injection and NC-4 post-recovery divergence rejection are now implemented in `hnd_v02/recovery_controls.py`; the controls are covered by `tests/test_v02_four_replica_state_convergence.py`, which is already part of the CI unittest command. The four-validator recovery harness now calls the convergence gate on all four recovered height, block-hash, and decoded app-hash fingerprints. Unit-test evidence: CI run `41883554557` on commit `ee579bd45106c1b64e011f8f2f366593a19f1bc0` passed all 146 Python tests, including the new timeout and divergence negative controls. The subsequent CometBFT integration portion and the clean-shutdown snapshot adjustment in commit `b4cb6e1fd8ba3af59091c9dfd54bcb4582794048` still require CI confirmation; WP4.13 remains open.

## 1. Purpose

The existing WP4.13 happy-path test proves that one stopped validator and its HND ABCI application can restart from the same local files, recover, and converge with the other three validators. It does not yet prove that recovery rejects substituted signer state, substituted validator identity, timeout, or post-recovery divergence.

These controls are required before WP4.13 can be closed. Implemented controls use disposable CI keys and state only; the remaining controls must preserve that isolation.

## 2. Findings from the current harness

The current four-validator harness captures SHA-256 digests for validator 4's HND state file, CometBFT consensus key file, and P2P node key file before stopping the processes. It checks that the HND state and identity files remain unchanged on the normal restart path.

The external signer recovery helpers now accept an expected SHA-256 digest and verify it before loading `privval.LoadFilePV` or opening the listener. The orchestrator captures the signer-state digest after clean signer shutdown, after FilePV has finished advancing its state. CI run `41881433042` passed both missing-state and substituted/digest-mismatch rejection probes for Unix and Noise transports, and both four-validator outage/recovery paths.

The harness now deliberately substitutes a valid alternate consensus key and a valid alternate P2P node key in isolated disposable homes, and confirms semantic identity preflight rejects each substitution. CI run `41881433042` emitted `HND_WP4_13_ALTERNATE_CONSENSUS_IDENTITY_REJECTED` and `HND_WP4_13_ALTERNATE_P2P_IDENTITY_REJECTED`.

## 3. Required negative controls

### NC-1 — External signer anti-double-sign state substitution

1. Create a disposable validator key and signer state.
2. Capture the signer-state SHA-256 before shutdown.
3. Stop the signer cleanly.
4. Replace the signer state with a different valid state file (including a previously captured empty/older state where the CometBFT format permits it).
5. Start recovery with the expected pre-stop digest supplied by the test orchestrator.
6. Require rejection before `privval.LoadFilePV` and before the signer opens its listener.
7. Assert a stable failure marker and no successful signer-connected marker.

Run the same test against Unix and Noise signer helpers if both support the same recovery mode.

**Boundary:** An expected digest passed by the same CI orchestrator detects substitution within this test run. It is not production anti-rollback protection if an attacker can also replace the expected digest. Production protection requires an independently trusted anchor, such as an HSM/KMS monotonic counter or separately protected append-only signing-state service.

### NC-2 — Validator identity substitution

Test consensus and P2P identity independently:

1. Capture the expected validator consensus public-key fingerprint and CometBFT node ID before shutdown.
2. Stop the node.
3. Replace the consensus key with a different, valid disposable key; require recovery preflight to reject the unexpected consensus identity.
4. Restore the original consensus key, then replace the P2P node key with a different, valid disposable key; require rejection of the unexpected node ID.
5. Verify neither negative case is reported as recovered and that no production or persistent key material is used.

The check must compare semantic public identities (consensus public-key fingerprint and node ID), not merely file existence. File digests may be recorded as supplementary evidence.

### NC-3 — Bounded recovery timeout

Implemented in `hnd_v02/recovery_controls.py` as `wait_for_recovery_readiness` and exercised by a deterministic subprocess fixture. It enforces an explicit deadline, terminates the disposable process (kill fallback if needed), raises a timeout error instead of returning success, and does not touch the caller-owned durable state. The unit test passed in CI run `41883554557` (146 tests total).

The test must not rely on an unbounded `wait()` or a timing race. The timeout should be short in the negative fixture and comfortably bounded in the ordinary CI happy path.

### NC-4 — Post-recovery divergence detection

Implemented as `assert_replica_convergence`: it compares every recovered validator's height, block hash, and decoded application hash and raises a fail-closed error naming divergent validators. The four-validator smoke harness invokes this gate before printing its all-four-recovered marker. The unit fixture injects a different app hash for validator 4 and asserts explicit rejection. The unit test passed in CI run `41883554557`; the full CometBFT recovery smoke path still needs to pass.

Do not corrupt a retained user database or any non-disposable environment. The fixture must be isolated and automatically cleaned up.

## 4. Acceptance evidence

WP4.13 remains open until all of the following are present:

- NC-1 and NC-2 run in CI and emit distinct machine-readable rejection markers (verified in run `41881433042`).
- NC-3 implementation and deterministic timeout test passed in CI run `41883554557` (146 tests total).
- NC-4 implementation and deterministic divergence test passed in CI run `41883554557`; full CometBFT smoke confirmation remains pending.
- The normal recovery path passes for both supported signer transports (verified in run `41881433042`).
- Failure cases are fail-closed and cannot be mistaken for successful recovery.
- Logs identify the failed control without exposing private keys, signer-state contents, tokens, or secrets.
- The phase plan links the exact workflow run and tested commit.
- A reviewer confirms that the test-only digest anchor is not described as production anti-rollback security.

## 5. Explicit non-claims

Passing these CI controls would demonstrate that the disposable harness detects the specified recovery failures. It would not prove production key custody, rollback resistance against an attacker controlling both the state file and its expected digest, Byzantine fault tolerance, or production readiness. WP4.14 custody design and the G2–G4 release gates remain separate and open.
