# HND / CometBFT v0.40.0 application-hash and block-proof semantics

**Status:** Source-grounded engineering note for HREC design review. Not a frozen wire protocol.
**Pinned CometBFT release:** v0.40.0, tag commit `0880b4d378f347ab16e54ec677ff50d803f37d62`.
**HND source reviewed:** `hnd_v02/abci_app.py` and `hnd_v02/cometbft_v040_server.py` on the HREC design branch.
**Purpose:** Prevent incorrect equality checks between an HND application-state height and a CometBFT signed-header AppHash.

## 1. Source facts

The following facts were checked against the pinned CometBFT v0.40.0 source and the HND adapter:

1. CometBFT ABCI++ `InfoResponse.last_block_height` is the latest height for which the application persisted state. `last_block_app_hash` is the latest AppHash returned by `FinalizeBlock`. Both are expected to be updated and persisted during `Commit`. The Info handshake is used to synchronize CometBFT with the application on startup/recovery.
2. HND `HNDABCIApplication.finalize_block(height=h,...)` requires `h == last_committed_height + 1`, executes the decided transactions and normalized misbehavior inputs against a candidate state, and computes the next application hash.
3. HND computes its app hash as SHA-256 over the domain prefix `HND-ABCI-APP-STATE-V1\0` followed by canonical JSON of `{"ledger_state_hash": ..., "evidence_journal": ...}`.
4. HND `commit()` durably writes the pending state, then updates `last_committed_height` and `_committed_app_hash`. The ABCI server maps these values to `InfoResponse`; its `FinalizeBlock` response returns the candidate app hash and its `Commit` handler calls the HND commit.
5. CometBFT's v0.40.0 data-structures specification defines a block header's `AppHash` as the application hash returned after executing and committing the **previous** block. The first block's header AppHash is initialized from `InitChainResponse.app_hash`.
6. A CometBFT `SignedHeader` contains a header and commit. In v0.40.0, its basic validation checks chain ID, matching header/commit height, and that the commit BlockID hash equals the header hash. A `LightBlock` additionally binds a validator set whose hash must equal the header's ValidatorsHash.
7. CometBFT's `ValidateBasic` checks structural consistency; it does **not** verify cryptographic commit signatures. The v0.40.0 light-client verifier must perform trust-based signature verification.

## 2. The one-block AppHash relationship

Let:
- `A[h]` be the HND application hash after HND has committed block `h`;
- `H[h]` be the CometBFT header at height `h);
- `B[h]` be the full CometBFT block at height `h).

For an established chain:

`H[h].AppHash == A[h-1]`

not `A[h]`.

At Genesis, `H[initial_height].AppHash` is the app hash returned by `InitChain` (the initial application state, normally application height zero when the chain initial height is one).

