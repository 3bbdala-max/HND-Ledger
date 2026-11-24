# HND/CometBFT Recovery Checkpoint Protocol v1 — Design Draft

**Status:** Draft for protocol-owner and independent security review. Not an implementation contract.
**Decision basis:** [DEC-HREC-01](DECISION_HREC_RECOVERY_POLICY_2026-11-18.md) and [HREC-CP-01](HREC_INDEPENDENT_CHECKPOINT_INTERFACE_DESIGN_2026-11-18.md) (2026-11-18).
**Target:** HND v0.2 with the pinned CometBFT v0.40.0 build.
**Release boundary:** This document does not authorize production deployment, signing, public listeners, token issuance, or real-value use.

## 1. Purpose and scope

Define the missing independent checkpoint contract for recovery of the HND application store and CometBFT native state. The checkpoint is a freshness and reconciliation authority, not a replacement for either store and not a validator signing authority.

The node MUST enter quarantine before recovery inspection. Consensus signing, transaction admission, ABCI/public listeners, and ordinary service exposure remain disabled until reconciliation succeeds and a separate activation gate authorizes service.

This protocol is deliberately separate from the existing Trust Manifest/VSP monotonic namespaces. The current remote monotonic-anchor v1 stores only a sequence and digest for the `trust-manifest` and `vsp-profile` namespaces. It does not store the HND/CometBFT recovery tuple, immutable recovery operation, or PREPARED/COMMITTED recovery lifecycle. It MUST NOT be treated as an HREC implementation.

## 2. Checkpoint record: required semantic fields

A checkpoint payload MUST bind, as one authenticated immutable record:

| Field | Required meaning |
|---|---|
| `record_schema` | Exact schema identifier and version |
| `domain` | Fixed domain-separation label for HND recovery checkpoints |
| `network_id` | HND network identifier |
| `genesis_hash` | Approved HND Genesis identity |
| `protocol_config_digest` | Digest of the approved HND protocol/configuration identity |
| `cometbft_release_identity` | Exact pinned CometBFT v0.40.0 source/build identity |
| `hnd_app_height` | HND application state height after deterministic execution and durable Commit of block `h` |
| `hnd_app_hash` | HND application hash produced after executing block `h` from the authenticated predecessor state |
| `predecessor_state_snapshot_digest` | Digest/reference for the complete predecessor HND state snapshot needed to replay block `h`; the app hash alone cannot reconstruct state |
| `successor_state_snapshot_digest` | Digest/reference for the resulting HND state snapshot, if retained for recovery
| `cometbft_proof_header_height` | Height `h` of the signed CometBFT header and committed block used to verify the HND transition |
| `cometbft_block_id` | Complete BlockID identity for the signed block, including header hash and PartSetHeader |
| `cometbft_header_app_hash` | `Header.AppHash` in the signed header; for height `h` it must equal the predecessor HND app hash at height `h-1` |
| `sequence` | Monotonic checkpoint generation |
| `predecessor_digest` | Digest of the preceding committed checkpoint; absent only at approved bootstrap |
| `operation_id` | Globally unique immutable identifier for the checkpoint transition |
| `signed_header_proof_digest` | Digest/reference for the signed header, commit, validator set, and trusted light-client verification evidence |
| `block_execution_input_digest` | Digest/reference for the full verified block and all HND execution inputs used to derive the successor app hash |
| `hnd_build_identity` | Exact approved HND source/build identity used for deterministic execution |
| `authenticator_metadata` | Authenticated principal/key identity and verification metadata, without private material |

The checkpoint MUST NOT infer equality merely from matching heights. Both store identities, block identity, and app-hash relationships must be compared using semantics established for the exact pinned CometBFT version. In particular, `Header[h].AppHash` is the application hash after the previous block, not the result of executing block `h`. For the normal HND transition, `Header[h].AppHash` must equal the predecessor HND app hash at height `h-1`; the successor HND app hash at height `h` is derived by deterministic execution of the full authenticated block `h`.

If the deployment requires validator-specific checkpoints, the protocol owner must decide whether validator identity is part of the record's scope and how a validator-set transition is represented. This draft does not silently impose a per-validator or network-global scope.

## 3. CometBFT v0.40.0 application-hash relationship

The source-grounded mapping is specified in `docs/HREC_COMETBFT_V0400_APPHASH_SEMANTICS.md`. It is mandatory input to this protocol, not optional background.

