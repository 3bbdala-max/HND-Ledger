# HND v0.2 deterministic genesis and block-header profile

**Status:** Implemented on the working branch. This is a local deterministic data-format prototype, not a consensus protocol or production blockchain.

## Genesis encoding

Genesis is encoded as a deterministic CBOR array:

`[protocol_version, chain_id, allocations]`

- `protocol_version`: unsigned integer 2.
- `chain_id`: exactly 32 bytes.
- `allocations`: array of two-element arrays `[account_id, balance]`.
- `account_id`: exactly 32 bytes.
- `balance`: unsigned 64-bit integer in smallest HND units.

Allocations are sorted by the raw account-ID bytes before encoding. This makes the genesis payload independent of input mapping insertion order. The sum of allocations cannot exceed 100,000,000,000,000 smallest units (the current 1,000,000 HND design cap at 10^8 smallest units per HND).

Genesis identifier:

`SHA-256("HND-GENESIS-V2\\0" || canonical_genesis_bytes)`

The chain ID used by the current local prototype is test-only and is not a production network identifier.

## State root

Each account record is encoded as:

`[account_id, balance, nonce]`

Records are sorted by raw account-ID bytes. Each leaf is:

`SHA-256("HND-STATE-LEAF-V2\\0" || canonical_account_record)`

The leaves are reduced using the Merkle node rule below. An empty state uses the defined empty-tree hash. An account omitted from the nonce map has nonce zero. A nonce for an account absent from the balance map is invalid.

## Transaction Merkle root

Each transaction ID must be exactly 32 bytes. Ordered transaction IDs are leaf-hashed:

`SHA-256("HND-MERKLE-LEAF-V2\\0" || transaction_id)`

For each pair of nodes:

`SHA-256("HND-MERKLE-NODE-V2\\0" || left || right)`

If a level has an odd number of nodes, its final node is duplicated. The empty tree root is:

`SHA-256("HND-MERKLE-EMPTY-V2\\0")`

Transaction order is significant. The implementation does not sort transactions.

## Block header

A v0.2 block header is the deterministic CBOR array:

`[version, chain_id, height, timestamp, previous_hash, transactions_root, state_root, transaction_count]`

The three hash fields are exactly 32 bytes. Height, timestamp, and transaction count are unsigned 64-bit integers. The genesis header has height zero, timestamp zero, a zero previous hash, an empty transaction root, the genesis allocation state root, and zero transactions.

Block hash:

`SHA-256("HND-BLOCK-V2\\0" || canonical_header_bytes)`

The decoder rejects malformed or noncanonical headers before hashing.

## Implementation and independent reproduction

- Implementation: `hnd_ledger/blocks.py`
- Tests: `tests/test_blocks.py`
- Public exports: `hnd_ledger/__init__.py`

A reviewer can reproduce the structures from the source and tests using Python and the pinned project dependencies. Hash outputs are deterministic for identical inputs.

## Explicit limitations

This profile does not yet define transaction execution inside blocks, block acceptance rules, fork choice, validator selection, consensus, networking, durable storage, snapshots, or crash recovery. A block header and its hash alone do not prove that its transactions are valid or that its state root follows from execution. Those require the next state-transition and chain-verification layer.
