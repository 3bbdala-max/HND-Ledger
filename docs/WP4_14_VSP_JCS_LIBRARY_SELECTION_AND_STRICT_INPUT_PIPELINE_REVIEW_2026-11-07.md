# WP4.14 — VSP JCS Library Selection and Strict Input Pipeline Review

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Review type:** Dependency/source review and protocol-input design  
**Change type:** Documentation only  
**Disposition:** Candidate selected for isolated compatibility spike; NOT approved for production dependency or runtime use

## 1. Decision summary

The VSP v1 contract correctly separates VSP serialization from HND transaction/Genesis serialization. The existing `hnd_v02.transaction.canonical_json` helper is Python `json.dumps` with sorted keys and compact separators; it is not RFC 8785 JCS and must not be reused for VSP signatures.

**Candidate for a disposable compatibility spike:** Trail of Bits' pure-Python `rfc8785` package, release `0.1.4`. It advertises RFC 8785 serialization, returns UTF-8 bytes and is Apache-2.0 licensed. This is a candidate, not a production dependency decision. Its latest GitHub release metadata is dated 2024-09-27 and marked non-immutable; this is not enough by itself to establish current maintenance, security posture, or reproducible supply-chain provenance.

Do not add the package to `requirements.txt` yet. Before any dependency change, the spike must establish behavior against the RFC 8785 test vectors, the VSP numeric/Unicode restrictions, a second independent implementation, package artifact hashes, and a reviewed version/source pin.

## 2. Repository facts

| Item | Current state |
|---|---|
| Existing HND canonical JSON | `hnd_v02/transaction.py::canonical_json` uses Python `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)` |
| HND serialization scope | Used for HND transaction signing/address derivation and Genesis manifest hashing; do not silently change this existing wire format |
| Current crypto dependency | `cryptography>=41.0` (not exact-version pinned) |
| Existing gRPC dependencies | `grpcio==1.76.0`, `grpcio-tools==1.76.0`, `protobuf==6.33.5` |
| Existing JCS dependency | None |
| Existing strict raw JSON parser for VSP | None identified |
| VSP golden vectors | Proposed in documentation; not generated or executed |
| VSP runtime verifier | Not implemented |

## 3. Candidate library assessment

### Candidate: `rfc8785` by Trail of Bits

Observed public package/repository facts:
- Package description: pure-Python, no-dependency RFC 8785/JCS implementation.
- API documented by the package: `rfc8785.dumps(value)` returns UTF-8 encoded bytes.
- Published license: Apache License 2.0.
- GitHub latest release observed: `v0.1.4`, published 2024-09-27.
- Release metadata reports `immutable=false`.

**Why it is the first spike candidate:** it is narrowly scoped to JCS, avoids a native runtime dependency, has an explicit byte-returning API, and has a permissive license. This is a more appropriate initial candidate than reusing the HND serializer or choosing a generic JSON canonicalization package whose exact semantics are not already tied to RFC 8785.

**Why it is not approved yet:** release age and mutable release metadata require additional diligence; package serialization does not solve duplicate-key detection in the input parser; conformance on the exact supported Python version and VSP value domain has not been demonstrated in this repository; no artifact hash or lockfile exists.

### Candidate spike acceptance

Before adoption, verify all of the following in a separate disposable branch/PR:
1. Pin exact package version and verify the wheel/sdist SHA-256 from the package index.
2. Record the exact upstream source commit and verify the release tag points to the reviewed source.
3. Run the RFC 8785 Appendix B numeric vectors and available upstream conformance vectors.
4. Run VSP-specific Unicode, UTF-16 property ordering, escaping, integer-boundary and exception tests.
5. Run the same canonicalization corpus through an independent JavaScript implementation (for example, a separately pinned `canonicalize` package/runtime).
6. Confirm both implementations produce byte-identical output and identical SHA-256 digests for every accepted vector.
7. Record license, package provenance, maintainer/release activity, vulnerability review and dependency-locking decision.
8. Reject the candidate if any unexplained mismatch, silent coercion or unsupported value type is observed.

The package's documented API is a serializer; it must not be treated as a complete strict JSON parser or duplicate-key detector.

## 4. Strict input pipeline — required design

A safe VSP pipeline has distinct stages:

1. Read a bounded byte sequence from a regular file/approved source. Reject symlink or unsafe file metadata where required by the deployment policy.
2. Decode strict UTF-8; reject BOM, invalid byte sequences and excessive input.
3. Parse JSON with duplicate-member detection **before** converting objects into ordinary dictionaries. In Python, an `object_pairs_hook` can detect duplicate keys at every object depth, provided the parser also rejects non-standard constants and the schema validates the resulting tree. A parser with source-location support may be preferable if byte spans are needed.
4. Validate exact schema, type, depth, array counts, identifier grammars, integer lexical form/range and absence of unsupported values.
5. Canonicalize the accepted object using the selected RFC 8785 implementation.
6. Verify canonical byte identity according to the envelope rule below.
7. Calculate the domain-separated profile digest and verify the detached Ed25519 signatures against the independently provisioned trust manifest.
8. Return a structured verification result without starting services or mutating rollback state.

Do not parse attacker-controlled JSON with a permissive default and assume that a later canonicalizer can recover duplicate keys. Once duplicate object members have collapsed into a dictionary, the ambiguity is lost.

## 5. Required clarification to the current VSP byte contract

The existing VSP contract says the raw payload bytes must equal JCS bytes, while the distributed object is an envelope containing both `payload` and detached `signatures`. A conventional JSON parser does not preserve the exact byte span of a nested payload object.

To avoid an unnecessary custom byte-span parser, the recommended v1 wire rule is:

- The **entire envelope** (`{"payload":...,"signatures":[...]}`) must be strict UTF-8 JSON with duplicate members rejected.
- The entire envelope byte sequence must equal RFC 8785 JCS serialization of the parsed envelope.
- The signed payload bytes `P` are independently produced by RFC 8785 serialization of the parsed `payload` value.
- The profile digest remains `SHA-256("HND-VSP-v1" || 0x00 || P)`.
- The signature array is excluded from `P` and from the profile digest, but is included in the envelope's canonical byte representation.
- Signature ordering and duplicate key-ID rejection remain schema rules.
- Whitespace, alternate key order, alternate escaping, duplicate members or any noncanonical envelope representation are rejected rather than normalized silently.

This resolves the raw nested-payload extraction ambiguity without changing the signed-payload digest formula. It is a proposed clarification and must be incorporated into the versioned VSP contract before any implementation is accepted.

## 6. Numeric and string constraints

Keep the VSP v1 rule that all numeric fields are unsigned integer tokens bounded by `2^53-1`, unless a reviewed CometBFT field requires a stricter maximum. Reject booleans, floats, exponent notation, negative values, NaN and Infinity. The parser must distinguish a JSON integer token from a floating-point token; a normal Python `json.loads` result can be supplemented with `parse_float` and `parse_constant` rejection callbacks.

JCS follows ECMAScript-compatible JSON number serialization and I-JSON constraints. It is not a general arbitrary-precision integer canonicalizer. Large protocol integers must not be silently coerced into floating point; if future fields exceed the selected bound, revise the schema deliberately (for example, a fixed-width decimal-string grammar) before use.

Use ASCII-only grammars for security identifiers and preserve other accepted Unicode strings exactly; do not apply Unicode normalization.

## 7. Ed25519 and domain separation

The existing project already imports Ed25519 primitives from `cryptography`. The proposed VSP contract's domain-separated message is distinct from the HND transaction signing domain and must remain distinct:

- Profile digest: `SHA-256("HND-VSP-v1" || 0x00 || JCS(payload))`
- Governance signature message: `"HND-VSP-AUTH-v1" || 0x00 || raw_profile_digest`
- Threshold: at least two valid signatures from two distinct keys in the independently pinned three-key trust manifest.

Do not use an HND account key, CometBFT consensus key, P2P node key, TLS key, CI identity or release key as a governance key. No private keys are needed by the verifier. No keys should be generated for production during the compatibility spike.

## 8. Required negative tests before source implementation

