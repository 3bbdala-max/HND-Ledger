# HND v0.2 — software supply-chain and dependency pinning audit

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Scope:** repository tree, Python requirements, GitHub Actions workflow, observed CI runs  
**Change policy:** documentation only; no source, test, workflow, or dependency files changed

## 1. Executive result

**Supply-chain assurance is incomplete; production release is not approved.**

The repository has a single `requirements.txt`. Three direct Python dependencies are exact-pinned, but `cryptography` is declared with a lower-bound range (`>=41.0`). No Python lockfile, hash-locked requirements file, Go module manifest/checksum, Dependabot configuration, SBOM workflow, or build-provenance/attestation workflow was found in the recursively queried branch tree.

The GitHub Actions workflow uses major-version action tags (`actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-go@v6`) rather than immutable commit SHAs. It clones CometBFT using the `v0.40.0` tag and builds it at workflow time; the workflow does not pin the tag to a verified source commit SHA.

## 2. Dependency evidence

Current `requirements.txt` content:

- `cryptography>=41.0` — range, not exact-pinned.
- `grpcio==1.76.0` — exact direct pin.
- `grpcio-tools==1.76.0` — exact direct pin.
- `protobuf==6.33.5` — exact direct pin.

Important limitations:
- Exact direct pins do not lock the complete transitive dependency graph.
- No hashes are specified, so pip is not enforcing artifact hashes from this file.
- The unbounded upper range for cryptography permits resolver changes over time.
- A repository-level dependency manifest is not a vulnerability scan; this review did not establish whether any resolved package version is currently vulnerable.

The recursive branch tree did not contain `requirements-lock.txt`, `requirements-dev.txt`, `pyproject.toml`, `Pipfile.lock`, `poetry.lock`, `go.mod`, or `go.sum`.

## 3. CI and external source pinning

Workflow `.github/workflows/hnd-v02-tests.yml`:
- Uses `actions/checkout@v4`, `actions/setup-python@v5`, and `actions/setup-go@v6`; these are movable major-version tags, not immutable action commit references.
- Installs dependencies with `python -m pip install -r requirements.txt`.
- Clones CometBFT with `git clone --depth 1 --branch v0.40.0` and builds from that tag; no explicit expected commit SHA is checked.
- Uses Go `1.25.0` exactly through setup-go.

This is adequate evidence that CI builds against the intended named CometBFT release tag, but not an immutable source-integrity pin for a high-assurance release pipeline.

## 4. Automation and artifact controls

The queried repository tree contains only `.github/workflows/hnd-v02-tests.yml` under `.github/workflows/`. No Dependabot configuration, dedicated CodeQL/security scan workflow, SBOM generation, artifact signing, provenance attestation, or release publication workflow was found in that tree.

This does not rule out external organization-level controls or manual processes; those were outside the accessible evidence.

## 5. Latest CI evidence

At inspection:
- Run `41978657337`, commit `3faf28cd968c3251c9399ad2eb0059f0256e5382`: both `hnd-v02-tests` and `cometbft-single-node-smoke` completed successfully.
- Run `41978862777`, commit `b13900a30112d494288d7006a6d74a121e0ade53`: both jobs completed successfully.

These successful runs establish that the configured jobs passed for those commits. They do not establish dependency vulnerability clearance, reproducible builds, signed artifacts, provenance, or production key custody.

## 6. Recommended remediation (not applied)

1. Replace the broad cryptography range with a reviewed exact version and maintain a fully resolved, hash-locked Python dependency set.
2. Add automated dependency update and vulnerability review (for example Dependabot plus an explicit security scanning policy).
3. Pin GitHub Actions to verified full commit SHAs, retaining readable version comments.
4. Pin CometBFT source to an audited commit SHA and verify the checked-out commit before building.
5. Generate and publish an SBOM for each release candidate; scan direct and transitive dependencies.
6. Produce build provenance/attestations and sign immutable release artifacts/tags.
7. Record toolchain versions and build inputs; define reproducibility criteria and independently verify a release build.

## 7. Disposition

**Status: PARTIAL / NOT RELEASE-READY.**

No dependency was changed, no workflow was modified, no SBOM or release artifact was generated, and no vulnerability scan was claimed. This is a repository-evidence audit, not a full software composition analysis or security certification.
