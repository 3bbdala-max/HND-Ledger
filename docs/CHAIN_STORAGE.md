# HND v0.2 local block and storage design

## Block commitment

A block ID is a domain-separated SHA-256 digest over canonical CBOR of [2, height, previous_hash, transaction_bytes[], state_root].

The state commitment uses HND-STATE-V3 and canonical CBOR of [2, chain_id, supply_cap, sorted_account_rows]. Each account row contains account ID, balance, and next expected nonce. Chain ID and supply cap are part of the application hash.

## Genesis and persistence

SQLite stores the canonical genesis snapshot, genesis hash, CometBFT genesis marker, and committed encoded blocks. Funded genesis state and marker are persisted in one transaction. Each validator runs its own SQLite database; databases are not shared across validator processes.

Blocks are limited to 1,000 transactions and 64 KiB of encoded payload. On reopen, the implementation starts from the stored genesis snapshot and replays blocks in height order, checking canonical CBOR, parent link, transaction signatures and chain ID, nonce/balance rules, state commitment, block identifier, and stored hash agreement.

A candidate block is validated against a copy of state before database persistence. The committed in-memory state is advanced only after the SQLite transaction succeeds. A rejected or failed block write must not alter committed state.

The Python test suite includes a SQLite trigger abort and a child process forcibly terminated from inside an uncommitted block-insert transaction. Reopening the database rolls back the incomplete transaction and restores the original genesis state with no block row. This is one tested crash point, not a full process-kill/power-loss campaign.

## Compatibility and limitations

Pre-v3 state-root databases are incompatible with the current v3 state commitment. No automatic migration is implemented; treat old local development databases as disposable.

No complete crash-injection campaign, backup/restore procedure, database migration, snapshot/state sync, or external rollback checkpoint is complete. SQLite is a per-validator local store, not a shared multi-writer database.
