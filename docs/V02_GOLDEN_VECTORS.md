# HND v0.2 canonical transaction golden vectors

**Status:** Initial executable reference vectors for the canonical transaction core.  
**Implementation:** `hnd_ledger/canonical.py`  
**Test file:** `tests/test_canonical.py`

These vectors freeze the byte-level encoding of the v0.2 transaction payload and the domain-separated account and transaction identifiers. They are interoperability fixtures, not evidence of a deployed network or a security audit.

## Fixed local chain identifier

The local-only chain identifier is the 12 ASCII bytes `HND-LOCAL-V2` followed by 20 zero bytes. Its length is exactly 32 bytes.

Hex:

```
484e442d4c4f43414c2d56320000000000000000000000000000000000000000
```

## Unsigned transaction payload

Inputs:

- protocol version: 2
- chain ID: the local chain identifier above
- sender: bytes `00` through `1f`
- recipient: bytes `20` through `3f`
- amount: 1000 smallest units
- nonce: 7

Expected deterministic CBOR (108 bytes):

```
86025820484e442d4c4f43414c2d56320000000000000000000000000000000000000000
5820000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f
5820202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f
1903e807
```

The Ed25519 signing message is the exact byte prefix `HND-TX-SIGN-V2` followed by one zero byte, then the 108 payload bytes above.

## Account identifier vector

Public key input: bytes `00` through `1f`.

Formula:

```
SHA256(ASCII("HND-ACCOUNT-V2") || 0x00 || public_key)
```

Expected account identifier:

```
9399beb2cb6dc960b8e227578fe99f1b6719c522037a6b0c383fa3e21b4fe86f
```

## Complete signed transaction identifier vector

This serialization-only fixture uses public key bytes `00` through `1f` and signature bytes `00` through `3f`. The synthetic signature is deliberately not asserted to be a valid Ed25519 signature. The vector verifies that the transaction identifier commits to the complete eight-field signed transaction, including the public key and signature.

Expected transaction identifier:

```
164efeed621c27792f3e7727959f308605af1a49c9dc023b3ec95adee41247cc
```

## Acceptance criteria

The automated tests must verify:

1. Exact CBOR payload bytes and byte length.
2. Exact account identifier and domain separation.
3. Exact signing-message prefix.
4. A real Ed25519 signature verifies over the exact signing message.
5. Altering the signature changes the transaction identifier.
6. Wrong byte lengths, booleans, negative values, zero amounts, and values above the unsigned 64-bit range are rejected.

A passing result on a commit proves only that these tests passed on that commit. It does not prove protocol completeness, consensus safety, production readiness, or independent security approval.