For HND application hash `A[h]` after committing block `h`, CometBFT header `H[h]` carries `H[h].AppHash == A[h-1]`. The signed header at height `h` commits to block `h`; the verifier must authenticate the full block against its BlockID, then execute the exact HND transition from the authenticated predecessor state `A[h-1]` to derive `A[h]`. The resulting HND app hash must match the local durable HND state. The ABCI `Info` handshake is a local consistency check only; it is not an independent cryptographic proof of the app hash.

The first block is a special bootstrap case: its header AppHash is the initial application hash returned by `InitChainResponse.app_hash`. Genesis authorization must pin that value, the chain ID, the initial validator set, and the exact Genesis/configuration identity.

Do not compare `HND Info.last_block_app_hash` directly with `Header[h].AppHash` at the same height. Do not use an ambiguous `cometbft_app_hash` field. The checkpoint must separately bind the predecessor hash in the signed header and the successor hash derived by deterministic execution.

## 4. Encoding and digest

Before implementation, the protocol owner and independent reviewer MUST freeze:
- canonical serialization format and exact version;
- domain-separation bytes and digest construction;
- integer bounds and textual encoding for heights/sequences;
- treatment of absent, null, and optional fields;
- exact CometBFT block-ID and app-hash extraction semantics;
- compatibility and schema migration rules.

The digest MUST cover every semantic field in the immutable checkpoint payload, excluding only fields explicitly designated as transport/authentication envelope metadata. The digest MUST be reproducible across independent implementations. Duplicate keys, unknown fields, non-canonical encodings, invalid ranges, and ambiguous optional-field representations MUST be rejected.

The checkpoint payload MUST NOT contain a mutable operation status. `PREPARED` and `COMMITTED` are states of the anchor's operation record, not fields in the checkpoint payload and not inputs to the checkpoint digest. The anchor operation response MUST carry the operation state separately from the immutable checkpoint payload. A transition from PREPARED to COMMITTED MUST therefore preserve the exact same checkpoint payload and digest.

No implementation may substitute a local checksum, unsigned JSON file, environment variable, CI artifact, or co-located digest for the authenticated checkpoint.

## 5. Independent anchor contract

The anchor MUST operate in a separate administrative and failure domain from the validator host, its ordinary writable storage, backups, and operator credentials. The existing SQLite anchor is reference/test-only and does not satisfy this deployment requirement.

The service contract MUST provide:

1. Authenticated reads of the latest committed checkpoint payload and the exact operation state for a supplied operation ID. The operation state is returned separately and is not embedded in the checkpoint payload.
2. A linearizable PREPARE operation that compares the exact committed predecessor (sequence and digest) and reserves one immutable successor under one operation ID.
3. A linearizable COMMIT operation that commits only the exact previously prepared operation, with matching operation ID, predecessor, successor digest, and full immutable checkpoint payload.
4. Durable-before-acknowledgement semantics for both PREPARE and COMMIT.
5. Idempotent retries using the same operation ID and identical request bytes/semantic digest.
6. Conflict rejection for a reused operation ID with different contents, a stale predecessor, a skipped sequence, a competing successor, or a commit without a matching prepared operation.
7. Read-after-write consistency across all replicas and regions.
8. Append-only attributable audit events for prepare, commit, conflict, and administrative recovery.
9. No ordinary rollback, deletion, namespace recreation, or backup restore that lowers the highest committed sequence.
10. A separately witnessed disaster-recovery ceremony that cannot silently lower the committed checkpoint.

A pending PREPARED operation MUST remain visible and MUST block a conflicting successor until it is explicitly reconciled under the same operation ID. This draft does not define an unsafe cancel/forget operation.

## 6. Candidate operation lifecycle

The following lifecycle is a proposal for review, not a frozen wire API.

### 5.1 Prepare

The caller reads the latest committed checkpoint, verifies the complete local HND and CometBFT state against the approved recovery policy, constructs the exact successor record, and submits PREPARE with:
- operation ID;
- exact predecessor sequence and digest (or approved bootstrap marker);
- complete successor record and digest;
- authenticated caller identity.

The anchor atomically verifies the predecessor and reserves the immutable operation as PREPARED. A competing operation cannot reserve the same predecessor.

### 5.2 Commit

After CometBFT `ApplyVerifiedBlock` has returned successfully, both native and HND stores have been independently reread, and the full proof/execution checks have passed, the caller submits COMMIT for the same operation ID and exact prepared digest. The anchor atomically promotes that immutable payload to the latest committed checkpoint and changes the separate operation record from PREPARED to COMMITTED. The payload and digest do not change during this transition.

