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

The leaves are reduced using the Merkle node rule below. An empty state uses the defined empty-tree hash. An account omitted from the nonce map has nonce zero. A nonce for an account absent from the balance map is invalid. An empty account state uses `SHA-256("HND-STATE-EMPTY-V2\\0")`, deliberately distinct from the empty transaction Merkle root.

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

This profile does not define fork choice, validator selection, consensus, or networking. Local deterministic execution and a single-host SQLite persistence layer are implemented separately. A block header and its hash alone do not prove that its transactions are valid or that its state root follows from execution; those require replay verification.


## Fixed golden vector

For the test chain ID `484e442d4c4f43414c2d56320000000000000000000000000000000000000000` and allocations `00…01 = 10`, `00…02 = 20` (in smallest units), the implementation must produce:

- Genesis ID: `5abf41e236488b231d109d1c0b5bddf4ae0bac2b4748e9e196cdd952d284876d`
- State root: `c319d4a7c593c436537410399a7a2f2b755e92ffdad4bfccb478eba5d401f92a`
- Genesis block hash: `de5c6f795a091c20b0a0f0e0ae2d73e4a0c66d3a00962deffd3dd3d7556bb3e9`

For transaction IDs `11` repeated 32 bytes followed by `22` repeated 32 bytes, the ordered transaction Merkle root is:

`c1f4d8d5a11caf4898b7f48c7ccbec0e52c774ea7576cd2ef3b36d4521b40774`

These are test vectors for the current local v0.2 profile, not production network parameters.
