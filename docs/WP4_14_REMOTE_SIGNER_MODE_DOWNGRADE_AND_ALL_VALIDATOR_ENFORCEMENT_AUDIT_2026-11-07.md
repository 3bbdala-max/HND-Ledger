# WP4.14 — Remote-Signer Selection, Local FilePV Downgrade, and Validator Coverage Audit

**Date:** 2026-11-07  
**Branch reviewed:** `phase-0.2-planning`  
**Review type:** Static source review of the repository's disposable CometBFT v0.40.0 integration harness and signer helper.  
**Change boundary:** Documentation only. No source, tests, workflows, keys, or runtime configuration changed.

## 1. Executive determination

The current four-validator smoke harness demonstrates a useful remote-signing path for **validator 4 only**. It configures that node's `priv_validator_laddr` to a Unix or Noise endpoint, moves validator 4's consensus key and anti-double-sign state into a separate signer-owned directory, starts a signer process, and later tests signer outage/restart.

It does **not** establish a release-grade policy that every production validator must use the approved remote signer, nor does it test a fail-closed response to a configuration downgrade that removes or changes the remote-signer endpoint while a local consensus key is available. Three validators in the same smoke network intentionally retain local FilePV signing.

This is a test-topology and deployment-enforcement gap, not evidence that the current validator-4 test successfully bypasses its remote signer. The harness's moved key file makes the validator-4 local fallback path unavailable in that particular fixture.

**Disposition:** OPEN. Do not treat the current smoke test as proof of universal remote-signer enforcement or production anti-downgrade protection.

## 2. Source observations

### 2.1 Four-validator harness selects remote signing for one validator

In `scripts/cometbft_v040_four_validator_network_smoke.py`:

- The harness creates four independent CometBFT homes using `cometbft init`.
- It initially reads each validator's `config/priv_validator_key.json` and constructs the four-member test validator set.
- When a signer binary is supplied, it moves validator 4's consensus private-key file and `data/priv_validator_state.json` into `root/signer4/`.
- It changes `priv_validator_laddr` only for `i == 3` (validator 4), choosing either `noise://...` or `unix://...`.
- Validators 1–3 do not receive that remote-signer setting and continue using their local FilePV configuration.
- The harness starts all four CometBFT nodes and starts the signer process for validator 4.

The test therefore covers a mixed topology (three local signers plus one remote signer), not a four-validator deployment in which every consensus key is isolated behind a remote signer.

### 2.2 The test-only Noise helper owns a FilePV behind a signer server

In `scripts/cometbft_v040_noise_remote_signer_helper.go`:

- The file explicitly labels the helper test-only and says it uses disposable identities.
- The helper loads the validator key/state with `privval.LoadFilePV(pvKeyPath, pvStatePath)`.
- It creates a CometBFT `privval.NewSignerServer(...)` and waits for the authenticated dialer connection.
- The Noise transport authenticates the expected CometBFT node peer identity and the harness separately probes rejection of an unauthorized peer.
- Recovery mode requires an existing regular state file and checks its expected SHA-256 before starting the signer.

These controls are valuable transport and recovery probes. They do not by themselves bind the node's selected signer mode to an independently trusted, signed deployment profile.

### 2.3 The harness does not exercise a signer-mode downgrade matrix

The reviewed four-validator harness sets the endpoint for validator 4 in the positive remote-signer case. The inspected flow does not include negative cases that:

- remove `priv_validator_laddr` while restoring a local consensus key into the node home;
- replace the approved Noise endpoint with a Unix/local endpoint;
- substitute an unapproved remote signer peer identity or endpoint in the node configuration and then attempt node startup;
- alter signer mode after an approved profile has been verified;
- assert, for every validator, that the running node is connected to the expected signer identity before consensus signing is possible.

The existing unauthorized Noise peer probe tests rejection at the Noise listener. It is not a test of CometBFT startup rejecting a downgraded `priv_validator_laddr` or a local FilePV fallback.

## 3. Security interpretation

A remote signer is not mandatory merely because one integration test uses `priv_validator_laddr`. A deployment must enforce the selected signing mode as part of an independently authenticated validator profile.

If a node is allowed to load a local consensus private key, changing or omitting the remote-signer endpoint may change the signing trust boundary. Whether a particular CometBFT configuration fails or falls back in a given case must be established against the exact pinned CometBFT source and tested with the exact production startup wrapper; this audit does not claim that the current v4 fixture demonstrates a successful fallback.

