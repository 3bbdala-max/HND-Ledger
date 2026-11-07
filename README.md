# HND-Ledger

HND-Ledger is an experimental educational project for studying a signed transaction ledger, deterministic state transitions, block chaining, and consensus design.

## Current status

- **Version 0.1:** archived documentation and historical claims; not independently reproduced by the current implementation.
- **Version 0.2 design:** protocol and cryptographic serialization specifications are maintained under `docs/`.
- **Local implementation branch:** `implementation/v0.2-local-ledger` contains an initial Python implementation of Ed25519-signed transactions, canonical CBOR encoding, an atomic account ledger, deterministic block commitments, and SQLite-backed replay on restart.
- **Automated tests:** pytest tests and a GitHub Actions workflow are included. A passing CI result has not yet been confirmed; test presence is not proof of passing behavior.
- **Consensus design:** threat model, validator design gate, and distributed test matrix are documented; no consensus engine or independent validators are implemented.
- **Not implemented:** peer-to-peer networking, wallet, public RPC, production genesis allocation, or public network.

## Protocol parameters

- Protocol version: 2
- Local chain identifier: `HND-LOCAL-V2` padded to 32 bytes
- Signatures: Ed25519
- Hash: SHA-256 with domain separation
- Serialization: deterministic CBOR
- Smallest unit: 10^-8 HND
- Maximum supply design cap: 1,000,000 HND

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Protocol](docs/PROTOCOL.md)
- [Cryptographic format](docs/CRYPTO_FORMAT.md)
- [Test plan](docs/TEST_PLAN.md)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Local block and storage design](docs/CHAIN_STORAGE.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Validator and consensus design gate](docs/VALIDATOR_CONSENSUS_DESIGN.md)
- [Consensus test matrix](docs/CONSENSUS_TEST_MATRIX.md)

## Safety and launch status

This is a local prototype, not a production blockchain or investment product. No decentralization, Byzantine fault tolerance, independent validator operation, security audit, regulatory approval, exchange listing, or readiness for public launch is claimed. Historical archive metrics must not be presented as current reproducible test results.
