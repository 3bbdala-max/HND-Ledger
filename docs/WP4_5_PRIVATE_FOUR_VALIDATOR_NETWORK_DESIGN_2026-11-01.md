# WP4.5 — Private Four-Validator Network Design and Acceptance Gate

**Status:** Design gate; implementation not yet claimed  
**Target branch:** `phase-0.2-planning`  
**Pinned consensus engine:** CometBFT v0.40.0  
**Predecessor:** WP4.4 single-node integration smoke test  
**Safety boundary:** Disposable private testnet only; no public peers, real funds, or production keys.

## 1. Purpose

WP4.5 defines the smallest useful distributed integration test after the successful WP4.4 one-validator smoke test. It must prove that four independently configured CometBFT validator processes can connect to four independent HND ABCI application processes, commit the same blocks, and recover from a controlled single-validator interruption.

This is an integration test plan, not a proof of Byzantine fault tolerance, a security audit, or production readiness.

## 2. Topology

Create four isolated validator instances: `val1` through `val4`.

Each instance MUST have its own:
- CometBFT home directory and generated validator private key;
- CometBFT P2P and RPC ports;
- HND ABCI gRPC listener port;
- HND application state file and process;
- node log and process lifecycle.

All four instances MUST share exactly the same:
- CometBFT chain ID and initial height;
- CometBFT genesis document and initial validator set;
- HND Genesis manifest and independently pinned manifest hash;
- HND protocol version and network configuration;
- CometBFT v0.40.0 binary and HND source revision.

No node may share a writable state file or validator private key with another node. Use a temporary root directory; delete it automatically after the test.

## 3. Validator set and consensus assumptions

- Four validators, each with equal voting power (10), for total voting power 40.
- CometBFT's greater-than-two-thirds commit threshold is therefore 30 voting power; three validators are sufficient to commit, while two are not.
- The test may interrupt one validator and require the remaining three to continue committing.
- Do not describe this as proof against arbitrary Byzantine behavior. A process-stop test covers crash/availability behavior only; it does not simulate equivocation, censorship, or malicious state transitions.
- Validator public keys and addresses must be generated from each isolated CometBFT home and inserted into the common genesis file using the exact CometBFT v0.40.0 genesis schema. The implementation must verify that the four validator addresses are unique and that every node loads the same validator set.

## 4. Network isolation and port plan

Use loopback-only listeners in CI. Allocate a deterministic, non-overlapping port range per node (or dynamically reserve ports and record the chosen values):
- P2P: one unique port per validator;
- RPC: one unique port per validator, bound to loopback;
- ABCI gRPC: one unique port per HND app, bound to loopback.

Configure persistent peers using the four generated node IDs and their loopback P2P endpoints. Disable external address advertisement and avoid public peer discovery. Never bind unauthenticated ABCI gRPC or RPC endpoints to `0.0.0.0`.

The test harness must check port uniqueness before starting processes and fail with a clear diagnostic if a port is already occupied.

## 5. Test sequence

### A. Genesis agreement
1. Generate four independent CometBFT homes and validator keys.
2. Construct one shared four-validator genesis document.
3. Start four separate HND ABCI application servers, each with its own state path and the same HND manifest/hash.
4. Start all four CometBFT nodes.
5. Wait for all nodes to report the same non-zero committed height.
6. Query each node's status and HND application state; compare chain ID, validator set, height, and app hash.

### B. Transaction agreement
1. Create one valid HND-signed transfer from a funded Genesis account.
2. Broadcast the exact same transaction to one validator's RPC endpoint.
3. Wait for the transaction to be committed.
4. Require all four nodes to report the same committed height and block hash.
5. Query the sender and recipient through each node's ABCI query endpoint; require identical balances and application hashes.
6. Verify total supply remains exactly 1,000,000 HND.

### C. Single-validator restart
1. Stop one validator and its associated HND app cleanly.
2. Keep the other three validators running and require at least one additional block to commit.
3. Restart the stopped HND app using its own persisted state, then restart its CometBFT node using its original home.
4. Require the restarted node to catch up to the common height and block hash.
5. Compare its HND application hash and account balances with the other three nodes.

### D. Negative and cleanup checks
- Confirm no two nodes share a state path, validator key path, or port.
- Confirm all RPC/ABCI listeners are loopback-only.
- Confirm the test fails if one node is configured with a different HND Genesis hash or network ID (prefer a separate negative test to avoid destabilizing the main happy-path run).
- Stop every process in a finally/cleanup path, including on timeout or assertion failure.
- Ensure temporary private keys and test data are not uploaded as CI artifacts.

## 6. Required evidence and acceptance criteria

WP4.5 is accepted only when CI logs demonstrate:
- exactly four distinct validator identities and four independent HND state paths;
- all four nodes started with the same chain ID and validator set;
- all four nodes committed the same transaction and reached matching height/block hash;
- all four HND application states agree on balances, total supply, and app hash;
- the three-node quorum continued committing while one validator was stopped;
- the restarted validator caught up and converged to the same committed state;
- all processes were stopped and temporary data remained outside the repository.

Publish a report recording the tested commit SHA, CometBFT version, workflow run URL, validator count, test sequence, observed heights/hashes, and limitations. Never infer a pass from partial logs.

## 7. Known integration risks to resolve during implementation

