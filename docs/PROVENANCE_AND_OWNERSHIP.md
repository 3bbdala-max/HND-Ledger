# HND-Ledger source provenance and ownership evidence

This guide separates three different claims that must not be confused:

1. **Integrity:** the files examined are byte-for-byte the same files identified by a manifest.
2. **Provenance:** a particular source revision existed in a particular repository history at a recorded time.
3. **Legal ownership:** a person or entity owns the relevant copyright, patent rights, or other intellectual property.

A SHA-256 manifest supports integrity checking. Git commit history and repository records support provenance. Neither alone proves legal ownership or inventorship.

## Reproducible source manifest

From a clean clone, run:

```bash
python scripts/create_provenance_manifest.py --output evidence/SHA256-MANIFEST.json
python scripts/create_provenance_manifest.py --verify evidence/SHA256-MANIFEST.json
```

The tool records the checked-out commit SHA, Git tree SHA, parent commits, commit timestamp, and SHA-256 plus byte length for every tracked file. It excludes the manifest output itself so the same checkout can be checked again.

Expected successful verification output:

`MANIFEST_OK`

A mismatch returns a non-zero exit status. Reviewers should preserve the manifest alongside the exact source archive and record the commit SHA they examined.

## Independent review procedure

1. Clone the repository and check out the exact commit under review.
2. Confirm the commit SHA and tree SHA in the manifest.
3. Install the dependencies from `requirements.txt`.
4. Run the full suite: `python -m pytest -q`.
5. Reproduce the fixed protocol vectors: `python -m hnd_ledger.vector_check`.
6. Generate and verify a fresh source manifest.
7. Record the operating system, Python version, dependency versions, commit SHA, test output, and reviewer identity in a signed review report.
8. Inspect the code and protocol documents independently; passing tests are not a substitute for a security review.

## Strengthening evidence over time

- Use signed Git commits or signed release tags controlled by the rights holder.
- Preserve immutable source archives and their SHA-256 hashes.
- Obtain an independent trusted timestamp for the signed manifest or release archive.
- Keep dated design notes, protocol drafts, diagrams, test vectors, and implementation records.
- Record contributors and obtain written agreements defining assignment or licensing of their contributions.
- Search prior art and obtain qualified IP/legal advice before making patentability, exclusivity, or ownership claims.

## Current evidence limitations

The repository's commit author fields are metadata and can be set by whoever creates a commit. A repository account, commit timestamp, or unsigned hash does not independently establish who authored the work or who legally owns it.

The current project has not yet received an independent signed engineering review, trusted timestamp attestation, contributor assignment audit, or legal opinion. Do not describe this repository alone as a registered patent, legally protected monopoly, or conclusive proof of ownership.
