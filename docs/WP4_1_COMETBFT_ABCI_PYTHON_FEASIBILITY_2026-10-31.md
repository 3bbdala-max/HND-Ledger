# HND Ledger — WP4.1 CometBFT / Python ABCI feasibility

**Date:** 2026-10-31  
**Workstream:** WP4.1 — integration feasibility  
**Status:** Design decision for a disposable development spike; no production integration  
**Branch:** `phase-0.2-planning`

## 1. Outcome

**Recommended first prototype:** keep the HND application state machine in Python and expose a narrow ABCI gRPC server to a pinned CometBFT v0.40.0 binary.

Do not rewrite the HND ledger in Go at this stage. Do not add a second custom consensus implementation. CometBFT owns proposal/vote rounds, validator signatures, block consensus, and the committed block history. The Python application owns only deterministic HND transaction validation and state transitions.

gRPC is selected for the first low-volume development spike because CometBFT's own ABCI server documentation describes it as the easiest option when the application is not written in Go and gRPC is available, while acknowledging performance overhead. Performance is not a goal of this four-node feasibility test. The socket transport remains a later option if profiling shows gRPC to be a bottleneck.

This recommendation is conditional on a passing compatibility spike against the exact v0.40.0 protobuf schema. It is not evidence that a ready-made, maintained Python ABCI++ server library exists.

## 2. Exact CometBFT release baseline

As checked on 2026-10-31:
- GitHub releases marks **v0.40.0** as the latest listed CometBFT release.
- The v0.40.0 `go.mod` declares `go 1.25.0`; the test environment must therefore use Go 1.25.0 or a compatible supported toolchain.
- The release is dated 2026-07-27 and is signed by its committer.
- Its changelog includes a fix for `double_sign_check_height = 1` not checking the previous block, plus an ABCI socket-transport fix involving `InsertTx`/`ReapTxs` when `mempool.type = "app"`.

For the initial test, use the released v0.40.0 tag, not the moving `main` branch. Before pinning a production dependency, review the full changelog, security advisories, upgrade policy, binary provenance, and reproducible build instructions again.

Sources:
- https://github.com/cometbft/cometbft/releases
- https://github.com/cometbft/cometbft/blob/v0.40.0/go.mod
- https://github.com/cometbft/cometbft/blob/v0.40.0/CHANGELOG.md

## 3. Protobuf version and source-of-truth rule

For the v0.40.0 tag, the ABCI service definition used for this spike is:

`proto/tendermint/abci/types.proto`

It declares the `tendermint.abci.ABCI` gRPC service and methods including `Info`, `InitChain`, `CheckTx`, `PrepareProposal`, `ProcessProposal`, `ExtendVote`, `VerifyVoteExtension`, `FinalizeBlock`, and `Commit`, as well as the other ABCI methods in that release.

**Compatibility warning:** the v0.40.0 `spec/abci/abci++_client_server.md` points to a different newer-looking protobuf path (`proto/cometbft/abci/v1/types.proto`) that is not present at that tag. The source file fetched from the v0.40.0 tag is under `proto/tendermint/abci/types.proto`. This mismatch must not be papered over by generating Python stubs from the moving `main` branch.

Rules:
1. Pin the repository tag to `v0.40.0`.
2. Generate Python protobuf and gRPC files from the exact tagged source tree and its imported dependencies.
3. Record hashes of the `.proto` inputs and generated Python files.
4. Run request/response round-trip tests for every ABCI method used by the node.
5. Do not mix v0.40.0 CometBFT messages with v1/v2 definitions from a different release or another Cosmos SDK tree.

Source:
- https://github.com/cometbft/cometbft/blob/v0.40.0/proto/tendermint/abci/types.proto
- https://github.com/cometbft/cometbft/blob/v0.40.0/spec/abci/abci++_client_server.md

## 4. Transport choice

| Option | Advantages | Costs / risks | WP4.1 decision |
|---|---|---|---|
| ABCI gRPC | Officially documented as easiest for non-Go applications; generated Python gRPC service is possible from the pinned schema | Extra serialization and RPC overhead; generated-code dependency compatibility must be tested | **Use for the first local prototype** |
| ABCI socket | Unix/TCP socket; Protobuf length-prefixed stream; can avoid gRPC overhead | Must implement framing, message ordering, connection handling, and reconnect behavior correctly | Defer until profiling justifies it |
| Go in-process app | Native integration with CometBFT | Would require moving or duplicating the Python state machine | Not selected now |
| Go adapter calling a Python sidecar | Reuses Python logic in theory | Adds another process boundary, lifecycle, IPC, failure modes, and state synchronization; not justified for the first spike | Do not build without evidence it is needed |

