# HND-Ledger v0.2 — Implementation Gap Audit

**Audit date:** 2026-11-21  
**Scope:** Read-only inspection of the current `main` tree and its tracked protocol, implementation, tests, and CI configuration.  
**Status:** Findings recorded; no runtime test execution or independent security review is claimed.

## 1. Repository snapshot

The inspected default branch is `main`. The repository contains protocol and architecture documents, Python package files under `hnd_ledger/`, a test file under `tests/`, a dependency manifest, and a GitHub Actions workflow. This contradicts older statements in some documentation that the repository contains no executable implementation or test suite.

## 2. Critical specification-to-code drift

The current implementation must not yet be treated as a conforming implementation of the v0.2 protocol documents.

| Area | Protocol / design baseline | Current code observed | Required resolution |
|---|---|---|---|
| Serialization | RFC 8949 deterministic CBOR, fixed positional arrays | JSON with sorted keys for transaction signing bytes | Implement deterministic CBOR or formally revise and version the protocol before compatibility claims |
| Account identifier | SHA-256 over `HND-ACCOUNT-V2\0` plus public key | SHA-256 over public key only | Align code and golden vectors with the normative domain-separated rule |
| Transaction signature | Domain-separated signing bytes | Raw JSON payload bytes without the specified HND domain prefix | Implement exact domain separation and test vectors |
| Transaction ID | Hash of domain prefix plus deterministic CBOR of complete signed transaction | SHA-256 of unsigned JSON signing payload | Implement the specified ID derivation |
| Network identifier | Immutable 32-byte chain ID | Arbitrary non-empty string | Enforce exact byte length and protocol-defined local chain ID |
| Self-transfer | Rejected by v0.2 protocol rules | Accepted; balance unchanged and nonce increments | Align implementation and tests with the selected rule |
| Nonce bounds | Unsigned 64-bit sequence | Non-negative Python integer without upper bound | Enforce 0..2^64-1 and reject increment overflow |
| Block chain | Versioned block header, parent linkage, transaction IDs, state commitment | No block model or block validation found in inspected implementation | Implement block format only after transaction/state encoding is frozen |
| Persistence/recovery | Atomic persistence and recovery are required gates | Current ledger is explicitly in-memory | Implement durable atomic storage and recovery tests |

## 3. Evidence limits

- The tracked tests cover basic in-memory transaction behavior; their presence does not establish that they pass.
- The workflow defines a pytest job, but no workflow run was executed as part of this audit.
- The version 0.1 archive's reported test and transfer counts were not independently reproduced.
- No distributed consensus, peer networking, multi-operator validator deployment, production readiness, or independent audit is established by this inspection.

## 4. Decision

Do not build backup/restore as if the present in-memory state were already a stable, protocol-conforming ledger. Doing so would preserve and potentially legitimize inconsistent state semantics.

The immediate prerequisite is a controlled protocol-conformance repair:
1. Freeze the byte-level v0.2 transaction, account, state, block, and genesis encodings.
2. Add golden vectors for account IDs, signing payloads, signatures, transaction IDs, state commitments, and genesis/block IDs.
3. Bring implementation and tests into exact agreement with the frozen specification.
4. Run the test suite in clean CI and record the exact commit SHA and workflow result.
5. Only then implement WP5.851–855 for durable backups, tamper detection, restore validation, consistency checks, and recovery acceptance gates.

## 5. Next work package

**WP5.851–855 remains queued, not completed:**
- WP5.851: backup format and versioned manifest;
- WP5.852: integrity/authenticity protection and anti-rollback metadata;
- WP5.853: restore into an isolated staging state;
- WP5.854: cross-check restored chain, state commitment, and trusted checkpoints;
- WP5.855: fail-closed recovery gate and reproducible corruption/interruption tests.

A backup is not a source of truth by itself. A restore must be rejected if its chain identity, block linkage, state commitment, trusted checkpoint, or anti-rollback condition fails.
