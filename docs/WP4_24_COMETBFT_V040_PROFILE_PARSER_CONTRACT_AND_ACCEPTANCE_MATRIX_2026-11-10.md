# WP4.24 — CometBFT v0.40.0 Profile Parser Contract and Acceptance Matrix

**Date:** 2026-11-10  
**Target:** HND-Ledger station 2 / VSP v1  
**Pinned CometBFT source:** `cometbft/cometbft@0880b4d378f347ab16e54ec677ff50d803f37d62`  
**Status:** Engineering contract for implementation; not an activation profile and not production approval.

## 1. Purpose

Define the executable boundary required before HND can claim that a VSP profile binds the actual CometBFT v0.40.0 runtime configuration. This document narrows the next implementation task to a deterministic, source-pinned normalization pipeline.

The field inventory in WP4.20 separates four identities that MUST NOT be collapsed:

1. Genesis consensus-state identity.
2. Shared consensus-service policy identity.
3. Per-node deployment policy identity.
4. Software/build identity.

The parser MUST preserve this separation. A single hash of raw TOML or a single hash of a loosely filtered configuration map is not acceptable.

## 2. Pinned-source authority

The implementation MUST be reviewed against these exact files at the pinned source commit:

- `config/config.go`
- `config/toml.go`
- `types/params.go`
- `go.mod` and the resolved dependency graph used by the pinned build.

The release tag or the version string is not a substitute for the immutable source commit. Defaults MUST be obtained from the pinned source's `config.DefaultConfig()` semantics and the matching default TOML template. A host's installed binary, local TOML parser defaults, or current upstream branch MUST NOT supply defaults.

The v0.40.0 source explicitly documents that the default TOML template must be kept synchronized with the configuration structs. Therefore the implementation must cross-check both source representations and fail its build-time conformance test if they disagree.

## 3. Parsing contract

The parser MUST:

- Accept UTF-8 TOML only; reject BOM and invalid UTF-8.
- Reject duplicate keys and duplicate table definitions according to the exact TOML version/parser semantics pinned for the implementation.
- Reject unknown top-level keys, tables, nested keys, and array-table members.
- Reject type mismatches rather than coercing strings, floats, booleans, or arrays.
- Reject non-finite numeric values and values outside explicit source-compatible integer/duration bounds.
- Reject unsupported CometBFT source commits and unsupported profile schema versions.
- Resolve omitted configuration fields from the pinned v0.40.0 defaults only; the resolved value must be represented explicitly in the normalized object.
- Never resolve a missing value from the local node's current environment, binary, filesystem, or implicit application defaults.
- Preserve ordered values where source semantics are ordered; only sort collections when the pinned source semantics prove order is irrelevant.
- Normalize durations to integer nanoseconds after parsing with the pinned source semantics. Preserve sentinel values exactly.
- Resolve path-valued fields only under a separate node-local policy; do not place host paths into the shared service-policy digest.
- Keep private key bytes, signer credentials, TLS private-key bytes, database credentials, and secret-bearing connection strings out of all public profile objects and diagnostic output.

A parser error MUST be stable and fail closed. It MUST NOT emit a partial normalized profile.

## 4. Typed output contract

The parser output is a versioned typed object, not a serialized copy of TOML. It MUST expose distinct typed subobjects:

### 4.1 Genesis identity

This subobject is sourced from the actual Genesis bytes and parsed consensus state, not from TOML. It includes the exact chain ID, initial height, validator roster and all consensus parameters. The full Genesis SHA-256 is retained alongside semantic validation.

The implementation MUST NOT use `ConsensusParams.Hash()` as a substitute for the full Genesis or full consensus-parameter digest. In the pinned v0.40.0 source, that method's header-hash contribution is narrower than the complete consensus parameter structure.

### 4.2 Shared consensus-service policy

This subobject includes the version-pinned fields classified in WP4.20 as shared consensus-service/network/mempool/sync policy. The schema MUST explicitly enumerate every included field and its units/type. Missing values are filled only from pinned defaults, then serialized explicitly.

Any field excluded from this subobject MUST have a documented reason and a separate policy location. Silent omission is forbidden.

### 4.3 Per-node deployment policy