Bind the first gRPC endpoint to loopback only. Do not expose an unauthenticated ABCI application endpoint to the public internet. If separate machines are later used, use authenticated/encrypted transport or a private protected network and review the threat model.

## 5. Application boundary

The architecture should be:

`CometBFT v0.40.0 node`
→ ABCI gRPC
→ `HND Python ABCI adapter`
→ existing `hnd_v02.transaction` and `hnd_v02.ledger` logic
→ durable HND application state

The Python adapter is an integration layer, not a second ledger. It must call the existing versioned transaction validator and state-transition implementation instead of re-implementing signature, account, nonce, balance, and supply rules.

### Native CometBFT blocks versus the HND local-chain reference

The CometBFT engine must own the network's block proposal, consensus, commit certificate, and block history. The application receives the decided transaction bytes through ABCI and computes the HND application state.

Consequently:
- `hnd_v02/blocks.py` remains a valuable local block-chain reference and test harness.
- It must not create a second competing block history inside the actual CometBFT network.
- Do not require the HND custom block hash to equal the native CometBFT block hash.
- HND's deterministic state hash can be returned as the ABCI application hash (`AppHash`) after checking the exact ABCI v0.40.0 contract and byte encoding.
- Account balances, nonces, accepted transaction IDs, and the signed transaction history remain HND application state.

This boundary avoids a "blockchain inside a blockchain" design and keeps the two hash domains conceptually separate.

## 6. ABCI method lifecycle and application state

The adapter must maintain distinct state views and follow the v0.40.0 ABCI++ lifecycle:

| ABCI method | HND behavior |
|---|---|
| `Info` | Return last durably committed height and application hash for recovery handshake |
| `InitChain` | Decode canonical application Genesis data; verify chain/network ID and pinned HND Genesis hash; initialise the state |
| `CheckTx` | Validate a transaction against a mempool/check-state view; do not mutate committed application state |
| `PrepareProposal` | Select valid mempool transactions without changing committed state; respect `max_tx_bytes` |
| `ProcessProposal` | Deterministically validate the proposed transaction list against a candidate copy of the last committed state; return the same result on all honest nodes |
| `ExtendVote` / `VerifyVoteExtension` | Return the minimal permitted empty behavior initially; do not add application-side consensus policy or state side effects |
| `FinalizeBlock` | Execute the block decided by consensus against a temporary state; calculate transaction results and the application hash; do not durably persist yet |
| `Commit` | Atomically persist the finalized application state and height; then update the committed view and rebuild/reset the mempool view |
| `Query` | Read only from a committed snapshot; initial paths may expose account balance and current height |
| Snapshot methods | Return an explicit unsupported/empty response for the first test network; do not claim state-sync support until chunked snapshot restore is implemented and tested |

Critical invariants:
1. `PrepareProposal`, `ProcessProposal`, `ExtendVote`, and `VerifyVoteExtension` must never mutate the last committed HND state.
2. `ProcessProposal` acceptance/rejection must be deterministic and depend only on the proposed block and the previous committed state.
3. Candidate states from earlier proposals or rounds must be safely discarded. The application cannot assume the proposal it previously processed will be the block eventually finalized.
4. `FinalizeBlock` executes only the block decided by consensus; persistence happens during `Commit`.
5. A crash/restart must recover the last committed height and app hash without replaying a candidate proposal as committed.
6. The application must handle multiple ABCI connections / concurrent RPC handling safely. State access must be serialized or protected by carefully designed isolated views and locks.
7. The mempool/check state is distinct from consensus execution state and is refreshed after commit.

Sources:
- https://github.com/cometbft/cometbft/blob/v0.40.0/spec/abci/abci++_basic_concepts.md
- https://github.com/cometbft/cometbft/blob/v0.40.0/spec/abci/abci++_app_requirements.md
- https://github.com/cometbft/cometbft/blob/v0.40.0/spec/abci/abci++_expected_behavior.md

## 7. Genesis and network identity

The launch configuration must pin two related but distinct objects:
1. The HND application Genesis manifest and its independently supplied expected hash.
2. The CometBFT validator set, with each validator's public consensus key and voting power.