Therefore:
- The HND app's `Info.last_block_height = h` and `Info.last_block_app_hash = A[h]` describe its latest persisted application state.
- The signed header at height `h` commits to `A[h-1]`, while its commit signs block `B[h]`.
- The value `A[h]` is deterministically derived by executing the authenticated block `B[h]` from the authenticated predecessor state `A[h-1]`. It is not directly present in `H[h].AppHash).
- A comparison that requires `HND app hash == Header[h].AppHash` at the same height is wrong by one application transition.
- A comparison of HND `Info` with the CometBFT startup handshake is necessary for local consistency, but it is not an independent cryptographic proof: the Info response is supplied by the application itself.

## 3. Required HREC verification transition

For a proposed transition from application height `h-1` to `h`, an independent HREC verifier must:

1. Load the previously committed HREC checkpoint and recover the complete predecessor application state snapshot (or a content-addressed snapshot whose app hash is independently verified to equal `A[h-1]`). An app hash alone cannot reconstruct application state.
2. Obtain a CometBFT v0.40.0 `LightBlock` for height `h`: the signed header and the validator set required by the light client.
3. Verify the signed header against the previously trusted light-client state using the pinned CometBFT light-client implementation. Check chain ID, header/commit height, commit BlockID/header hash consistency, validator-set hash binding, cryptographic signatures, voting power, trust period, and the configured sequential or skipping verification rules.
4. Obtain the full CometBFT block `B[h]`. Validate its header against the verified signed header and validate the complete block identity, including the BlockID hash and PartSetHeader, not merely a caller-supplied header hash.
5. Require `H[h].AppHash == A[h-1]`. This is the cross-layer link from the previously authenticated HND state to the newly committed block.
6. Execute the exact HND ABCI transition for height `h` using the full block's transactions and every application input that affects HND state, including normalized misbehavior/evidence inputs. Use the exact approved HND application build, Genesis, protocol configuration, and canonical encoding.
7. Recompute `A[h]` using the HND v0.2 app-hash function. Require exact equality with the resulting local HND store's `Info.last_block_app_hash`, height, and independently reconstructed state. A mismatch is a hard quarantine.
8. Only then may the anchor prepare and commit a checkpoint for application height `h`, binding the verified signed-header/block evidence, predecessor checkpoint digest, exact HND build/config identity, and derived `A[h]`.

The anchor must retain the proof material and complete predecessor state snapshot, or durable content-addressed references to both. A digest without retrievable state bytes is evidence of identity, not a recovery source. A bare block hash or app hash without the signed-header trust path and deterministic execution evidence is insufficient.

## 4. Light-client verification requirements

The v0.40.0 upstream implementation exposes:
- `light.NewClient` with a trusted `TrustOptions` height/hash and a trusted store;
- `SequentialVerification()`, which checks every intermediate header and requires the trusted validator set's commit threshold;
- `SkippingVerification(trustLevel)`, which uses the trust-level/verify-skipping path for non-adjacent headers;
- `VerifyLightBlockAtHeight` and `VerifyHeader` for verifying new light blocks/headers against trusted state.

The v0.40.0 client documentation states that at least one witness provider must be supplied when skipping verification is used (the default mode). The initial HREC prototype should prefer upstream `SequentialVerification()` for the simplest auditable proof path, then benchmark it. Skipping verification must remain disabled until trust level, witness independence, trust period, clock drift, and attack-handling rules are explicitly frozen and independently reviewed.

The light client must start from an explicitly trusted Genesis/light-client root. A header supplied by the same untrusted node being checked is not a trust root. The verifier's trusted store and its backups must be protected against rollback and administered separately from validator storage.

## 5. Checkpoint field semantics

The protocol schema must distinguish these values rather than use one ambiguous `cometbft_height` / `cometbft_app_hash` pair:

- `hnd_app_height`: HND state height after deterministic execution and durable Commit of block `h`.
- `hnd_app_hash`: derived `A[h]`.
- `predecessor_state_snapshot_digest`: digest/reference to the complete predecessor HND application state needed to replay block `h`; the hash alone cannot reconstruct state.
- `successor_state_snapshot_digest`: optional retained snapshot reference for the resulting HND state, governed by explicit recovery retention.
- `cometbft_proof_header_height`: the signed CometBFT header height `h` for the transition.
- `cometbft_header_app_hash`: `H[h].AppHash`, which must equal the predecessor HND app hash `A[h-1]`.
- `cometbft_block_id`: complete BlockID identity, including header hash and PartSetHeader.
- `signed_header_proof_digest`: digest/reference for the signed header, commit, validator set, and trusted light-client verification evidence.
- `block_execution_input_digest`: digest/reference for the full verified block and all HND execution inputs used to derive `A[h]`.
- `hnd_build_identity`: immutable source/build identity for the deterministic HND execution implementation.
- `predecessor_checkpoint_digest`: digest of the checkpoint for `A[h-1]`.

The normal transition relation is `hnd_app_height == cometbft_proof_header_height`, but the two AppHash fields have different meanings: `cometbft_header_app_hash == predecessor.hnd_app_hash`; `hnd_app_hash` is the deterministic output after executing the signed block.

Do not add a field named simply `cometbft_app_hash` without defining whether it means the header's previous-state AppHash, CometBFT's in-memory state AppHash, or HND's post-Commit application hash.

## 6. Recovery consequences

- A node's HND state at height `h` is accepted only if it matches deterministic execution of the verified block `h` from the anchored predecessor state `h-1`.
- A CometBFT signed header alone does not authenticate the post-execution HND state at the same height. The full block and deterministic HND transition are required.
- A CometBFT `Info` handshake is a consistency check, not a substitute for signed-header verification and replay.
- If the full block, predecessor state, exact HND build, evidence inputs, or light-client trust path is missing/ambiguous, remain quarantined.
- Genesis bootstrap must bind the approved Genesis file, initial validator set, `InitChainResponse.app_hash`, chain ID, and the first committed block's header. No implicit empty-state bootstrap is allowed.

## 7. Exact source references reviewed

Pinned CometBFT v0.40.0:
- `spec/core/data_structures.md` — execution state transition, Header.AppHash, BlockID, Commit, SignedHeader, LightBlock.
- `spec/abci/abci++_methods.md` — Info, InitChain, FinalizeBlock, Commit semantics.
- `types/light.go` — `LightBlock.ValidateBasic` and `SignedHeader.ValidateBasic`.
- `light/client.go` — `NewClient`, sequential/skipping options, `VerifyLightBlockAtHeight`, and trust verification.
- Release tag commit: `0880b4d378f347ab16e54ec677ff50d803f37d62`.

HND:
- `hnd_v02/abci_app.py` — `_calculate_app_hash`, `info`, `finalize_block`, and `commit`.
- `hnd_v02/cometbft_v040_server.py` — ABCI `Info`, `FinalizeBlock`, and `Commit` adapters.

## 8. Implementation gate

This note is a source-grounded design correction, not an implementation. Before production code:
- independently review the light-client trust-root and verifier lifecycle;
- specify exact full-block retrieval and PartSetHeader verification;
- freeze the deterministic HND replay API and all inputs;
- test the one-block AppHash relationship at Genesis, ordinary heights, restart, crash boundaries, and replay;
- test wrong-height, wrong-header-apphash, wrong-block-data, validator-set-transition, stale-trust-root, and HND replay mismatch cases;
- retain exact commit SHA and evidence for every test.

No production signing, public listener, token issuance, or real-value use is authorized.
