# HND-Ledger

HND-Ledger is an experimental educational ledger and consensus-integration project. It is not a production blockchain, investment product, or public token launch.

## Current implementation

The implementation/v0.2-local-ledger branch contains a deterministic Python ledger, Ed25519-signed transfers, canonical CBOR, account nonces, supply-cap checks, SQLite replay/recovery, a Python ABCI++ application, private Unix IPC, and a Go ABCI adapter pinned to CometBFT v0.40.0.

The project has passing one-node restart and three-validator integrations. The three-validator workflow exercises a signed transfer, read-only account and ledger-info queries, a signed overspend admitted by weak CheckTx but filtered by PrepareProposal, and restart recovery.

## Verified CI evidence

- Python tests: run 42362574022 on commit d81c8fb5033fec1b369658df5671c1e3e45bfdcf, success (75 tests).
- One-node CometBFT restart: run 42362573986 on the same commit, success.
- Three-validator transfer, query, overspend filtering, app-hash comparison, and restart integration: run 42362574012 on the same commit, success.
- Go adapter tests/static analysis: run 42359852685 on commit 1c62d3cad548315b8cecb811edd76ee6b93808af, success; subsequent integration runs also rebuilt and exercised the adapter.

The three-validator run verifies a funded development genesis, a real signed transfer, matching local state commitments and CometBFT app hashes, and recovery after validator restart. A correctly signed overspend is admitted by weak CheckTx but filtered before commit by proposal preparation. The funded-genesis tests also verify idempotent retry after restart, rejection of a conflicting genesis, and rejection of non-canonical base64 without partial state changes.

The 75-test Python suite includes SQLite rollback and child-process crash injection during block insertion and both sides of genesis-marker insertion. It verifies that rejected transactions do not partially mutate balances or nonces, including when a pre-existing in-memory state violates the supply cap.

The validators ran as separate processes and data directories on one CI runner. This is not independent multi-operator deployment or an adversarial Byzantine test.

## Protocol parameters

- Transaction protocol version: 2
- Local chain ID: HND-LOCAL-V2
- Ed25519 signatures; SHA-256 domain-separated hashes
- Canonical CBOR transactions
- Smallest unit: 10^-8 HND
- Design ceiling: 1,000,000 HND
- State commitment domain: HND-STATE-V3, including chain ID, supply cap, balances, and nonces

Pre-v3 local database roots are incompatible with the v3 state-commitment format. Treat old development databases as disposable.

## Not production-ready

Wallet/key custody, public user API and explorer, production genesis allocation governance, validator onboarding/key rotation, snapshots/state sync, validator-set changes, adversarial consensus tests, independent security audit, economic review, and legal review remain incomplete. The local CometBFT RPC is not a production public API.
