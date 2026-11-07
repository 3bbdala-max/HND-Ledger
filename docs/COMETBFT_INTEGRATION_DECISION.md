# HND consensus engine integration decision

**Decision status:** CometBFT v0.40.0 is selected and integrated for controlled local testing. This is not approval for public deployment or production use.

## Selected engine

Use **CometBFT v0.40.0** as the pinned consensus engine for the v0.2 integration. Do not build from the moving `main` branch. Re-evaluate the pin before any public testnet or production deployment; version upgrades require coordinated compatibility and migration tests.

Upstream references:
- Release and versioning policy: https://github.com/cometbft/cometbft/releases
- v0.40.0 changelog: https://github.com/cometbft/cometbft/blob/v0.40.0/CHANGELOG.md
- ABCI++ basic concepts: https://github.com/cometbft/cometbft/blob/v0.40.0/spec/abci/abci%2B%2B_basic_concepts.md
- ABCI++ application requirements: https://github.com/cometbft/cometbft/blob/v0.40.0/spec/abci/abci%2B%2B_app_requirements.md
- Running an out-of-process application: https://github.com/cometbft/cometbft/blob/v0.40.0/docs/core/using-cometbft.md

## Integration architecture

- CometBFT runs as a separately pinned process and owns P2P communication, validator voting, and block consensus.
- The Go ABCI socket adapter implements the CometBFT application interface and delegates HND logic to Python over a private Unix-domain socket.
- Python remains the reference implementation for transaction verification, state transitions, supply policy, and state commitments.
- Only Commit writes the finalized block to the SQLite ledger. Proposal candidates remain isolated from committed state.
- The Python IPC service uses a bounded JSONL envelope, strict request validation, and a mode-0600 Unix socket.
- The Go ABCI listener is restricted to loopback TCP addresses.

## Implemented ABCI lifecycle

- `Info`: reports committed height and application hash.
- `InitChain`: validates the fixed chain ID and bounded canonical genesis envelope; persists funded test allocations and the CometBFT genesis marker atomically.
- `CheckTx`: validates encoding, chain ID, and signature. State-dependent nonce and balance validity is checked against ordered proposals.
- `InsertTx` and `ReapTxs`: bounded in-memory mempool operations.
- `PrepareProposal` and `ProcessProposal`: deterministic transaction selection and validation.
- `FinalizeBlock`: computes a candidate without durable writes.
- `Commit`: persists the decided block and updates the committed state.

Query, snapshots, state sync, and vote-extension methods are not implemented by the Python dispatcher and fail closed.

## Verified local integration

On commit `1c62d3cad548315b8cecb811edd76ee6b93808af`:

- One-node CometBFT block production and restart recovery passed: run 42359852690.
- Three-validator funded-genesis and signed-transfer integration passed: run 42359852656.
- The three-validator test compared all local state commitments after the signed transfer and all CometBFT header app hashes at height H+1. It restarted validator 0 and verified the transfer, balances, nonce, and matching app hash remained intact.
- Python tests passed: run 42359852666.
- Go adapter tests and static analysis passed: run 42359852685.

The three validators were separate processes and data directories on one CI runner. This does not establish independent validator operation or adversarial BFT safety.

## Remaining integration and release gates

- Crash injection at every boundary around FinalizeBlock, SQLite commit, and process restart.
- Conflicting proposals, equivocation, duplicate/replayed votes, and Byzantine voting-power tests.
- Network delay, loss, partition, healing, and validator downtime tests.
- Validator-set changes, key persistence, anti-double-signing, and rotation.
- Snapshots, state sync, Query API, database backup/restore, and schema migration.
- Multi-host, independently operated validator tests.
- Independent protocol, cryptographic, application security, economic, and legal review.

No validator keys, public network, real-value transfers, token distribution, or public claims of decentralization are authorized by this integration decision.
