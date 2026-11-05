# WP4.14 — P1 Strict Genesis JSON Parsing: Implementation Review and Acceptance Plan

**Date:** 2026-11-05  
**Branch reviewed:** `phase-0.2-planning`  
**Reviewed head:** `2fdc665994d06ed8b78506a690c719b172939d4e`  
**Status:** Static review complete; implementation not changed in this document.

## 1. Executive decision

Proceed with a narrowly scoped parser-hardening change for the CLI Genesis manifest reader. The CLI currently calls Python `json.load` without `object_pairs_hook`; duplicate object keys can therefore be collapsed by the parser before the manifest is hashed and validated.

The ABCI application-state decoder has a different defense: it parses JSON and then requires the original bytes to equal the canonical re-encoding. That rejects duplicate-key JSON because the duplicate member cannot survive canonical re-encoding. However, it does not explicitly reject duplicates at parse time, so a shared strict parser would make the trust boundary clearer and easier to test.

Do not change Genesis schema, hash domain, canonical byte format, transaction rules, or network identity as part of this patch.

## 2. Source observations

### 2.1 CLI manifest loading — finding P1-GEN-01

File: `hnd_v02/cometbft_v040_server.py`  
Reviewed blob SHA: `f29b07f1e24bbcc6806efb068ed09e3dcac970e6`

Current flow:
1. Opens `--manifest` as UTF-8 text.
2. Calls `json.load(handle)` with default duplicate-key behavior.
3. Computes `genesis_manifest_hash(manifest)`.
4. Compares with independently supplied `--genesis-hash`.

Risk: a JSON document containing repeated names is interpreted using the standard library's last-value-wins behavior. The program hashes the resulting Python object, not the original ambiguous document. A publisher and operator can misunderstand which member was effective.

### 2.2 ABCI application-state decoding — partial mitigation

File: `hnd_v02/abci_app.py`  
Reviewed blob SHA: `80de13be94cf4c457434aeac4fa93c78d34e2103`

`_decode_canonical_object`:
- decodes UTF-8;
- rejects non-standard JSON constants;
- requires a top-level object;
- canonicalizes the parsed object;
- requires canonical bytes to equal the exact input bytes.

This rejects non-canonical duplicate-key input in practice. It does not currently pass `object_pairs_hook` to the JSON decoder, so the duplicate is detected indirectly by byte comparison rather than explicitly by the parser.

### 2.3 Existing state-store parsing — stronger duplicate-key handling

The durable store loader already uses `object_pairs_hook=_reject_duplicate_json_keys` and `parse_constant=_reject_json_constant`. The implementation can be used as a behavioral reference, but avoid creating circular imports between the ABCI app and transport server.

### 2.4 Canonical serialization

File: `hnd_v02/transaction.py`  
Reviewed blob SHA: `79f8affeac9960e34c2038856b512e27830520c6`

`canonical_json` sorts keys, removes insignificant whitespace, emits UTF-8 without ASCII escaping, and disallows NaN/Infinity. Preserve this exact encoding contract for the narrow P1 change.

## 3. Required implementation behavior

Introduce a small shared strict JSON decoding helper in a dependency-neutral module (or another location that does not create import cycles). Requirements:

1. Reject duplicate keys at every object nesting level using `object_pairs_hook`.
2. Reject NaN, Infinity, and -Infinity through `parse_constant`.
3. Decode bytes as strict UTF-8; do not silently replace invalid sequences.
4. Define BOM behavior explicitly; recommended behavior is reject UTF-8 BOM rather than silently strip it.
5. Preserve Python JSON's exact integer parsing; do not convert integers through floating point.
6. For the CLI manifest, require a top-level object and then run the existing manifest schema/hash validation.
7. For ABCI app-state bytes, preserve the exact canonical-byte equality check after strict parsing.
8. Convert parser failures into concise, stable CLI/ABCI errors without echoing file contents or secrets.
9. Do not normalize Unicode, alter key ordering, change domain separators, or rewrite the Genesis document automatically.
10. Bound input size before parsing. Select and document a conservative limit based on expected Genesis size; do not invent a consensus parameter silently. If the limit is intended to affect network validity, defer it to Config-v1 instead of applying node-local policy.

## 4. Acceptance tests

Add focused tests covering:

- duplicate top-level manifest key;
- duplicate nested allocation key;
- duplicate keys in unrelated nested object;
- valid unique-key manifest still loads and hashes identically;
- NaN, Infinity, and -Infinity rejected;
- invalid UTF-8 rejected;
- UTF-8 BOM behavior matches the documented decision;
- top-level array/scalar rejected where an object is required;
- canonical ABCI payload accepted unchanged;
- duplicate-key ABCI payload rejected explicitly;
- non-canonical whitespace/key-order payload remains rejected;
- very large input rejected before expensive parsing, if a size bound is approved;
- CLI error does not print raw manifest contents.

Suggested test IDs: `GENJSON-01` through `GENJSON-12`.

## 5. Compatibility and risk controls

- No changes to `GENESIS_DOMAIN`, `genesis_manifest_hash`, manifest fields, allocation ordering, or hash vectors.
- Existing valid canonical manifests must produce byte-for-byte identical hashes.
- Do not alter the on-chain ABCI state envelope.
- Do not modify CometBFT configuration or consensus parameters.
- Do not edit GitHub Actions workflow files.
- Before changing any existing source/test file, fetch its current blob SHA and use it as the update precondition.
- Never update the same path concurrently.
- Run the focused unit tests and the full configured CI workflow; report exact commit and run IDs.
- If any existing valid Genesis vector changes hash, stop and investigate; do not update expected hashes to make the test pass.

## 6. Scope boundary

This P1 task is limited to strict parsing and CLI/ABCI consistency. It does not:
- authenticate the publisher of Genesis;
- make a supplied hash trustworthy if the same untrusted party supplies both document and hash;
- solve Config-v1 configuration binding;
- establish a maximum monetary supply or consensus resource policy;
- secure gRPC, CometBFT P2P, or remote signer transport.

## 7. Gate

**Static review:** complete.  
**Implementation:** pending explicit authorization for this narrowly scoped source/test change.  
**Tests:** not run as part of this review.  
**Workflow files:** unchanged.

Recommended next step: implement the shared strict decoder and focused tests only, preserving all existing canonical Genesis hash vectors.
