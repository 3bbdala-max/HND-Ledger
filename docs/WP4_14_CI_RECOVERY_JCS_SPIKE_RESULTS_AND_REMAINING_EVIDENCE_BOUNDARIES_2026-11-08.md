# WP4.14 — CI Recovery, JCS Spike Results, and Remaining Evidence Boundaries

**Inspection date:** 2026-11-08  
**Branch:** `phase-0.2-planning`  
**Inspected HEAD:** `372157f6ef06a224dc528a940530b1b4b7ae89bf`  
**Run ID:** `42415836225`  
**Review type:** Commit-bound GitHub Actions inspection and static test-source review  
**Change type:** Documentation only  
**Disposition:** CI recovery confirmed; JCS spike is successful but remains a compatibility experiment, not production adoption or VSP approval

## 1. Current CI result on exact branch HEAD

The branch currently points to commit `372157f6ef06a224dc528a940530b1b4b7ae89bf`. Workflow run `42415836225` references that exact SHA and completed with overall conclusion `success`.

Both jobs completed successfully:

- `hnd-v02-tests`: success.
- `cometbft-single-node-smoke`: success.

The HND job includes the isolated JCS dependency installation, the independent JavaScript comparator installation, the JCS compatibility test module, and the explicitly enumerated v0.2 test modules. The enumerated test command now includes both `tests.test_v02_anti_rollback_reference` and `tests.test_v02_recovery_controls`, which were absent from the earlier workflow snapshot documented in the CI coverage-gap audit.

The CometBFT job completed all listed steps, including four-replica P2P equivocation evidence integration, validator signer anti-double-sign smoke, authenticated Noise remote-signer probes, restart/recovery probes, four-validator network integration, and four independent external Noise signers.

This closes the previously documented CI run blocker for the exact current commit. It does not retroactively change the failure result of run `42338348291` on its older SHA.

## 2. JCS compatibility spike: what passed

The workflow ran `tests.test_vsp_jcs_compatibility_spike` successfully. Static inspection of that module shows five test methods:

1. A Python candidate canonical-byte assertion covering property sorting, decimal normalization, negative zero, and a small exponent.
2. UTF-16 property-order behavior for U+E000 versus U+10000.
3. Duplicate-member rejection at root and nested object levels in the Python strict parser helper.
4. Rejection of UTF-8 BOM, invalid UTF-8, NaN, Infinity, and an unpaired surrogate in the Python strict parser helper.
5. Cross-language canonical-output equality for five representative JSON inputs using Python `rfc8785==0.1.4` and JavaScript `canonicalize@2.1.0`.

The Python candidate dependency is isolated in `requirements-vsp-jcs-spike.txt` and pinned with a SHA-256 package hash. The JavaScript comparator is isolated under `tools/vsp-jcs-node`, pinned to version 2.1.0 with a lockfile integrity value; the workflow independently checks the published npm integrity string before `npm ci`.

The cross-language test compares canonical output strings. It does not yet compare a separately published set of payload digest/signature golden vectors.

## 3. Important limits: do not overstate the result

The successful spike does **not** establish that a production VSP parser or verifier exists.

- The strict byte parser in the test module is a test helper, not a production parser.
- The JavaScript comparator uses `JSON.parse`; duplicate-key rejection is tested in the Python helper only, not as a symmetric strict-parser contract across both runtimes.
- The five cross-language inputs are representative samples, not the complete RFC 8785 Appendix B number-vector suite.
- No VSP envelope schema validation, trust-manifest validation, signature verification, activation/rollback enforcement, or CometBFT startup gate is exercised by this spike.
- No production dependency adoption is implied. The candidate Python dependency remains isolated from `requirements.txt`.
- No protocol golden-vector set or approved VSP version is established by this run.

The spike therefore supports the narrow conclusion: the two selected JCS implementations produced matching canonical output for the tested inputs under the CI environment.

## 4. Separation from existing HND serialization

The test module explicitly avoids importing or replacing HND `canonical_json`. Keep this boundary. The existing HND transaction/Genesis serialization and hash/signature semantics must not be silently migrated to JCS as a side effect of the VSP experiment.

Any future VSP implementation must use its own byte-oriented strict input boundary and must not reinterpret existing HND transaction or Genesis bytes.

## 5. CI coverage update

The current workflow's explicit v0.2 test invocation now includes:

- `tests.test_v02_anti_rollback_reference`
- `tests.test_v02_recovery_controls`

Their successful execution is part of the current HND job's result. However, the anti-rollback module is a synthetic reference-model suite; its success is not proof that production CometBFT signing is bound to a durable independent anchor. The recovery-controls suite is not a production backup/restore drill.

Likewise, successful signer and four-validator smoke steps establish that the tested scenarios completed in this CI environment. They do not by themselves establish production key custody, independent infrastructure, disaster recovery, external security review, or operational readiness.

## 6. Next acceptance gates

1. Expand JCS validation to the complete applicable RFC 8785 Appendix B numeric vectors and additional Unicode/property-order edge cases.
2. Add strict duplicate-key and invalid-input parity tests for the actual parser boundary intended for VSP; do not rely on the JavaScript comparator's permissive `JSON.parse` as a strict-input validator.
3. Generate independently cross-checked VSP payload bytes, domain-separated digests, and Ed25519 signature golden vectors only after the schema and trust model are reviewed.
4. Implement and test a production VSP parser/verifier as an unavoidable pre-start gate for both the HND application and CometBFT launcher.
5. Verify signer anti-double-sign state and recovery against the actual production persistence/anchor design, not only CI probes or synthetic models.
6. Preserve commit-specific CI evidence and retain logs/artifacts sufficient for independent reproduction.

No source code, test, workflow, dependency, key, validator configuration, or protocol approval was changed by this report. No CI rerun was triggered. Public launch, production signing, token issuance, and production-readiness approval remain blocked pending the gates above.
