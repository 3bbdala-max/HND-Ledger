# WP4.18 — Supply-Chain, CI Provenance, and Release Governance Delta Review

**Inspection date:** 2026-11-08  
**Branch:** `phase-0.2-planning`  
**Inspected HEAD:** `fb261f02f4c421f4cff0c8e900d70447e242f42e`  
**Review type:** Repository metadata, dependency, workflow, and release-evidence review  
**Change type:** Documentation only  
**Disposition:** Several previously identified CI pinning and test-matrix gaps have been corrected; branch enforcement, complete dependency locking, and release provenance remain open.

## 1. Why this update exists

The earlier WP4.14 supply-chain and release-governance reports were written on 2026-11-05. They are historical snapshots, not authoritative descriptions of the current branch. This report records the verified changes since those snapshots and the controls that remain absent or unverified.

This review does not amend those historical reports or imply that every earlier recommendation has been completed.

## 2. Verified improvements since WP4.14

### 2.1 Python dependency pins

Current `requirements.txt` contains exact direct pins:

- `cryptography==50.0.2`
- `grpcio==1.76.0`
- `grpcio-tools==1.76.0`
- `protobuf==6.33.5`

This supersedes the earlier observation that `cryptography` used a broad lower-bound range.

The isolated JCS spike also has its own hash-verified Python requirement file and a locked JavaScript package manifest/lockfile. The workflow checks the expected npm package integrity before running `npm ci`.

**Still not established:** `requirements.txt` does not specify hashes and is not a complete transitive lock. Exact direct pins alone do not prove that every transitive wheel/sdist used by a production build is fixed to an approved digest.

### 2.2 CI action and CometBFT source pinning

Current `.github/workflows/hnd-v02-tests.yml` pins the referenced GitHub Actions by full commit SHA, with readable version comments. The workflow builds CometBFT after fetching the explicit source commit:

`0880b4d378f347ab16e54ec677ff50d803f37d62`

The workflow verifies that the checked-out CometBFT source HEAD equals this SHA. Go is set to `1.25.0`.

The Python binding generation script also fetches and verifies explicit commits for CometBFT and gogoproto. These are materially stronger source-selection controls than movable version tags.

The inspected HND repository tree does not contain its own `go.mod` or `go.sum`; the integration build occurs from the separately fetched pinned CometBFT source tree. This review did not independently audit every transitive Go module or the remote module proxy/cache used by that build.

### 2.3 Dependency update automation

`.github/dependabot.yml` is now present and schedules weekly updates for the pip and GitHub Actions ecosystems.

Dependabot update PR generation is useful maintenance automation. It does not, by itself, establish that all dependencies are vulnerability-scanned, that alerts are enabled, that findings are triaged within a defined SLA, or that an approved dependency graph is hash-locked.

### 2.4 Current CI test matrix

The current workflow's explicit Python test command includes both:

- `tests.test_v02_anti_rollback_reference`
- `tests.test_v02_recovery_controls`

This corrects the older WP4.14 CI audit observation that those two modules were omitted from the explicit command. The current workflow now lists them; their execution result must still be read from the exact run being reported.

## 3. Remaining software supply-chain controls

The recursive branch tree and inspected workflow do not demonstrate:

- a complete hash-locked Python dependency set for all direct and transitive dependencies;
- an SBOM generated for each candidate artifact and published with that artifact;
- a defined dependency vulnerability scan, triage owner, severity policy, and remediation SLA;
- a build provenance attestation binding source commit, dependency graph, toolchain, builder identity, and produced artifact digest;
- a reproducible-build comparison independently performed by a second builder;
- signed immutable release artifacts/tags with a documented verification procedure;
- a distinct production release workflow with immutable artifact promotion and authorization gates.

These are evidence gaps in the inspected repository workflow, not a claim that no external organizational controls exist.

## 4. Release governance and branch enforcement

The GitHub branch metadata for `phase-0.2-planning` reports:

- `protected: false`;
- protection `enabled: false`;
- required-status-check enforcement `off`;
- no required check contexts returned.

The repository rulesets query returned an empty list. The queried GitHub Releases collection also returned an empty list.

The current commit `fb261f02f4c421f4cff0c8e900d70447e242f42e` is reported by GitHub as unsigned (`verified: false`, reason `unsigned`).

Accordingly, the inspected branch is not protected by the reported branch-protection metadata and does not enforce required CI checks. There is no returned GitHub Release in the queried collection. These observations do not rule out external release storage or separate controls outside the queried repository settings.

The workflow is configured for pushes to `phase-0.2-planning` and pull requests targeting `main`; it does not configure the planning branch itself as a pull-request base branch.

## 5. Exact-commit CI status at inspection

Run `42420946912` is tied to the exact reviewed HEAD `fb261f02f4c421f4cff0c8e900d70447e242f42e`.

At inspection:

- `hnd-v02-tests`: completed successfully. Its steps include dependency installation, isolated JCS compatibility spike, and the explicit v0.2 Python test command.
- `cometbft-single-node-smoke`: still in progress. The CometBFT build, remote-only CLI negative test, Byzantine evidence tests, signer conformance/process tests, same-host single-writer check, authenticated Noise peer rejection, vote-withholding probe, persistence/restart probes, single-node ABCI smoke, four-validator identity preflight/network smoke, and four-validator external-signer outage/recovery steps were completed successfully.
- The step `Run four independent authenticated Noise signers with no local consensus keys` was in progress at inspection; subsequent steps had not yet completed.

The overall workflow is therefore **in progress, not a completed green run** at this inspection point.

Run link: https://github.com/3bbdala-max/HND-Ledger/actions/runs/42420946912

## 6. Required acceptance gates before release

| Gate | Required evidence |
|---|---|
| Python dependencies | Full transitive lock, approved hashes, repeatable installation |
| Go dependency graph | Audited module graph and checksum/proxy policy for the pinned CometBFT source build |
| Vulnerability management | Automated scan, triage owner, policy, and remediation SLA |
| SBOM | Per-artifact SBOM, stored and published with the candidate |
| Provenance | Verifiable attestation for source, build inputs, toolchain, builder, and artifact digest |
| Reproducibility | Independent second build with matching digest or documented variance policy |
| Release signing | Signed immutable tag and artifact, documented verification |
| Branch governance | Protected release branch, required reviews, required checks, stale approval policy, restricted admin bypass |
| PR CI | Explicit decision and tested trigger for PRs targeting the planning/release branch |
| Release pipeline | Separate approval-controlled artifact promotion/deployment workflow |
| Final approval | Independent security sign-off tied to the exact release commit and artifact digest |

## 7. Decisions and boundary

1. Retain the current immutable SHA pins for GitHub Actions, CometBFT, and gogoproto; do not regress to floating tags.
2. Retain Dependabot, but do not treat update automation as vulnerability clearance.
3. Treat direct Python pins as improved but incomplete until a fully hash-locked transitive set is produced and reviewed.
4. Do not publish or promote a production release from the unprotected planning branch.
5. Require branch/release governance, SBOM, provenance, artifact signing, and independent approval before production release.

This report is documentation only. It changes no workflow, source, test, dependency, branch setting, release, tag, key, Genesis, or deployment configuration. It does not rerun CI or claim a vulnerability scan, reproducible build, signed artifact, or production approval.
