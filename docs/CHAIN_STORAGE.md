# HND v0.2 local block and storage design

## Scope

This module adds a single-process, SQLite-backed local chain. It is a development harness, not peer-to-peer networking, distributed consensus, or a validator implementation.

## Block commitment

Each block has a sequential height, previous block hash, exact canonical signed-transaction byte strings, and resulting state commitment. The block identifier is SHA-256 over the domain-separated canonical CBOR tuple:

`[2, height, previous_hash, transaction_bytes[], state_root]`

The state commitment is SHA-256 over `HND-STATE-V2\0` and canonical CBOR of account rows sorted by account identifier. Each row contains account identifier, balance, and next expected nonce.

The genesis identifier commits to protocol version, chain identifier, supply cap, and the initial state commitment. The supply cap is included so two chains with identical initial balances but different issuance limits cannot share a genesis identifier.

## Persistence and recovery

SQLite stores the canonical genesis snapshot and each encoded block. On reopen, the implementation starts from the stored genesis state and replays every block in height order. It checks the parent link, transaction signatures and chain ID, nonce and balance rules, state commitment, and block identifier before accepting the recovered state.

A block is validated against a candidate copy of state before the database transaction is committed. A rejected block must not alter the live state or append to the database.

## Limitations

- No consensus, validator voting, fork choice, networking, or multi-writer coordination.
- No wall-clock timestamp is included in block identity; block ordering is deterministic by height.
- SQLite durability settings, crash fault-injection, schema migrations, and backup/restore procedures still require dedicated testing.
- The genesis snapshot is local bootstrap data, not a public token allocation decision.
- Passing local tests would not constitute a security audit or production-readiness evidence.
