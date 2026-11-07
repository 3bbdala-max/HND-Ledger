# HND protocol specification — version 0.2 local baseline

Status: implemented in the local ledger and CometBFT integration; not a production or public-token specification.

## Core parameters

| Parameter | Value |
|---|---|
| Transaction protocol version | 2 |
| Local chain ID | HND-LOCAL-V2 |
| Account model | 32-byte account ID, balances, next nonce |
| Signature | Ed25519 |
| Hash | SHA-256 with domain separation |
| Serialization | Canonical CBOR |
| Amounts | Positive unsigned integers; 8 decimal display places |
| Nonce | uint64, starts at 0; exact next nonce required |
| Design supply ceiling | 1,000,000 HND = 100,000,000,000,000 smallest units |
| Fees | Zero in local prototype |
| Consensus engine | CometBFT v0.40.0 for controlled local integration |

## Transaction and account rules

Canonical transaction data binds protocol version, chain ID, sender, recipient, amount, and nonce. The signed transaction also carries the 32-byte public key and 64-byte Ed25519 signature. Account identity is derived from the public key using a domain-separated SHA-256 hash.

Unknown fields, non-canonical CBOR, invalid lengths, wrong chain IDs, invalid signatures, self-transfers, zero amounts, stale/skipped nonces, insufficient funds, and arithmetic overflow are rejected.

## State commitment

The v3 state commitment uses domain prefix HND-STATE-V3 followed by canonical CBOR of [2, chain_id, supply_cap, sorted_account_rows]. Each row commits account ID, balance, and next nonce. Chain identity and supply ceiling are part of the app hash. Pre-v3 local state roots are incompatible; old development databases must not be reused.

## Blocks and genesis

Block IDs commit to protocol version, height, previous block hash, exact ordered transaction bytes, and resulting state root. Genesis identity commits to chain ID, supply cap, and initial state commitment.

The configured supply ceiling is a maximum, not a claim that the full amount has been issued. Initial allocations must be positive, sorted, unique, and sum to no more than the cap. CI funded allocations are deterministic test fixtures only. Minting, burning, fees, rewards, and public issuance governance are not implemented.

## Consensus and query boundaries

CometBFT v0.40.0 handles consensus and P2P in the integration. HND implements deterministic application validation and state transitions. Local three-process agreement is not an adversarial BFT proof or production decentralization claim.

The dispatcher supports latest-state /hnd/v1/account and /hnd/v1/info queries. Historical queries and proofs are not implemented.

## Release warning

This is an experimental engineering protocol. It is not an audited financial product, authorization to issue or trade a token, or evidence of legal approval or production readiness.
