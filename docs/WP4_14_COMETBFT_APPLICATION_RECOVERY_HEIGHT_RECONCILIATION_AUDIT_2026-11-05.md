# HND v0.2 — CometBFT/application recovery-height reconciliation audit

**Date:** 2026-11-05  
**Workstream:** WP4.14 — Startup recovery and cross-store consistency  
**Branch:** `phase-0.2-planning`  
**Status:** Documentation-only static review. No application code, tests, or workflow files changed.

## 1. Executive result

The HND ABCI adapter reports the application store's persisted height and app hash through CometBFT's ABCI `Info` response. The adapter does not independently read CometBFT's native block-store/state height or compare the two stores before serving.

The repository contains application-level restart tests that verify the HND store's own height, app hash, and ledger state. The inspected four-validator Genesis preflight explicitly does not start nodes. The inspected adapter tests exercise the HND application lifecycle but do not establish a restart integration test in which CometBFT's native state/block store and the HND application store are deliberately made inconsistent.

This is an **integration-evidence and operational startup-gate gap**, not proof that CometBFT v0.40.0 lacks its own ABCI handshake/replay checks. The exact behavior of the pinned CometBFT binary must be demonstrated by an integration test; it must not be inferred from the Python adapter alone.

## 2. Source reviewed

At the reviewed branch head:

- `hnd_v02/cometbft_v040_server.py`
  - `HNDCometBFTv040Servicer.Info()` returns `application.info()` values directly.
  - `main()` creates the HND application and starts the gRPC server; it does not inspect CometBFT's native database.
  - `--recovery` requires an existing HND state file, but it is an explicit CLI option rather than an unconditional startup mode.
- `hnd_v02/abci_app.py`
  - `info()` reports `_last_committed_height` and `_committed_app_hash`.
  - `_load_store()` verifies the local store checksum, Genesis/network identity, ledger snapshot, evidence journal, and app hash.
- `tests/test_v02_abci_app.py`
  - Covers HND application restart, committed height/hash recovery, and local storage fault scenarios.
- `scripts/cometbft_v040_four_validator_genesis_preflight.py`
  - Explicitly states that it is a Genesis/identity preflight and that no nodes are started.

No test command was run for this report.

## 3. What is already protected

1. The HND application persists the committed height together with the ledger snapshot, evidence journal, and application hash.
2. The local store hash binds the persisted recovery metadata to the snapshot payload; tampering with the height without resealing is rejected.
3. The loader reconstructs and verifies the ledger from its signed transaction history and checks the calculated application hash.
4. The ABCI `Info` endpoint reports the recovered HND application height and app hash rather than silently resetting a valid loaded store to height zero.
5. The adapter's `Info` method does not synthesize a height from an unrelated local counter; it forwards the application result.

These are application-store guarantees. They do not, by themselves, prove that the native CometBFT block store and state database are at the same recovery point.

## 4. Identified gap

There is no inspected repository test that starts the pinned CometBFT v0.40.0 node against the HND ABCI server, creates committed blocks, stops the node, and then tests restart with controlled divergence between:

- CometBFT native state/block-store height and last block app hash; and
- HND application's persisted `last_committed_height` and `last_block_app_hash`.

Consequently, the repository evidence does not yet establish the exact behavior for these cases:

- application height equals CometBFT height and hashes match;
- application is behind CometBFT;
- application is ahead of CometBFT;
- heights match but app hashes differ;
- application state file is missing on a restart path;
- application state is restored from an older backup while CometBFT's database remains newer;
- CometBFT database is restored from an older backup while HND application state remains newer.

The local `store_hash` is an integrity checksum, not an authenticated anti-rollback anchor. A complete older valid HND store can therefore still be internally self-consistent. Cross-store reconciliation and an independent recovery policy are required to detect/handle that situation.

## 5. Required integration acceptance matrix

Run these tests with the exact pinned CometBFT v0.40.0 binary and retain native logs, database heights, ABCI Info values, app hashes, and final process status.

| ID | Setup | Required evidence / safe outcome |
|---|---|---|
| HREC01 | Fresh Genesis; start node and commit several blocks | CometBFT and HND heights/app hashes agree at the documented handshake boundary |
| HREC02 | Clean shutdown and restart with both stores intact | Restart resumes without losing or reapplying committed transactions |
| HREC03 | HND application store one height behind native CometBFT state | Demonstrate the pinned CometBFT replay/reconciliation behavior; final app hash and height must match the native committed chain |
| HREC04 | HND application store one height ahead of native CometBFT state | Node must not serve a divergent state; capture the exact fail-closed behavior |
| HREC05 | Same height, deliberately mismatched HND app hash | Startup must reject or follow a precisely documented safe recovery path; no silent acceptance |
| HREC06 | Restore an older but internally valid HND state backup | Detect the rollback relative to native CometBFT state or an independent trusted checkpoint; no silent signing/serving |
| HREC07 | Restore an older CometBFT database while HND state is newer | Detect mismatch and block; no automatic truncation or overwrite without a separately approved recovery procedure |
| HREC08 | Restart with missing HND state and recovery mode enabled | Startup fails closed; it must not initialize a new empty application state |
| HREC09 | Restart with missing HND state and recovery mode omitted | Demonstrate why this is prohibited for an established chain, or enforce a production launcher policy that always enables recovery mode |

For each case, capture:
- CometBFT version and binary checksum;
- CometBFT native state and block-store heights;
- HND `Info.last_block_height` and `Info.last_block_app_hash`;
- CometBFT's expected/recorded last app hash, where exposed by the pinned version;
- startup logs and whether the node began accepting/serving requests;
- resulting HND state hash and representative account/nonces after recovery.

## 6. Recommended disposition

1. Add a real CometBFT v0.40.0 restart integration harness; the current Genesis preflight is not a substitute.
2. Verify the pinned CometBFT handshake behavior for lower, equal, and higher application heights and for app-hash mismatch. Record exact source/version and observed outcomes.
3. Define a production launcher policy that always requires an existing HND state file on established-chain restarts; reserve fresh-state initialization for explicit first-boot Genesis ceremony only.
4. Treat any unresolved height/hash mismatch as a recovery incident. Do not automatically reset, truncate, replay from an untrusted point, or overwrite either store.
5. Keep independent anti-rollback checkpointing separate from the local HND `store_hash`; a self-contained checksum cannot prove that a valid snapshot is the newest one.

No source/test changes are authorized or made by this review.

## 7. Release boundary

The repository currently demonstrates local HND application persistence/restart behavior, not complete cross-store crash recovery against a running CometBFT node. Until HREC01–HREC09 are executed and reviewed on the pinned binary, the cross-store recovery gate remains open and production validator operation is not certified.
