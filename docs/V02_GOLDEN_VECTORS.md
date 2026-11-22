# HND v0.2 canonical transaction and block golden vectors

**Status:** Executable reference vectors for canonical transactions, genesis, state roots, Merkle roots, and block headers.  
**Implementations:** `hnd_ledger/canonical.py`, `hnd_ledger/blocks.py`  
**Tests:** `tests/test_canonical.py`, `tests/test_blocks.py`

These vectors freeze byte-level encodings and domain-separated identifiers for the local v0.2 protocol profile. They are interoperability fixtures, not evidence of a deployed network, distributed consensus, or a security audit.

## Fixed local chain identifier

The local-only chain identifier is the 12 ASCII bytes `HND-LOCAL-V2` followed by 20 zero bytes. Its length is exactly 32 bytes.

```
484e442d4c4f43414c2d56320000000000000000000000000000000000000000
```

## Unsigned transaction payload

Inputs: protocol version 2; the chain identifier above; sender bytes `00` through `1f`; recipient bytes `20` through `3f`; amount 1000 smallest units; nonce 7.

Expected deterministic CBOR (108 bytes):

```
86025820484e442d4c4f43414c2d56320000000000000000000000000000000000000000
5820000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f
5820202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f
1903e807
```

The Ed25519 signing message is `ASCII("HND-TX-SIGN-V2") || 0x00 || payload`.

## Account identifier

Public key input: bytes `00` through `1f`.

Formula: `SHA256(ASCII("HND-ACCOUNT-V2") || 0x00 || public_key)`

Expected account identifier:

```
9399beb2cb6dc960b8e227578fe99f1b6719c522037a6b0c383fa3e21b4fe86f
```

## Complete signed transaction identifier

This serialization-only fixture uses public key bytes `00` through `1f` and signature bytes `00` through `3f`. The synthetic signature is not asserted to be a valid Ed25519 signature. The vector verifies that the identifier commits to all eight signed-transaction fields.

```
164efeed621c27792f3e7727959f308605af1a49c9dc023b3ec95adee41247cc
```

## Genesis and state-root vector

Inputs:

- Chain ID: the fixed local chain identifier above.
- Allocation A: address `00` repeated 31 times followed by `01`; balance 10.
- Allocation B: address `00` repeated 31 times followed by `02`; balance 20.
- Allocations are sorted by raw 32-byte account identifier before encoding.

Expected canonical genesis payload:

```
83025820484e442d4c4f43414c2d56320000000000000000000000000000000000000000
8282582000000000000000000000000000000000000000000000000000000000000000010a
825820000000000000000000000000000000000000000000000000000000000000000214
```

Expected genesis identifier:

```
5abf41e236488b231d109d1c0b5bddf4ae0bac2b4748e9e196cdd952d284876d
```

Expected state root for balances `{A: 10, B: 20}` and default zero nonces:

```
c319d4a7c593c436537410399a7a2f2b755e92ffdad4bfccb478eba5d401f92a
```

The state-root construction sorts account records and commits to each account identifier, balance, and nonce using the `HND-STATE-LEAF-V2\0` domain. Empty state uses a separate `HND-STATE-EMPTY-V2\0` domain.

## Merkle-root vectors

The empty transaction Merkle root is:

```
e915dc5e01273ce33c203835702fdf82ee0937b2baef7c8bd4e89dc012603eb9
```

For ordered transaction identifiers `11` repeated 32 bytes followed by `22` repeated 32 bytes, the expected root is:

```
c1f4d8d5a11caf4898b7f48c7ccbec0e52c774ea7576cd2ef3b36d4521b40774
```

Merkle leaves use `HND-MERKLE-LEAF-V2\0`, internal nodes use `HND-MERKLE-NODE-V2\0`, and the empty tree uses `HND-MERKLE-EMPTY-V2\0`. The final node is duplicated at odd-width levels.

## Genesis block-header vector

For the same allocations above, the genesis header uses height 0, timestamp 0, a 32-byte zero previous hash, the empty transaction root, the state root above, and transaction count 0.

Expected canonical header (141 bytes):

```
88025820484e442d4c4f43414c2d563200000000000000000000000000000000
0000000000005820000000000000000000000000000000000000000000000000
00000000000000005820e915dc5e01273ce33c203835702fdf82ee0937b2baef
7c8bd4e89dc012603eb95820c319d4a7c593c436537410399a7a2f2b755e92ff
dad4bfccb478eba5d401f92a00
```

Expected block hash:

```
de5c6f795a091c20b0a0f0e0ae2d73e4a0c66d3a00962deffd3dd3d7556bb3e9
```

The block hash formula is `SHA256(ASCII("HND-BLOCK-V2") || 0x00 || canonical_header)`. Header decoding must reject noncanonical encodings before a hash is accepted.

## Acceptance criteria

Automated tests must verify:

1. Exact transaction CBOR bytes, account identifier, signing-message domain, and signed transaction identifier.
2. Real Ed25519 signing and verification over the exact signing message.
3. Exact genesis payload, genesis identifier, state root, empty and non-empty transaction Merkle roots, canonical genesis header, and block hash.
4. Mapping insertion order does not change genesis or state roots.
5. Altering an allocation, balance, nonce, transaction order, header field, or signature changes the relevant commitment or is rejected.
6. Wrong byte lengths, booleans, negative values, zero transaction amounts, and values above the unsigned 64-bit range are rejected.

A passing result on a commit proves only that these tests passed on that commit. It does not prove protocol completeness, consensus safety, production readiness, or independent security approval.
