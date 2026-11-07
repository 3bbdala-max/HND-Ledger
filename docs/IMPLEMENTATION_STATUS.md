# HND v0.2 implementation status

**Status:** initial local prototype implementation; not production-ready.

## Implemented in this branch

- Python package scaffold targeting Python 3.11+.
- Ed25519 transaction signing and verification using the maintained `cryptography` library.
- Canonical CBOR transaction serialization and strict re-encoding checks.
- Domain-separated account identifiers, transaction signing messages, state commitments, genesis identifiers, and block identifiers.
- Chain-ID binding, sender/public-key binding, uint64 amount and nonce validation.
- Atomic local balance transfers with sequential nonces, insufficient-funds rejection, overflow checks, and supply-cap invariant.
- Deterministic blocks with sequential heights, parent hashes, transaction bytes, and state roots.
- SQLite persistence and restart recovery by replaying every stored block from the genesis snapshot.
- Tests for protocol validation, ledger invariants, block restoration, rejected-block atomicity, and persisted-block tampering.
- GitHub Actions workflow definition.

## Not yet implemented

- Independent validators, validator registration, voting, consensus, fork choice, or peer-to-peer networking.
- Block production across multiple nodes or multi-writer coordination.
- Wallet, RPC/API, explorer, public network, or production genesis allocation.
- Crash fault-injection, backup/restore procedures, schema migrations, or external security audit.
- Economic review, legal review, or authorization to issue or trade a token.

## Verification status

The test suite is committed but has not yet been run successfully in a controlled environment. The current execution environment lacks the `cbor2` dependency, and no passing GitHub Actions result has been observed. A workflow definition is not evidence of a passing run.

## Important scope limitation

This is a deterministic, single-process local prototype. It does not establish decentralization, Byzantine fault tolerance, production security, or readiness for public launch.
