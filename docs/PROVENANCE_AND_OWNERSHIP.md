# HND-Ledger source provenance and ownership evidence

This guide separates three different claims that must not be confused:

1. **Integrity:** the files examined are byte-for-byte the same files identified by a manifest.
2. **Provenance:** a particular source revision existed in a particular repository history at a recorded time.
3. **Legal ownership:** a person or entity owns the relevant copyright, patent rights, or other intellectual property.

A SHA-256 manifest supports integrity checking. Git commit history and repository records support provenance. Neither alone proves legal ownership or inventorship.

## Reproducible source manifest

From a clean clone, check out the exact commit under review and run:

\`\`\`bash
git checkout --detach <candidate-commit-sha>
git status --porcelain
python scripts/create_provenance_manifest.py --output evidence/SHA256-MANIFEST.json
python scripts/create_provenance_manifest.py --verify evidence/SHA256-MANIFEST.json
\`\`\`

The V2 tool reads file bytes from Git blob objects reachable from \`HEAD\`, not from the mutable working tree. It records the commit SHA, tree SHA, parent commits, commit timestamp, Git object format, and for each committed file its path, mode, Git object ID, byte length, and SHA-256. Git submodule entries are recorded as gitlinks with their commit ID; they are not misrepresented as ordinary file blobs.

Before generating or verifying, the tool requires tracked files to match \`HEAD\` and rejects unexpected untracked files. The one permitted in-repository manifest path is \`evidence/SHA256-MANIFEST.json\`; it is excluded from its own file list to avoid recursive self-hashing. Ignored files are outside this check and must be controlled separately by the review environment.

Expected successful verification output:

\`MANIFEST_OK\`

A mismatch returns a non-zero exit status. An invalid or dirty checkout returns exit status 2 with a diagnostic. Preserve the manifest alongside the exact source archive and record the commit SHA independently.

The manifest proves which Git objects were hashed. It does not authenticate the person who created the commit, prove a trusted creation time, or establish legal title.

## Independent review procedure

1. Clone the repository and check out the exact commit under review.
2. Confirm the commit SHA and tree SHA in the manifest.
3. Install the dependencies from \`requirements.txt\`.
4. Run the full suite: \`python -m pytest -q\`.
5. Reproduce the fixed protocol vectors: \`python -m hnd_ledger.vector_check\`.
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
