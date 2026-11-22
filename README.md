# HND-Ledger

HND-Ledger is an experimental educational project for studying a signed transaction ledger, deterministic state transitions, block chaining, and consensus design.

## Current status

- **Archived baseline:** version 0.1 is preserved in the project archive.
- **Version 0.2 working branch:** `work/v02-canonical-transaction-core`.
- **Implemented on this branch:** restricted deterministic CBOR encoding and strict transaction decoding; domain-separated transaction identifiers and Ed25519 signatures; deterministic genesis, state roots, transaction Merkle roots, canonical block headers, and local block execution with independent replay verification.
- **Test evidence:** golden byte/hash vectors and unit tests are committed. A passing CI result for the current branch has not yet been independently confirmed.
- **Not yet implemented:** durable multi-block chain storage and validation, backup/restore, distributed consensus, peer networking, mempool policy, or production key management.
- **Production status:** not production-ready; no public network, exchange, or investment use is authorized or implied.

The version 0.1 archive reports 1,212 core tests, 3,000 sequential transfer operations, and a displayed total supply of 1,000,000 units. These are archive-reported results and have not been independently reproduced from the current repository.

## Protocol baseline

Version 0.2 uses an account/balance model, Ed25519 signatures, SHA-256 with domain separation, deterministic CBOR arrays, a 32-byte chain ID, integer smallest units, and a 1,000,000 HND maximum-supply design target. The local chain ID is test-only.

See:
- [Strict transaction decoder profile](docs/V02_STRICT_DECODER.md)
- [Deterministic genesis and block-header profile](docs/V02_GENESIS_AND_BLOCKS.md)
- [Block execution and independent replay verification](docs/V02_BLOCK_EXECUTION.md)
- [Source provenance and ownership evidence](docs/PROVENANCE_AND_OWNERSHIP.md)
- [Architecture and implementation gates](docs/ARCHITECTURE.md)
- [Version 0.2 protocol baseline](docs/PROTOCOL.md)
- [Cryptographic and canonical encoding profile](docs/CRYPTO_FORMAT.md)
- [Golden transaction vectors](docs/V02_GOLDEN_VECTORS.md)
- [Implementation gap audit](docs/IMPLEMENTATION_GAP_AUDIT_2026-11-21.md)

## Reproducing the current test profile

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m hnd_ledger.vector_check
python scripts/create_provenance_manifest.py --output evidence/SHA256-MANIFEST.json
python scripts/create_provenance_manifest.py --verify evidence/SHA256-MANIFEST.json
```

The vector checker must print `"passed": true`; the manifest verifier must print `MANIFEST_OK`. Record the exact commit SHA and environment with any independent test report.

## Development principles

1. Preserve the version 0.1 archive and its evidence.
2. Do not claim a feature is implemented until its source and tests are committed and reproducibly run.
3. Freeze canonical serialization and protocol rules before implementing cryptographic signing or hashing.
4. Use established cryptographic libraries rather than custom cryptography.
5. Keep private keys out of the ledger, source control, and logs.
6. Treat consensus and networking as separate design gates.
7. Require independent security and legal review before any public deployment or token-related activity.

## Scope

This repository is an educational engineering project. It is not a production blockchain, investment product, exchange, or authorization to issue or trade a cryptocurrency.
