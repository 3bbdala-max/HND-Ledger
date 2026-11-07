# HND-Ledger

HND-Ledger is an experimental educational ledger and consensus-integration project. It is not a production blockchain, investment product, or public token launch.

## Current status

The `implementation/v0.2-local-ledger` branch contains:

- A Python reference ledger with Ed25519-signed transfers, canonical CBOR transactions, sequential nonces, bounded integer arithmetic, supply-cap checks, deterministic block commitments, and SQLite replay on restart.
- An ABCI++ application lifecycle implemented in Python, exposed through a bounded private Unix-domain IPC service.
- A thin Go ABCI socket adapter pinned to CometBFT v0.40.0. The adapter delegates HND transaction and state logic to Python.
- Passing one-node CometBFT integration and restart recovery.
- Passing three-validator CI integration using three separate node homes, validator identities, Python processes, SQLite databases, and IPC sockets. The test submits a signed transfer, checks each ledger, compares the post-transfer application hash, restarts one validator, and verifies its persisted state.

## Verified CI evidence

All four workflows passed on commit `1c62d3cad548315b8cecb811edd76ee6b93808af`:

| Workflow | Run |
|---|---:|
| Python tests | [42359852666](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42359852666) |
| Go adapter tests and static analysis | [42359852685](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42359852685) |
| One-node CometBFT smoke and restart | [42359852690](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42359852690) |
| Three-validator funded-genesis and transfer integration | [42359852656](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42359852656) |

The three-validator run committed a test transfer at height 4. All three local ledgers agreed on balances, nonce, and state commitment `78b774640f86986f70e5528d94aee5e8aa56fa5b79320dc6bc99b50b1bfa5438`. They also agreed on the CometBFT header app hash at height 5. After validator 0 restarted, it retained the committed transfer and the same balances, nonce, and app hash.

These are controlled CI integration results. The validators ran as separate processes on one CI runner; this is not independent multi-operator deployment or a Byzantine-adversarial test.

## Protocol parameters

- Transaction protocol version: 2
- Local CometBFT chain ID: `HND-LOCAL-V2`
- Signatures: Ed25519
- Hash: SHA-256 with domain separation
- Serialization: canonical CBOR
- Smallest unit: (10^{-8}) HND
- Design supply ceiling: 1,000,000 HND
- State commitment domain: `HND-STATE-V3`, committing chain ID, supply cap, balances, and nonces

The state-commitment upgrade is not backward-compatible with pre-v3 local database roots. Treat old local databases as disposable development data; do not reuse them as a live network database.

## Not yet production-ready

Not implemented or not independently validated: wallet and key custody, public account API and explorer, production genesis/allocation governance, validator onboarding and key rotation, snapshots and state sync, validator-set changes, adversarial partition/equivocation testing, independent security audit, economic review, and jurisdiction-specific legal review.

The local CometBFT RPC used in CI is not a production public API. The Go ABCI listener is restricted to loopback addresses.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Protocol](docs/PROTOCOL.md)
- [Cryptographic format](docs/CRYPTO_FORMAT.md)
- [Test plan](docs/TEST_PLAN.md)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Local block and storage design](docs/CHAIN_STORAGE.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Validator and consensus design](docs/VALIDATOR_CONSENSUS_DESIGN.md)
- [Consensus test matrix](docs/CONSENSUS_TEST_MATRIX.md)
- [CometBFT integration decision](docs/COMETBFT_INTEGRATION_DECISION.md)
- [ABCI application lifecycle](docs/ABCI_APPLICATION_BOUNDARY.md)
- [ABCI transport design](docs/ABCI_TRANSPORT_DESIGN.md)
- [Verified local adapter status](docs/ABCI_LOCAL_ADAPTER_STATUS.md)

## Safety and launch status

No public network, real-value transfer, token issuance, decentralization claim, security certification, regulatory approval, or exchange listing is asserted or authorized by this prototype.
