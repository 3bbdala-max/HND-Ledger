# HND v0.2 — Independent Cross-Store Recovery Checkpoint Interface

**Date:** 2026-11-18  
**Design ID:** HREC-CP-01  
**Status:** Interface design proposal derived from DEC-HREC-01; not implemented or production-approved.  
**Scope:** Independent freshness and identity checkpoint for HND application state and CometBFT v0.40.0 native state.

## 1. Decision and non-reuse finding

The existing `RemoteMonotonicAnchor` protocol is **not sufficient** to serve as the HND/CometBFT recovery checkpoint.

The existing API is intentionally limited to two namespaces (`trust-manifest` and `vsp-profile`) and records containing only `sequence` and `digest`. Its client/server and SQLite backend are designed for trust-manifest/VSP activation freshness. They do not encode or validate a committed HND height, HND app hash, CometBFT block identity, predecessor relationship, chain/Genesis identity, or CometBFT build/profile identity.

The existing remote anchor protocol may remain appropriate for its documented activation purpose. It must not be relabelled, overloaded, or cited as proof of cross-store recovery freshness. The existing SQLite implementation and mTLS reference server are explicitly single-host/reference components, not an independently operated production trust domain.

**Selected direction:** define a separate typed recovery-checkpoint contract and adapter boundary. Reuse of transport or storage primitives may be considered later only after the new record semantics, server invariants, administration boundary, and independent review are specified. No production service, vendor, hardware root, or consensus protocol is selected here.

## 2. Security objective

For an established HND network, startup must be able to compare the locally recovered HND and CometBFT state against an authenticated, rollback-resistant checkpoint administered outside the validator host's ordinary writable storage, backup, credentials, and administrative failure domain.

A local checksum, SQLite database on the validator host, VM snapshot, CI artifact, adjacent manifest, timestamp, or unsigned digest supplied by the node is not an independent freshness authority.

If the checkpoint is missing, unavailable, stale, unauthenticated, malformed, from another chain/build, or inconsistent with either local store, the node remains quarantined. No listener, transaction admission, or consensus signing may be enabled by this interface.

## 3. Typed checkpoint record

The logical record is versioned and canonical. The following fields are mandatory; exact canonical encoding and digest domain separation must be frozen before implementation.

| Field | Meaning |
|---|---|
| `record_version` | Checkpoint schema version |
| `checkpoint_sequence` | Strictly increasing service-controlled sequence; distinct from block height |
| `checkpoint_id` | Globally unique idempotency identifier for this checkpoint publication |
| `predecessor_checkpoint_digest` | Digest of the exact preceding committed checkpoint, null only for the approved bootstrap |
| `network_id` / `chain_id` | Exact HND network and CometBFT chain identity |
| `genesis_hash` | Digest of the approved Genesis manifest |
| `protocol_config_digest` | Digest binding protocol and consensus configuration identity |
| `hnd_store_schema` | HND application-store schema/version |
| `hnd_height` | Last committed HND application height |
| `hnd_app_hash` | HND application hash at that height |
| `cometbft_version` | Exact pinned CometBFT version |
| `cometbft_binary_digest` | Digest of the approved CometBFT executable/build |
| `cometbft_profile_digest` | Digest of the approved CometBFT node/profile configuration |
| `cometbft_height` | Last committed native CometBFT block height |
| `cometbft_block_id` | Canonical identity of the corresponding committed block, including the fields required by the pinned CometBFT version |
| `cometbft_app_hash` | App hash recorded by CometBFT for that committed state |
| `commit_evidence_digest` | Digest/reference to the commit evidence required to authenticate the checkpointed block and its predecessor relationship |
| `publication_operation_id` | Idempotent identity of the publication operation |

The record must bind one coherent recovery point. The implementation must reject records in which the HND height, CometBFT height, block identity, app hash, network identity, Genesis, protocol configuration, or binary/profile identity do not satisfy the exact pinned-version reconciliation contract.

A service-generated timestamp may be retained for audit, but it is never the freshness authority. Freshness is established by the independently protected checkpoint sequence and predecessor chain.

## 4. API boundary (proposed)

Use a separate recovery namespace and typed endpoints; do not extend the current trust-manifest/VSP record shape in place.

### Read latest checkpoint

`POST /v1/recovery/checkpoint/read`

Request identifies the exact network/chain namespace. Response returns either an explicit uninitialized state (allowed only during the separately approved first-boot ceremony) or the complete authenticated checkpoint record, its canonical digest, and service authentication evidence.

### Compare and publish successor

`POST /v1/recovery/checkpoint/compare-and-publish`

Request contains:
- exact network/chain namespace;
- exact predecessor checkpoint sequence and digest (or explicit bootstrap marker);
- complete proposed checkpoint record;
- stable publication operation ID.

Response distinguishes:
- committed successor;
- predecessor conflict;
- same operation already committed with byte-identical record;
- same operation ID with different content (fatal conflict);
- unknown outcome / unavailable (caller must read and reconcile; never assume failure).

