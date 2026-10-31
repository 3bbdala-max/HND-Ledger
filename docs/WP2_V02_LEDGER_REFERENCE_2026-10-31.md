# HND v0.2 — In-memory ledger and recovery reference

**Date:** 2026-10-31  
**Workstream:** WP2 — Ledger state transitions  
**Status:** Experimental in-memory reference; GitHub Actions completed successfully for the 48-test v0.2 suite.  
**Branch:** phase-0.2-planning

## 1. Scope

This module connects the previously isolated transaction-envelope and genesis-manifest validators into one local ledger, with in-memory state and atomic JSON snapshot files. It initializes balances from a validated manifest, tracks account nonces, validates signed transfers, prevents transaction replay, preserves total supply, and supports deterministic snapshot/recovery by replaying transaction history from genesis.

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

The ledger can atomically save a JSON snapshot to a sibling temporary file and replace the destination. Loading replays every signed transaction from the pinned Genesis and compares rebuilt balances, nonces, accepted IDs, history, and state hash. Snapshot accessors return detached history so callers cannot mutate the live ledger. This remains a simple local-file mechanism, not a transactional database; directory-level crash guarantees, schema migrations, file locking, backup management, and authenticated snapshot distribution are not implemented.

## 4. Tests

The original ledger suite contains 13 test cases covering genesis initialization, successful transfers, sequential nonces, duplicate/replayed transactions, stale nonce rejection, overspending, unknown recipients, invalid signatures, snapshot round-trip recovery, snapshot tampering, wrong genesis binding, and unknown account views.

The complete isolated v0.2 suite ran in GitHub Actions on 2026-10-31: **48 tests passed, 0 failed** (22 transaction/account-identity tests, 13 genesis tests, and 13 ledger tests). The workflow job completed with conclusion `success`. This is automated CI evidence for the committed test suite, not an independent security audit or proof of production readiness.

Latest workflow run: https://github.com/3bbdala-max/HND-Ledger/actions/runs/41232371189

The extended ledger suite adds 8 cases for atomic file save/load, malformed files, wrong Genesis binding, re-hashed balance tampering, strict snapshot types, detached history, and 2,000 signed transfers. The extended 21-case ledger suite passed locally. The complete isolated v0.2 suite then passed in GitHub Actions: **56 tests passed, 0 failed** (22 transaction/account-identity tests, 13 Genesis tests, and 21 ledger/persistence tests). Workflow run 41232371189 completed with conclusion `success` for commit `6a722f6bf5da27281d882475ef3b36acb7081848`.

## 5. Limitations

- The live state is held in process memory; snapshots can be written to local JSON files and reconstructed by replay.
- No blocks, peer discovery, networking, distributed consensus, validator selection, or Byzantine fault tolerance exist.
- The account registry is created only from the Genesis manifest.
- The state hash is a deterministic integrity checksum, not a Merkle tree or proof system.
- Replay-based restoration is correct for this reference model but not optimized for long histories; snapshots do not yet use checkpoints.
- The Genesis hash must be pinned through a trusted release/configuration channel.
- No independent security audit, cross-language implementation, fuzzing campaign, or production threat model has been completed.

## 6. Release boundary

This is an experimental local engineering reference. It does not issue, mint, sell, distribute, custody, or activate any asset. No real funds or public network are in scope. v0.1 and main remain unchanged.
