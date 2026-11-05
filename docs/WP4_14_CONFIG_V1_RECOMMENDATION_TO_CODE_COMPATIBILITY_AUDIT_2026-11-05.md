# WP4.14 — Config-v1 Recommendation-to-Code Compatibility Audit

**Date:** 2026-11-05  
**Status:** Static source review — findings require design/implementation follow-up  
**Branch:** `phase-0.2-planning`  
**Baseline commit:** `b04408e6a02e7f3641bb7aaf62bdb35fd50d1fd3`

## 1. Scope and method

This review compares the 14 proposed Config-v1 decisions with the current source files on `phase-0.2-planning`. It is a static source inspection, not a runtime test, security audit, or implementation approval.

Files inspected:

| File | Blob SHA |
|---|---|
| `hnd_v02/transaction.py` | `79f8affeac9960e34c2038856b512e27830520c6` |
| `hnd_v02/genesis.py` | `a5e18b675868afc719e31117f33b51e9cc1645a8` |
| `hnd_v02/abci_app.py` | `80de13be94cf4c457434aeac4fa93c78d34e2103` |
| `hnd_v02/cometbft_v040_server.py` | `e2b6f721d2dff164b96156e88136e41af4f7884c` |
| `scripts/cometbft_v040_four_validator_genesis_preflight.py` | `9368a26693829f38209e1c3da818728dda36babc` |

No source files were changed. No test command was run.

## 2. Executive assessment

The existing v0.2 code already contains several useful foundations: exact Python integer checks for transaction amounts and nonces, canonical JSON serialization, deterministic allocation ordering, duplicate-allocation rejection, a Genesis manifest hash, a durable store integrity checksum, and a four-validator Genesis preflight.

However, the proposed Config-v1 identity is not present in the implementation. The current system still uses the manifest-only Genesis payload and v0.2 store identity. The largest blockers are:

1. Config-v1 fields and their consensus-critical bounds are not represented in `ProtocolConfig`.
2. The InitChain payload contains only `genesis_hash` and `manifest`.
3. The durable store has schema version 3 and no Config-v1 digest or CometBFT profile identity.
4. The CLI independently accepts `--max-amount` and `--network-id`; these are not bound to a Config-v1 identity.
5. The CometBFT gRPC server uses insecure transport and allows a caller-supplied bind address.
6. The CLI manifest file parser does not explicitly reject duplicate JSON keys before object construction.

These findings confirm that Config-v1 remains a design/planning task, not an implementation-ready feature.

## 3. Findings by decision ID

### DEC-01 — Exact schema and field set

**Observed:**
- `ProtocolConfig` contains only `network_id`, `protocol_version`, and `max_amount`.
- The Genesis manifest contains exactly `manifest_version`, `network_id`, `protocol_version`, `total_supply`, and `allocations`.
- The application Genesis envelope contains exactly `genesis_hash` and `manifest`.
- No Config-v1 schema object is currently wired into InitChain.

**Assessment:** NOT IMPLEMENTED.

**Required:** Freeze the exact schema first, then implement one authoritative parser/model. Do not add optional consensus fields with implicit defaults.

### DEC-02 — Integer semantics and numeric bounds

**Observed:**
- Transaction amount validation requires `type(value) is int`, positive amount, and amount no greater than `config.max_amount`.
- Nonce uses an explicit U64 range with `MAX_NONCE = (1 << 64) - 1`.
- `ProtocolConfig.max_amount` requires a positive Python int but has no upper bound.
- Genesis total supply and allocation amounts require positive Python ints, but there is no explicit U64 or global supply ceiling in these validators.
- `MAX_BLOCK_TRANSACTIONS = 1000` is a module constant.
- Proposal byte budget is supplied through the CometBFT request and is not part of the HND config digest.

**Assessment:** PARTIAL. Strict integer-vs-bool checking exists for several fields, but protocol-wide bounds and binding are incomplete.

**Required:** Freeze per-field numeric maxima, make the relationship between `max_amount`, `amount_max`, and `total_supply` explicit, and bind all consensus-critical acceptance limits to a verified identity.

### DEC-03 — Network ID grammar

**Observed:**
- `_NETWORK_ID_RE` is `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$`.
- This accepts uppercase letters, periods, underscores, colons, and hyphens.
- The proposed candidate grammar is narrower and lowercase-only.

**Assessment:** CONFLICT.

**Required:** Decide whether to preserve existing IDs under a versioned compatibility policy or require a new Config-v1-only grammar. Do not silently lowercase or rewrite existing network IDs. Existing fixtures and launch scripts must be inventoried before choosing a maximum length or grammar.

### DEC-04 — Canonical JSON and wire-byte acceptance

**Observed:**
- `canonical_json` uses sorted keys, compact separators, UTF-8 output, `ensure_ascii=False`, and `allow_nan=False`.
- ABCI byte decoding parses JSON and compares the canonical re-encoding with the submitted bytes, thereby rejecting noncanonical byte representations.
- The ABCI decoder does not use an `object_pairs_hook`; duplicate keys are materialized by the JSON parser before canonical-byte comparison. The byte comparison should reject a duplicated-key wire representation, but it does not satisfy the stronger proposed requirement to detect duplicates before object construction.
- Durable-store loading does use `object_pairs_hook=_reject_duplicate_json_keys`.
- CLI manifest loading uses ordinary `json.load` without an explicit duplicate-key hook.

