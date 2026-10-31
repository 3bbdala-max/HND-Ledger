# HND v0.2 — WP4.4 CometBFT v0.40.0 single-node integration

**Date:** 2026-10-31  
**Workstream:** WP4.4 — native CometBFT single-node integration  
**Status:** Passed in GitHub Actions for the recorded commit and disposable CI environment  
**Branch:** `phase-0.2-planning`

## 1. Scope and method

The CI job builds the CometBFT binary from the pinned `v0.40.0` source tag, generates the matching Python ABCI protobuf bindings, starts the HND Python ABCI gRPC application on loopback, and launches a disposable one-validator CometBFT node.

All validator keys, HND test keys, node home, Genesis, and application persistence data are created inside a temporary directory. The smoke test does not use real funds, persistent private keys, a public network, or a public token.

The test uses a synthetic development network ID:

`hnd-cometbft-v040-smoke`

The test fixture begins with Alice at 600,000 HND and submits a signed transfer of 1,237 HND.

## 2. Verified CI evidence

**Workflow run:** https://github.com/3bbdala-max/HND-Ledger/actions/runs/41242087625  
**Tested commit:** `ede5acf8a786d1d29e8af1d9c54b583f4446ec3f`  
**Single-node job:** `124658015716`  
**Workflow conclusion:** success  
**Jobs:** `hnd-v02-tests` and `cometbft-single-node-smoke` both succeeded.

The job log contains the following direct evidence:

- `HND_ABCI_GRPC_PREFLIGHT_OK`
- `HND_COMETBFT_GO_GRPC_PROBE_OK`
- `HND_ABCI_INFO` reports HND application version `HND-v0.2`, app version 2, and initial committed height 1.
- `HND_BROADCAST_RESULT` reports JSON-RPC result code 0 and log `ok`.
- The native CometBFT block height after the transaction is 2.
- Alice's balance is 600,000 HND before the transfer and 598,763 HND after it.
- After stopping and restarting the HND application and CometBFT node, the native CometBFT height remains 2 and HND committed height remains 2.
- The script emits `COMETBFT_V040_SINGLE_NODE_SMOKE_OK`.

The final machine-readable result recorded by the smoke script:

| Field | Verified value |
|---|---:|
| Initial CometBFT height | 1 |
| Height after transaction | 2 |
| Height after restart | 2 |
| HND committed height after restart | 2 |
| Alice balance before | 600,000 HND |
| Transfer amount | 1,237 HND |
| Alice balance after | 598,763 HND |
| Result marker | `COMETBFT_V040_SINGLE_NODE_SMOKE_OK` |

The application state hash recorded after restart is `b9afb4ea6a6042d80f4c991e45af5b00584050248571ab26a33fed1ac37a4f39`. The development Genesis manifest hash is `a3965a54f4431cacb6e677bf5b5ce07b901118508706ecc7981083bba15e541f`.

## 3. Corrections made during integration

The integration work exposed two HTTP JSON-RPC test-client issues:

1. CometBFT's `broadcast_tx_sync` accepts the transaction as a JSON-RPC `[]byte` value. The test client was changed to send a JSON-RPC POST request with the Base64 string as the parameter value, rather than encoding a string through a GET query parameter.
2. The broadcast response exposes the CheckTx result directly under `result`; the smoke script now reads that response shape and fails immediately if its code is non-zero.

These changes are in the tested commit above. The successful log confirms the transaction was accepted and committed.

## 4. What this milestone proves

For this exact code revision and disposable CI setup, it proves:
- the built CometBFT v0.40.0 node starts and communicates with the HND ABCI gRPC application;
- the HND application initializes from the node's development Genesis configuration;
- a signed HND transaction is accepted through the CometBFT JSON-RPC endpoint and committed at native block height 2;
- the account query reflects the committed transfer;
- the HND application state is recovered after stopping and restarting the application and node.

## 5. What this milestone does not prove

This is a **single-node integration smoke test**, not a production network or independent security audit. It does not prove:
- multi-validator agreement, Byzantine fault tolerance, or liveness under partitions;
- peer-to-peer network security, validator admission/governance, or production key custody;
- production database durability, backup/restore, or operational crash guarantees beyond the tested restart path;
- performance, load capacity, denial-of-service resistance, or long-term stability;
- legal approval, public token issuance, exchange listing, or readiness to handle real funds.

The test's synthetic accounts, keys, and chain ID are disposable engineering fixtures. The result must not be described as a mainnet launch or a public financial asset.

## 6. Next engineering gate

Proceed to a separately scoped multi-validator private test network only after documenting validator configuration and a fault model. The next tests must cover at least:
- multiple independent nodes and matching committed application hashes;
- validator shutdown/restart and state synchronization;
- network delay, message loss, and partition scenarios;
- conflicting or invalid transactions and deterministic rejection;
- validator key isolation and private-network transport protection.

Keep all work on `phase-0.2-planning`. Do not merge to `main` or enable public deployment without a separate explicit review and approval.
