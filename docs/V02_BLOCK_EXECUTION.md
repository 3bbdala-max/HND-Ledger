# HND v0.2 block execution and replay verification

**Status:** Local deterministic execution prototype implemented on the working branch. No distributed consensus or durable chain database is included.

## Inputs

A block is built from:

- a canonical parent block header and its expected 32-byte hash;
- the parent account balance map;
- the parent account nonce map;
- an ordered list of signed HND v0.2 transactions;
- a proposed timestamp.

The parent header is decoded and re-encoded under the strict block-header profile. Its hash must match the supplied parent hash. The timestamp must be a uint64 and cannot be earlier than the parent timestamp. The next height is exactly parent height plus one.

## State transition

Transactions are submitted to a fresh ledger restored from the supplied parent balances and nonces. They are processed in list order. Each transaction must pass the existing chain-ID, account-key ownership, Ed25519 signature, amount, nonce, replay, balance, and overflow checks.

The parent maps are not mutated. If any transaction fails, block construction fails and no resulting state is returned.

After all transactions are accepted, the implementation computes:

- the ordered transaction Merkle root from transaction IDs;
- the account state root from sorted account IDs, balances, and nonces;
- the next canonical block header;
- the domain-separated block hash.

## Independent replay

`verify_block` repeats execution from the supplied parent state and compares the recomputed canonical header and block hash with the candidate values. A matching hash alone is not treated as proof of valid execution.

## Implementation

- State-transition engine: `hnd_ledger/chain.py`
- Restorable ledger snapshots: `hnd_ledger/ledger.py`
- Block, genesis, and root primitives: `hnd_ledger/blocks.py`
- Tests: `tests/test_chain.py`

## Current limitations

This is a single-process deterministic execution routine. It does not provide peer-to-peer networking, consensus, validator election, fork choice, mempool policy, durable storage, crash recovery, state snapshots on disk, or production key custody. It is not yet a complete blockchain node.

A full independent audit still requires successful execution of the committed test suite on the exact reviewed commit, a clean-room reproduction by a third party, and a security review of protocol edge cases.
