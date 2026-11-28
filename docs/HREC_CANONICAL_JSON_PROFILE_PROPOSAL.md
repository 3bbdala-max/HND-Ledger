# HND HREC Canonical JSON Profile — Design Proposal

Status: proposal for review. This is an HREC-only encoding profile. It does not change transaction signing, existing ledger hashes, ABCI app hashes, or persisted state formats.

## 1. Why a separate profile is required

The current HND v0.2 helper in `hnd_v02/transaction.py` implements:

```python
json.dumps(
    value,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
).encode("utf-8")
```

That is deterministic for the current Python implementation and current HND payloads, but it is not a complete language-neutral protocol specification. In particular, Python's default encoder accepts arbitrary-size integers and Unicode strings; Python key ordering and Go JSON escaping must not be assumed equivalent for every possible JSON value.

The current HND state model is substantially narrower: account identifiers and signatures are ASCII encodings, network IDs are constrained, balances/nonces are integers, and evidence timestamps are normalized ASCII strings. HREC can therefore define a restricted value domain that Go and Python can reproduce without changing the legacy transaction/hash rules.

## 2. Proposed profile identifier and value domain

Profile identifier: `HND-HREC-CJSON-V1`.

Allowed values:

- object with unique string keys;
- array;
- string containing printable ASCII bytes only, U+0020 through U+007E;
- non-negative integer in canonical decimal notation; the enclosing artifact schema supplies a field-specific maximum value and digit bound;
- boolean;
- null.

Rejected values:

- negative integers, floating-point values, exponent-form numbers, NaN, and Infinity;
- negative integers, and integers exceeding the field-specific bound or configured digit limit;
- strings or object keys containing non-ASCII characters or control characters;
- duplicate object keys;
- invalid UTF-8, UTF-8 BOM, unpaired surrogates;
- unknown or missing fields at the enclosing artifact-schema validation layer.

Python implementations MUST use exact type checks so `bool` is not accepted as an integer. Go implementations MUST decode number tokens without converting through float64 (for example with `json.Decoder.UseNumber()` and `math/big.Int`) and MUST reject any token outside the non-negative integer grammar or that field's schema-specific range.

The profile permits JSON null and booleans at the generic encoder layer, but each HREC artifact schema must state explicitly whether a particular field permits them. The HND snapshot and execution-input schemas should reject null for all required fields.

## 3. Exact byte encoding

The canonical byte stream is UTF-8 with no BOM and no trailing newline.

- Object keys are sorted by ascending unsigned ASCII byte sequence.
- Object syntax is `{` key `:` value (comma-separated) `}`.
- Array order is preserved exactly.
- No insignificant whitespace is emitted.
- Strings are enclosed in ASCII double quotes. Within a string, only quote and backslash are escaped as `\\"` and `\\\\`. All other permitted characters are emitted as their single ASCII byte.
- Non-negative integers use shortest base-10 notation: zero is `0`; no leading zeroes. The generic profile does not impose one global bit width. Each artifact schema defines its maximum value and maximum decimal digits per field; those limits must be consistent with the pinned HND protocol and must be checked before expensive big-integer allocation.
- Booleans are lowercase `true` and `false`; null is lowercase `null`.

Because strings are printable ASCII only, there are no Unicode normalization, UTF-16 ordering, HTML escaping, or Unicode escape-case ambiguities. The profile intentionally rejects such inputs rather than attempting to normalize them.

## 4. Go and Python implementation requirements

### Python

The HREC encoder must recursively validate the value domain before serialization. It may use the existing `canonical_json` helper only after validation, provided conformance tests prove its output matches this profile. It must not modify `transaction.py:canonical_json` or existing signing/hash semantics as part of HREC work.

### Go

The Go encoder must preserve integers exactly, reject unsupported values before serialization, disable HTML escaping, remove the encoder's terminal newline if using `json.Encoder`, and verify the final bytes against the same fixture. A generic decode through `interface{}` with float64 numbers is prohibited. Decode numbers with `json.Decoder.UseNumber()` or typed unsigned fields.

Both implementations must validate object keys and string values before encoding. The HND ledger currently bounds nonces to u64 but does not impose a universal u64 ceiling on `total_supply`, balances, or `ProtocolConfig.max_amount`; therefore a blanket u64 limit would silently narrow existing semantics. Every numeric field needs an explicit schema-specific bound before protocol freeze. Both must reject duplicate keys while parsing untrusted bytes, then re-encode and require byte-for-byte equality with the received bytes.

## 5. HREC artifact digest domains

The nested artifact proposals use distinct domain separation:

- predecessor snapshot: `ASCII("HND-HREC-HND-SNAPSHOT-V1") || 0x00 || canonical_bytes`;
- execution inputs: `ASCII("HND-HREC-EXECUTION-INPUT-V1") || 0x00 || canonical_manifest_bytes`;
- proof bundle manifest: `ASCII("HND-HREC-COMMIT-PROOF-V1") || 0x00 || canonical_manifest_bytes`.

The digest is SHA-256 over the exact concatenated bytes. The digest is represented externally as lowercase hexadecimal and internally as 32 raw bytes.

This profile does not redefine the existing HND ledger state hash, HND app hash, ABCI store hash, transaction IDs, or operation ID. Those domains remain exactly as currently specified. Any future change to an existing hash input requires a separate versioned protocol decision.

## 6. Encoding-only conformance vector

The following vector tests only the canonical encoder and snapshot-domain digest. It is deliberately synthetic and is **not** a semantically valid restorable HND snapshot: placeholder hashes are not recomputed from a Genesis manifest.

Semantic input:

```json
{
  "app_hash": "1111111111111111111111111111111111111111111111111111111111111111",
  "chain_id": "hanadi-test-1",
  "evidence_journal": [],
  "format": "HND-HREC-SNAPSHOT-V1",
  "height": 8,
  "ledger_snapshot": {
    "accepted": [],
    "balances": {"alice": 1000, "bob": 0},
    "genesis_hash": "2222222222222222222222222222222222222222222222222222222222222222",
    "history": [],
    "network_id": "hanadi-test",
    "nonces": {"alice": 0, "bob": 0},
    "protocol_version": 2,
    "schema_version": 1,
    "state_hash": "3333333333333333333333333333333333333333333333333333333333333333",
    "total_supply": 1000
  },
  "network_id": "hanadi-test"
}
```

Exact canonical bytes (557 bytes, no newline):

```text
{"app_hash":"1111111111111111111111111111111111111111111111111111111111111111","chain_id":"hanadi-test-1","evidence_journal":[],"format":"HND-HREC-SNAPSHOT-V1","height":8,"ledger_snapshot":{"accepted":[],"balances":{"alice":1000,"bob":0},"genesis_hash":"2222222222222222222222222222222222222222222222222222222222222222","history":[],"network_id":"hanadi-test","nonces":{"alice":0,"bob":0},"protocol_version":2,"schema_version":1,"state_hash":"3333333333333333333333333333333333333333333333333333333333333333","total_supply":1000},"network_id":"hanadi-test"}
```

Expected digest:

`SHA256("HND-HREC-HND-SNAPSHOT-V1" || 0x00 || canonical_bytes) = 390002794c7d75b36190b48055b3fbd0167d8f47a5556629ee80bc0b76650602`

Go and Python implementations must independently reproduce all 557 bytes and the digest. This fixture is an encoding test only; a separate fixture must use a real deterministic Genesis and valid replay-derived state before testing snapshot verification.

## 7. Mandatory rejection and mutation tests

Both implementations must reject:

- duplicate object keys at any nesting level;
- BOM, invalid UTF-8, non-ASCII strings, control characters, and unpaired surrogates;
- negative, fractional, exponent-form, non-finite, and out-of-range numbers;
- booleans where a schema field requires an integer;
- leading-zero integer spellings and non-canonical whitespace/escaping;
- reordered object keys in received canonical bytes;
- unknown/missing fields, nulls, or wrong types in artifact schemas;
- oversized input before allocating unbounded parse structures.

Both implementations must accept the same valid vectors and produce byte-identical output. Mutating one semantic field must change the canonical bytes and digest. Reordering an array must change the digest; reordering object members in the semantic input must not change canonical output.

## 8. Open limits and freeze gate

The maximum snapshot, execution-input, and proof-bundle sizes; maximum nesting depth; and maximum collection/string lengths must be fixed per artifact profile before implementation freeze. They must be selected from actual HND block, transaction, evidence, and state limits, not copied from unrelated VSP limits.

This proposal does not authorize implementation against a guessed limit. Before freeze, reviewers must confirm that every string in the real HND consensus state is printable ASCII and every integer is within the field-specific numeric bounds, including the existing u64 nonce constraint. If any existing consensus field violates those constraints, the profile must be revised or the field must receive a separately specified encoding; silent coercion is forbidden.

## 9. Relationship to existing CI

The existing `hnd-v02-tests.yml` workflow does not yet contain dedicated HREC canonical-JSON Go/Python conformance tests. Its current Python JCS compatibility spike is explicitly isolated to VSP and explicitly does not replace HND's `canonical_json`. HREC tests should be added only after this profile and its limits are approved. This proposal does not modify workflows or claim any CI pass.


## 10. Current HND numeric/string source audit

A read-only source audit of the current HND v0.2 implementation confirms why numeric bounds must be field-specific:

| Field family | Current source behavior | HREC encoding consequence |
|---|---|---|
| `nonce` | Explicit u64 check in `transaction.py` | Enforce 0..2^64-1 |
| `protocol_version` | Positive Python integer; no explicit upper bound | Freeze an explicit protocol schema maximum |
| `max_amount` | Positive Python integer; no explicit upper bound | Do not assume u64 without a protocol decision |
| `total_supply` | Positive Python integer in Genesis; no explicit upper bound | Do not assume u64 without a protocol decision |
| `balances` | Non-negative Python integers; supply sum invariant | Bound by approved total supply and artifact limits |
| `validator_power`, `total_voting_power`, evidence height | Positive/non-negative integer checks in evidence normalization; source inputs originate in CometBFT ABCI types | Bind to the pinned CometBFT field widths and reject overflow before HND normalization |
| `network_id`, account IDs, signatures, evidence timestamps | ASCII-constrained network ID, ASCII account prefix/digest, Base64 signature, normalized `unix:seconds:nanos` timestamp | Compatible with the printable-ASCII string profile |

Relevant current source locations: `hnd_v02/transaction.py` (`MAX_NONCE`, `ProtocolConfig.__post_init__`, `validate_transaction`); `hnd_v02/ledger.py` (`_assert_invariants`, `_state_payload`, `restore`); `hnd_v02/genesis.py` (Genesis supply/allocation validation); and `hnd_v02/abci_app.py` (`_merge_evidence`, app/store hash construction).

This audit supports the restricted ASCII string domain for the current HND consensus payload fields. It does **not** establish final maximum decimal digits, maximum artifact sizes, or every upstream CometBFT numeric bound. Those values must be written into the final artifact schemas before a protocol freeze. If a future consensus field introduces Unicode or negative numbers, it requires an explicit versioned schema change rather than implicit normalization.