For this controlled test, require the CometBFT `chain_id` to equal the HND `network_id` exactly. Include the HND manifest and its expected hash in the canonical CometBFT application-state Genesis payload. Every validator must verify the same application Genesis payload and the same validator set before starting.

Validator keys are consensus keys. HND account-spending Ed25519 keys remain separate. Do not place private validator keys in the repository, CI artifacts, screenshots, logs, or shared Genesis files.

The initial validator set remains fixed at four equal-power development validators. No dynamic validator updates, staking, rewards, or governance are implemented in this spike.

## 8. Mempool setting for the first spike

Use CometBFT's normal `flood` mempool for the first development test. Do not select `mempool.type = "app"` yet. The v0.40.0 changelog documents a socket-transport fix concerning `InsertTx` and `ReapTxs` for app-side mempool mode; the first test should avoid adding that extra mode and transport variable before basic state replication works.

The HND `CheckTx` path must still validate transaction bytes and maintain a separate pending/mempool view. Passing `CheckTx` means only that a transaction is acceptable for mempool admission; it is not a guarantee that consensus will include it.

Source:
- https://github.com/cometbft/cometbft/blob/v0.40.0/CHANGELOG.md
- https://github.com/cometbft/cometbft/blob/v0.40.0/docs/core/using-cometbft.md

## 9. Required dependencies and build discipline

Candidate development dependencies only (not yet added to `requirements.txt`):
- Python gRPC runtime and generated-code compatible protobuf runtime.
- A pinned `protoc` / Python gRPC code-generation toolchain.
- The exact CometBFT v0.40.0 Protobuf source tree and its declared imports.
- CometBFT v0.40.0 binary built or obtained from a verified release artifact.
- Go 1.25.0 for a source build, as required by the tagged `go.mod`.

Do not add unbounded dependencies. Pin versions after the first successful reproducible build. Record binary checksum, source tag, protobuf input hashes, generated-file hashes, Python version, Go version, and CI run identifiers.

## 10. WP4.1 acceptance tests

The feasibility spike passes only if the following work on a disposable network:

### Protocol compatibility
- The Python ABCI gRPC server starts and CometBFT connects using the v0.40.0 schema.
- `Info` handshake works at genesis and after restart.
- `InitChain` verifies chain ID, HND network ID, Genesis manifest, and expected hash.
- Each ABCI method used in normal operation has request/response serialization tests.
- A malformed or incompatible request fails closed without corrupting state.

### State-machine correctness
- Two independent Python application instances execute the same transactions and return identical state hashes.
- `ProcessProposal` is deterministic for valid, invalid, duplicate, stale-nonce, bad-signature, wrong-network, and overspending transactions.
- Multiple different proposals at the same height do not mutate committed state.
- `FinalizeBlock` creates pending state; a crash before `Commit` does not expose it as committed.
- `Commit` is atomic and restart reports the exact last committed height and AppHash.
- Mempool state resets/rechecks against committed state after each commit.
- The application hash remains equal on all honest validators after each committed block.

### Four-node network behavior
- Four validators commit the same transactions and heights.
- One validator offline: remaining three may continue and the restarted validator catches up.
- Two validators unavailable: no two-vote partition commits; chain progress halts without quorum.
- A 2+2 partition does not result in either side creating a conflicting committed history.
- One Byzantine test node sends malformed/invalid proposals or withholds votes; honest nodes do not apply invalid HND state.
- Validator signing state survives node restart and no private key is written to public logs or artifacts.

Passing these tests is an integration milestone only. It is not an independent security audit, a proof against every Byzantine behavior, or production readiness.

## 11. Explicit non-goals

No mainnet, public token issuance, public allocation, sale, exchange listing, payment integration, custody, validator rewards, staking, public validator admission, or real funds are in scope. No legal approval or security certification is implied.

## 12. Next work item

**WP4.2 — minimal Python ABCI adapter contract and tests.**

Create the smallest application wrapper that maps the exact v0.40.0 ABCI methods to the existing HND transaction and ledger APIs. Begin with `Info`, `InitChain`, `CheckTx`, `PrepareProposal`, `ProcessProposal`, `FinalizeBlock`, and `Commit`; add query and state-sync methods under separate tests. Do not start the four-validator run until the single-node handshake, deterministic proposal execution, and commit/recovery tests pass.
