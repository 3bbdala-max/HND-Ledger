# HND/CometBFT Recovery Checkpoint Protocol v1 — Design Draft

**Status:** Draft for protocol-owner and independent security review. Not an implementation contract.
**Decision basis:** DEC-HREC-01 (2026-11-18).
**Target:** HND v0.2 with the pinned CometBFT v0.40.0 build.
**Release boundary:** This document does not authorize production deployment, signing, public listeners, token issuance, or real-value use.

## 1. Purpose and scope

Define the missing independent checkpoint contract for recovery of the HND application store and CometBFT native state. The checkpoint is a freshness and reconciliation authority, not a replacement for either store and not a validator signing authority.

The node MUST enter quarantine before recovery inspection. Consensus signing, transaction admission, ABCI/public listeners, and ordinary service exposure remain disabled until reconciliation succeeds and a separate activation gate authorizes service.

This protocol is deliberately separate from the existing Trust Manifest/VSP monotonic namespaces. The current remote monotonic-anchor v1 stores only a sequence and digest for the `trust-manifest` and `vsp-profile` namespaces. It does not store the HND/CometBFT recovery tuple, immutable recovery operation, or PREPARED/COMMITTED recovery lifecycle. It MUST NOT be treated as an HREC implementation.

## 2. Checkpoint record: required semantic fields

A committed checkpoint MUST bind, as one authenticated immutable record:

| Field | Required meaning |
|---|---|
| `record_schema` | Exact schema identifier and version |
| `domain` | Fixed domain-separation label for HND recovery checkpoints |
| `network_id` | HND network identifier |
| `genesis_hash` | Approved HND Genesis identity |
| `protocol_config_digest` | Digest of the approved HND protocol/configuration identity |
| `cometbft_release_identity` | Exact pinned CometBFT v0.40.0 source/build identity |
| `hnd_height` | Last committed HND application height |
| `hnd_app_hash` | HND application hash at that height |
| `cometbft_height` | Corresponding CometBFT committed height |
| `cometbft_block_identity` | Version-pinned identity of the corresponding CometBFT block |
| `cometbft_app_hash` | CometBFT-recorded application hash, with semantics verified against the pinned source |
| `sequence` | Monotonic checkpoint generation |
| `predecessor_digest` | Digest of the preceding committed checkpoint; absent only at approved bootstrap |
| `operation_id` | Globally unique immutable identifier for the checkpoint transition |
| `operation_state` | `PREPARED` or `COMMITTED`, as returned by the anchor's operation API |
| `authenticator_metadata` | Authenticated principal/key identity and verification metadata, without private material |

The checkpoint MUST NOT infer equality merely from matching heights. Both store identities, block identity, and app-hash relationships must be compared using semantics established for the exact pinned CometBFT version.

If the deployment requires validator-specific checkpoints, the protocol owner must decide whether validator identity is part of the record's scope and how a validator-set transition is represented. This draft does not silently impose a per-validator or network-global scope.

## 3. Encoding and digest

Before implementation, the protocol owner and independent reviewer MUST freeze:
- canonical serialization format and exact version;
- domain-separation bytes and digest construction;
- integer bounds and textual encoding for heights/sequences;
- treatment of absent, null, and optional fields;
- exact CometBFT block-ID and app-hash extraction semantics;
- compatibility and schema migration rules.

The digest MUST cover every semantic field in the committed record, excluding only fields explicitly designated as transport/authentication envelope metadata. The digest MUST be reproducible across independent implementations. Duplicate keys, unknown fields, non-canonical encodings, invalid ranges, and ambiguous optional-field representations MUST be rejected.

No implementation may substitute a local checksum, unsigned JSON file, environment variable, CI artifact, or co-located digest for the authenticated checkpoint.

## 4. Independent anchor contract

The anchor MUST operate in a separate administrative and failure domain from the validator host, its ordinary writable storage, backups, and operator credentials. The existing SQLite anchor is reference/test-only and does not satisfy this deployment requirement.

The service contract MUST provide:

