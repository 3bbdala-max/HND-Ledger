# HND-Ledger

HND-Ledger is an experimental educational project for studying a signed transaction ledger, deterministic state transitions, block chaining, and consensus design.

## Current status

- **Version 0.1:** archived documentation and historical claims; not independently reproduced by the current implementation.
- **Version 0.2 design:** protocol and cryptographic serialization specifications are maintained under `docs/`.
- **Local implementation branch:** `implementation/v0.2-local-ledger` contains an initial Python implementation of Ed25519-signed transactions, canonical CBOR encoding, an atomic account ledger, deterministic block commitments, and SQLite-backed replay on restart.
- **Automated tests:** 38 pytest tests passed in GitHub Actions run [42344679339](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42344679339), tied to commit `29ae7ec7bee8cbea8b11469407ec48ab7be006a6`. This run includes lifecycle isolation, stale-candidate guards, weak CheckTx admission, and ordered nonce execution.
- **Consensus evaluation:** CometBFT v0.40.0 is the pinned candidate for a controlled ABCI++ integration spike. The application lifecycle and Go socket-adapter/Python-engine boundary are documented; the adapter is not implemented and no independent validators are running.
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
- [CometBFT integration decision](docs/COMETBFT_INTEGRATION_DECISION.md)
- [ABCI application lifecycle boundary](docs/ABCI_APPLICATION_BOUNDARY.md)
- [ABCI transport design](docs/ABCI_TRANSPORT_DESIGN.md)

## Safety and launch status

This is a local prototype, not a production blockchain or investment product. No decentralization, Byzantine fault tolerance, independent validator operation, security audit, regulatory approval, exchange listing, or readiness for public launch is claimed. Historical archive metrics must not be presented as current reproducible test results.
