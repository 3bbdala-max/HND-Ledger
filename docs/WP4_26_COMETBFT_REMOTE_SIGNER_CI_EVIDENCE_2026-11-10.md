# WP4.26 — CometBFT v0.40.0 remote-signer integration CI evidence

Date: 2026-11-10

## Run identity

- Repository: `3bbdala-max/HND-Ledger`
- Workflow run: `42798888553`
- Commit SHA: `ea16d97a97eeb22390b4f6d49837d561205bc9e7`
- PR: #11
- Run URL: https://github.com/3bbdala-max/HND-Ledger/actions/runs/42798888553
- Result: both workflow jobs completed successfully.

## Job results

### hnd-v02-tests

- Conclusion: success.
- All 19 job steps completed successfully.
- Scope includes strict VSP envelope and payload verification, Trust Manifest bootstrap, Trust Manifest-to-VSP authorization composition, operator acknowledgements, activation-bundle preflight, strict CometBFT profile-parser tests, and the isolated HND v0.2 regression suite.

### cometbft-single-node-smoke

- Conclusion: success.
- All 32 execution steps completed successfully (plus setup/post-job steps).
- The build used pinned CometBFT source commit `0880b4d378f347ab16e54ec677ff50d803f37d62`.
- Successful integration scope includes:
  - remote-only CLI rejection of missing/unauthenticated signer configuration without generating local consensus keys;
  - Byzantine prevote equivocation/evidence regression and HND four-replica evidence integration;
  - signer protocol conformance, process isolation, same-host single-writer locking, authenticated Noise peer rejection, vote withholding, anti-double-sign persistence, and crash/recovery probes;
  - single-node ABCI integration;
  - four-validator Genesis/identity preflight and private network integration;
  - four external remote signers with no local consensus keys;
  - four-validator authenticated Noise remote-signer integration/recovery and four independent authenticated Noise signers without local consensus keys.

## Evidence boundary

This is commit-scoped CI evidence for the exact SHA above. It demonstrates successful disposable CI integration tests; it does **not** establish production deployment, real-world operator/custodian independence, a durable external anti-rollback trust anchor, a complete CometBFT TOML field/default inventory or production profile digest, atomic activation/startup enforcement, witnessed catastrophic-key-loss recovery, or an independent security audit.

PR #11 remains unmerged. Station 2 remains open.