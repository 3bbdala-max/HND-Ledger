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

## 5. What WP4.3 alone did not prove

At the time WP4.3 was completed, its adapter tests did not prove that a CometBFT node could initialize, commit a native block, or recover after restart. Those integration gaps were subsequently addressed by WP4.4.

## 6. Next milestone — WP4.4 completed; next gate is multi-validator testing

WP4.4 has now passed in GitHub Actions. See `docs/WP4_4_COMETBFT_V040_SINGLE_NODE_INTEGRATION_2026-10-31.md`.

**Successful CI run:** https://github.com/3bbdala-max/HND-Ledger/actions/runs/41242087625  
**Tested commit:** `ede5acf8a786d1d29e8af1d9c54b583f4446ec3f`.

The disposable CometBFT v0.40.0 one-validator integration:
- completed the node-to-ABCI gRPC startup handshake and HND Genesis initialization;
- accepted a signed 1,237 HND transfer with CheckTx code 0;
- committed it at native CometBFT height 2;
- changed the synthetic sender balance from 600,000 to 598,763 HND;
- stopped and restarted the application and node, then recovered the same committed height and account state;
- emitted `COMETBFT_V040_SINGLE_NODE_SMOKE_OK`.

The next engineering gate is a separately scoped multi-validator private test network with matching application hashes, validator restart/state synchronization, partition/delay tests, and validator-key/transport isolation. Single-node success does not prove distributed safety or BFT.

## 7. Release boundary

Development-only, single-process application integration. No public network, real token issuance, sale, trading, custody, validator rewards, production deployment, legal approval, or independent security audit is claimed.
