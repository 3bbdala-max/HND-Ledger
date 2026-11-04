# WP4.13 — Negative Recovery Controls Design (2026-11-04)

**Target branch:** `phase-0.2-planning`  
**Baseline commit reviewed:** `18ba780686730a9a90ddb1ebe50b8af62438b0d5`  
**Status:** Test design only. No negative-control implementation or new CI pass is claimed by this document.

## 1. Purpose

The existing WP4.13 happy-path test proves that one stopped validator and its HND ABCI application can restart from the same local files, recover, and converge with the other three validators. It does not yet prove that recovery rejects substituted signer state, substituted validator identity, timeout, or post-recovery divergence.

These controls are required before WP4.13 can be closed. They are disposable CI tests using temporary keys and state only.

## 2. Findings from the current harness

The current four-validator harness captures SHA-256 digests for validator 4's HND state file, CometBFT consensus key file, and P2P node key file before stopping the processes. It checks that the HND state and identity files remain unchanged on the normal restart path.

The external signer helper's recovery path checks that the anti-double-sign state file exists and is a regular file, then loads it with CometBFT `privval.LoadFilePV`. It does not receive an independently captured expected digest. Consequently, a different but parseable signer-state file is not proven to be rejected.

The normal restart path also does not deliberately replace the consensus or P2P identity with another valid key. A digest check on the untouched original files is not a negative identity test.

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

1. Give the recovery supervisor an explicit timeout parameter.
2. Use a deterministic test fixture that delays or withholds the required readiness signal beyond that timeout.
3. Require a timeout failure marker, termination of the disposable recovery process, and no success marker.
4. Verify the original durable state and signer state are not silently reinitialized or overwritten.

The test must not rely on an unbounded `wait()` or a timing race. The timeout should be short in the negative fixture and comfortably bounded in the ordinary CI happy path.

### NC-4 — Post-recovery divergence detection

1. Complete the ordinary recovery and four-node convergence check.
2. In a separate disposable negative fixture, make one replica expose a deliberately different application-state commitment (or provide a controlled mismatching commitment to the convergence assertion).
3. Require the convergence gate to fail and identify the divergent validator.
4. Verify the test harness does not emit the all-four-recovered success marker when any height, block hash, app hash, or required account state differs.

Do not corrupt a retained user database or any non-disposable environment. The fixture must be isolated and automatically cleaned up.

## 4. Acceptance evidence

WP4.13 remains open until all of the following are present:

- Each negative control runs in CI and emits a distinct, machine-readable rejection marker.
- The normal recovery path still passes for both supported signer transports.
- Failure cases are fail-closed and cannot be mistaken for successful recovery.
- Logs identify the failed control without exposing private keys, signer-state contents, tokens, or secrets.
- The phase plan links the exact workflow run and tested commit.
- A reviewer confirms that the test-only digest anchor is not described as production anti-rollback security.

## 5. Explicit non-claims

Passing these CI controls would demonstrate that the disposable harness detects the specified recovery failures. It would not prove production key custody, rollback resistance against an attacker controlling both the state file and its expected digest, Byzantine fault tolerance, or production readiness. WP4.14 custody design and the G2–G4 release gates remain separate and open.