1. Authenticated reads of the latest committed checkpoint and the exact operation state for a supplied operation ID.
2. A linearizable PREPARE operation that compares the exact committed predecessor (sequence and digest) and reserves one immutable successor under one operation ID.
3. A linearizable COMMIT operation that commits only the exact previously prepared operation, with matching operation ID, predecessor, successor digest, and full record.
4. Durable-before-acknowledgement semantics for both PREPARE and COMMIT.
5. Idempotent retries using the same operation ID and identical request bytes/semantic digest.
6. Conflict rejection for a reused operation ID with different contents, a stale predecessor, a skipped sequence, a competing successor, or a commit without a matching prepared operation.
7. Read-after-write consistency across all replicas and regions.
8. Append-only attributable audit events for prepare, commit, conflict, and administrative recovery.
9. No ordinary rollback, deletion, namespace recreation, or backup restore that lowers the highest committed sequence.
10. A separately witnessed disaster-recovery ceremony that cannot silently lower the committed checkpoint.

A pending PREPARED operation MUST remain visible and MUST block a conflicting successor until it is explicitly reconciled under the same operation ID. This draft does not define an unsafe cancel/forget operation.

## 5. Candidate operation lifecycle

The following lifecycle is a proposal for review, not a frozen wire API.

### 5.1 Prepare

The caller reads the latest committed checkpoint, verifies the complete local HND and CometBFT state against the approved recovery policy, constructs the exact successor record, and submits PREPARE with:
- operation ID;
- exact predecessor sequence and digest (or approved bootstrap marker);
- complete successor record and digest;
- authenticated caller identity.

The anchor atomically verifies the predecessor and reserves the immutable operation as PREPARED. A competing operation cannot reserve the same predecessor.

### 5.2 Commit

After all required state writes and independent verification required by the final protocol are durable, the caller submits COMMIT for the same operation ID and exact prepared digest. The anchor atomically promotes that successor to the latest COMMITTED checkpoint and retains the operation outcome.

The protocol owner MUST decide the precise ordering between local durable state, CometBFT native commit, PREPARE, and COMMIT. The order must be consistent with the pinned CometBFT commit boundary and must be proven by crash injection. This draft intentionally does not guess that ordering.

### 5.3 Unknown outcomes

A timeout after PREPARE or COMMIT is an unknown outcome, not a failure and not permission to create another operation ID.

The caller MUST:
1. remain quarantined;
2. query the same operation ID and latest committed checkpoint;
3. accept only an exact matching PREPARED or COMMITTED outcome;
4. retry only the same idempotent operation when the observed state proves that retry is safe;
5. reject any conflicting operation, digest, predecessor, or unexpected sequence.

If the anchor is unavailable or the outcome cannot be established, no replay, listener, transaction admission, or signing is permitted.

## 6. Recovery decision matrix

| Observed condition | Required result |
|---|---|
| Fresh Genesis with no prior committed state | Explicit, separately authorized Genesis bootstrap only |
| HND and CometBFT match the authenticated checkpoint | Continue to the separate startup authorization gate |
| HND is behind CometBFT | Quarantine; explicit replay only if every DEC-HREC-01 prerequisite is met |
| HND is ahead of CometBFT | Quarantine; no automatic HND rollback |
| Equal height but app hash or block identity differs | Quarantine; reject silent acceptance |
| Established-chain HND state is missing | Quarantine; no empty-state initialization |
| CometBFT native store is missing, stale, or older than checkpoint | Quarantine; witnessed restore only |
| Anchor unavailable, stale, unauthenticated, or ambiguous | Quarantine; no replay/listener/signing |
| Replay does not reproduce the authenticated target | Quarantine and preserve all evidence |
| Operation outcome is PREPARED or unknown | Quarantine; reconcile the same operation ID |
| Operation is COMMITTED and all local/native state re-reads match it | Continue to a separate activation authorization gate |

No automatic truncation, reset, downgrade, regeneration of established-chain state, or fallback to a convenient older backup is permitted.

## 7. Replay requirements