For validator 4 in the current test, the key is moved out of the node home, which is a useful defense-in-depth fixture. It is not a substitute for a startup policy that rejects an unapproved signer mode before the node can start.

## 4. Required closure tests (not implemented or executed by this audit)

| ID | Required negative/positive test | Expected result |
|---|---|---|
| RS-MODE-01 | Start a validator whose approved profile requires Noise but whose `priv_validator_laddr` is absent | Startup rejected before consensus operation |
| RS-MODE-02 | Replace the approved Noise endpoint with Unix/local FilePV mode | Startup rejected |
| RS-MODE-03 | Restore a local key while removing the required remote endpoint | Startup rejected; no local signing |
| RS-MODE-04 | Substitute an unapproved Noise peer ID or endpoint | Startup rejected before signing |
| RS-MODE-05 | Apply the approved signer profile to all four test validators | Each node proves connection to its own expected signer identity |
| RS-MODE-06 | Kill/disconnect the required signer after startup | Validator cannot sign locally or through an alternate path; node enters defined fail-closed behavior |
| RS-MODE-07 | Change signer mode after profile verification but before node startup completes | Startup rejected or re-verification required |
| RS-MODE-08 | Verify the exact running binary, profile digest, node identity, validator key identity, and signer peer identity as one startup attestation | All values match independently trusted pins |

These are proposed acceptance tests only. No test result is implied.

## 5. Closure requirements

1. Define a versioned validator signing-mode policy (for example, mandatory remote signer, approved transport, expected signer identity, and explicit prohibition of local FilePV) for each validator profile.
2. Authenticate that policy independently of the node's editable local TOML and key directory.
3. Enforce the policy in the production startup path before CometBFT listeners and consensus signing become available.
4. Ensure the local consensus key is not provisioned to a node that must use remote signing; treat this as defense in depth, not the sole enforcement.
5. Add the downgrade and all-validator coverage tests above to CI and retain exact run/commit evidence.
6. Combine this gate with the already-open signer-side TOCTOU, single-writer, durable anti-rollback, and recovery requirements. Noise authentication alone does not establish signer authorization linearization or single-writer ownership.

## 6. Evidence boundary

This report is based on static inspection of the repository files named above. It does not claim to have reproduced a downgrade, observed a local fallback, audited every CometBFT v0.40.0 startup branch in this report, or run any of the proposed tests. CI evidence must be associated with the exact commit and job that executed it.

**Final status:** Remote-signer integration exists as a disposable test path for validator 4. Universal remote-signer enforcement, signer-mode anti-downgrade policy, and all-validator coverage remain OPEN. No production approval or launch authorization is granted.


## 7. Correction after pinned CLI startup-path trace (2026-11-07)

The original evidence boundary above predates a deeper trace of the exact CometBFT v0.40.0 CLI path and must be read with this correction.

The CI-pinned CometBFT source commit is `0880b4d378f347ab16e54ec677ff50d803f37d62`. Its standard CLI `node`/ `start` command is wired to `node.DefaultNewNode`. That provider calls `privval.LoadOrGenFilePV(config.PrivValidatorKeyFile(), config.PrivValidatorStateFile())` before calling `node.NewNode`. `NewNodeWithContext` then replaces the supplied validator object with the remote socket client when `PrivValidatorListenAddr` is configured.

The HND CI workflow builds this stock CLI from the pinned source and the harness launches it using `[binary, "node", "--home", ...]`. In the external-signer fixture, validator 4's original key/state are moved out of its node home before this command is run. Consequently, the stock CLI provider can generate a replacement local FilePV key/state in that home before the node switches to the external signer client.

**Corrected interpretation:** the earlier statement that moving validator 4's key makes the local fallback path unavailable is incomplete and must not be used as a security conclusion. The existing test has not demonstrated no-local-key behavior; it may leave a newly generated local consensus key alongside the remote signer path. This is a provisioning hazard even if the remote signer remains the active interface used by consensus.

The current harness does not assert that the node home remains free of `priv_validator_key.json` after startup. Its later identity assertions read that path, which is consistent with the harness relying on a local file rather than proving its absence.

**Required action:** use a reviewed custom provider/startup executable or an approved upstream code change that avoids `LoadOrGenFilePV` for remote-signer validators; assert no local key file is created before and after startup; assert remote `GetPubKey` equals the Genesis validator identity; and execute downgrade/no-fallback tests. Do not remove a regenerated key after startup and call that prevention.

This correction supersedes the narrower interpretation in sections 1 and 3 for the stock CLI path. All-validator external signing and mandatory no-local-key enforcement remain OPEN.