1. CometBFT v0.40.0 genesis JSON schema and public-key encoding must be verified against the pinned binary, not copied from another release.
2. Node IDs must be derived from each node's generated P2P key and persistent peer strings must be validated before startup.
3. HND ABCI application instances must not share mutable process memory or persistence files.
4. CometBFT may continue producing blocks with empty transaction lists; tests must identify the transaction's committed height and verify it on every node.
5. The current HND ABCI adapter rejects snapshot transfer and does not implement state-sync snapshots. The first WP4.5 restart test should use normal CometBFT block replay/catch-up. Do not claim fast state sync.
6. The current HND state persistence is a prototype file-based mechanism. Multi-process safety, crash consistency, fsync guarantees, and database-grade durability remain separate verification work.
7. A single stopped-validator test is not a network partition test and does not test Byzantine faults.

## 8. Out of scope

- Public internet peering or public testnet deployment;
- production validator key custody or remote signing;
- validator admission/removal governance;
- malicious-validator/equivocation tests;
- network partition, message-delay, packet-loss, or DDoS testing;
- snapshot-based state sync;
- independent security audit or production certification.

## 9. Decision gate

Implementation may begin only after the harness can create a valid four-validator genesis from four isolated CometBFT homes and verify the same validator set on all nodes. If the pinned CometBFT schema or HND app lifecycle requires architectural changes, stop and document the change before coding. Keep all work on `phase-0.2-planning`; do not modify or merge into `main`.

---
This document is an engineering test plan, not a claim that WP4.5 has been implemented or passed.


## 10. Pinned CometBFT v0.40.0 schema findings and preflight

The implementation has now been checked against the pinned v0.40.0 source rather than relying on generic CometBFT examples:

- `types.GenesisValidator` uses `address`, `pub_key`, `power`, and `name`; `GenesisDocFromFile` parses and validates the Genesis document and checks a supplied validator address against the public key's derived address.
- `cometbft init --home <path>` creates an independent `priv_validator_key.json`, `node_key.json`, and starter Genesis under each home.
- `cometbft show-node-id --home <path>` is the pinned CLI operation used to derive the P2P node ID for persistent-peer strings.
- For four nodes on one loopback host, the pinned P2P config exposes `addr_book_strict` (set false for private/local networks) and `allow_duplicate_ip` (must be enabled to permit multiple peers from the same loopback IP). Each node must still have unique P2P and RPC ports.
- Persistent peer entries use `nodeID@host:port`; each node should list the other three node IDs/endpoints.

A new CI preflight was added:
- `scripts/cometbft_v040_four_validator_genesis_preflight.py` creates four isolated homes and keys in a temporary directory, checks unique validator addresses and P2P node IDs, constructs one byte-identical four-validator HND Genesis, and invokes the pinned Go validator.
- `scripts/cometbft_v040_genesis_validate.go` uses CometBFT's own `types.GenesisDocFromFile` from the cloned v0.40.0 module to parse the document and verify four validators.
- The workflow now runs this preflight after the existing single-node smoke test.

**Scope warning:** this preflight checks identities and Genesis schema only. It does not start four nodes, prove peer connectivity, commit blocks, test quorum continuation, or test catch-up. Those remain the actual WP4.5 multi-node integration acceptance tests.

## 12. WP4.5 live four-validator integration — passed 2026-11-01

**CI evidence:** [GitHub Actions run 41243674122](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41243674122)  
**Tested branch commit:** `d2f2eb609b223f40265ad16d4ae062930657b6ba`  
**Pinned consensus engine:** CometBFT v0.40.0  
**Result marker:** `COMETBFT_V040_FOUR_VALIDATOR_NETWORK_OK`

The workflow executed `scripts/cometbft_v040_four_validator_network_smoke.py` successfully. The harness created four isolated CometBFT homes and validator identities, four independent HND ABCI application processes/state files, and a shared four-validator chain configuration. All runtime keys and state were held in a temporary directory and were not retained as repository artifacts.

Observed results from the successful CI log:

- Four validators, each voting power 10 (total 40).
- All four nodes converged; initial committed height was 1.
- The signed transfer of 1,237 HND committed at height 2.
- Alice balance after transfer: 598,763 HND; Bob balance after transfer: 401,237 HND.
- Transaction block hash: `76DE3E39DFAE3E4F48837F3C184C4B09CBCA90FA58467851C0EF38B6E4CF0143`.
- With one validator and its application stopped, the remaining three continued to height 3.
- After restarting the stopped application and validator, it caught up; reported catch-up height was 4 and all four nodes converged.
- Final block hash: `F0209E38C0F4E66A9DF6BDF911303AD225754A26A5D85F5FA6C5D7DF22F2BB8A`.
- Application hash after transaction: `l4S3koPeJUCvKDJe0czbW+YtQgYShfilr4Y79nsZEKk=`.

**Acceptance decision:** The local four-validator crash-stop integration scenario in this document is implemented and passed in CI. This does not prove Byzantine fault tolerance, network-partition safety, malicious-validator resistance, production durability, state-sync snapshot support, or production readiness. The HND application persistence remains file-based prototype storage. No public deployment or real-value use is authorized.

The separate single-node and four-validator Genesis preflight steps also passed in the same workflow. The CI run checks out the tested branch commit shown above; `main` was not modified.
