# HND-Ledger

HND-Ledger is an experimental educational ledger and consensus-integration project. It is not a production blockchain, investment product, or public token launch.

## Current implementation

The implementation/v0.2-local-ledger branch contains a deterministic Python ledger, Ed25519-signed transfers, canonical CBOR, account nonces, supply-cap checks, SQLite replay/recovery, a Python ABCI++ application, private Unix IPC, and a Go ABCI adapter pinned to CometBFT v0.40.0.

The project has passing one-node restart and three-validator integrations. The three-validator workflow exercises a signed transfer, read-only account and ledger-info queries, a signed overspend admitted by weak CheckTx but filtered by PrepareProposal, and restart recovery.

## Verified CI evidence

- Python tests: run 42361314253 on commit d0832723ee533e7c27f47e62bcdedc7c5d1e3149, success (70 tests).
- One-node CometBFT restart: run 42361234790 on commit f08e0e053920a989b8b7b200c4ee856d6cefee54, success.
- Three-validator transfer, query, overspend filtering, and restart integration: run 42361234762 on the same commit, success.
- Go adapter tests/static analysis: run 42359852685 on commit 1c62d3cad548315b8cecb811edd76ee6b93808af, success.

The three-validator run committed a signed transfer at height 4. All ledgers agreed on balances, nonce, and state commitment 78b774640f86986f70e5528d94aee5e8aa56fa5b79320dc6bc99b50b1bfa5438. Account and ledger-info queries succeeded on all three nodes. A correctly signed 800,000-unit spend from an account holding 750,000 passed weak CheckTx admission but was excluded by PrepareProposal; no validator committed it and balances/nonces remained unchanged. All CometBFT header app hashes matched at height 5. After validator 0 restarted, it retained the valid transfer and matching app hash.

The 70-test Python suite includes a SQLite trigger failure and a real child-process termination during block insertion. After the process exits inside the uncommitted SQLite transaction, reopening the database recovers the original genesis state with no partially committed block.

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