The server, not only the client, enforces schema, chain identity, sequence progression, predecessor linkage, immutable operation identity, and consistency rules. It returns a durable commit acknowledgement only after the record is committed to the independent authority.

The exact wire encoding, cryptographic envelope, response authentication format, HTTP status mapping, request-size limits, and service discovery/certificate lifecycle remain implementation-spec work. No numeric bounds are invented in this design.

## 5. Mandatory independent-service invariants

The production authority must provide:

1. Linearizable compare-and-publish for each chain namespace across all replicas.
2. Durable commit before acknowledging success, with read-after-write visibility.
3. Strictly increasing service-controlled checkpoint sequence and exact predecessor digest matching.
4. Idempotent publication by operation ID; reuse with different content is rejected.
5. Authenticated client identity and authorization scoped to the intended chain/validator role.
6. An authenticated read response; TLS transport alone does not make a returned record authoritative if service identity or state can be rolled back.
7. Append-only audit binding principal, operation ID, predecessor, successor digest, outcome, and service commit evidence.
8. Backup/restore and disaster recovery that preserve the highest acknowledged checkpoint; ordinary service restore must not lower or fork the committed sequence.
9. Administrative, backup, and validator-host credentials separated across independent principals/failure domains.
10. Fail-closed behavior on service unavailability, authentication failure, stale replica, conflicting operation, malformed response, or ambiguous state.
11. A separately witnessed recovery ceremony for exceptional service loss; no silent reset, namespace recreation, truncation, or older-checkpoint fallback.

A remote endpoint backed by a database that the validator operator can restore or rewrite together with the validator host does not meet the independence requirement.

## 6. Publication and recovery semantics

The checkpoint is a statement about an already committed, verified cross-store state; it is not a substitute for CometBFT consensus finality or signer anti-double-sign protection.

The implementation must define a pinned-version transaction boundary and prove the order of:
- CometBFT block commit and native-store durability;
- HND application state durability and app-hash calculation;
- verification that both stores describe the same committed block;
- publication of the checkpoint successor;
- permission to continue normal operation.

If a process crashes after a block is committed but before the checkpoint publication is acknowledged, startup enters quarantine. The outcome is unknown until the independent service is read and the local/native evidence is reconciled. The node must not invent a checkpoint, roll back either store, or assume that a timed-out publication failed.

Recovery from a checkpoint may use deterministic CometBFT replay only under DEC-HREC-01: the exact native database and binary are trusted, the replay input is contiguous and independently verifiable from the authenticated checkpoint, signing/listeners remain disabled, and the final HND/CometBFT state is checked against an authenticated target before a separate activation gate. If the target cannot be authenticated or replay cannot be proved deterministic, require witnessed restore.

The checkpoint protocol does not authorize validator signing. Signer anti-rollback and anti-double-sign protection remain a separate independent control.

## 7. State classifications

| Observed condition | Required state |
|---|---|
| Fresh network before any committed state | First-boot ceremony only; no implicit restart initialization |
| Both local stores match the authenticated checkpoint exactly | Eligible for the separate startup authorization gate |
| HND behind CometBFT | Quarantine; replay only under DEC-HREC-01 and pinned-version evidence |
| HND ahead of CometBFT | Quarantine; no automatic rollback |
| Same height but different app hash or block identity | Quarantine |
| Either local store missing on an established network | Quarantine; no empty-state regeneration |
| Local state older than authenticated checkpoint | Quarantine; reject rollback |
| Checkpoint missing, stale, unavailable, or ambiguous | Quarantine |
| Publication outcome timed out | Quarantine until read/reconciliation proves exact outcome |
| Checkpoint identity/build/profile mismatch | Quarantine |
| Replay result differs from authenticated target | Quarantine; preserve evidence |

## 8. Required implementation and test gates

Before implementation can be accepted:

- Freeze canonical record encoding, digest domain separation, and exact CometBFT block-ID/commit-evidence fields against the pinned v0.40.0 source.
- Specify how checkpoint publication is integrated with CometBFT/HND commit lifecycle, including crash windows and service outages.
- Specify authenticated service identity, authorization, key/certificate lifecycle, independent administration, backup/restore, and witnessed disaster recovery.
- Implement a server whose linearizability, durable acknowledgement, idempotency, anti-rollback backup behavior, and audit guarantees are independently testable.
- Implement a client that authenticates both service and record, rejects stale/conflicting responses, and reconciles ambiguous writes by operation ID.
- Integrate the checkpoint read into the mandatory quarantine/startup gate; remove every alternate route that can start listeners or sign without that gate.
- Add disposable HREC01–HREC09 and FRESH-01–FRESH-14 tests, including crash/lost-response injection around each local commit and remote publication boundary, stale/rolled-back service replicas, conflicting concurrent publishers, backup restore, chain/build mismatch, and unavailable service.
- Execute the complete test matrix on the exact pinned CometBFT build and exact commit; independently review results and the service threat boundary.

No source code, test, workflow, runtime configuration, signer, or persistent store is changed by this design document. Production signing and public service remain disabled.
