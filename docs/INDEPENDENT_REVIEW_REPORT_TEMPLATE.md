# HND-Ledger independent verification report

**Purpose:** Record a reproducible, independent examination of one immutable HND-Ledger source revision. Complete this report only after running the commands below. Do not mark a check as passed from source inspection alone.

## 1. Review identity and scope

- Reviewer name / organization:
- Reviewer contact:
- Review date (UTC):
- Relationship to project / conflicts of interest:
- Review scope: protocol / implementation / tests / security / provenance / other:
- Explicit exclusions:

## 2. Immutable source identification

- Repository URL:
- Branch or tag used only for navigation:
- Exact commit SHA checked out:
- Git tree SHA:
- Parent commit(s):
- Source archive SHA-256:
- Manifest format:
- Manifest SHA-256:
- Git object format:
- Was the checkout detached at the exact commit? yes / no
- Was the working tree clean before running checks? yes / no

Commands:

```bash
git checkout --detach <exact-commit-sha>
git rev-parse HEAD
git rev-parse HEAD^{tree}
git status --porcelain
```

## 3. Environment

- Operating system and version:
- CPU architecture:
- Python version:
- Git version:
- Dependency installation command:
- Installed dependency versions:
- Network access / package index used:
- Any environment modifications:

Commands:

```bash
python --version
git --version
python -m pip install -r requirements.txt
python -m pip freeze
```

## 4. Reproduction results

Record the exact command, exit code, stdout, stderr, and execution time. Attach unedited logs.

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Unit and integration tests | `python -m pytest -q` | | |
| Golden vectors | `python -m hnd_ledger.vector_check` | | |
| Source manifest generation | `python scripts/create_provenance_manifest.py --output evidence/SHA256-MANIFEST.json` | | |
| Source manifest verification | `python scripts/create_provenance_manifest.py --verify evidence/SHA256-MANIFEST.json` | | |

- Test count collected:
- Passed:
- Failed:
- Skipped:
- Warnings:
- Any test not executed and why:

## 5. Independent technical findings

For every finding, include severity, affected file and line, exact reproduction steps, observed result, expected result, and whether the reviewer independently confirmed it.

| ID | Severity | Component | Finding | Reproduction evidence | Status |
|---|---|---|---|---|---|
| | | | | | |

Review at minimum:

- Canonical encoding and strict decoding.
- Ed25519 key and signature handling.
- Transaction validation, replay protection, and nonce handling.
- Genesis, state root, Merkle root, and block hash derivation.
- SQLite atomic append, replay, corruption detection, and process interruption recovery.
- Error handling, resource limits, and malformed input behavior.
- Gaps between normative protocol text and executable behavior.

## 6. Provenance and rights evidence reviewed

This section records evidence; it is not a legal opinion.

- Manifest verified against the exact commit:
- Signed commit or signed release tag and signer key fingerprint:
- Trusted timestamp receipt and timestamp authority:
- Immutable source archive and digest:
- Contributor list and contribution dates:
- Written assignment / license agreements inspected:
- Third-party code and dependency license review:
- Prior-art search performed and scope:
- Evidence unavailable or not independently authenticated:

A Git account, commit author field, commit timestamp, repository history, or SHA-256 digest alone does not prove legal ownership, inventorship, or a trusted creation time. Record those claims as unverified unless separate evidence supports them.

## 7. Overall conclusion

Select one:

- [ ] Reproduction successful within the stated scope.
- [ ] Reproduction partially successful; limitations listed.
- [ ] Reproduction failed.
- [ ] Insufficient evidence to conclude.

- Critical unresolved issues:
- Security limitations:
- Protocol limitations:
- Operational limitations:
- Recommended next actions:

## 8. Reviewer attestation

I confirm that this report describes checks I personally performed, that attached logs are unedited to the best of my knowledge, and that conclusions are limited to the exact commit and environment identified above.

- Reviewer name:
- Date:
- Signature method:
- Signature / verification reference:
