# WP4.14 — Durable State Freshness, Anti-Rollback and CometBFT Recovery Reconciliation Audit

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Review type:** Static source, recovery-design, test and CI-evidence review; documentation only.  
**Change boundary:** No source, tests, workflow, store, CometBFT database, keys or runtime settings changed.

## 1. Executive determination

HND has useful local persistence and disposable restart/convergence tests, but it does not yet establish production-grade freshness of the HND application store or an independently authenticated cross-store recovery checkpoint.

Three properties must remain distinct:

1. **Store integrity:** the file is internally well-formed and its checksum/state reconstruction is consistent.
2. **Store identity:** it belongs to the expected network, protocol and Genesis (and, once implemented, application/profile configuration).
3. **Store freshness:** it is not older than the highest state already committed or independently authorized.

The current schema-v3 store checks internal integrity and legacy identity fields. Its unkeyed SHA-256 checksum does not prove freshness. Existing recovery tests compare selected heights and app hashes after restart in disposable environments; that is not an independent production trust anchor or a pre-listener startup gate.

**Disposition: Critical anti-rollback/freshness gate remains open. Cross-store startup reconciliation is not established as a production invariant. This report selects no vendor, checkpoint protocol, migration, or launch decision.**

## 2. Verified baseline

### 2.1 HND durable store

The current store schema is `APP_STORE_VERSION = 3`. It persists schema version, network ID, protocol version, legacy Genesis hash, committed height, ledger snapshot, evidence journal, app hash and store hash.

Recovery validates the exact key set and schema, verifies the checksum, checks legacy network/protocol/Genesis identity, validates height/hash fields, reconstructs ledger state from Genesis/history, validates the evidence journal and recomputes the app hash.

The store hash is an unkeyed integrity checksum. An older, internally valid store with its matching checksum can be replayed unless an independent freshness source rejects its lower committed position. A checksum recomputed by the same host is not authentication or monotonicity.

### 2.2 Existing restart evidence

Existing lifecycle/recovery audits record bounded positive evidence for local HND store reload, discarding uncommitted state on restart, disposable four-validator outage/restart, post-recovery comparison of height/block hash/app hash, and deterministic timeout/divergence negative controls.

These are useful tests. They do not prove production custody, independent freshness, or rollback resistance against an attacker who can replace both state and local expected values. Process-level failure injection is not a universal power-loss/storage-device guarantee.

### 2.3 HND–CometBFT boundary

HND exposes local committed height and app hash through ABCI Info. The current server startup path loads the HND application and starts the ABCI listener; it does not itself consume an independently authenticated CometBFT checkpoint tuple and compare it with restored HND state before opening the listener.

CometBFT owns its native block store, consensus state and replay/handshake behavior. HND must not guess undocumented CometBFT recovery semantics. Exact pinned CometBFT v0.40.0 behavior for lower/equal/higher application heights and app-hash mismatch needs source-backed integration tests.

## 3. Threat and failure cases

| Case | Current local checks | Required safe outcome |
|---|---|---|
| Truncated/malformed store | Detect malformed data | Reject before listener |
| Modified store without matching checksum | Detect checksum mismatch | Reject |
| Old but internally valid store with matching checksum | No independent freshness proof | Reject against independent high-water checkpoint |
| Old store plus replaced local expected digest | Co-located values are not independent | Anchor still rejects stale state |
| HND store newer than CometBFT native state | HND integrity cannot reconcile it | Quarantine; no automatic truncation |
| CometBFT state newer than HND store | HND integrity cannot recreate missing app state | Quarantine; authenticated recovery only |
| Same height but mismatched app hash/block identity | Height alone is insufficient | Reject and preserve evidence |
| Anchor unavailable or outcome ambiguous | No trustworthy freshness decision | Fail closed; no signing/listening |
| Concurrent restore attempts | Local file checks do not serialize authority | Anchor serializes one monotonic successor |

These are required design outcomes, not claims that every case has occurred in production.

## 4. Required authenticated checkpoint

A future checkpoint should bind:
- record schema/domain;
- chain/network and Genesis identity;
- HND application-config digest and CometBFT profile/release identity once implemented;
- validator identity where validator-specific;
- committed HND height and app hash;
- corresponding CometBFT height, block ID/hash and app hash using semantics verified for the pinned version;
- monotonic sequence/generation and predecessor digest;
- operation ID and PREPARED/COMMITTED state;
- authenticator identity and verification metadata.

A bare height, local JSON file, environment variable, unsigned manifest, CI artifact, or store checksum is not an authenticated checkpoint. Canonical encoding and domain separation must be specified before implementation.

## 5. Trust-anchor requirements

The anchor must be administered independently of the ordinary validator host and its writable backups. Candidate classes include hardware-backed monotonic state, an independently administered authenticated checkpoint/witness service, or a governed multi-witness scheme. This audit selects none.

It must provide authenticated reads, monotonic compare-and-swap (or equivalent serialization), binding of sequence to the complete checkpoint digest, idempotent operation IDs, conflict rejection, and documented behavior for partitions, unavailability, key rotation, device replacement and disaster recovery.

