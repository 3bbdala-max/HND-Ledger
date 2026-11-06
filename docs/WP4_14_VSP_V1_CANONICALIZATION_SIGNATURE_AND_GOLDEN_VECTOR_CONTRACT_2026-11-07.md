# WP4.14 — VSP v1 Canonicalization, Signature and Golden-Vector Contract

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Status:** Documentation-only protocol contract proposal; no implementation or vectors executed  
**Disposition:** Candidate contract for review; NOT APPROVED for production use

## 1. Purpose and implementation boundary

This document resolves the serialization and signature ambiguities that must be settled before implementing a VSP verifier. It is intentionally separate from the HND transaction and Genesis serialization formats.

No source code, tests, workflow, dependency, Genesis, validator roster, trust root, key, or runtime configuration was changed. No governance or consensus key was generated. All examples and proposed test fixtures are synthetic.

## 2. Critical compatibility finding: HND canonical JSON is not JCS

The existing `hnd_v02.transaction.canonical_json` uses Python `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`. This is the project's existing HND serialization helper. It is not a complete implementation or conformance claim for RFC 8785 JSON Canonicalization Scheme (JCS).

Differences that matter include:
- JCS property ordering follows UTF-16 code units, not Python's general Unicode code-point ordering.
- JCS string escaping and number serialization follow ECMAScript-compatible rules.
- A Python JSON encoder does not, by itself, reject duplicate object members in source JSON before they collapse into a dictionary.
- JCS does not define application schema, integer bounds, field ordering within arrays, or semantic normalization.
- JCS number handling is constrained by the interoperable IEEE-754/ECMAScript number model; arbitrary-precision Python integers cannot be assumed portable.

**Decision:** VSP uses its own explicitly versioned JCS contract. Do not reuse `canonical_json` as a VSP canonicalizer. Existing HND transaction and Genesis hashes remain unchanged.

## 3. Candidate frozen v1 envelope

The signed object is exactly the `payload` member. The detached `signatures` array is not included in the payload digest.

Top-level envelope exact keys:
- `payload`
- `signatures`

Payload exact keys, matching the existing VSP schema specification:
- `schema`
- `schema_version`
- `chain_id`
- `hnd_genesis_sha256`
- `cometbft`
- `profile_sequence`
- `previous_profile_sha256`
- `activation`
- `validators`
- `total_voting_power`
- `governance_policy`
- `change`

Nested objects have exact key sets. Unknown fields, missing fields and duplicate members at any depth are rejected. Schema v1 has no extension mechanism. Any future extension requires a new schema version.

The schema example in `WP4_14_VALIDATOR_SET_PROFILE_CANONICAL_SCHEMA_AND_VERIFICATION_SPEC_2026-11-07.md` remains illustrative. It is not a production profile.

## 4. Canonical input contract

### 4.1 Byte-level acceptance

1. Input is a bounded byte sequence, decoded as strict UTF-8.
2. UTF-8 BOM is rejected.
3. Invalid UTF-8, trailing non-whitespace data, unpaired surrogate values and duplicate object member names at any depth are rejected.
4. The parser must detect duplicate keys before constructing ordinary dictionaries. A normal `json.loads` call without an `object_pairs_hook` or equivalent duplicate-aware parser is insufficient.
5. The parsed object is validated against exact schema v1 types and ranges.
6. Canonical payload bytes are generated using a conforming RFC 8785 JCS implementation.
7. For the distributed signed payload representation, the raw payload bytes must equal the generated JCS bytes exactly. This rejects alternate whitespace, key ordering, escape spellings and number spellings instead of silently normalizing them.
8. No Unicode normalization is performed. Consensus-critical identifiers are restricted to the ASCII grammars below; other textual fields preserve exact Unicode scalar values as represented by JCS.
9. Resource limits (maximum envelope bytes, nesting depth, validator count, string lengths and signature count) must be constants in a reviewed schema implementation. They must not be silently inherited from host defaults.

### 4.2 Numeric interoperability

For schema v1, every numeric field is an unsigned JSON integer token. Reject booleans, strings, floats, exponent notation, negative values, NaN and Infinity.

To avoid cross-language precision loss in JCS implementations, candidate v1 maximum for every JSON integer is **9,007,199,254,740,991 (2^53−1)**. The verifier must also enforce the stricter CometBFT v0.40.0 field-specific maximum, if lower. No value may be silently rounded or narrowed.

This conservative bound is a VSP wire-format constraint, not a claim that CometBFT's internal integer type has the same maximum. If a required CometBFT value cannot fit, schema v1 must be revised before implementation rather than encoding it as a floating-point number.

### 4.3 String and identifier rules

