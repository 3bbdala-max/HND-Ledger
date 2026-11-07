# HND-Ledger

HND-Ledger is an experimental educational project for studying a signed transaction ledger, deterministic state transitions, block chaining, and consensus design.

## Current status

- **Archived baseline:** version 0.1, described in the project's master archive.
- **Current repository:** version 0.2 design documentation is being established; executable implementation and reproducible CI tests are not yet present.
- **Current design baseline:** account/balance model, Ed25519 signatures, SHA-256, deterministic CBOR, integer smallest units, and a 1,000,000 HND maximum-supply design target.
- **Next implementation target:** a deterministic local ledger. Distributed consensus and networking remain separate, gated work.
- **Production status:** not production-ready; no public network, exchange, or investment use is authorized or implied.

The version 0.1 archive reports 1,212 core tests, 3,000 sequential transfer operations, and a displayed total supply of 1,000,000 units. These are archive-reported results and have not been independently reproduced from the current GitHub repository.

## Project documents

- [Architecture and implementation gates](docs/ARCHITECTURE.md)
- [Version 0.2 protocol baseline](docs/PROTOCOL.md)
- [Cryptographic and canonical encoding profile](docs/CRYPTO_FORMAT.md)
- [Reproducible test plan](docs/TEST_PLAN.md)

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