A same-host file, adjacent digest, or orchestrator-supplied expected hash is not independent. A counter alone is insufficient unless transactionally bound to the full state commitment.

## 6. Required startup and recovery ordering

1. Start isolated; disable consensus signing and public/ABCI listeners.
2. Verify the independently provisioned trust root and authenticate the latest committed checkpoint.
3. Validate signed release/config/profile pins and expected network/Genesis identity.
4. Strictly parse the HND store; verify schema, checksum, reconstructed app hash and configuration identity.
5. Read CometBFT native status/checkpoint through a reviewed, version-pinned mechanism.
6. Reconcile HND and CometBFT height, block identity and app hash against each other and the independent checkpoint.
7. Complete only an explicitly authorized, idempotent checkpoint transaction.
8. Verify validator identity and remote-signer anti-double-sign state under its separate trust procedure.
9. Only then enable ABCI listener, CometBFT exposure and signing.

Missing, stale, ambiguous or mismatched state must leave the node quarantined. No automatic truncation, state regeneration, fallback to an older backup, or signer enablement is permitted as a convenience recovery path.

## 7. Crash-consistent checkpoint transaction

A candidate protocol retains immutable generation-addressed state objects, durably writes and rereads the candidate, submits PREPARED with predecessor/generation/operation ID/full digest, independently verifies and commits the successor, rereads the authenticated COMMITTED record, and only then activates the generation. Keep the previous committed generation until the new one is independently verified and retention policy allows collection.

A timeout after a commit request is an unknown outcome. Query using the same operation ID and reconcile; do not issue a conflicting successor or assume rollback. Concurrent restores must be serialized by the anchor. Review every crash boundary and platform-specific durability assumption.

## 8. Required negative and integration tests

| ID | Test | Required result |
|---|---|---|
| FRESH-01 | Restore older internally valid HND store with valid checksum | Independent anchor rejects |
| FRESH-02 | Replace store and adjacent local expected digest | Independent anchor still rejects |
| FRESH-03 | Anchor sequence ahead of local store | Quarantine; no listener/signing |
| FRESH-04 | HND height ahead of CometBFT checkpoint | Quarantine; no automatic rollback |
| FRESH-05 | CometBFT height ahead of HND store | Quarantine; authenticated recovery only |
| FRESH-06 | Same height, different app hash/block identity | Reject |
| FRESH-07 | Anchor unavailable, unauthenticated or stale | Fail closed |
| FRESH-08 | Crash before/after PREPARED, during COMMIT, after acknowledgement loss | Idempotent reconciliation; no signing while ambiguous |
| FRESH-09 | Concurrent restore/start for same validator generation | One successor wins; conflict rejected |
| FRESH-10 | Replace both HND and CometBFT data directories with older snapshot | Independent checkpoint detects rollback |
| FRESH-11 | First boot versus established-chain restart | Fresh init only through explicit Genesis ceremony; established restart requires authenticated state |
| FRESH-12 | Pinned CometBFT v0.40.0 lower/equal/higher app-height and app-hash mismatch matrix | Exact native and HND outcomes recorded |
| FRESH-13 | Restore across approved schema/profile activation | Only authenticated migration/activation accepted; downgrade rejected |
| FRESH-14 | Anchor key rotation, witness loss, hardware replacement and disaster recovery | Auditable threshold/two-person recovery |

Use disposable state and keys. Capture exact CometBFT source/build identity, HND/CometBFT heights and hashes, checkpoint sequence, listener/signing state and machine-readable rejection markers. Unit fixtures do not substitute for the CometBFT integration matrix.

## 9. Ownership and closure evidence

| Control | Primary owner | Closure evidence |
|---|---|---|
| HND store schema, app hash and config identity | HND application | Versioned schema, migration rules, negative tests |
| Native block store and consensus recovery | CometBFT | Exact v0.40.0 source review and reproducible integration |
| Cross-store comparison and startup quarantine | HND launcher/integration | Mismatch tests proving no listener/signing |
| Independent monotonic checkpoint | Separate trust-anchor domain | Threat model, authenticated protocol, failure/recovery drills |
| Validator anti-double-sign state | Remote signer/custody | Independent signer anchor and restore evidence |
| Release pins and upgrade activation | Governance/release process | Signed release manifest, two-person approval, rollback policy |

## 10. CI evidence and limitations

At review time, workflow run `42299443418` was on commit `c94cbaf85835bdb3facf6da657532644d964a811`. The `hnd-v02-tests` job completed successfully; `cometbft-single-node-smoke` remained in progress, with the CometBFT binary build step active and subsequent integration steps pending.

This is not a completed full-workflow pass. No CI run for this new documentation commit is claimed. Earlier passing runs apply only to their exact commits and scopes.

## 11. Release decision

**NOT APPROVED** for public network launch, production validator signing, token issuance or exchange launch.

Closure requires implemented and independently reviewed configuration identity, independent freshness anchor, HND/CometBFT cross-store reconciliation, crash-consistent restore semantics, FRESH-01–14, signed release governance and production operations evidence.

This is a design/audit artifact only. Recommendations remain proposals until the protocol owner explicitly approves them.