- `chain_id`, schema identifiers, policy IDs, key IDs and operator IDs use documented ASCII-only grammars and explicit maximum lengths.
- SHA-256 digests are exactly 64 lowercase hexadecimal characters, with no prefix or whitespace.
- CometBFT source commit is exactly 40 lowercase hexadecimal characters.
- Base64 fields use canonical RFC 4648 standard Base64 with padding; decode then re-encode and require byte-for-byte equality.
- Public-key and signature byte lengths are exact for Ed25519.
- Human-readable reason text is descriptive only; it never changes authorization semantics beyond being covered by the payload signature.
- No private keys, seed phrases, passwords, tokens, recovery codes or secret material are valid fields.

### 4.4 Array ordering and uniqueness

- `validators` is sorted by lowercase hexadecimal consensus address in ascending byte/lexicographic order, with the exact ordering rule frozen in tests.
- `authorized_key_ids` is sorted lexicographically by ASCII bytes.
- `signatures` is sorted lexicographically by `key_id`; duplicate key IDs are rejected.
- Duplicate consensus public keys, derived consensus addresses, operator IDs, governance key IDs or signer identities are rejected.
- The declared total voting power must equal the checked sum of all validator powers exactly.

## 5. Exact digest and signature preimages

The following is the proposed unambiguous v1 formula. Domain labels include one NUL byte (`0x00`) after the ASCII label.

Let `P` be the exact JCS UTF-8 bytes of the payload object only.

**Profile digest:**

`D = SHA-256(ASCII("HND-VSP-v1") || 0x00 || P)`

The digest is 32 raw bytes. Its display form is 64 lowercase hexadecimal characters.

**Governance signature message:**

`M = ASCII("HND-VSP-AUTH-v1") || 0x00 || D`

Each enrolled Ed25519 governance private key signs exactly `M`. The verifier checks the 64-byte signature against the enrolled raw 32-byte public key and the exact message `M`.

The detached signature record contains exactly:
- `key_id`
- `algorithm` (literal `ed25519`)
- `signature` (canonical Base64 of 64 raw signature bytes)

At least two signatures from two distinct enrolled governance key IDs must verify. Duplicate signatures from the same key do not increase the threshold. Unknown key IDs and all unsupported algorithms are rejected.

**Important:** the Ed25519 signature is over the domain-separated 32-byte digest message above, not over an unspecified JSON wrapper, a hexadecimal digest string, or a concatenation with ambiguous separators.

## 6. Governance key identifier and trust-root binding

Candidate key ID derivation:

`key_id = "gk1-" || lowercase_hex(SHA-256(ASCII("HND-GOV-KEY-v1") || 0x00 || raw_ed25519_public_key))`

The trust manifest must independently pin exactly three governance public keys and threshold 2. Each public key is raw 32-byte Ed25519 encoded as canonical Base64. The key ID is recomputed and compared; it is not accepted as a caller-chosen label.

The initial trust-manifest digest remains established by the witnessed out-of-band bootstrap ceremony. This document does not bootstrap, enroll or rotate actual keys. It does not make a trust manifest self-authenticating.

## 7. Validator identity binding

For each VSP validator entry:
- decode the consensus public key using the exact key encoding supported by the pinned CometBFT version;
- derive the consensus address using the pinned CometBFT v0.40.0 implementation and compare exact lowercase hexadecimal bytes;
- compare the complete roster and voting powers with the actual CometBFT Genesis/profile inputs;
- verify that the local validator's configured consensus public key maps to exactly one active entry;
- reject a roster that is merely the same size but has any substituted key, address, operator, or power.

Do not substitute HND account IDs, P2P node IDs, governance key IDs or TLS identities for CometBFT consensus addresses. These are separate namespaces and key roles.

## 8. Golden-vector corpus required before implementation

The following corpus must be checked into tests only after an independently reviewed JCS implementation is selected and exact expected values are generated by at least two independent implementations.

