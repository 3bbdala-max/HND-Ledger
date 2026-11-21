# HND v0.2 Golden Vectors (Draft 1)

**Status:** Deterministic reference fixture for implementation work. Not yet wired into the production package or CI.
**Protocol profile:** `docs/PROTOCOL.md` and `docs/CRYPTO_FORMAT.md`
**Purpose:** Freeze exact byte-level examples so independent implementations can be compared byte-for-byte.

> **Security warning:** The private seeds below are public test fixtures. They have no value and must never be used to hold funds, derive real accounts, or operate any live network.

## 1. Encoding rules exercised

- RFC 8949 deterministic CBOR, using fixed-position arrays.
- Ed25519 signing over the exact domain-separated message.
- SHA-256 account, transaction, state, and block identifiers with the v0.2 domain prefixes.
- Chain ID is the 32-byte local test identifier.
- All displayed hexadecimal strings represent raw bytes.

## 2. Test keys and identifiers

| Field | Hex |
|---|---|
| Test private seed 1 | `000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f` |
| Test private seed 2 | `202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f` |
| Public key 1 | `03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8` |
| Public key 2 | `29acbae141bccaf0b22e1a94d34d0bc7361e526d0bfe12c89794bc9322966dd7` |
| Account ID 1 | `118b55acdf23a22252e0558235f0df469d4d8bc331dfa130a925ea7bbb9f4c24` |
| Account ID 2 | `573f599a1db50b47d91e440abab85e625b84af43887a9d461014bd8f20b327db` |
| Chain ID | `484e442d4c4f43414c2d56320000000000000000000000000000000000000000` |

Account ID 1 and 2 are calculated as SHA-256(`HND-ACCOUNT-V2\0` || public_key).

## 3. Signed transaction vector

Unsigned transaction fields, in order:

`[2, chain_id, account_id_1, account_id_2, 123456789, 0]`

Canonical CBOR of the unsigned array:

`86025820484e442d4c4f43414c2d563200000000000000000000000000000000000000005820118b55acdf23a22252e0558235f0df469d4d8bc331dfa130a925ea7bbb9f4c245820573f599a1db50b47d91e440abab85e625b84af43887a9d461014bd8f20b327db1a075bcd1500`

Signing message is `HND-TX-SIGN-V2\0` followed by those exact CBOR bytes.

Signature (Ed25519, private seed 1):

`6b30d484d67c325a0ba79e0f587ff49914ed69666906536d83830c0ebc8b0ac697e0ea11f4c2853ac56450949fc17499718c2ef06546a3bccd3dacec46f43e0c`

Canonical CBOR of the complete signed transaction array:

`88025820484e442d4c4f43414c2d563200000000000000000000000000000000000000005820118b55acdf23a22252e0558235f0df469d4d8bc331dfa130a925ea7bbb9f4c245820573f599a1db50b47d91e440abab85e625b84af43887a9d461014bd8f20b327db1a075bcd1500582003a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b858406b30d484d67c325a0ba79e0f587ff49914ed69666906536d83830c0ebc8b0ac697e0ea11f4c2853ac56450949fc17499718c2ef06546a3bccd3dacec46f43e0c`

Transaction ID:

`ae09db957a068b9126895b18a8128d131d9eaf54fd28270dba207dd10c80339d`

Calculated as SHA-256(`HND-TX-ID-V2\0` || canonical CBOR of the complete signed array).

## 4. Genesis state and block vector

Genesis fixture contains one funded account:
- Account ID 1: balance `1000000000`, next nonce `0`.
- No other account records are included in the genesis state.

Canonical CBOR of the sorted genesis state array:

`81835820118b55acdf23a22252e0558235f0df469d4d8bc331dfa130a925ea7bbb9f4c241a3b9aca0000`

Genesis state commitment:

`05e0792576096cce5d64bf326a5c746445c7716a344ac0eb551a3f4cd2639b82`

Genesis block header array:

`[2, chain_id, 0, 32_zero_bytes, [], genesis_state_commitment]`

Canonical CBOR of that header:

`86025820484e442d4c4f43414c2d56320000000000000000000000000000000000000000005820000000000000000000000000000000000000000000000000000000000000000080582005e0792576096cce5d64bf326a5c746445c7716a344ac0eb551a3f4cd2639b82`

Genesis block ID:

`46a982a1c5e6c5cafc09bb86ff11ecbc3650340dd8702246658f60e796ea145b`

Calculated as SHA-256(`HND-BLOCK-ID-V2\0` || canonical CBOR of the genesis header).

## 5. Reproduction requirements

An implementation must reproduce every byte string and digest above exactly. Tests must also:
1. Verify the Ed25519 signature against the signing message.
2. Reject a one-byte mutation of the signed payload.
3. Reject non-canonical, truncated, wrong-length, and trailing-byte encodings.
4. Verify account IDs, transaction ID, state commitment, and genesis block ID independently.
5. Confirm that no private test seed is read by production runtime code.

## 6. Explicit limitation

This fixture does not resolve the exact genesis allocation serialization beyond the state and header arrays shown here. It does not prove the current repository implementation conforms. The current Python implementation still uses JSON-based signing and hashing and must be migrated before these vectors can pass against the package.
