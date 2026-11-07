# HND v0.2 — Cryptographic and Canonical Encoding Profile

**Status:** Normative design detail for the local prototype; implementation and test vectors are pending.
**Protocol:** HND version 2
**Date:** 2026-11-07

This document removes encoding ambiguity from the v0.2 design baseline. Implementations must not substitute JSON, native object serialization, floating-point values, or non-deterministic encoders.

## 1. Byte conventions

- All identifiers and public keys are byte strings, not hexadecimal text, when hashed or signed.
- SHA-256 output is exactly 32 bytes.
- Ed25519 public keys are exactly 32 bytes; signatures are exactly 64 bytes.
- Integers are unsigned CBOR integers and are range-checked before encoding.
- The CBOR profile is RFC 8949 deterministic encoding. For v0.2, protocol objects use CBOR arrays with fixed positional fields; no maps are used in signed transaction or block objects.
- Reject indefinite-length items, trailing bytes, wrong array lengths, wrong types, out-of-range integers, and any encoding that does not round-trip to the exact deterministic encoding.

## 2. Domain separation constants

The following exact ASCII byte strings, each followed by one zero byte, are reserved:
- Account identifier: `HND-ACCOUNT-V2\0`
- Transaction signing: `HND-TX-SIGN-V2\0`
- Transaction identifier: `HND-TX-ID-V2\0`
- State commitment: `HND-STATE-V2\0`
- Block identifier: `HND-BLOCK-ID-V2\0`
- Genesis identifier: `HND-GENESIS-V2\0`

These prefixes are byte strings; the two-character sequence backslash-zero in this document denotes a single 0x00 byte, not two printable characters.

## 3. Account identifier

Given a valid 32-byte Ed25519 public key P:

`account_id = SHA256(ASCII("HND-ACCOUNT-V2") || 0x00 || P)`

The result is exactly 32 bytes. No address checksum or human-readable address format is defined in this local prototype. A UI must display a clearly labelled hexadecimal representation and must not treat it as a payment address.

## 4. Transaction payload and signature

The unsigned transaction is a CBOR array of exactly six elements, in this order:

`[2, chain_id, sender, recipient, amount, nonce]`

Field constraints:
1. protocol version: integer 2;
2. chain_id: byte string of exactly 32 bytes;
3. sender: byte string of exactly 32 bytes;
4. recipient: byte string of exactly 32 bytes;
5. amount: integer in [1, 2^64 - 1], measured in smallest units;
6. nonce: integer in [0, 2^64 - 1].

The signing message is:

`ASCII("HND-TX-SIGN-V2") || 0x00 || deterministic_cbor(unsigned_transaction_array)`

The sender public key must derive the sender account identifier using section 3. Verify the Ed25519 signature over the exact signing message. Do not normalize, parse-and-reserialize with a different schema, or sign a JSON representation.

## 5. Signed transaction and transaction identifier

The complete signed transaction is a CBOR array of exactly eight elements:

`[2, chain_id, sender, recipient, amount, nonce, public_key, signature]`

The transaction ID is:

`SHA256(ASCII("HND-TX-ID-V2") || 0x00 || deterministic_cbor(signed_transaction_array))`

A transaction ID is not a substitute for signature verification. Nodes must verify all field constraints and the signature before accepting or indexing the transaction.

## 6. Account state and state commitment

For commitment calculation, include every account with a non-zero balance or a non-zero next nonce. Sort records by the raw 32-byte account identifier in ascending lexicographic byte order.

Each record is a CBOR array of exactly three elements:

`[account_id, balance, next_nonce]`

The complete state is a CBOR array containing those records in sorted order. The commitment is:

`SHA256(ASCII("HND-STATE-V2") || 0x00 || deterministic_cbor(sorted_state_array))`

The empty state is the deterministic CBOR encoding of an empty array. A test fixture must explicitly document genesis accounts and their next nonce (zero).

## 7. Block identifier

The v0.2 local block header is a CBOR array of exactly six elements:

`[2, chain_id, height, parent_block_id, transaction_ids, state_commitment]`

Constraints:
- chain_id: 32-byte byte string;
- height: unsigned 64-bit integer;
- parent_block_id: 32-byte byte string; genesis uses 32 zero bytes;
- transaction_ids: array of 32-byte transaction IDs in execution order, with no duplicates;
- state_commitment: 32-byte state commitment after executing all transactions.

The block ID is:

`SHA256(ASCII("HND-BLOCK-ID-V2") || 0x00 || deterministic_cbor(block_header_array))`

Genesis uses height zero and an empty transaction list. Its state commitment is computed from the sorted genesis state. The genesis identifier uses the separate genesis domain prefix over the deterministic CBOR genesis header and allocation array. The exact genesis array shape must be frozen in a committed fixture before implementation compatibility is claimed.

## 8. Chain identifiers

All v0.2 local test fixtures use the 32-byte chain ID formed by the ASCII bytes for `HND-LOCAL-V2` followed by zero bytes to a total length of 32. This identifier is for isolated local tests only.

A future public or shared test network must use a separately generated, immutable 32-byte chain ID. It must never reuse the local test chain ID.

## 9. Amount display

The smallest unit is 10^-8 HND. Convert integer units to display text using integer division and remainder only. Never use binary floating point for balances, transaction amounts, supply totals, or fees.

## 10. Compatibility and security requirements

- Publish golden byte vectors for account IDs, transaction payloads, signatures, transaction IDs, state commitments, block IDs, and genesis IDs.
- Test malformed, truncated, overlong, non-canonical, wrong-length, and trailing-byte inputs.
- Use a maintained Ed25519 implementation and a maintained deterministic CBOR implementation.
- Do not log private keys, seed phrases, signing seeds, or raw secret material.
- Any change to field order, domain prefix, chain ID interpretation, integer bounds, or CBOR profile requires a protocol-version change.
- This document does not define a production wallet, validator consensus, network transport, or authorization to issue or trade tokens.
