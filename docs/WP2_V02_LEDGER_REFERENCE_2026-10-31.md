# HND v0.2 — In-memory ledger and recovery reference

**Date:** 2026-10-31  
**Workstream:** WP2 — Ledger state transitions  
**Status:** Experimental in-memory reference; CI verification is triggered by the commit that adds this file.  
**Branch:** phase-0.2-planning

## 1. Scope

This module connects the previously isolated transaction-envelope and genesis-manifest validators into one in-memory ledger. It initializes balances from a validated manifest, tracks account nonces, validates signed transfers, prevents transaction replay, preserves total supply, and supports deterministic snapshot/recovery by replaying transaction history from genesis.

It is not a peer-to-peer network, block format, persistent database, validator implementation, or consensus engine.

## 2. State transition

For every proposed transfer, the ledger:

1. Requires sender and recipient to exist in the genesis account registry.
2. Rejects duplicate transaction IDs.
3. Validates network/version, sender identity, registered public key, signature, exact nonce, amount and balance.
4. Computes the proposed new balances and nonce before mutating state.
5. Applies the transfer, records the transaction, checks the total-supply invariant, and recalculates the deterministic state hash.

The total supply is required to remain equal to the Genesis total after every accepted transfer. No mint, burn, fee, or administrator override operation exists in this reference.

## 3. Snapshot and recovery

A snapshot contains protocol/network identifiers, the pinned genesis hash, total supply, balances, nonces, accepted transaction IDs, transaction history, and a state hash.

Recovery does not trust the serialized balances or nonce counters. It initializes from the validated genesis manifest, replays each signed transaction in order, and compares the resulting balances, nonces, accepted IDs, history, and state hash with the supplied snapshot. Tampered state is rejected.

The snapshot is an in-memory JSON-compatible structure. Durable file storage, atomic filesystem writes, crash consistency, schema migrations, and backup management are not implemented.

## 4. Tests

The new ledger suite contains 13 test cases covering genesis initialization, successful transfers, sequential nonces, duplicate/replayed transactions, stale nonce rejection, overspending, unknown recipients, invalid signatures, snapshot round-trip recovery, snapshot tampering, wrong genesis binding, and unknown account views.

A Python syntax compilation check was performed for the new ledger module and its tests. The complete unit suite is configured to run in GitHub Actions by the workflow added in this commit. Do not treat the CI run as successful until its status is checked after the push.

## 5. Limitations

- All state is held in process memory.
- No blocks, peer discovery, networking, distributed consensus, validator selection, or Byzantine fault tolerance exist.
- The account registry is created only from the Genesis manifest.
- The state hash is a deterministic integrity checksum, not a Merkle tree or proof system.
- Replay-based restoration is correct for this reference model but not optimized for long histories.
- The Genesis hash must be pinned through a trusted release/configuration channel.
- No independent security audit, cross-language implementation, fuzzing campaign, or production threat model has been completed.

## 6. Release boundary

This is an experimental local engineering reference. It does not issue, mint, sell, distribute, custody, or activate any asset. No real funds or public network are in scope. v0.1 and main remain unchanged.
