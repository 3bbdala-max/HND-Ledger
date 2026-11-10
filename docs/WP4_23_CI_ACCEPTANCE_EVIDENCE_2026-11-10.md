# WP4.23 — PR #8 CI Acceptance Evidence

**Date:** 2026-11-10  
**Workflow:** HND v0.2 reference tests  
**Run ID:** 42753028814  
**Run attempt:** 1  
**Verified head SHA:** `4b4b6a9fe8c7d60df2c98b9b9872e19ebb79c6b0`  
**PR:** #8 — VSP payload, governance signature and Genesis verifier  
**Disposition:** CI run completed successfully on the exact SHA above. This is implementation/test evidence, not station completion or production approval.

## Workflow result

The GitHub Actions run reports `status=completed` and `conclusion=success`. Both jobs completed successfully on the same head SHA:

- `hnd-v02-tests`: success.
- `cometbft-single-node-smoke`: success.

## HND v0.2 test job

Completed steps include:

1. Install hash-verified isolated JCS spike dependency.
2. Install integrity-locked independent JavaScript JCS comparator.
3. Generate pinned CometBFT v0.40.0 Python bindings.
4. Run isolated VSP JCS cross-language compatibility spike.
5. Run strict VSP envelope and digest boundary tests.
6. Run VSP payload, signature and Genesis verifier tests.
7. Run isolated v0.2 tests.

All listed steps and job completion reported `success`.

## CometBFT integration job

Completed steps include:

- Build pinned CometBFT v0.40.0 binary.
- Reject missing remote signer without generating local consensus keys.
- Byzantine prevote equivocation/evidence regression and four-replica P2P evidence integration.
- Validator signer anti-double-sign smoke test and remote-signer protocol probes.
- Authenticated Noise remote-signer integration and unauthorized-peer rejection.
- Remote-signer vote-withholding probe.
- Anti-double-sign persistence across restart.
- Crash-after-state-save recovery probe.
- Reject missing or substituted anti-double-sign state in recovery mode.
- Single-node ABCI integration.
- Four-validator Genesis and identity preflight.
- Private four-validator network integration.
- Four-validator external remote-signer integration and outage recovery.
- Four independent external signers with no local consensus keys.
- Noise signer lock-contention, recovery-state, and four-validator integration probes.

All listed steps and job completion reported `success`.

## Evidence boundary

This run proves that the configured CI cases passed on commit `4b4b6a9fe8c7d60df2c98b9b9872e19ebb79c6b0`. It does not prove:

- a complete CometBFT TOML parser/normalizer or independently computed full runtime-profile digest;
- trust-manifest bootstrap, enrollment, rotation, revocation, or durable trust-root custody;
- durable independent anti-rollback anchors and crash-safe activation;
- unanimous configured-operator acknowledgement and an enforced activation/startup gate;
- OS/service-level prevention of direct-binary or signer bypass;
- real-world operator independence, witnessed catastrophic-key-loss recovery, or independent security review.

No production keys, live validator identities, or independent operator attestations are established by this CI record.

## Next engineering gates

1. Implement and test a version-pinned, strict CometBFT v0.40.0 configuration parser and typed profile normalizer. Defaults must come from the pinned source, and shared consensus-service policy must remain distinct from per-node deployment policy.
2. Implement trust-manifest parsing and bootstrap/enrollment verification against the ratified governance-key derivation and signature policy.
3. Implement separate durable monotonic records for trust-manifest sequence and VSP profile sequence, including crash/tamper/restore negative tests.
4. Implement all-operator acknowledgement collection and fail-closed atomic activation.
5. Integrate an unavoidable pre-start check and signer-side enforcement; demonstrate bypass denial in the actual deployment environment.
6. Obtain real operator-independence evidence, conduct a witnessed recovery exercise, and complete independent security review.

**Conclusion:** PR #8's previously pending CometBFT job is now confirmed successful. Station 2 remains open until every required gate above is implemented and evidenced.
