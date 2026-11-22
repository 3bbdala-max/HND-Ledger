# HND v0.2 strict transaction decoder

**Status:** Implemented on the working branch; awaiting repository CI and independent review.

## Accepted data model

The decoder accepts only a single top-level CBOR array. Its members may be unsigned integers or definite-length byte strings. Nested arrays, maps, text strings, negative integers, tags, floats, simple values, indefinite-length items, and reserved additional-information values are rejected.

CBOR integer arguments and byte-string/array lengths must use the shortest possible representation. Truncated values and trailing bytes are rejected.

## Transaction schemas

Unsigned transaction payload, exactly six fields:

1. protocol version: unsigned integer, exactly 2;
2. chain ID: 32-byte byte string;
3. sender account ID: 32-byte byte string;
4. recipient account ID: 32-byte byte string;
5. amount: positive unsigned 64-bit integer;
6. nonce: unsigned 64-bit integer.

Complete signed transaction, exactly eight fields, adds:

7. raw Ed25519 public key: 32-byte byte string;
8. Ed25519 signature: 64-byte byte string.

The decoder validates encoding and field shape. It does not, by itself, establish that a signature is valid or that the transaction is acceptable against ledger state. Those checks belong to transaction verification and state transition processing.

## Reproducibility

The decoder is implemented in `hnd_ledger/decoder.py`. Its tests are in `tests/test_decoder.py`. Round-trip fixtures are checked against the canonical encoders. Negative tests cover malformed lengths, non-minimal integer encodings, indefinite arrays, unsupported major types, trailing bytes, incorrect schemas, and invalid signature lengths.

A passing unit test is evidence only for the exact source revision and test environment used. Repository CI must pass on the exact commit before this decoder is treated as an accepted protocol component.