Replay is an explicit recovery operation, never an ordinary startup fallback. It is eligible only when:
- exact HND network/Genesis/config and pinned CometBFT release identities match;
- the independent authenticated checkpoint establishes the target chain identity and position;
- the native CometBFT store is independently shown to be the trusted source for the missing transitions;
- the replay range is contiguous and verifiable from the last authenticated HND point to the anchored target;
- replay occurs in quarantine with signing, listeners, and transaction admission disabled;
- every transition is deterministic and the final HND app hash matches the checkpoint;
- both stores are reread and match the checkpoint before separate activation authorization.

Any absent, stale, ambiguous, or inconsistent prerequisite prohibits replay.

## 8. Required tests and evidence

The final protocol implementation must execute HREC01–HREC09 and FRESH-01–FRESH-14 against the exact pinned CometBFT v0.40.0 build, with disposable keys and state.

In addition to the existing local HREC03 pre-rename fsync-failure regression, add integration/fault-injection coverage for:
- initial checkpoint bootstrap;
- matching clean restart;
- HND-behind replay and exact target verification;
- HND-ahead quarantine;
- equal-height app-hash and block-identity mismatch;
- older but internally valid HND backup;
- older CometBFT native database;
- missing established-chain HND state;
- anchor unavailable, stale, unauthenticated, and malformed responses;
- crash before/after PREPARE, during COMMIT, and after durable COMMIT with lost response;
- same-operation retry and conflicting operation-ID reuse;
- two concurrent recovery attempts for one predecessor;
- anchor replica failover and read-after-write consistency;
- recovery service disaster-recovery and witnessed restore;
- proof that no listener, transaction admission, or signer becomes active while quarantined or ambiguous.

Each test must capture exact source/build identity, HND height/app hash, CometBFT height/block identity/app hash, checkpoint sequence/digest/operation state, process/listener/signing state, logs, and final store hashes. Test steps must actually execute on the exact commit; zero-step Actions failures are infrastructure blocks, not test results.

## 9. Decisions still required before implementation

The following are intentionally unresolved and require explicit protocol-owner disposition plus independent review:

1. Network-global versus validator-specific checkpoint scope.
2. Canonical encoding, digest domain separation, and schema versioning.
3. Exact CometBFT block identity and app-hash semantics from pinned v0.40.0 source.
4. Genesis bootstrap authorization and initial sequence.
5. Exact PREPARE/COMMIT ordering relative to HND and CometBFT durable commit boundaries.
6. Whether a pending PREPARED operation can ever be superseded, and the witnessed procedure if its owner is permanently unavailable.
7. Checkpoint cadence and performance/availability budget.
8. Service identity, administrator separation, mTLS certificate issuance/rotation/revocation, and independent backup/disaster recovery.
9. Retention and audit evidence requirements.
10. Validator identity and validator-set transition binding, if checkpoint scope is validator-specific.

No source code, schema, production endpoint, key, trust root, workflow, or runtime configuration should be changed until these decisions are frozen.

## 10. Relationship to existing components

- `hnd_v02/remote_monotonic_anchor.py` and `docs/REMOTE_MONOTONIC_ANCHOR_PROTOCOL.md` implement/reference the existing Trust Manifest/VSP sequence-and-digest contract. They are not the HREC record or operation protocol.
- `hnd_v02/remote_activation_intent.py` and `hnd_v02/activation_coordinator.py` coordinate profile activation intent and local activation. They do not reconcile HND application state with CometBFT native state.
- `hnd_v02/cometbft_supervisor.py` verifies and launches a pinned executable after the existing activation authorization flow. It does not prove cross-store recovery or enforce that every possible OS launch path is disabled.
- `hnd_v02/cometbft_v040_server.py` serves the HND ABCI application and must not be exposed before the recovery/activation gates are satisfied.

These components may be reused only after their contracts are extended and reviewed for HREC semantics. Reusing their names or interfaces does not establish the required guarantees.

## 11. Approval and release boundary

This draft records a proposed protocol decomposition derived from DEC-HREC-01. It is not the independent review, signed protocol freeze, implementation, integration test, or production approval.

Until the unresolved decisions are ratified and the required tests pass on exact commits:
- no production signing;
- no public or untrusted listener;
- no real-value transactions or token issuance;
- no claim of production anti-rollback or cross-store recovery safety.

