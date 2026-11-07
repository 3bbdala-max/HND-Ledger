# HND consensus engine evaluation

**Decision status:** candidate selected for a controlled integration spike; not integrated and not approved for public deployment.

## Candidate

Use **CometBFT v0.40.0** as the first integration candidate. Pin the exact release tag for experiments; do not build production artifacts from the moving `main` branch. The upstream release page lists v0.40.0 as a release dated 27 July 2026 and documents API-breaking changes in that release series. Re-evaluate the pin before any public testnet or production deployment.

Upstream references:
- Release and versioning policy: https://github.com/cometbft/cometbft/releases
- v0.40.0 changelog: https://github.com/cometbft/cometbft/blob/v0.40.0/CHANGELOG.md
- ABCI++ basic concepts: https://github.com/cometbft/cometbft/blob/v0.40.0/spec/abci/abci%2B%2B_basic_concepts.md
- ABCI++ application requirements: https://github.com/cometbft/cometbft/blob/v0.40.0/spec/abci/abci%2B%2B_app_requirements.md
- Running an out-of-process application: https://github.com/cometbft/cometbft/blob/v0.40.0/docs/core/using-cometbft.md

## Why this candidate

CometBFT supplies a mature Byzantine-fault-tolerant consensus engine and an application boundary (ABCI++). HND can retain ownership of transaction validity, balances, nonces, supply policy, and deterministic state commitments while CometBFT handles proposal gossip, validator voting, and block decision.

The release must be pinned. Upstream explicitly warns against depending on `main`, and documents that minor-version changes can break public APIs. A version upgrade is therefore a protocol/infrastructure change that requires a coordinated compatibility plan.

## Required application lifecycle

The adapter must implement the ABCI++ lifecycle without confusing candidate state with committed state:

1. `InitChain`: validate the HND genesis configuration, chain identifier, supply cap, initial allocations, and validator set.
2. `CheckTx`: validate transaction encoding, signature, chain ID, nonce against mempool state, and basic resource limits. This is admission checking, not final execution.
3. `PrepareProposal`: select and order only transactions that fit the configured byte and transaction limits. Any speculative execution must use an isolated candidate state.
4. `ProcessProposal`: deterministically validate the proposed transactions against the last committed state and the proposal limits. Reject only for deterministic protocol-invalid proposals; careless rejection can harm liveness.
5. `FinalizeBlock`: deterministically execute the decided block and compute transaction results and the application state hash. Do not make speculative candidate state durable here.
6. `Commit`: atomically persist the resulting application state and committed height before returning. Recovery must reconcile the application height with CometBFT's stored height.

ABCI++ may call proposal methods multiple times for different rounds and candidate blocks. Candidate state from a proposal that is not ultimately decided must be discarded. The adapter must be correct across retries, process restarts, and crashes between block storage, finalization, and commit.

## Integration architecture

- Keep the existing Python HND protocol/state implementation as the reference state machine during the spike.
- Run CometBFT as a separately version-pinned process.
- Implement a narrow ABCI socket adapter. The adapter must call the deterministic HND transition logic and must not duplicate transaction rules in a second implementation.
- Use separate committed and candidate state snapshots. Only `Commit` advances durable application state.
- Derive `AppHash` from the deterministic HND state commitment, with explicit chain/genesis domain separation.
- Configure explicit maximum block bytes, transaction count, gas/resource policy, validator voting power, timeouts, and peer access controls.
- Store validator private keys outside the application database; define backup, access, rotation, and double-sign prevention procedures before any validator carries voting power.

A Python ABCI socket adapter is not yet selected as an implementation library. Before coding it, the spike must prove compatibility with the exact v0.40.0 protobuf/service definitions and exercise restart and commit semantics. If the available Python ecosystem cannot provide a reliable maintained adapter, use a small Go ABCI transport shim that calls the Python state machine through a versioned local IPC boundary; do not rewrite consensus rules in Go.

## Mandatory integration gates

- Exact release pin and reproducible build.
- One-node ABCI handshake, genesis initialization, transaction admission, block proposal, finalization, and commit.
- Three-node local cluster with independent data directories and validator keys.
- Same application hash on all nodes after each committed height.
- Invalid signature, wrong chain, replay, nonce gap, insufficient funds, overflow, duplicate transaction, oversized block, and malformed transaction rejection.
- Proposal retries and different candidate blocks across rounds do not mutate committed state.
- Crash injection before and after `FinalizeBlock` and `Commit`; restart must converge to the same committed height and app hash.
- Validator-set change and validator key persistence tests.
- Network partition, delayed messages, validator downtime, and Byzantine proposal scenarios.
- Reproducible test evidence tied to exact source commit and CometBFT binary version.

## Explicit non-goals at this stage

No validator keys, public network, token distribution, exchange listing, public claims of decentralization, or real-value transfers are authorized by this evaluation. CometBFT integration is not complete merely because a single-node process starts. Independent security review and legal review remain release gates.
