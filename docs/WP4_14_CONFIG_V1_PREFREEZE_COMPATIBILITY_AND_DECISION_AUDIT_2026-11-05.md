# WP4.14 — Config-v1 Pre-Freeze Compatibility and Decision Audit — 2026-11-05

**Branch:** phase-0.2-planning  
**Reviewed baseline:** 6c3f2f250a6647d99cae248d9233d95f4b829475  
**Assessment type:** Static source/document compatibility review; no runtime test, no protocol approval  
**Decision:** CONFIG-V1 REMAINS A DESIGN-ONLY CHANGE. SCHEMA FREEZE AND IMPLEMENTATION ARE NOT AUTHORIZED BY THIS REVIEW.

## 1. Purpose

The repository already contains a Config-v1 design, candidate canonical identity/preimage specification, candidate positive golden vector, negative-vector matrix, 14-item decision register, implementation sequence and code-compatibility audit. This review does not duplicate those artifacts. It checks whether their current status is consistent, identifies compatibility conflicts against the current v0.2 implementation, and defines the minimum decision package needed before any source/test changes.

No source, test, workflow, dependency, Genesis fixture, CometBFT configuration, deployment setting or key was modified. No test command was run.

## 2. Executive assessment

The Config-v1 direction is technically coherent: consensus-critical HND application settings should have one strict canonical representation, a domain-separated digest, Genesis binding, durable-store binding and fail-closed startup checks. CometBFT's own consensus profile should remain a separately pinned identity, with a trusted deployment artifact binding the two.

However, the proposal is not yet a frozen protocol:
- all 14 decisions in the decision register remain PROPOSED/PENDING or DEFERRED;
- numeric maxima and resource limits are not finalized;
- current network-ID grammar differs from the proposed narrower grammar;
- the existing Genesis and store formats are legacy v0.2 shapes;
- the proposed Config-v1 object includes limits not currently represented or enforced uniformly in the application;
- the candidate vector package has one positive independently reproduced example, but the negative vectors are not yet executable/frozen;
- the current source still constructs ProtocolConfig from CLI values and emits a manifest-only application Genesis payload.

**Disposition: continue specification reconciliation only. Do not implement Config-v1 piecemeal.**

## 3. Current implementation facts

### 3.1 Application configuration
- `hnd_v02/transaction.py` defines the current ProtocolConfig with network_id, protocol_version and max_amount.
- `hnd_v02/cometbft_v040_server.py` accepts network ID and max amount through CLI parameters, loads the manifest and constructs the local ProtocolConfig.
- `hnd_v02/genesis.py` validates the allocation manifest and computes the legacy manifest-only Genesis hash under `HND-LEDGER/GENESIS\0`.
- `hnd_v02/abci_app.py` emits an application Genesis envelope containing exactly `genesis_hash` and `manifest`; InitChain checks that envelope, chain ID, manifest hash and manifest.
- The current durable application store is a legacy schema and does not persist a Config-v1 application-config digest or CometBFT profile digest.
- Current tests validate the legacy manifest, transaction and ABCI lifecycle; they do not constitute Config-v1 implementation tests.

### 3.2 Consensus-critical limits and resource semantics
- The current application has a hard-coded transaction-count ceiling of 1000.
- Transaction amount acceptance uses local ProtocolConfig.max_amount.
- Nonce validation has a U64 ceiling in the transaction implementation.
- The proposed Config-v1 candidate adds amount_max, max_block_transactions, max_transaction_bytes and nonce_max to the canonical identity.
- The current code does not yet demonstrate one uniform application-enforced maximum transaction byte policy across every ABCI acceptance path. PrepareProposal's CometBFT max_tx_bytes budget is not itself an HND Config-v1 field or an authenticated HND identity.
- The exact upper bounds and whether a particular byte limit belongs to HND application validity or the separately pinned CometBFT block profile remain unresolved.

### 3.3 Canonical parsing
- `canonical_json` already provides sorted keys, compact separators, UTF-8 and non-finite-number rejection.
- ABCI canonical-byte equality rejects noncanonical wire encodings in the covered path.
- Durable-store loading has duplicate-key rejection.
- CLI manifest loading in `cometbft_v040_server.py` still uses ordinary `json.load` without an explicit duplicate-key hook.
- The candidate Config-v1 requirement is stronger and should be one shared strict parser policy: duplicate detection before object construction, strict UTF-8/BOM behavior, exact types, exact key sets, lexical numeric rules and bounded input parsing.

## 4. Compatibility conflicts requiring explicit decisions

### CF-01 — Network ID grammar conflict
**Status: OPEN / DEC-03.**

The current network ID regular expression accepts uppercase letters and punctuation including period, underscore and colon, with up to 64 characters. The proposed Config-v1 recommendation is lowercase ASCII letters/digits/hyphen with explicit length rules.

**Decision required:** either preserve existing identifiers under a clearly versioned legacy compatibility policy, or define Config-v1-only grammar and require a new network identity. Never silently lowercase, normalize or rewrite a current network ID.

**Acceptance evidence:** inventory every committed fixture, script, test, Genesis and launch example; freeze exact grammar and maximum encoded byte length; add accepted/rejected vectors.

### CF-02 — Amount range semantics are not fully specified
**Status: OPEN / DEC-02.**

Current max_amount is a positive per-transaction limit. The candidate introduces amount_max as an absolute amount-field ceiling and requires max_amount <= amount_max. The relationship to total_supply, allocation values and future issuance/burn rules is not yet a complete monetary policy.

**Decision required:** distinguish transaction cap, absolute field cap, total supply and any future issuance policy. Define exact inclusive/exclusive bounds and checked arithmetic across Python and Go/other implementations. Do not infer the desired one-million HND supply as a hard protocol constant from an example fixture.

**Acceptance evidence:** frozen numeric table; minimum, maximum, maximum+1, bool, float, exponent, negative and cross-field relation vectors; supply conservation tests.

### CF-03 — Block transaction count and byte-budget ownership
**Status: OPEN / DEC-10.**

The proposed config includes max_block_transactions and max_transaction_bytes. The current count limit is a module constant; byte-budget behavior partly arrives through CometBFT ABCI request data. A Config-v1 design must not ambiguously duplicate a CometBFT block limit and an HND application validity limit.

**Decision required:** classify each bound:
1. deterministic HND acceptance bound, which must be included in the HND application config digest and enforced consistently at all relevant application boundaries; or
2. CometBFT consensus block parameter, which must be included in the CometBFT profile identity and validated by preflight; or
3. local operational guard, which must never cause one validator to accept a block another rejects.

**Acceptance evidence:** field ownership table; explicit precedence rules; ProcessProposal/FinalizeBlock/PrepareProposal mismatch tests; CometBFT profile mutation tests.

### CF-04 — Legacy manifest hash versus aggregate Config-v1 identity
**Status: OPEN / DEC-07 and DEC-08.**

The current `genesis_hash` is a manifest-only digest. The candidate design correctly treats this as a legacy component hash and proposes a distinct aggregate network identity binding manifest hash and application-config hash.

**Decision required:** freeze exact identity object fields, domain separator bytes including NUL, canonical preimage, envelope schema and legacy rejection behavior. Never silently reinterpret the existing manifest-only digest as a Config-v1 aggregate identity.

**Acceptance evidence:** independent preimage review, byte-level fixtures and a negative test proving that a legacy manifest hash cannot pass as a Config-v1 aggregate identity.

### CF-05 — CometBFT profile identity and deployment binding
**Status: OPEN / DEC-08 and DEC-09.**

The candidate correctly separates HND application identity from CometBFT consensus profile identity. Existing disposable harnesses use generated defaults and selected TOML edits; they do not establish a complete approved profile digest.

**Decision required:** define exact CometBFT binary/source build identity, canonical Genesis bytes, validator set/power, consensus version and every consensus-critical parameter; classify timeouts/network endpoints/worker counts as operational unless they affect consensus validity. Define one trusted deployment manifest binding HND and CometBFT digests together.

**Acceptance evidence:** canonical profile, pinned CometBFT commit/build, independent digest vector, per-node preflight, and deliberate one-field mismatch rejection before listener start or signing.

### CF-06 — Store schema and legacy migration
**Status: OPEN / DEC-12.**

The current store has no Config-v1 digest or profile identity. Adding these fields changes required store identity and cannot be handled by a normal startup rewrite.

**Decision required:** freeze target store schema, version bump, no-rewrite failure behavior, explicit offline migration, backup verification, before/after state commitments, activation/rollback boundary and recovery after interrupted migration.

**Acceptance evidence:** legacy store rejected by normal Config-v1 startup; mismatch leaves bytes unchanged; migration on disposable copies; crash/restart at every migration boundary; post-migration state and identity verification.

### CF-07 — CLI source of truth and startup ordering
**Status: OPEN / DEC-08 and implementation stages C–E.**

