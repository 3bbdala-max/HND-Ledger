# HND v0.2 durable local chain storage

**Status:** SQLite reference implementation added on the working branch. It is a single-host persistence layer, not distributed consensus or a production node.

## Database contract

`SQLiteChainStore` stores:
- an immutable metadata record binding the database format, 32-byte chain ID, canonical genesis header/hash, and canonical initial account state;
- one row per non-genesis block, containing height, canonical header, block hash, and a length-prefixed sequence of canonical signed transactions.

The store refuses to reopen a database with a different chain ID or genesis allocation. The genesis state is checked against the state root committed in the genesis header.

## Atomic append

Every append uses SQLite `BEGIN IMMEDIATE`. Before adding a block, the store replays the existing chain from genesis, validates each stored transaction and block, reconstructs balances/nonces, and verifies parent links. It then builds the proposed next block using the same deterministic execution engine and inserts the complete block row before committing.

If validation or insertion fails, the SQLite transaction is rolled back. WAL mode and `synchronous=FULL` are configured for local durability. SQLite's own integrity check is run as part of `verify()`.

## Independent reconstruction

A new process can instantiate the store with the same database path, chain ID, and genesis allocations. `get_state()`, `get_tip()`, and `verify()` reconstruct and validate the chain by replay; they do not trust a cached balance snapshot.

The stored transaction framing is deliberately simple: each canonical signed transaction is preceded by a four-byte big-endian length. Per-transaction, per-block, and transaction-count limits are enforced before decoding. Heights are bounded to SQLite's signed 64-bit integer range even though the header encoding itself supports uint64.

## Reproduction

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

The storage regression tests cover multi-block append, process-style close/reopen, deterministic replay, nonce continuity, invalid-block rollback, genesis mismatch, persisted-hash tampering, preflight rejection of oversized transaction sets before database access or transaction decoding, concurrent append serialization, and recovery after a child process terminates with an uncommitted block row. This is a process-termination simulation, not a physical power-loss or filesystem fault-injection test.

## Limitations and next gates

- This is a single-host SQLite reference store; no multi-node replication or consensus is implemented.
- Full replay on each append is intentionally conservative and will become expensive as the chain grows. A later optimization may add authenticated snapshots, but only with replay-equivalence tests.
- WAL and `synchronous=FULL` improve local crash durability but do not replace filesystem, disk, backup, or disaster-recovery testing.
- No production key custody, public networking, mempool, fork choice, validator selection, or release authorization is provided.
- Independent clean-room execution of the complete test suite on the exact commit remains mandatory.