**Assessment:** PARTIAL / CONFLICT.

**Required:** Use one strict parser policy for config, manifest, InitChain, transaction, and store inputs. Explicitly reject duplicate keys before object construction. Keep canonical-byte equality as the recommended consensus-boundary rule.

### DEC-05 — Unicode and normalization

**Observed:**
- Network IDs are restricted by an ASCII regular expression, but the accepted grammar is broader than the proposed lowercase-only grammar.
- Canonical JSON uses UTF-8 and does not normalize Unicode.
- No general Config-v1 per-field Unicode policy exists.

**Assessment:** PARTIAL.

**Required:** Freeze a per-field policy. Prefer ASCII for identifiers/enums/digests; preserve exact code points for any explicitly permitted Unicode data. No implicit normalization should be introduced.

### DEC-06 — Allocation ordering and duplicates

**Observed:**
- Genesis validation requires allocations to be a non-empty list.
- Each account ID must be strictly greater than the previous account ID.
- This rejects both unsorted allocation arrays and duplicate account IDs.
- The sum of allocation amounts must equal `total_supply`.
- Allocation amounts and total supply do not yet have a common explicit global upper bound.

**Assessment:** PARTIAL / MOSTLY ALIGNED.

**Required:** Preserve deterministic ordering and duplicate rejection, but freeze the exact comparison key/encoding and add bounded arithmetic and cross-language vectors.

### DEC-07 — Domain separators and hash preimages

**Observed:**
- Manifest hash uses `HND-LEDGER/GENESIS\0`.
- Transaction signing uses `HND-LEDGER/TX\0`.
- Account identity uses `HND-LEDGER/ACCOUNT-ID\0`.
- The application state hash and store checksum use separate HND-specific prefixes.
- There is no Config-v1 application-config digest or aggregate network identity implementation in the inspected files.

**Assessment:** PARTIAL for existing domains; NOT IMPLEMENTED for Config-v1 identity.

**Required:** Freeze Config-v1-specific domains and exact preimages without changing the meaning of existing v0.2 domains. New identity must not be conflated with the current manifest-only Genesis hash.

### DEC-08 — HND identity and CometBFT profile identity

**Observed:**
- Application InitChain verifies chain ID against HND network ID and checks the existing manifest-only Genesis hash and manifest bytes.
- No separate CometBFT profile digest is passed to or verified by the HND application.
- The four-validator preflight checks unique node IDs, unique consensus addresses, validator records, and byte-identical CometBFT Genesis files.
- That preflight is explicitly Genesis/identity preflight only; it does not start nodes or verify a full Config-v1 profile.

**Assessment:** NOT IMPLEMENTED for the proposed dual-identity model.

**Required:** Define the HND application identity and CometBFT profile identity separately, then require both to pass before startup/listening/signing.

### DEC-09 — CometBFT profile contents and pinning

**Observed:**
- The four-validator preflight creates four validators with voting power 10 each and a shared CometBFT Genesis.
- It checks unique P2P node IDs and consensus addresses.
- It does not construct or verify a complete frozen profile digest covering all consensus-critical CometBFT parameters and exact build identity.
- Generated defaults are used as the starting point.

**Assessment:** PARTIAL.

**Required:** Produce a canonical profile inventory, classify settings as consensus-critical or operational, pin exact resolved values and build identity, and test deliberate profile mismatches.

### DEC-10 — Resource limits

**Observed:**
- The HND application caps block transactions at 1000.
- Proposal byte budget comes from the CometBFT request.
- Transaction decoding checks non-empty bytes and canonical JSON, but no explicit maximum transaction byte length is visible in the inspected application path.
- No Config-v1 parser bounds for nesting depth, member count, manifest bytes, or allocation count are defined in the inspected files.

**Assessment:** PARTIAL / NOT BOUND TO CONFIG IDENTITY.

**Required:** Define and test explicit parser/resource limits. Any limit that changes consensus acceptance must be included in the appropriate pinned identity. Keep local safety limits separate only when they cannot cause validator disagreement.

### DEC-11 — Stable machine-readable error contract

**Observed:**
- Existing validators return short string categories such as `schema`, `amount`, `nonce`, `genesis-hash-mismatch`, and `allocation-order-or-duplicate`.
- ABCI and gRPC layers often expose exception text directly as logs.
- No single versioned cross-module error taxonomy exists.

**Assessment:** PARTIAL.

**Required:** Define stable error codes and map existing local messages to them. Diagnostic text must not influence consensus decisions and must not leak secret material.

### DEC-12 — Durable-store migration policy

**Observed:**
- Durable store schema is `APP_STORE_VERSION = 3`.
- Store keys include network ID, protocol version, manifest-only Genesis hash, ledger snapshot, evidence journal, app hash, and store checksum.
- There is no Config-v1 config digest or CometBFT profile identity.
- Store loading rejects mismatched network/protocol/Genesis values and verifies its checksum and restored ledger snapshot.
- Normal startup with a legacy store is not yet defined in Config-v1 terms.

