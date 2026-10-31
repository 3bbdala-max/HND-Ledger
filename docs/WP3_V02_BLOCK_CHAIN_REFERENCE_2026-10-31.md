# HND v0.2 — Block format and local chain reference

**Date:** 2026-10-31  
**Workstream:** WP3 — Block structure and chain integrity  
**Status:** Experimental local block-chain reference; no distributed consensus or networking.  
**Branch:** phase-0.2-planning

## 1. Scope

This work item adds a deterministic block format on top of the v0.2 ledger. Each block commits to a batch of complete signed transaction envelopes, the resulting ledger state hash, the preceding block hash, and the pinned Genesis hash.

The implementation is deliberately local. It does not add peer-to-peer transport, block gossip, leader election, validator signatures, proof of work, distributed finality, or Byzantine fault tolerance.

## 2. Block structure

Every block contains a header, a transaction list, and the block hash.

The version-1 header has exactly these fields:

| Field | Meaning |
|---|---|
| block_version | Block format version |
| network_id | Configured network |
| protocol_version | Transaction/protocol version |
| height | Zero-based block height |
| timestamp_ms | Non-negative integer milliseconds; cannot move backwards |
| previous_block_hash | Hash of the parent block |
| genesis_hash | Pinned Genesis manifest hash |
| transaction_count | Number of transaction envelopes |
| transaction_root | Merkle root of full canonical transaction envelopes |
| state_hash | Ledger state hash after applying all transactions in the block |

The genesis block is height 0, has no transactions, uses an all-zero parent hash, and commits to the initial ledger state.

## 3. Hashing rules

- Block hash: SHA-256 of the `HND-LEDGER/BLOCK\0` domain prefix followed by canonical JSON of the complete header.
- Transaction Merkle leaf: SHA-256 of `HND-LEDGER/MERKLE-LEAF\0` followed by canonical JSON of the complete transaction envelope, including its signature.
- Merkle parent: SHA-256 of `HND-LEDGER/MERKLE-NODE\0` followed by the left and right child hash bytes.
- Odd Merkle levels duplicate the final node. The empty tree uses a dedicated `HND-LEDGER/MERKLE-EMPTY\0` hash.
- State hash is computed by the existing v0.2 ledger after the block's transactions have been applied.

The Merkle root commits to the full signed envelope rather than only the signature-excluded transaction ID. The block hash commits to the Merkle root and post-state hash.

## 4. Validation and state transition

A candidate block is checked for exact schema, block/network/protocol versions, expected height, parent hash, Genesis hash, non-decreasing timestamp, transaction count, Merkle root, and header hash.

Transactions are then applied in order to a rebuilt candidate ledger. The live chain is changed only after every transaction succeeds and the resulting state hash matches the block header. Therefore a block with a late invalid transaction does not partially change the current chain state.

The reference limits a block to 1–1,000 transactions. This is an engineering test limit, not a throughput or economic parameter.

## 5. Recovery

A chain snapshot stores the pinned network/protocol/Genesis identifiers, all blocks, and the head hash. Recovery starts from the trusted Genesis manifest, recreates the genesis block, then validates and applies each later block in order. It rejects modified headers/bodies, missing or reordered blocks, broken parent links, invalid transactions, and a mismatched final head hash.

Atomic local JSON save/load is included for reproducible tests. It is not a distributed database, authenticated backup, or crash-consistency guarantee across all filesystems.

## 6. Test suite

The new block-chain suite contains 20 tests covering genesis block anchoring, valid and multi-transaction blocks, atomic rejection, duplicate transactions, block limits, strict timestamps, Merkle behavior, tampering, parent/height/network/protocol/Genesis checks, post-state commitment, detached block views, chain replay, snapshot tampering, reordering/deletion, and file save/load.

The workflow runs this suite together with the three existing v0.2 suites. GitHub Actions completed successfully for commit `8c4b53ff36597ee57713b31f84951dbc0df4b74d`: **78 tests passed, 0 failed** (22 transaction/account-identity tests, 13 Genesis tests, 21 ledger/persistence tests, and 22 block/chain tests). The block suite ran in the same CI job as the full v0.2 suite. This is automated CI evidence for the committed tests, not an independent security audit or production-readiness certification.

Workflow run: https://github.com/3bbdala-max/HND-Ledger/actions/runs/41232806836

## 7. Limitations and remaining gates

1. No distributed nodes, peer discovery, transport security, message propagation, or synchronization protocol.
2. No validator identities, signatures, leader selection, consensus algorithm, fork choice, or finality.
3. The timestamp is informational and monotonic only; it is not trusted wall-clock proof.
4. The chain is a local ordered history. It does not yet define block rewards, fees, minting, burning, or governance.
5. The state commitment is a flat deterministic state hash, not a Merkle state tree or membership proof.
6. Block-size limits and canonical encoding need cross-language test vectors and independent review.
7. The protocol, address format, Genesis release authentication, and economic parameters remain proposals requiring approval.

## 8. Release boundary

This is an experimental local block-chain reference, not a public network, deployable currency, or approved financial product. It does not authorize issuance, sale, exchange listing, custody, payment integration, or use of real funds. v0.1 and main remain unchanged.
