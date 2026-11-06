# WP4.14 — Genesis, Application Config and Durable Store Identity-Binding Closure Audit

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Review type:** Static source/spec/test review; documentation-only.  
**Change boundary:** No source, tests, workflow, Genesis fixture, store file, or runtime setting changed.

## 1. Executive determination

The current HND v0.2 runtime does not yet bind the complete deterministic application configuration into its Genesis identity and durable application store.

The current implementation checks:
- CometBFT chain ID against the local `ProtocolConfig.network_id`;
- the legacy HND manifest hash against an independently supplied expected hash;
- manifest equality between the local process and InitChain payload;
- persisted network ID, protocol version and legacy Genesis hash during store recovery;
- internal store consistency through an unkeyed SHA-256 checksum, ledger snapshot reconstruction and application-hash recomputation.

But the current runtime does not bind `max_amount` or a Config-v1 digest into the application Genesis envelope or durable store. The server independently receives `--max-amount`, and the application store schema v3 has no field for application-config digest or CometBFT profile digest.

**Disposition:** Critical configuration identity gap remains open. Config-v1 remains a candidate design, not an implemented protocol. This audit does not authorize source changes, select numeric bounds, approve a migration, or authorize a public network.

## 2. Verified implementation facts

### 2.1 Legacy application Genesis envelope

`HNDABCIApplication.application_genesis_bytes()` currently serializes exactly:
- `genesis_hash`;
- `manifest`.

`init_chain()` requires exactly those two fields, compares the supplied Genesis hash to the local expected hash, and compares the supplied manifest to the local manifest. It also requires the CometBFT chain ID to equal the local `config.network_id`.

There is no Config-v1 object, application-config digest, aggregate network-genesis digest, or CometBFT profile digest in this envelope.

### 2.2 CLI policy is not authenticated by the legacy manifest

The CometBFT server CLI requires `--max-amount` and constructs `ProtocolConfig` using the independently supplied network ID, protocol version and max amount. It computes the legacy manifest hash and compares it with `--genesis-hash`. The shown startup path compares the manifest's network ID with the CLI network ID, but does not compare a Genesis-authenticated Config-v1 max amount because no such field currently exists.

The existing runtime Genesis/config audit documents the concrete mismatch: two nodes may use the same legacy Genesis and manifest but different `--max-amount` values, with no current Genesis/store identity check rejecting the discrepancy. This can change deterministic transaction validity.

### 2.3 Durable store schema v3

`APP_STORE_VERSION = 3`. The current exact store key set contains:
- `schema_version`;
- `network_id`;
- `protocol_version`;
- `genesis_hash`;
- `last_committed_height`;
- `ledger_snapshot`;
- `evidence_journal`;
- `app_hash`;
- `store_hash`.

The store payload does not contain:
- Config-v1 schema/version;
- application-config digest;
- aggregate HND network-genesis digest;
- CometBFT consensus-profile digest;
- CometBFT binary/source identity;
- authenticated release-manifest identity or upgrade activation identity.

On recovery, the loader checks exact key set and store schema version, verifies the store checksum, compares network ID/protocol version/legacy Genesis hash, validates height and app hash, restores the ledger snapshot and evidence journal, and recomputes the app hash.

The checksum comment explicitly describes the store hash as an integrity checksum, not an authentication secret or MAC. Therefore, a self-consistent older store can be replayed if no independent freshness anchor is consulted. Config binding and rollback protection are separate controls.

### 2.4 Current test coverage boundary

The ABCI application tests cover InitChain chain-ID mismatch, unpinned legacy Genesis hash, canonical application Genesis bytes, store reload, and several tampering/corruption cases. The existing tests do not demonstrate:
- a node with a different max amount being rejected by an authenticated Genesis config digest;
- Config-v1 digest mismatch rejection during InitChain;
- a durable store carrying and checking application-config and CometBFT profile digests;
- a valid old store rejected by an independent monotonic checkpoint;
- an approved store schema migration with rollback and mixed-version tests.

The four-validator smoke uses one common test ProtocolConfig and common generated Genesis for all disposable nodes. That is a useful integration fixture, not proof that a divergent validator configuration is rejected at startup.