| Vector | Fixture or mutation | Required result |
|---|---|---|
| VSP-GV-001 | Minimal valid payload, fixed synthetic public keys, canonical bytes | Exact canonical byte match |
| VSP-GV-002 | Same payload with object keys reordered | Raw package rejected as noncanonical |
| VSP-GV-003 | Whitespace inserted into payload | Rejected as noncanonical |
| VSP-GV-004 | Duplicate top-level payload member | Reject before object construction |
| VSP-GV-005 | Duplicate nested validator member | Reject before object construction |
| VSP-GV-006 | Duplicate governance policy member | Reject before object construction |
| VSP-GV-007 | UTF-8 BOM | Reject |
| VSP-GV-008 | Invalid UTF-8 | Reject |
| VSP-GV-009 | Unpaired surrogate escape | Reject |
| VSP-GV-010 | Exponent notation for an integer field | Reject lexical integer rule |
| VSP-GV-011 | Float value such as 1.0 | Reject |
| VSP-GV-012 | Boolean in an integer field | Reject |
| VSP-GV-013 | Integer greater than 2^53−1 | Reject |
| VSP-GV-014 | NaN or Infinity token | Reject as invalid JSON |
| VSP-GV-015 | Uppercase or prefixed digest | Reject |
| VSP-GV-016 | Noncanonical Base64 | Reject |
| VSP-GV-017 | Wrong Ed25519 public-key length | Reject |
| VSP-GV-018 | Wrong Ed25519 signature length | Reject |
| VSP-GV-019 | Correct signature over raw digest without auth domain | Reject |
| VSP-GV-020 | Correct signature over hexadecimal digest text | Reject |
| VSP-GV-021 | Correct signature over a different payload digest | Reject |
| VSP-GV-022 | Two valid signatures from the same key ID | Reject threshold |
| VSP-GV-023 | One valid and one invalid signature | Reject threshold |
| VSP-GV-024 | Two valid distinct enrolled signatures | Accept cryptographic threshold only |
| VSP-GV-025 | Unknown governance key ID | Reject |
| VSP-GV-026 | Wrong key ID for supplied public key | Reject trust-root lookup |
| VSP-GV-027 | Wrong chain ID or HND Genesis digest | Reject |
| VSP-GV-028 | Wrong CometBFT source commit or binary digest | Reject |
| VSP-GV-029 | Duplicate consensus public key/address | Reject |
| VSP-GV-030 | Correct validator count with one substituted validator | Reject |
| VSP-GV-031 | Voting-power sum differs from declared total | Reject |
| VSP-GV-032 | Validator array not in canonical order | Reject |
| VSP-GV-033 | Signature array not in canonical key-ID order | Reject |
| VSP-GV-034 | Old sequence or wrong predecessor digest | Reject anti-replay/rollback |
| VSP-GV-035 | Same profile copied to another chain ID | Reject cross-network replay |

Acceptance of VSP-GV-024 is not permission to start a node. It proves only that the detached signatures satisfy the cryptographic threshold for the exact synthetic payload and test trust root.

## 9. Golden-vector generation policy

A vector package must contain:
- exact UTF-8 canonical payload bytes (reviewable escaped representation plus byte length);
- exact profile digest in lowercase hex;
- exact signature message bytes (hex);
- three synthetic governance public keys and two deterministic test signatures;
- expected result and stable rejection code for every negative vector;
- the exact JCS implementation name, version and source digest used by the generator;
- a second independent implementation's matching canonical bytes and digest;
- a note that test seeds are deterministic public test fixtures and are never valid governance credentials.

Never place production private keys or real custodian secrets in fixtures. Test private seeds must be clearly marked, generated solely for tests, and rejected by production provisioning procedures.

## 10. Library selection and cross-implementation gate

No JCS dependency is currently declared in `requirements.txt`. The project currently depends on `cryptography>=41.0` plus pinned gRPC/protobuf packages. Ed25519 support exists in the installed cryptography dependency, but that does not supply RFC 8785 canonicalization.

Before source implementation:
1. Evaluate maintained Python RFC 8785/JCS libraries and their behavior on duplicate-key parsing, Unicode, numeric bounds and exceptions.
2. Select a pinned, reviewed implementation or implement a minimal conforming layer with independent conformance vectors.
3. Do not add a dependency based only on a package name or an unpinned version range.
4. Verify JCS vectors independently in a second language/runtime.
5. Verify Ed25519 signatures independently using a second implementation.
6. Record dependency license, maintenance status, vulnerability posture and lock/hash policy.
7. Freeze the exact package version and test vectors before accepting VSP v1 as an implementation contract.

## 11. Fail-closed verifier API shape — proposal only

The future pure verifier should accept:
- raw envelope bytes;
- independently provisioned trust-manifest bytes/digest;
- independently pinned chain and Genesis identities;
- approved CometBFT source/binary/profile identities;
- current durable profile sequence and digest;
- local validator consensus public identity.

It must return a structured decision with:
- accepted/rejected boolean;
- stable reason code;
- profile digest and sequence when safely parsed;
- local validator identifier when safely resolved;
- no secret material and no signer capability.

It must not:
- generate keys;
- access private keys;
- start listeners or subprocesses;
- mutate application or consensus state;
- advance anti-rollback state in the pure verification phase;
- treat an input-provided digest as an independent trust anchor.

Durable sequence advancement and process start belong to later separately reviewed layers.

## 12. Open gates and disposition

The contract is ready for implementation planning only after the following are explicitly resolved:
- exact Python JCS library or independently tested implementation;
- exact schema byte/size/depth/validator-count limits;
- exact ASCII grammars and maximum lengths for all identifiers;
- exact CometBFT v0.40.0 consensus address derivation API and supported key type;
- exact power bounds from the pinned CometBFT implementation;
- trust-manifest wire schema and witnessed bootstrap evidence format;
- stable rejection-code registry;
- two independent canonicalization/signature vector generators.

**Status: NOT APPROVED for production.** This document proposes a deterministic contract and test corpus; it does not claim a working verifier, completed golden vectors, completed tests, or launch readiness.

---
Documentation-only change. No source, tests, workflow, dependency, key, Genesis, or runtime behavior changed.