This subobject contains validated local overrides, including listener binds, host-specific peer addresses, filesystem paths, local observability endpoints, and signer transport endpoint details. It is authenticated and bound to the validator/operator identity separately from the shared policy digest.

A local-only change MUST NOT alter the shared consensus-service digest, but MUST alter the node deployment digest when it changes a policy-controlled value.

### 4.4 Software/build identity

This subobject binds the pinned source commit, version, build toolchain/dependency identity, and exact binary SHA-256. A version string alone is insufficient. Build provenance must be independently verifiable by the release process.

## 5. Canonicalization and digest contract

The implementation MUST:

1. Normalize to the typed schema before hashing.
2. Serialize the typed object using RFC 8785 JCS, with cross-language golden vectors.
3. Use a distinct domain separator for each subobject digest and the aggregate profile digest.
4. Include explicit schema identifiers and schema versions in every digest preimage.
5. Reject unknown fields and unknown schema versions.
6. Keep Genesis digest, service-policy digest, node-deployment digest, and software/build digest independently inspectable.
7. Ensure that comments, TOML whitespace, TOML key ordering, and equivalent duration spellings do not alter a digest after normalization.
8. Ensure that semantically meaningful changes do alter the appropriate digest.

Exact domain-separator strings and the final field schema are implementation freeze items. They MUST be committed with positive and negative golden vectors before activation code consumes the digest. They are deliberately not guessed in this contract.

## 6. Required acceptance vectors

| ID | Input variation | Required result |
|---|---|---|
| CBP01 | Same semantic TOML with different comments/whitespace/key order | Same normalized object and digest |
| CBP02 | Equivalent duration spellings | Same normalized integer-nanosecond value and digest |
| CBP03 | Duplicate key at top level or nested table | Reject |
| CBP04 | Duplicate table or array-table member with invalid structure | Reject |
| CBP05 | Unknown top-level, nested, or array-table key | Reject |
| CBP06 | Wrong TOML value type | Reject without coercion |
| CBP07 | Omitted field with pinned default | Resolve from pinned v0.40.0 default and make explicit |
| CBP08 | Same omission with a changed local host default | Result remains identical to pinned default |
| CBP09 | Unsupported CometBFT source commit | Reject |
| CBP10 | Local RPC bind/path/peer-address change only | Shared service digest unchanged; deployment digest changes |
| CBP11 | Consensus timeout / mempool policy change | Shared service digest changes |
| CBP12 | Genesis validator power/key/consensus parameter change | Genesis identity changes |
| CBP13 | Binary bytes change while version string remains constant | Software/build identity changes |
| CBP14 | Secret material appears in a public-profile input field | Reject or redact before serialization; never hash or emit secret bytes |
| CBP15 | Unknown profile schema version | Reject |
| CBP16 | Cross-language JCS vectors | Byte-for-byte equality |
| CBP17 | TOML parser/default template drift against pinned structs | Build-time conformance test fails |

## 7. Integration contract

The pure parser/normalizer/digest layer MUST have no side effects: no filesystem writes, network calls, process startup, signer access, or trust-store mutation.

The subsequent pre-start gate MUST consume the parser's result and compare it against an independently authenticated VSP profile before opening ABCI, RPC, P2P, or signer endpoints. It must re-check the exact bytes or hold a protected immutable snapshot to avoid a time-of-check/time-of-use race.

A wrapper alone is not an enforcement boundary while an operator can execute the CometBFT binary directly. OS/service policy and signer-side verification remain separate mandatory acceptance gates.

## 8. Implementation sequence

1. Add the parser against the pinned v0.40.0 parser/config source and lock its dependency graph.
2. Add source-derived default extraction and a conformance test against the pinned default TOML template.
3. Add the typed schema and field classification table.
4. Add strict parse, type, unknown-key, default-resolution, and duration tests.
5. Add JCS cross-language vectors and domain-separated digest tests.
6. Add four-validator mismatch integration cases.
7. Only after those tests pass, wire the resulting digest into VSP verification.
8. Implement trust-manifest bootstrap, durable anti-rollback, unanimous acknowledgements, activation and pre-start enforcement as separate changes.

## 9. Non-claims

This contract does not claim that the parser, trust manifest, durable anchor, activation gate, OS enforcement, operator independence, or security review has been implemented. It does not define production numeric values or a live validator profile. The PR containing this document is a reviewable design artifact only.