## 3. Identity components must remain separate

The implementation target should preserve separate, domain-separated identities rather than overload the legacy manifest hash.

| Identity | What it commits to | Owner |
|---|---|---|
| Legacy manifest hash | Exact HND allocation manifest bytes under its existing domain | HND Genesis validation |
| HND application-config digest | All deterministic HND validation and state-transition parameters | HND application |
| Aggregate HND network-genesis digest | Manifest component hash plus application-config digest | HND application / release governance |
| CometBFT consensus-profile digest | Exact CometBFT build and consensus-affecting profile inputs | CometBFT release/profile governance |
| Validator-set artifact identity | Consensus public keys, voting power and activation semantics | Network governance / CometBFT |
| Durable store integrity hash | Internal consistency of one persisted store payload | HND store |
| Independent freshness/anti-rollback anchor | Highest accepted committed checkpoint or approved recovery epoch | Separate trusted recovery mechanism |

Do not include local-only endpoint addresses, paths, log levels or secrets in the HND application-config digest. Classify CometBFT fields separately against the exact pinned source version.

## 4. Proposed future Genesis contract (not approved or implemented)

The Config-v1 candidate spec proposes an application Genesis envelope that carries the validated manifest and full application config, together with recomputable component and aggregate digests.

Before implementation, owner-approved schema and independent golden vectors must define:
1. exact envelope keys and nested object schemas;
2. Config-v1 field meanings, bounds and supported enum values;
3. strict duplicate-key and unknown-field behavior;
4. canonical UTF-8 JSON bytes and domain-separated hash preimages;
5. legacy manifest-hash compatibility;
6. aggregate network-genesis digest calculation;
7. relationship to CometBFT chain ID and separately pinned CometBFT profile;
8. independently authenticated expected pins and their rotation process.

All digest strings supplied inside Genesis must be recomputed from their corresponding data. A digest supplied beside an untrusted object is not an authentication mechanism.

The current Config-v1 spec is explicitly a candidate and leaves numeric bounds, some schema details, independent vector generation and profile identity decisions open. This audit does not convert those proposals into approved decisions.

## 5. Proposed future durable store contract

A future store schema should bind at least:
- store schema version;
- network ID and protocol version;
- legacy manifest hash;
- application-config schema version and application-config digest;
- aggregate HND network-genesis digest;
- separately pinned CometBFT profile digest (or an explicitly justified reference to a trusted release identity);
- committed height and app hash;
- ledger snapshot and evidence journal;
- store integrity checksum.

The store loader must compare each identity field against independently validated startup expectations before restoring application state. Missing fields, unknown schema, digest mismatch, unsupported version and ambiguous migration state must fail closed.

Do not use the store's own checksum as the trusted expected digest. The checksum detects internal modification/corruption; it does not authenticate who produced the file or prove that it is the newest valid state.

### Store schema migration is a protocol decision

Changing the store key set and version is not a harmless metadata-only edit. It changes restart compatibility and requires a versioned migration policy.

Before a migration is authorized, define:
- supported source store versions;
- whether v3 stores are rejected, migrated offline, or accepted only under a one-time explicitly approved migration procedure;
- how migration proves the same Genesis and application state;
- whether migration changes app hash or only recovery metadata;
- atomicity and crash behavior during conversion;
- downgrade behavior (normally reject);
- mixed-version validator behavior and activation height;
- independent backup and restore drill evidence.

No automatic fallback from a missing digest to a legacy v3 interpretation should be introduced for a production network. Any legacy conversion must be an explicit, authenticated and auditable operation.

## 6. Rollback resistance is a separate required layer

Even after config/profile digests are stored, an older internally valid store can still carry the same identities and a lower committed height. The store checksum cannot establish freshness.

A separate trusted monotonic anchor is required. Candidate mechanisms to evaluate include:
- hardware-backed monotonic storage or secure element;
- independently authenticated remote checkpoint service with a documented quorum/trust model;
- signed checkpoint records distributed through a separately controlled recovery channel;
- another independently governed mechanism that cannot be rolled back together with the local store.

