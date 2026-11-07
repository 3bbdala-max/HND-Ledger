# HND v0.2 implementation status

**Status:** initial local prototype implementation and validator design documents; not production-ready.

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

## Design documents added

- Threat model with assets, trust boundaries, threats, controls, and release gates.
- Validator and consensus design gate. CometBFT is an evaluation candidate only, not a selected or integrated dependency.
- Distributed-consensus test matrix. All entries are planned tests, not executed results.

## Not yet implemented

- Independent validators, validator registration, voting, consensus, fork choice, or peer-to-peer networking.
- Block production across multiple nodes or multi-writer coordination.
- Wallet, RPC/API, explorer, public network, or production genesis allocation.
- Crash fault-injection, backup/restore procedures, schema migrations, or external security audit.
- Economic review, legal review, or authorization to issue or trade a token.

## Verification status

- GitHub Actions run `42342012227` completed successfully on commit `6319630828ab0893e981bacc8472f60741245bf2`.
- Python 3.12 dependency installation completed successfully.
- The full pytest suite completed successfully: **30 tests passed**.
- The passing suite includes protocol and state validation, chain append/recovery, multiple sequential transactions in one block, genesis supply-cap binding, canonical storage checks, tamper detection, and block transaction-count/encoded-size limits.
- This is automated prototype verification only; it is not an independent security audit or a distributed-network test.

## Important scope limitation

This is a deterministic, single-process local prototype. It does not establish decentralization, Byzantine fault tolerance, production security, or readiness for public launch.
