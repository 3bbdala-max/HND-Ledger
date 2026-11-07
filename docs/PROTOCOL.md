# HND Protocol Specification — Version 0.2 Design Baseline

**Status:** Selected engineering baseline for the local prototype; implementation and security review are still pending.
**Target:** HND-Ledger version 0.2
**Updated:** 2026-11-07

## 1. Scope and evidence

This specification turns the prior open design questions into a conservative baseline for a deterministic local ledger. It does not select or claim a production consensus protocol, network deployment, wallet product, or authorization to issue or trade a token.

The version 0.1 archive reports a displayed supply of 1,000,000 units and 3,000 sequential transfers. Those archive-reported results have not been independently reproduced from this repository.

## 2. Version 0.2 baseline decisions

| Topic | Version 0.2 baseline |
|---|---|
| State model | Account/balance model |
| Account identifier | 32-byte SHA-256 digest of domain prefix plus 32-byte Ed25519 public key |
| Signature | Ed25519 using a maintained, reviewed cryptographic library; no custom cryptography |
| Hash | SHA-256 with explicit domain separation for account, transaction, block, and genesis identifiers |
| Serialization | Deterministic CBOR under RFC 8949; reject non-canonical encodings |
| Protocol version | Integer version 2 in every signed transaction and block header |
| Network separation | Explicit immutable chain ID included in every signed transaction |
| Amounts | Unsigned integer smallest units; 8 decimal places for display; no floating-point arithmetic |
| Nonce | Per-account unsigned 64-bit sequence, starting at 0; next accepted transaction must use the exact next nonce |
| Transaction ID | SHA-256 over a domain prefix and deterministic CBOR encoding of the complete signed transaction |
| Block linkage | Each block commits to parent block ID, height, chain ID, ordered transaction IDs, and state commitment |
| Supply | Maximum supply cap of 1,000,000 HND; no discretionary minting. Genesis allocation must sum to the cap before any public network is considered |
| Fees | Zero fees in the isolated v0.2 local prototype; fee economics are deferred |
| Consensus | None selected for v0.2 local ledger. A single local sequencer is not decentralization |
| Networking | Out of scope until consensus and threat model are independently reviewed |

## 3. Canonical transaction data

The signed transaction payload consists of exactly these fields, encoded using deterministic CBOR:
- protocol_version: unsigned integer, exactly 2;
- chain_id: fixed byte string identifying the network;
- sender: 32-byte account identifier;
- recipient: 32-byte account identifier;
- amount: positive unsigned integer in smallest units;
- nonce: unsigned 64-bit integer.

The Ed25519 signature is computed over a domain-separated byte sequence containing the canonical encoding of the six fields above. The public key is supplied as a 32-byte value and must derive the stated sender identifier. The signature is 64 bytes. Unknown fields, duplicate map keys, non-canonical encodings, invalid lengths, and unsupported versions are rejected.

The exact byte-level domain prefixes and deterministic CBOR library behavior must be frozen in implementation fixtures before the first compatibility release. They must not be improvised independently by different implementations.

## 4. Account and balance rules

- Account IDs are derived from the public key using the account domain prefix and SHA-256.
- Balances and amounts are integers only.
- Amount must be greater than zero.
- Sender and recipient must be distinct in v0.2.
- A transaction is valid only when its sender has sufficient balance and its nonce equals the account's next expected nonce.
- A successful transfer debits and credits the same amount atomically.
- A rejected transaction changes neither balances nor nonce.
- All arithmetic is checked; overflow or underflow causes rejection.
- The local prototype has no implicit account creation through arbitrary malformed input; recipient account creation occurs only as part of a valid transfer.

## 5. Supply and genesis

The design target is a hard maximum of 1,000,000 HND, represented as 100000000000000 smallest units at 8 decimal places. The genesis allocation table must be explicit, reproducible, and sum exactly to that amount. No allocation addresses are invented in this document. Until the allocation table and genesis identifier are committed, genesis is a test fixture only and the supply policy is not ready for public deployment.

Version 0.2 does not implement minting. Burning is also deferred; therefore the local prototype's total supply remains constant. Any later change requires a protocol-version change and new invariant tests.

## 6. Block format and deterministic execution

A local block header contains:
- protocol version;
- chain ID;
- height;
- parent block ID;
- ordered transaction IDs;
- deterministic state commitment.

The block ID is a domain-separated SHA-256 digest of the deterministic CBOR header and body. The implementation must define the state commitment precisely and publish golden test vectors before compatibility is claimed. Transactions execute in block order. A block is committed atomically only after every transaction and the resulting state commitment validate.

## 7. Consensus and validator safety gate

Version 0.2 does not claim Byzantine fault tolerance, distributed finality, or independent validators. No validator quorum or fork-choice rule is selected in this baseline.

Before consensus implementation, a separate specification must define validator admission/removal, fault assumptions, quorum intersection, safety and liveness arguments, proposal/vote messages, timeouts, finality, double-sign evidence, partition recovery, and fork choice. Independent multi-operator tests are required before any decentralization claim.

## 8. Required rejection cases

Reject malformed or non-canonical encoding; unsupported protocol version; wrong chain ID; invalid public-key or signature length; invalid signature; sender/public-key mismatch; zero amount; integer overflow/underflow; self-transfer; insufficient balance; stale, repeated, or skipped nonce; duplicate transaction ID; invalid parent/height; invalid block commitment; duplicate transaction in a block; and any state transition violating the supply invariant.

## 9. Implementation and compatibility gates

1. Freeze byte-level domain prefixes, CBOR schema, and golden vectors.
2. Implement the local transaction and account state machine using maintained libraries.
3. Add unit, integration, negative, property-based, and deterministic replay tests.
4. Verify atomic persistence and recovery.
5. Reproduce all test results in clean CI and attach commit-specific artifacts.
6. Design consensus separately; do not treat local simulation as a validator network.
7. Obtain independent security and jurisdiction-specific legal review before public deployment or token-related activity.

## 10. Release warning

This is an engineering design baseline, not an audit, production implementation, financial product, or authorization to issue, market, list, or trade an HND token. Do not use it to handle real funds.