The chosen mechanism must define outage behavior, quorum/trust assumptions, recovery authority, key rotation, checkpoint cadence, retention, compromise recovery and offline disaster recovery. A locally stored unsigned height file is not an independent anchor.

At startup, compare the recovered store's network identity, config/profile digests, height and app hash with the trusted checkpoint. Reject stale, conflicting or unverifiable state before enabling signing. Do not silently select whichever source has the lower height or whichever state file happens to exist.

## 7. Required negative and lifecycle test matrix

| Test | Required outcome |
|---|---|
| Same manifest, different max_amount on one validator | Reject before listener/signing |
| Same manifest, altered Config-v1 field but old config digest | Reject during strict validation |
| Wrong manifest hash or aggregate network-genesis digest | Reject |
| Config digest matches but CometBFT profile digest differs | Reject at profile/startup gate |
| InitChain envelope omits config or has unknown/duplicate keys | Reject |
| Existing store has wrong config/profile digest | Reject before state restore |
| Existing store has missing digest fields | Reject or enter only an explicitly approved migration path |
| Store checksum is recomputed after changing a bound identity | Identity comparison still rejects |
| Older valid store with same config and Genesis | Independent freshness anchor rejects |
| Anchor unavailable or signature/quorum invalid | Fail closed for signing |
| Crash during approved store migration | Recover old or new complete state; never partial |
| Downgrade to legacy store schema after migration | Reject |
| Mixed validators run old/new config or store schema | Reject outside an approved activation window |
| Matching independent validators restart | Same network identity, height and app hash; converge |
| Local endpoint/log changes only | No change to HND app-config digest; deployment exposure checks remain enforced |

Tests must distinguish deterministic HND application rejection from CometBFT profile rejection and external recovery-anchor rejection. A single generic "startup failed" result is insufficient evidence; record stable error categories and prove the failure occurs before listeners/signing.

## 8. Implementation sequencing and authorization gates

1. **Owner decisions:** approve Config-v1 schema, numeric bounds, canonicalization, independent golden-vector process, CometBFT profile field classification, validator-set identity and trust-root model.
2. **Independent vectors:** generate and cross-check canonical byte/hash vectors with at least two independent implementations before freezing the preimages.
3. **Design review:** approve Genesis envelope, store schema, migration policy and anti-rollback anchor contract.
4. **Explicit implementation authorization:** only then modify source and tests. Keep changes isolated and reviewable; do not combine application identity, CometBFT profile identity and rollback anchor into one opaque patch.
5. **Negative tests:** prove all mismatches reject at InitChain/startup before listeners/signing.
6. **Multi-validator CI:** exercise matching and intentionally divergent validators, restarts, recovery, migration and rollback scenarios.
7. **Independent review:** review code, vectors, trust model, deployment artifacts and evidence before any launch decision.

Current user instruction to continue review is not source-code modification authorization. This document therefore adds no code or tests.

## 9. Decision register

| Item | Current disposition |
|---|---|
| Bind complete HND app config to Genesis | Required; proposed, not implemented |
| Bind config digest to durable store | Required; proposed, not implemented |
| Bind CometBFT profile identity separately | Required; covered by companion profile audit |
| Change store schema v3 | Deferred pending approved migration design |
| Preserve legacy v3 fallback automatically | Not recommended |
| Independent anti-rollback checkpoint | Required for production recovery; mechanism undecided |
| Select numeric bounds / public monetary policy | Not selected |
| Approve public launch or production signing | Not approved |

## 10. Release gate

Until authenticated Genesis/config identity, durable-store identity binding, a separately trusted CometBFT profile pin, and an independent rollback-resistant recovery anchor are implemented and independently reviewed, HND must not claim fail-closed production startup or rollback-resistant recovery.

Existing local restart and multi-validator smoke tests are bounded engineering evidence. They do not prove the missing identity bindings or independent anti-rollback guarantees.

**No source, test, workflow, or runtime changes were made. No public-network, token-issuance, production-signing, or exchange-launch approval is granted.**