| ID | Input condition | Required result |
|---|---|---|
| JCS-PIPE-T01 | Duplicate top-level envelope member | Reject before dictionary construction |
| JCS-PIPE-T02 | Duplicate nested payload member | Reject before dictionary construction |
| JCS-PIPE-T03 | Duplicate nested validator member | Reject before dictionary construction |
| JCS-PIPE-T04 | UTF-8 BOM | Reject |
| JCS-PIPE-T05 | Invalid UTF-8 | Reject |
| JCS-PIPE-T06 | Unpaired surrogate | Reject |
| JCS-PIPE-T07 | NaN/Infinity | Reject |
| JCS-PIPE-T08 | Float or exponent token in integer field | Reject lexical/type rule |
| JCS-PIPE-T09 | Boolean in integer field | Reject |
| JCS-PIPE-T10 | Integer above 2^53−1 | Reject |
| JCS-PIPE-T11 | Canonical payload inside noncanonical envelope | Reject |
| JCS-PIPE-T12 | Canonical envelope with altered payload signature | Reject signature |
| JCS-PIPE-T13 | Same semantic object with whitespace variation | Reject raw envelope |
| JCS-PIPE-T14 | UTF-16 ordering edge-case property names | Match JCS golden bytes |
| JCS-PIPE-T15 | Escaping/control-character edge cases | Match JCS golden bytes |
| JCS-PIPE-T16 | Negative zero / number edge case | Reject if prohibited by VSP schema |
| JCS-PIPE-T17 | Unsupported Python object type | Reject, never coerce |
| JCS-PIPE-T18 | Excessive nesting or byte length | Reject before expensive processing |
| JCS-PIPE-T19 | More validators/signatures than configured cap | Reject |
| JCS-PIPE-T20 | Independent JS and Python canonicalizers disagree | Block release; no fallback |

All tests are proposed. None were executed as part of this documentation review.

## 9. Next work package

The next safe coding unit, after explicit source-change authorization, is **VSP-IMPL-01 only**:
- implement a duplicate-aware bounded JSON parser wrapper;
- integrate the selected JCS serializer behind a narrow internal API;
- enforce exact envelope canonical-byte equality;
- add the parser/JCS negative tests and cross-language golden vectors;
- do not add governance trust-root provisioning, signature threshold verification, startup launch, anti-rollback persistence or signer controls in the same patch.

This package must not start HND or CometBFT and must not mutate application/consensus state. It is a parser/canonicalization component only.

## 10. Current CI context

At the time of this review, the latest observed run for commit `ac839a891ebd3ff79b53052ac303cdddfd31a7d8` had:
- `hnd-v02-tests`: completed successfully;
- `cometbft-single-node-smoke`: still in progress, at the CometBFT binary build step.

This CI run is not evidence that any VSP parser, JCS library, golden vector or signature verifier has been implemented or tested.

## 11. Final disposition

**Candidate:** Trail of Bits `rfc8785` v0.1.4 for an isolated compatibility spike only.

**Not approved:** production dependency adoption, VSP implementation, trust-root enrollment, validator startup, production signing, token issuance or public launch.

**Change boundary:** this review adds documentation only. No source code, tests, workflows, dependencies, lockfiles, keys, Genesis or runtime configuration were changed.

---
This is an engineering dependency/input-pipeline review, not a security certification or launch authorization.


## Test-only Node comparator supply-chain pin update (2026-11-07)

The isolated JavaScript comparator now has a committed minimal
`tools/vsp-jcs-node/package.json` and npm lockfile. The lock pins
`canonicalize@2.1.0` to the registry tarball URL and SHA-512 integrity
`sha512-F705O3xrsUtgt98j7leetNhTWPe+5S72rlL5O4jA1pKqBVQ/dT1O1D6PFxmSXvc0SUOinWS57DKx0I3CHrXJHQ==`.
CI compares the registry's `npm view canonicalize@2.1.0 dist.integrity`
value with that exact value and installs via `npm ci --ignore-scripts`.

This remains an isolated test-only tool, not a production VSP dependency.
The new integrity check and lockfile installation require a fresh successful
CI run before being treated as verified.


### CI result for the locked JavaScript comparator

Workflow run `42338218975` completed the `hnd-v02-tests` job successfully.
The run passed the registry-integrity equality check, installed the committed
Node lockfile with `npm ci --ignore-scripts`, passed the cross-language JCS
compatibility spike, and completed the isolated v0.2 test suite. This verifies
the test-only package lock and install path for that commit. It does not
approve the package for production use or freeze VSP v1.