The pinned v0.40.0 ordering is specified in `docs/HREC_CHECKPOINT_PUBLICATION_BOUNDARY_PROPOSAL.md` and `docs/HREC_INDEPENDENT_CHECKPOINT_INTERFACE_DESIGN_2026-11-18.md` §9. The publisher MUST NOT run inside the HND ABCI `Commit` handler: HND state may be durable while CometBFT's native state database has not yet completed `Store.Save(state)`. PREPARE/COMMIT are permitted only after `ApplyVerifiedBlock` returns successfully and the publisher independently rereads and verifies both stores, the native block/commit evidence, and deterministic HND execution. No such post-ApplyVerifiedBlock hook is currently implemented in this repository. Until its exact integration point and failure propagation are reviewed and tested, HREC checkpoint publication is not implementable through the current Python ABCI adapter alone.

### 5.3 Unknown outcomes

A timeout after PREPARE or COMMIT is an unknown outcome, not a failure and not permission to create another operation ID.

The caller MUST:
1. remain quarantined;
2. query the same operation ID and latest committed checkpoint;
3. accept only an exact matching PREPARED or COMMITTED outcome;
4. retry only the same idempotent operation when the observed state proves that retry is safe;
5. reject any conflicting operation, digest, predecessor, or unexpected sequence.

If the anchor is unavailable or the outcome cannot be established, no replay, listener, transaction admission, or signing is permitted. If publication fails after local commit, the node must not proceed into the next consensus round; it must stop or remain in an enforced quarantine state until the exact operation outcome is reconciled. A restarted process must not resume consensus until the same operation ID, anchor outcome, and both local stores have been reconciled.

## 7. Recovery decision matrix

| Observed condition | Required result |
|---|---|
| Fresh Genesis with no prior committed state | Explicit, separately authorized Genesis bootstrap only |
| HND state at height `h` equals deterministic execution of verified block `h` from anchored predecessor state `h-1`, and local CometBFT native state verifies against the same signed block | Continue to the separate startup authorization gate |
| HND state is behind the anchored application checkpoint | Quarantine; replay only from the authenticated predecessor and verified contiguous blocks under DEC-HREC-01 |
| HND app height exceeds the latest verified CometBFT block height, or the local native store cannot prove the intervening blocks | Quarantine; no automatic HND rollback or acceptance |
| Equal numeric height but HND hash differs from deterministic replay output, or signed block identity differs | Quarantine; reject silent acceptance. Never compare HND `Info.last_block_app_hash` directly to the same-height header `AppHash` |
| Established-chain HND state is missing | Quarantine; no empty-state initialization |
| CometBFT native store is missing, stale, or older than the latest anchored proof header | Quarantine; witnessed restore only |
| Anchor unavailable, stale, unauthenticated, or ambiguous | Quarantine; no replay/listener/signing |
| Replay does not reproduce the exact HND app hash derived from the verified block | Quarantine and preserve all evidence |
| Operation outcome is PREPARED or unknown | Quarantine; reconcile the same operation ID |
| Operation is COMMITTED and all local/native state re-reads match it | Continue to a separate activation authorization gate |

No automatic truncation, reset, downgrade, regeneration of established-chain state, or fallback to a convenient older backup is permitted.

## 8. Replay requirements

Replay is an explicit recovery operation, never an ordinary startup fallback. The checkpoint must make the complete predecessor state recoverable; a digest without retrievable state bytes is evidence of identity, not a recovery source. The normal transition is: signed header/block at height `h` authenticates the predecessor HND app hash `A[h-1]`; deterministic execution of that full block produces `A[h]`. It is eligible only when:
- exact HND network/Genesis/config and pinned CometBFT release identities match;
- the independent authenticated checkpoint establishes the target chain identity and position;
- the native CometBFT store is independently shown to be the trusted source for the missing transitions;
- the replay range is contiguous and verifiable from the last authenticated HND point to the anchored target;
- replay occurs in quarantine with signing, listeners, and transaction admission disabled;
- every transition is deterministic and the final HND app hash matches the checkpoint;
- both stores are reread and match the checkpoint before separate activation authorization.

Any absent, stale, ambiguous, or inconsistent prerequisite prohibits replay.

