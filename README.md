# HND-Ledger

HND-Ledger is an experimental educational project for studying a signed transaction ledger, deterministic state transitions, block chaining, and consensus design.

## Current status

- **Archived baseline:** version 0.1 is preserved in the project archive.
- **Version 0.2 working branch:** `work/v02-canonical-transaction-core`.
- **Implemented on this branch:** restricted deterministic CBOR encoding and strict transaction decoding for v0.2; domain-separated account identifiers, transaction signing messages, and complete signed-transaction IDs; Ed25519 signature verification; an in-memory account ledger enforcing chain ID, amount, nonce, self-transfer, replay, and supply-cap rules.
- **Test evidence:** golden byte/hash vectors and unit tests are committed. A passing CI result for the current branch has not yet been independently confirmed.
- **Not yet implemented:** genesis/block execution, durable storage, backup/restore, distributed consensus, peer networking, or production key management.
- **Production status:** not production-ready; no public network, exchange, or investment use is authorized or implied.

The version 0.1 archive reports 1,212 core tests, 3,000 sequential transfer operations, and a displayed total supply of 1,000,000 units. These are archive-reported results and have not been independently reproduced from the current repository.

## Protocol baseline

Version 0.2 uses an account/balance model, Ed25519 signatures, SHA-256 with domain separation, deterministic CBOR arrays, a 32-byte chain ID, integer smallest units, and a 1,000,000 HND maximum-supply design target. The local chain ID is test-only.

See:
- [Strict transaction decoder profile](docs/V02_STRICT_DECODER.md)
- [Architecture and implementation gates](docs/ARCHITECTURE.md)
- [Version 0.2 protocol baseline](docs/PROTOCOL.md)
- [Cryptographic and canonical encoding profile](docs/CRYPTO_FORMAT.md)
- [Golden transaction vectors](docs/V02_GOLDEN_VECTORS.md)
- [Implementation gap audit](docs/IMPLEMENTATION_GAP_AUDIT_2026-11-21.md)

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
