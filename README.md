# HND Ledger — recovered v0.1 baseline

This branch restores the HND v0.1 local educational prototype and its evidence.

## v0.1 baseline

- `hnd_prototype.py`: canonical integrity-fixed implementation.
- `archive/v0.1/hnd_prototype_pre_integrity_fix.py`: earlier implementation preserved for traceability.
- `test_hnd.py`: original 12-test suite.
- `docs/`: technical specification and security test report.

Run locally with Python 3.10+:

```bash
python -m pip install -r requirements.txt
python -m unittest -v test_hnd.py
```

## v0.2 isolated engineering reference

- `hnd_v02/transaction.py`: versioned Ed25519 transaction envelope, strict type checks, and candidate public-key-derived account IDs.
- `tests/test_v02_transaction_envelope.py`: local conformance tests for the isolated reference.
- `vectors/v0.2-transaction-envelope-example.json`: deterministic public test vector.
- `docs/WP1_V02_ACCOUNT_IDENTITY_DESIGN_2026-10-31.md`: account identity design, limits, and test record.
- `hnd_v02/genesis.py`: deterministic genesis-manifest validation against a separately pinned hash.
- `hnd_v02/ledger.py`: in-memory balances, signed transfers, nonce/replay checks, supply invariant, atomic JSON snapshot saving, and replay-verified file recovery.
- `tests/test_v02_ledger.py`: 21 ledger state-transition, persistence, and recovery tests.
- `hnd_v02/blocks.py`: deterministic block headers, parent links, transaction Merkle roots, and full local chain replay.
- `tests/test_v02_blocks.py`: block validation, atomic batch, chain integrity, and recovery tests.
- `hnd_v02/abci_app.py`: transport-independent HND application lifecycle core for a future ABCI adapter; it does not implement CometBFT networking or consensus.
- `tests/test_v02_abci_app.py`: 31 tests for proposal validation, committed/mempool isolation, finalize/commit lifecycle, and recovery.
- `docs/WP4_CONSENSUS_SELECTION_AND_FAULT_MODEL_2026-10-31.md`: CometBFT candidate and validator fault model.
- `docs/WP4_1_COMETBFT_ABCI_PYTHON_FEASIBILITY_2026-10-31.md`: pinned Python ABCI gRPC feasibility and integration plan.
- `docs/WP4_2_ABCI_APPLICATION_CORE_2026-10-31.md`: WP4.2 scope, limitations, and CI evidence.
- `hnd_v02/cometbft_v040_server.py`: Python ABCI gRPC transport for CometBFT v0.40.0.
- `scripts/generate_cometbft_v040_python.sh`: generates pinned v0.40.0 Python bindings and gogoproto dependency.
- `tests/test_v02_cometbft_v040_adapter.py`: 13 wire-level and real local gRPC tests.
- `docs/WP4_3_COMETBFT_V040_ABCI_GRPC_ADAPTER_2026-10-31.md`: WP4.3 scope, method mapping, limitations, and CI evidence.
- `docs/WP3_V02_BLOCK_CHAIN_REFERENCE_2026-10-31.md`: block format, hashing rules, test scope, and limitations.
- `docs/WP2_V02_LEDGER_REFERENCE_2026-10-31.md`: ledger design, limits, and test status.
- `.github/workflows/hnd-v02-tests.yml`: CI workflow for the isolated v0.2 suites.
- `tests/test_v02_genesis_manifest.py`: genesis validation tests.
- `vectors/v0.2-genesis-devnet-example.json`: synthetic two-account devnet fixture; not a public allocation.

Run the isolated v0.2 tests from the repository root:

```bash
python -m unittest -v tests.test_v02_transaction_envelope tests.test_v02_genesis_manifest tests.test_v02_ledger tests.test_v02_blocks tests.test_v02_abci_app tests.test_v02_cometbft_v040_adapter
```

The archived reports record the historical 3,000-transfer run; that run is not claimed as repeated here. HND v0.1 is a local educational prototype, and v0.2 is an isolated engineering reference. Neither is production software or an approved financial product. No public deployment, real funds, token sale, exchange listing, or payment integration is authorized.
