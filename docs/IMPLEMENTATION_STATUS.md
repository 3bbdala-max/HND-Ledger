# HND v0.2 implementation status

**Status:** deterministic local ledger prototype with a tested Python application-lifecycle facade; not production-ready.

## Implemented in this branch

- Python package scaffold targeting Python 3.11+.
- Ed25519 transaction signing and verification using the maintained `cryptography` library.
- Canonical CBOR transaction serialization and strict re-encoding checks.
- Domain-separated account identifiers, transaction signing messages, state commitments, genesis identifiers, and block identifiers.
- Chain-ID binding, sender/public-key binding, uint64 amount and nonce validation.
- Atomic local balance transfers with sequential nonces, insufficient-funds rejection, overflow checks, and supply-cap invariant.
- Deterministic blocks with sequential heights, parent hashes, transaction bytes, and state roots.
- SQLite persistence and restart recovery by replaying every stored block from the genesis snapshot.
- ABCI++-style Python application lifecycle facade with isolated proposal/finalized candidate state; see `ABCI_APPLICATION_BOUNDARY.md`.
- Weak CheckTx admission semantics: canonical encoding, chain ID, and signature are checked without reserving nonces or applying state-dependent balance checks.
- GitHub Actions workflow for Python 3.12 test execution.

## Design decisions

- CometBFT v0.40.0 is pinned as the candidate ABCI++ integration version.
- The selected topology uses CometBFT's official Go ABCI socket server as a thin transport adapter, with Python retaining all HND transaction and state-transition rules. See `ABCI_TRANSPORT_DESIGN.md`.
- The Go adapter, private IPC protocol, CometBFT process, and multi-node consensus are not yet implemented.
- Distributed-consensus test matrix entries are planned tests, not executed results.

## Not yet implemented

- ABCI protobuf/socket transport and CometBFT process integration.
- A versioned private IPC service between the Go adapter and Python engine.
- CometBFT InitChain/genesis lifecycle integration and production genesis allocation.
- Independent validators, validator registration, voting, consensus, fork choice, or peer-to-peer networking.
- Block production across multiple nodes or multi-writer coordination.
- Wallet, RPC/API, explorer, public network, or public token distribution.
- Crash fault-injection, backup/restore procedures, schema migrations, or external security audit.
- Economic review, legal review, or authorization to issue or trade a token.

## Verification status

- GitHub Actions run [42344708044](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42344708044) completed successfully on commit `57eb4ee01111e277cd97112c2f7dd459c465dbd3`.
- The workflow's Python 3.12 test job completed successfully, including dependency installation and the automated test step.
- The latest verified code test run [42344679339](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42344679339) completed successfully on code commit `29ae7ec7bee8cbea8b11469407ec48ab7be006a6`: **38 tests passed**.
- Subsequent commits `809c8ee` and `57eb4ee` updated documentation only; their GitHub Actions runs also completed successfully.
- The passing suite is automated prototype verification only; it is not an independent security audit or a distributed-network test.

## Important scope limitation

This remains a deterministic, single-process local prototype. It does not establish decentralization, Byzantine fault tolerance, production security, or readiness for public launch.