The current CLI independently supplies max_amount and network ID. A Config-v1 launcher must read a pinned artifact, verify expected digests from a separately trusted deployment/release mechanism, construct the application from the validated object, and refuse to listen or sign on any mismatch. InitChain must independently verify the received authenticated envelope.

**Decision required:** exact CLI transition policy, trusted pin delivery, preflight order, and how local operator overrides are rejected. A digest next to an attacker-replaceable artifact is not origin authentication.

**Acceptance evidence:** mismatched CLI override rejected; missing/extra config fields rejected; no socket opened and no signing enabled on failure; InitChain repeats the identity check; durable state digest must match on restart.

### CF-08 — Candidate vector status and decision-register authority
**Status: OPEN / documentation consistency issue.**

The candidate golden-vector report says the vector package is not frozen and that no repository tests were run, but its final line also says “G2–G4 remain closed.” This conflicts with the canonical identity specification, implementation plan and consolidated launch assessment, all of which leave Config-v1 implementation/startup/store gates open.

**Required correction:** treat G2–G4 as OPEN until actual Config-v1 code, durable-store binding, mismatch tests and multi-validator evidence exist. The “closed” phrase must not be used as status evidence. The decision register remains the authority for whether a proposal has been accepted; a candidate vector does not approve protocol decisions.

## 5. Golden-vector and parser acceptance package

Before schema freeze, the candidate vector package must be expanded and checked into executable tests with independently generated expected literals. Minimum categories:

1. Exact Config-v1 canonical bytes and digest.
2. Exact legacy manifest bytes/hash retained unchanged.
3. Exact aggregate network identity bytes/hash.
4. Cross-language large integer handling, including nonce maximum.
5. Duplicate keys at root and nested object levels.
6. BOM, invalid UTF-8, invalid Unicode scalar and noncanonical whitespace/key order.
7. Unknown/missing fields, bool-as-int, float, exponent, negative and overflow.
8. Each field mutation with unchanged digest.
9. Component digest mutation with unchanged aggregate identity.
10. Legacy digest supplied as aggregate identity.
11. Wrong HND network ID, chain ID, config version and protocol version.
12. Config mismatch against persisted store, including proof of no file rewrite.
13. CometBFT profile mismatch before startup.
14. Oversized/deeply nested manifest/config inputs rejected before expensive processing.

Expected digests must be generated by at least two independent implementations and reviewed by someone other than the production serializer author. Candidate examples remain test data, not production monetary parameters.

## 6. Required decision closure order

| Order | Decision package | Required outcome | Status |
|---|---|---|---|
| 1 | DEC-01, DEC-02, DEC-03 | Exact fields, types, numeric bounds, identifier grammar | OPEN |
| 2 | DEC-04, DEC-05, DEC-06 | Canonical bytes, Unicode, allocation order/duplicates | OPEN |
| 3 | DEC-07, DEC-08 | Hash preimages, aggregate identity, CometBFT separation | OPEN |
| 4 | DEC-09, DEC-10 | CometBFT profile and resource-bound ownership | OPEN |
| 5 | DEC-11 | Stable error categories and bounded diagnostics | OPEN |
| 6 | DEC-12, DEC-13 | Legacy store migration, upgrade activation/rollback | OPEN |
| 7 | DEC-14 | Independent vector ownership and review sign-off | OPEN |

No implementation stage should begin while a decision affecting consensus acceptance, canonical bytes, numeric limits, identity preimages or migration remains unresolved.

## 7. Implementation authorization boundary

The existing implementation-sequence document explicitly permits planning only. This review preserves that restriction:
- no source edits;
- no test edits;
- no CI workflow edits;
- no store migration;
- no Config-v1 Genesis conversion;
- no live validator startup or signing.

Once the decision owner explicitly approves a frozen specification, implementation should proceed as one dependency-controlled work package: strict parser and model, independent vectors, Genesis/InitChain binding, durable-store identity, CLI/startup preflight, CometBFT profile validation, migration/recovery tests, then four-validator mismatch tests.

## 8. Final decision

**Config-v1 is well-motivated but not frozen, implemented or authorized for implementation.** The most important technical conflict is not the hash function; it is the boundary and exact ownership of every consensus-critical parameter across HND application rules, CometBFT block/consensus rules and operational controls.

The next safe step is to complete the compatibility inventory and freeze the schema/decision register, with independent review of numeric bounds and CometBFT profile ownership. No application code should be changed before that gate is explicitly approved.

This document is a static engineering review, not an independent security audit, not a protocol approval, and not a production-readiness certification.
