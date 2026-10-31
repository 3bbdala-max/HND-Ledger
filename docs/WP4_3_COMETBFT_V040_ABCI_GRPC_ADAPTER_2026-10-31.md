# HND v0.2 — WP4.3 CometBFT v0.40.0 ABCI gRPC adapter

**Date:** 2026-10-31  
**Workstream:** WP4.3 — pinned ABCI gRPC transport  
**Status:** Implemented; generated from the exact CometBFT tag; wire-tested in CI  
**Branch:** `phase-0.2-planning`

## 1. Implementation

Added `hnd_v02/cometbft_v040_server.py`, a Python gRPC server implementing the `tendermint.abci.ABCI` service from CometBFT v0.40.0.

The server delegates all HND state transitions to `HNDABCIApplication`; it does not implement a second ledger or consensus algorithm.

Added `scripts/generate_cometbft_v040_python.sh`. It:
- clones CometBFT tag `v0.40.0`;
- clones Cosmos gogoproto tag `v1.7.2`;
- generates Python message and gRPC bindings from the complete tagged `proto/tendermint` tree and the imported `gogoproto/gogo.proto`;
- uses the Google protobuf includes bundled with the pinned `grpcio-tools` package;
- writes generated bindings to `hnd_v02/_cometbft_v040`.

Generated code is intentionally not committed. It is reproducibly generated in CI and locally with the same script. The tag and dependency are pinned; the script prints their resolved commit hashes.

## 2. ABCI method mapping

| CometBFT v0.40.0 RPC | HND behavior |
|---|---|
| Echo / Flush | Standard echo / empty flush response |
| Info | Returns HND app version, committed height, and 32-byte application hash |
| InitChain | Checks chain ID and canonical, pinned HND Genesis payload |
| CheckTx | Validates transaction against the isolated mempool view |
| PrepareProposal | Selects valid ordered transactions within CometBFT's byte budget |
| ProcessProposal | Deterministically accepts/rejects against committed HND state |
| ExtendVote | Returns an empty extension |
| VerifyVoteExtension | Accepts only empty extensions |
| FinalizeBlock | Executes decided transactions in temporary state and returns tx results plus app hash |
| Commit | Persists the pending HND state and returns the v0.40.0 Commit response |
| Query | Supports `/height` and `/account`; proof queries are explicitly unsupported |
| Snapshot RPCs | Explicitly report no snapshots / reject snapshot restore |
| InsertTx / ReapTxs | App-side mempool is disabled; these methods return unsupported/empty behavior |

The test configuration must keep CometBFT's normal `flood` mempool. Do not set `mempool.type = "app"` until HND implements and tests the separate `InsertTx`/`ReapTxs` queue lifecycle.

## 3. Concurrency and network exposure

- The gRPC server uses a worker pool with a minimum of four workers; default is 16.
- The HND application core serializes shared state access with its re-entrant lock and uses isolated proposal copies.
- The server defaults to `127.0.0.1:26658`.
- This endpoint uses insecure gRPC to match the local CometBFT development setup. Do not expose it to the public internet. Multi-host deployment requires a private protected network or authenticated encrypted transport and a separate threat-model review.

## 4. Tests and CI

Added `tests/test_v02_cometbft_v040_adapter.py` with **13 tests**, including:
- protobuf request/response mapping for Info, InitChain, CheckTx, proposal handling, FinalizeBlock, Commit, Query, vote extensions, and snapshot behavior;
- explicit rejection of app-mempool-only operations;
- a real local gRPC server/client Echo round-trip;
- four concurrent gRPC Info requests.

The CI workflow installs the pinned Python gRPC/protobuf tooling, generates the CometBFT v0.40.0 bindings from tagged sources, then runs the full v0.2 suite.

**Successful CI result:** 122 tests passed, 0 failed, in 9.751 seconds.  
Run: https://github.com/3bbdala-max/HND-Ledger/actions/runs/41234446227  
Tested code commit: `8e49d924dcbcb547fc13c8b5819770f421290392`.

The first wire-test run found that the generator had omitted the imported `gogoproto/gogo.proto` file. The generator was corrected to generate that dependency too; the successful run above uses the corrected generator.

## 5. What is not proven

This milestone does **not** yet prove:
1. A CometBFT v0.40.0 node can connect to and complete its startup handshake with this Python server.
2. CometBFT can initialize the application from a real node Genesis file.
3. A transaction can be broadcast through the node, included in a native CometBFT block, committed, and queried after restart.
4. Multiple independent nodes converge on the same app hash.
5. Four-validator safety/liveness under crash, partition, Byzantine, or delayed-message scenarios.

The current end-to-end gRPC test is a Python client calling the real local server; it is not a CometBFT node test.

## 6. Next milestone — WP4.4

Run a pinned CometBFT v0.40.0 single-node integration:
- obtain/build the exact v0.40.0 binary and verify its checksum/provenance;
- create a disposable one-validator development Genesis with a fixed chain ID and the exact HND application Genesis bytes/hash;
- start the Python server on loopback and CometBFT with gRPC ABCI;
- prove Echo/Info startup handshake, InitChain, one signed HND transaction, native block commit, Info/Query after commit, and restart recovery;
- record native CometBFT height/hash separately from HND application hash.

Only after the single-node integration passes should the four-validator network be created.

## 7. Release boundary

Development-only, single-process application integration. No public network, real token issuance, sale, trading, custody, validator rewards, production deployment, legal approval, or independent security audit is claimed.
