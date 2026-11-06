# WP4.14 — VSP JCS Compatibility Spike Readiness and Parser-Boundary Audit

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Reviewed head:** `8f1132de57365e5549656e6fd3e41d6c1452ef53`  
**Review type:** Read-only source and design audit  
**Change type:** Documentation only  
**Disposition:** Compatibility spike not executed; VSP parser not implemented

## 1. Executive result

The repository is **not yet ready to claim JCS compatibility**. The existing HND serializer is a project-specific deterministic JSON encoding, not an RFC 8785 implementation. There is no declared JCS package in `requirements.txt`, and no VSP parser, VSP digest implementation, governance signature verifier, or VSP golden-vector suite exists in the reviewed source paths.

A safe next coding unit remains a separately authorized, isolated compatibility spike. It must not change HND transaction or Genesis serialization, and must not silently replace existing canonicalization.

## 2. Exact repository observations

### 2.1 Dependency inventory

Reviewed `requirements.txt` at blob `0c2317b2a068dc1d5bb16d77103b876137d81580`.

Declared:
- `cryptography>=41.0`
- `grpcio==1.76.0`
- `grpcio-tools==1.76.0`
- `protobuf==6.33.5`

No RFC 8785/JCS library is declared. There is no package lock or artifact-hash record in this file.

### 2.2 Existing HND serializer

Reviewed `hnd_v02/transaction.py` at blob `79f8affeac9960e34c2038856b512e27830520c6`.

The `canonical_json` helper calls Python `json.dumps` with:
- `sort_keys=True`
- compact separators
- `ensure_ascii=False`
- `allow_nan=False`

It is used by HND transaction signing and other HND identity/state hashes. This behavior is part of existing HND serialization compatibility. It must remain unchanged for this VSP work package.

Python key ordering is not the JCS UTF-16-code-unit property ordering rule. The helper also does not by itself prove duplicate-key rejection for raw JSON input. Therefore it must not be labelled or reused as the VSP JCS implementation.

### 2.3 CLI Genesis manifest parser

Reviewed `hnd_v02/cometbft_v040_server.py` at blob `f29b07f1e24bbcc6806efb068ed09e3dcac970e6`.

The CLI opens the manifest as UTF-8 text and calls `json.load(handle)` without an `object_pairs_hook` or explicit `parse_constant` rejection at that call site. Duplicate object names can be collapsed by the standard parser before the resulting object is hashed and validated.

This is an existing Genesis parsing boundary. It is not a VSP parser and must not be silently modified as part of a JCS library spike.

### 2.4 ABCI application-state decoder

Reviewed `hnd_v02/abci_app.py` at blob `80de13be94cf4c457434aeac4fa93c78d34e2103`.

The `_decode_canonical_object` path:
- decodes UTF-8;
- rejects non-standard JSON constants;
- requires a top-level object;
- re-encodes with HND `canonical_json`;
- requires exact byte equality.

This rejects many ambiguous/noncanonical inputs by canonical-byte comparison, but its JSON decode call does not pass `object_pairs_hook`. The duplicate is therefore not rejected explicitly at parse time in this function.

By contrast, the durable store loader in the same module passes both `parse_constant=_reject_json_constant` and `object_pairs_hook=_reject_duplicate_json_keys`. That is an existing behavioral example for explicit duplicate detection, but it is not a complete VSP strict-input implementation or a JCS implementation.

### 2.5 Existing planning record

The prior strict Genesis parsing review already identified the CLI duplicate-key issue and proposed a shared strict decoder. That implementation remains separately gated. This VSP audit does not reopen or authorize that source change.

## 3. Separation requirements

Keep these formats and responsibilities separate:

| Area | Existing or proposed contract | Required treatment |
|---|---|---|
| HND transactions | Existing `canonical_json` and transaction signing domain | Preserve byte-for-byte |
| HND Genesis manifest | Existing Genesis schema/hash domain | Preserve byte-for-byte |
| ABCI app-state envelope | Existing HND canonical-byte check | Do not replace with JCS |
| Durable application store | Existing duplicate-aware parser and HND store hash | Preserve behavior |
| VSP v1 envelope | RFC 8785 JCS, strict duplicate-aware parser, VSP-specific domain separation | New isolated implementation |
| CometBFT Genesis | CometBFT v0.40.0 JSON/protobuf decoding | Decode typed values and compare; do not assume VSP JSON byte identity |

A JCS dependency must not become a global replacement for `canonical_json`.