**Assessment:** NOT IMPLEMENTED for Config-v1 migration.

**Required:** Keep normal startup fail-closed for legacy stores under Config-v1. Define a separate offline migration tool and no-rewrite assertions before any store-schema change.

### DEC-13 — Upgrade activation and rollback

**Observed:**
- No Config-v1 activation-height or coordinated validator-set upgrade mechanism is present in the inspected files.
- Current InitChain rejects replacement after the application has progressed, but this is not a complete protocol upgrade or rollback mechanism.

**Assessment:** NOT IMPLEMENTED.

**Required:** Design coordinated activation, readiness checks, restart behavior, and recovery/rollback policy separately. Do not infer that InitChain's existing guard solves protocol upgrades.

### DEC-14 — Independent vector generation and review

**Observed:**
- Candidate positive vectors have been cross-checked in Python and Node.js in prior documentation.
- The source implementation currently has no Config-v1 serializer or aggregate identity to test.
- The four-validator preflight uses the current manifest hash, not Config-v1 aggregate identity.

**Assessment:** PARTIAL PROCESS EVIDENCE; Config-v1 vectors remain candidates.

**Required:** Once schema decisions are frozen, independent generators must compare exact bytes, preimages, and hashes. The implementation author must not be the sole vector approver.

## 4. Additional high-priority source findings

### AUD-01 — CLI manifest duplicate-key handling

The CometBFT server CLI loads the manifest using ordinary `json.load`. Unlike the durable-store loader, this path does not install a duplicate-key rejection hook. A duplicate-key source file can therefore be reduced to an ordinary Python object before its manifest hash is calculated.

**Required:** Use the strict duplicate-key parser for CLI manifest input and ensure the exact canonical bytes/manifest identity are verified before server startup.

### AUD-02 — Insecure gRPC bind override

The gRPC server calls `add_insecure_port(bind_address)`. The default bind address is loopback, but CLI `--listen` can override it. There is no TLS or client authentication in this server path.

**Required:** Until a separately reviewed secure transport exists, enforce loopback-only binding in code rather than relying on the default value or operator caution. This is a security prerequisite, not merely a Config-v1 schema choice.

### AUD-03 — Operational startup occurs after independent CLI config

The CLI takes `--network-id`, `--protocol-version`, and `--max-amount` as arguments, constructs `ProtocolConfig`, and then checks the manifest network ID. There is no full application config digest or profile preflight before gRPC server startup.

**Required:** Config-v1 must derive consensus-critical settings from a verified pinned config object and reject command-line mismatches before listening or enabling any signing path.

### AUD-04 — Store checksum is integrity detection, not authentication

The store checksum is an unkeyed SHA-256 over the store payload. The source comment correctly states that it is not an authentication secret or MAC.

**Required:** Do not treat this checksum as proof against an attacker who can rewrite the store. Config identity binding and the separate trust/host threat model must remain explicit.

## 5. Decision disposition after source comparison

| Decision | Compatibility result | Required next action |
|---|---|---|
| DEC-01 | Not implemented | Freeze schema, then implement |
| DEC-02 | Partial | Freeze all bounds and bind them |
| DEC-03 | Conflict | Decide compatibility grammar |
| DEC-04 | Partial/conflict | Strict duplicate detection before object creation |
| DEC-05 | Partial | Freeze per-field Unicode policy |
| DEC-06 | Mostly aligned | Preserve ordering; add bounds/vectors |
| DEC-07 | Existing domains only | Add separately versioned Config-v1 domains |
| DEC-08 | Not implemented | Design and verify dual identities |
| DEC-09 | Partial | Pin complete CometBFT profile |
| DEC-10 | Partial | Freeze and bind resource limits |
| DEC-11 | Partial | Define stable error taxonomy |
| DEC-12 | Not implemented | Design offline migration and fail-closed startup |
| DEC-13 | Not implemented | Design coordinated activation/recovery |
| DEC-14 | Partial process evidence | Independent Config-v1 vector review |

## 6. Recommended next sequence

1. Resolve DEC-03 against existing network IDs and fixtures; do not silently change existing IDs.
2. Resolve DEC-02 and DEC-10 numeric/resource limits using current code constraints and measured workloads.
3. Freeze strict parsing behavior, especially CLI manifest duplicate-key rejection.
4. Finalize Config-v1 schema and exact identity preimages.
5. Design the HND/CometBFT dual-identity startup preflight.
6. Define durable-store v4 (or another explicitly chosen version) and offline migration semantics.
7. Address insecure non-loopback gRPC binding as a separate security hardening item before any non-local deployment.
8. Generate independent vectors and only then request implementation approval.

## 7. Gate assessment

- Static review completed against the listed source blobs.
- No application source was modified.
- No tests were executed.
- No CI workflow was modified.
- Config-v1 implementation is not present in the inspected source.
- G2–G4 and public-network/production gates remain closed.
