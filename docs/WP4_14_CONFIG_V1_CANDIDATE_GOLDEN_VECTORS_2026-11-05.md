# HND Config v1 — Candidate Golden Vectors

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Status:** Candidate test vectors, independently cross-checked — not frozen protocol constants  
**Scope:** One positive Config-v1 / manifest / aggregate identity vector and reproducibility record.

## 1. Important status

These vectors instantiate the candidate schema and hash preimages from `WP4_14_CONFIG_V1_CANONICAL_IDENTITY_AND_HASH_PREIMAGE_SPEC_2026-11-05.md`.

They are **test-only examples**, not production settings, supply policy, public Genesis data, or authorization to implement or launch. The schema's open decisions remain open. In particular, numeric bounds and exact byte-size limits must be approved before the vector package is frozen.

The digest calculations were reproduced through two separate runtime implementations:
- Python: canonical JSON serialization, Ed25519 public-key derivation, and SHA-256.
- Node.js: separately implemented sorted-key canonical serializer, Ed25519 public-key derivation, and Node crypto SHA-256.

Both implementations produced identical canonical JSON strings and all three digests below. This is a reproducibility cross-check, not a formal independent audit and not a substitute for checked-in executable tests.

## 2. Candidate application config

The following values are deliberately small, synthetic test values. The `nonce_max` value is represented as a JSON integer, not a string.

```json
{
  "config_version": 1,
  "network_id": "hnd-vector-net",
  "protocol_version": 2,
  "max_amount": 1000000,
  "max_block_transactions": 1000,
  "max_transaction_bytes": 65536,
  "amount_max": 1000000000,
  "nonce_max": 18446744073709551615,
  "transaction_encoding": "canonical-json-v1",
  "recipient_policy": "genesis-registered-only-v1"
}
```

Canonical HND-CJSON-1 UTF-8 bytes, shown as a single line:

```text
{"amount_max":1000000000,"config_version":1,"max_amount":1000000,"max_block_transactions":1000,"max_transaction_bytes":65536,"network_id":"hnd-vector-net","nonce_max":18446744073709551615,"protocol_version":2,"recipient_policy":"genesis-registered-only-v1","transaction_encoding":"canonical-json-v1"}
```

Domain bytes (hex):

```text
484e442d4c45444745522f4150502d434f4e4649472f563100
```

Exact digest preimage is the domain byte sequence above concatenated with the UTF-8 bytes of the canonical JSON line above.

<text weight="semibold">Expected application_config_hash</text>

```text
04e541dddd5da413b21942f162ddb5f4582a1578a454240fb48e379225b11e04
```

## 3. Candidate manifest

The manifest contains one synthetic allocation. Its Ed25519 public key and account ID are deterministic test fixtures; no private key is included in this document.

```json
{
  "manifest_version": 1,
  "network_id": "hnd-vector-net",
  "protocol_version": 2,
  "total_supply": 1000,
  "allocations": [
    {
      "account_id": "hnd2:hnd-vector-net:11e09e372fb1515926869e48e836b7d5ca45da94cedd5963cf51d47bfa370857",
      "public_key": "A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg=",
      "amount": 1000
    }
  ]
}
```

Canonical HND-CJSON-1 UTF-8 bytes:

```text
{"allocations":[{"account_id":"hnd2:hnd-vector-net:11e09e372fb1515926869e48e836b7d5ca45da94cedd5963cf51d47bfa370857","amount":1000,"public_key":"A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg="}],"manifest_version":1,"network_id":"hnd-vector-net","protocol_version":2,"total_supply":1000}
```

Domain bytes (hex):

```text
484e442d4c45444745522f47454e4553495300
```

Exact digest preimage is the domain byte sequence above concatenated with the UTF-8 bytes of the canonical manifest line above.

<text weight="semibold">Expected legacy-compatible manifest_hash</text>

```text
1938cdd0840b438aae7582ae9c3f3970e357dc179a52938347d52adcfecd7211
```

This is still the manifest-only component hash. It must not be mistaken for the aggregate Config-v1 network identity.

## 4. Aggregate network identity

The exact identity object is:

```json
{
  "identity_version": 1,
  "manifest_hash": "1938cdd0840b438aae7582ae9c3f3970e357dc179a52938347d52adcfecd7211",
  "application_config_hash": "04e541dddd5da413b21942f162ddb5f4582a1578a454240fb48e379225b11e04"
}
```

Canonical UTF-8 bytes:

```text
{"application_config_hash":"04e541dddd5da413b21942f162ddb5f4582a1578a454240fb48e379225b11e04","identity_version":1,"manifest_hash":"1938cdd0840b438aae7582ae9c3f3970e357dc179a52938347d52adcfecd7211"}
```

Domain bytes (hex):

```text
484e442d4c45444745522f4e4554574f524b2d47454e455349532f563100
```

Exact digest preimage is the domain byte sequence above concatenated with the UTF-8 bytes of the canonical identity line above.

<text weight="semibold">Expected network_genesis_hash</text>

```text
a13c84bc3efe9a95853d067a9754609b33c093f8099bdc8ac04a20035a8a30a0
```

## 5. Cross-implementation reproduction

| Output | Python implementation | Node.js implementation | Result |
|---|---|---|---|
| Test Ed25519 public key | `A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg=` | Same | Match |
| Derived account ID | `hnd2:hnd-vector-net:11e09e372fb1515926869e48e836b7d5ca45da94cedd5963cf51d47bfa370857` | Same | Match |
| Canonical config JSON | Exact line in §2 | Same | Match |
| Canonical manifest JSON | Exact line in §3 | Same | Match |
| Application config digest | `04e541dddd5da413b21942f162ddb5f4582a1578a454240fb48e379225b11e04` | Same | Match |
| Manifest digest | `1938cdd0840b438aae7582ae9c3f3970e357dc179a52938347d52adcfecd7211` | Same | Match |
| Aggregate network digest | `a13c84bc3efe9a95853d067a9754609b33c093f8099bdc8ac04a20035a8a30a0` | Same | Match |

The Node.js implementation used BigInt for `nonce_max` so that the canonical JSON contains the exact unsigned 64-bit decimal integer. Converting that value through a JavaScript Number would lose precision and is not an acceptable implementation.

## 6. Required negative-vector derivations

The following cases should be added to the executable vector suite. They are specified here as expected rejection behavior; their executable test results have not yet been run.

| Case | Mutation | Expected result |
|---|---|---|
| NV01 | Change `max_amount` but retain the old config digest | Config digest mismatch |
| NV02 | Change `total_supply` or allocation amount but retain old manifest digest | Manifest digest mismatch |
| NV03 | Change either component digest but retain old aggregate digest | Aggregate identity mismatch |
| NV04 | Use the legacy manifest digest as `network_genesis_hash` | Reject wrong identity type/value |
| NV05 | Replace `nonce_max` integer with a quoted decimal string | Reject config type |
| NV06 | Replace an integer with `true` | Reject config type |
| NV07 | Add an unknown config field | Reject exact schema |
| NV08 | Remove a required config field | Reject exact schema |
| NV09 | Supply duplicate JSON keys | Reject before object construction |
| NV10 | Use NaN, Infinity, or a floating-point value | Reject non-integer / invalid JSON number |
| NV11 | Uppercase or prefix a digest with `0x` | Reject digest syntax |
| NV12 | Change one domain-separation byte | Digest must differ |
| NV13 | Use a public key whose account ID does not match | Reject manifest allocation |
| NV14 | Reorder or duplicate allocation account IDs contrary to manifest rules | Reject manifest |
| NV15 | Use a config value outside the eventually approved numeric bounds | Reject config |

## 7. Freeze checklist

Before calling these vectors frozen:

- [ ] Approve the Config-v1 field names and exact types.
- [ ] Approve all numeric bounds and maximum encoded lengths.
- [ ] Confirm that `nonce_max` remains the unsigned 64-bit maximum.
- [ ] Confirm the three domain separators byte-for-byte.
- [ ] Confirm the aggregate identity object schema and whether the manifest hash is repeated in the Genesis envelope.
- [ ] Add the exact canonical JSON fixtures to the repository's executable test suite.
- [ ] Add independent expected digest literals; do not compute expected values with the function under test.
- [ ] Run the tests in the authorized environment and retain full logs.
- [ ] Obtain independent review of canonical byte construction and cross-language integer handling.

## 8. Gate decision

**Decision: one positive candidate vector independently reproduced in Python and Node.js; vector package is not frozen.**

No application code, test code, or CI workflow was changed. No repository test suite was run as part of producing this document. G2–G4 remain closed, and this work does not authorize public distribution, production deployment, or real-value operation.

Next safe step: obtain review of the proposed Config-v1 schema and identity preimages, then convert these candidate fixtures into executable positive and negative tests only after the schema is frozen.