## 4. Compatibility spike — acceptance protocol

Before production dependency adoption, a disposable, isolated spike should establish all of the following:

1. Pin one exact package release and obtain the published wheel/sdist SHA-256 from the package index.
2. Verify the package source tag/commit and license independently.
3. Confirm the exact API returns UTF-8 bytes and does not coerce unsupported Python values.
4. Run the RFC 8785 Appendix B number vectors, including edge cases around negative zero, exponent formatting and IEEE-754 boundaries.
5. Run JCS property ordering cases that distinguish UTF-16 code-unit order from Python code-point order.
6. Run escaping, control-character and Unicode scalar-value cases.
7. Run the VSP-specific accepted value domain: ASCII identifiers, descriptive Unicode text, bounded integers, arrays and nested objects.
8. Compare every output byte against a separately pinned JavaScript JCS implementation.
9. Compare SHA-256 of the byte outputs, not just parsed semantic objects.
10. Record all inputs, expected bytes, observed bytes, implementation versions, source/artifact hashes and exact test commands.
11. Reject adoption on any unexplained mismatch, coercion, silent normalization or exception ambiguity.

The selected package remains only a compatibility candidate until this process is complete. The Python `rfc8785` v0.1.4 candidate has not been installed, pinned, or tested by this audit.

## 5. Strict VSP input pipeline

The VSP parser must be an independent component with a narrow byte-oriented interface. It must:

- enforce a documented maximum envelope size and nesting/array/string limits;
- reject UTF-8 BOM and invalid UTF-8;
- reject duplicate JSON object member names at every depth before dictionary construction;
- reject NaN and Infinity tokens;
- reject trailing data and unpaired surrogates;
- validate exact schema and types before canonicalization;
- reject bool values in integer fields;
- reject non-integer tokens, negative values and values outside field-specific bounds;
- produce canonical JCS bytes for the complete envelope and require exact byte equality;
- separately canonicalize the payload for the VSP digest;
- return typed validation results without file access, network access, service startup, private-key access or rollback-state mutation.

The exact numeric resource caps still require an approved operational policy. Do not invent arbitrary consensus-validity limits in a local implementation.

## 6. VSP cryptographic compatibility boundary

Once JCS compatibility is independently established, the VSP contract uses:

```text
P = JCS(payload)
D = SHA-256("HND-VSP-v1" || 0x00 || P)
M = "HND-VSP-AUTH-v1" || 0x00 || D
```

Ed25519 governance signatures verify over exactly `M`. This spike does not generate governance keys, sign a production profile, verify a trust manifest, or implement threshold authorization.

Golden vectors must not be hand-authored with guessed outputs. Generate expected bytes and digests using two independent implementations, then independently verify signatures with a second Ed25519 implementation before recording a vector as verified.

## 7. Non-goals and explicit exclusions

This audit does not:
- change `requirements.txt` or add a dependency;
- alter HND `canonical_json`, transaction signatures, Genesis hashes or ABCI state bytes;
- fix the existing CLI Genesis parser;
- refactor the ABCI or durable-store parser;
- implement VSP schema parsing, signatures, trust roots, anti-rollback or startup gates;
- create keys, signatures, validator rosters or production profiles;
- execute a JCS compatibility spike or claim golden vectors passed.

## 8. Recommended sequence after approval

1. Authorize a disposable compatibility spike only.
2. Pin and verify the candidate JCS package and an independent JavaScript implementation.
3. Generate a small cross-language byte-comparison corpus.
4. Record exact results in a separate report.
5. Only after review, authorize a new VSP-only parser module and its unit tests.
6. Keep all HND transaction, Genesis and ABCI serialization paths unchanged.
7. Do not integrate governance signatures or startup enforcement until the parser contract and protocol-owner approval are complete.

## 9. CI observation

At the time of the source review, workflow run `42313329528` was associated with reviewed head `8f1132de57365e5549656e6fd3e41d6c1452ef53`:
- `hnd-v02-tests`: completed successfully;
- `cometbft-single-node-smoke`: still running at the pinned CometBFT binary build step.

This workflow does not test VSP/JCS compatibility. The VSP parser and compatibility corpus do not exist in the reviewed source tree. Do not interpret the passing HND job as VSP verification.

**Disposition: SOURCE BOUNDARIES DOCUMENTED — JCS SPIKE NOT EXECUTED — NO VSP IMPLEMENTATION — NO GOLDEN VECTORS VERIFIED — NOT APPROVED FOR PRODUCTION.**