## 9. Required tests and evidence

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
- crash before/after blockstore save and WAL EndHeight, during ABCI FinalizeBlock/Commit, after HND durable Commit but before CometBFT state Store.Save, after Store.Save but before ApplyVerifiedBlock returns, before/after PREPARE, during COMMIT, and after durable COMMIT with lost response;
- same-operation retry and conflicting operation-ID reuse;
- two concurrent recovery attempts for one predecessor;
- anchor replica failover and read-after-write consistency;
- recovery service disaster-recovery and witnessed restore;
- proof that no listener, transaction admission, or signer becomes active while quarantined or ambiguous.

Each test must capture exact source/build identity, HND app height/hash, CometBFT proof-header height, Header.AppHash, complete BlockID, signed-header verification result, block execution-input digest, checkpoint sequence/digest/operation state, process/listener/signing state, logs, and final store hashes. Tests must explicitly prove the one-block AppHash relationship and must reject same-height direct AppHash comparisons. Test steps must actually execute on the exact commit; zero-step Actions failures are infrastructure blocks, not test results.

## 10. Decisions still required before implementation

The following are intentionally unresolved and require explicit protocol-owner disposition plus independent review:

1. Canonical encoding, digest domain separation, and schema versioning.
2. Exact full-block retrieval, BlockID/PartSetHeader verification, and proof-material retention.
3. Exact HND deterministic execution inputs, app build identity, and replay API.
4. Genesis bootstrap authorization, InitChain app hash, initial validator set, and initial sequence.
5. Exact PREPARE/COMMIT ordering relative to HND durable Commit and CometBFT native-state commit boundaries.
6. Deterministic operation-ID preimage shared across validators; whether a pending PREPARED operation can ever be superseded, and the witnessed procedure if its owner is permanently unavailable.
7. Sequential versus skipping light-client verification; if skipping is ever used, trust level, witness independence, trust period, clock drift, and attack handling.
8. Checkpoint cadence and performance/availability budget.
9. Service identity, administrator separation, mTLS certificate issuance/rotation/revocation, and independent backup/disaster recovery.
10. Retention and audit evidence requirements.

No source code, schema, production endpoint, key, trust root, workflow, or runtime configuration should be changed until these decisions are frozen.

## 11. Record separation invariant

The checkpoint payload, anchor operation record, and audit event are three distinct data objects:

- **Checkpoint payload:** immutable chain/recovery facts; one canonical digest; no mutable PREPARED/COMMITTED field.
- **Operation record:** operation ID, exact predecessor and successor digest, lifecycle state, authenticated principal, and timestamps/sequence metadata. Its state may transition from PREPARED to COMMITTED without changing the checkpoint payload.
- **Audit event:** append-only evidence of each accepted or rejected operation and administrative action; it is not authoritative checkpoint state and cannot replace the anchor's linearizable operation API.

Any implementation that hashes mutable lifecycle status into the checkpoint payload violates this protocol and MUST be rejected by tests.

## 12. Relationship to existing components

- `docs/HREC_CHECKPOINT_PUBLICATION_BOUNDARY_PROPOSAL.md` records the exact pinned v0.40.0 publication boundary. A publisher invoked from the HND ABCI Commit handler is prohibited; no post-ApplyVerifiedBlock callback is currently implemented.

- `hnd_v02/remote_monotonic_anchor.py` and `docs/REMOTE_MONOTONIC_ANCHOR_PROTOCOL.md` implement/reference the existing Trust Manifest/VSP sequence-and-digest contract. They are not the HREC record or operation protocol.
- `hnd_v02/remote_activation_intent.py` and `hnd_v02/activation_coordinator.py` coordinate profile activation intent and local activation. They do not reconcile HND application state with CometBFT native state.
- `hnd_v02/cometbft_supervisor.py` verifies and launches a pinned executable after the existing activation authorization flow. It does not prove cross-store recovery or enforce that every possible OS launch path is disabled.
- `hnd_v02/cometbft_v040_server.py` serves the HND ABCI application and must not be exposed before the recovery/activation gates are satisfied.

These components may be reused only after their contracts are extended and reviewed for HREC semantics. Reusing their names or interfaces does not establish the required guarantees.

## 13. Approval and release boundary

This draft records a proposed protocol decomposition derived from DEC-HREC-01. It is not the independent review, signed protocol freeze, implementation, integration test, or production approval.

Until the unresolved decisions are ratified and the required tests pass on exact commits:
- no production signing;
- no public or untrusted listener;
- no real-value transactions or token issuance;
- no claim of production anti-rollback or cross-store recovery safety.

