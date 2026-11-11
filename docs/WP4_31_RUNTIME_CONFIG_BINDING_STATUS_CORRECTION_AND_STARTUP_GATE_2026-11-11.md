# WP4.31 — Runtime Config-Binding Status Correction and Remaining Startup Gate

**Date:** 2026-11-11  
**Base branch:** `phase-0.2-planning`  
**Base commit inspected:** `a1423f22a8e7a53a690be2a3b25a77ed00002304`  
**Scope:** Source-level correction of the older WP4.14 runtime/config audit against the current merged tree. Documentation only; no runtime behavior is changed.

## 1. Disposition

The older WP4.14 audit statement that the current runtime does not bind `max_amount` or the block transaction limit into the HND application Genesis and durable store is stale for the inspected base commit.

The current source has implemented local Genesis/config equality checks and durable-store equality checks for both values. This closes that specific mismatch path when all validators consume the same CometBFT application Genesis bytes.

This correction does **not** mean Config-v1 is frozen, that the application configuration has an independently authenticated digest, or that VSP is enforced before node startup.

## 2. Verified current implementation

### 2.1 Application Genesis payload

In `hnd_v02/abci_app.py`, `application_genesis_bytes()` emits an exact canonical object containing:
- `genesis_hash`;
- `manifest`;
- `protocol_config.network_id`;
- `protocol_config.protocol_version`;
- `protocol_config.max_amount`;
- `protocol_config.max_block_transactions`.

`init_chain()` requires exactly those three top-level members and compares the complete `protocol_config` object against the locally constructed `ProtocolConfig` plus the fixed `MAX_BLOCK_TRANSACTIONS` value. A mismatch raises `ABCIApplicationError("application Genesis protocol config mismatch")` before the application initializes or writes its initial state.

The existing test `test_init_chain_rejects_protocol_config_mismatch` mutates `max_amount` in the supplied application Genesis and verifies rejection without creating the state file. A separate test covers the block-transaction limit mismatch.

### 2.2 Durable application store

The current application store is version 5. Its exact key set includes:
- `max_amount`;
- `max_block_transactions`;
- `network_id`;
- `protocol_version`;
- `genesis_hash`;
- state height, ledger snapshot, evidence journal, app hash and store hash.

On recovery, `_load_store()` compares both persisted numeric configuration values against the local runtime configuration and rejects a mismatch. This prevents a state file created under a different `max_amount` or block transaction limit from being silently reused.

The store checksum remains an unkeyed integrity checksum. It is not an authenticity or freshness mechanism and does not prevent replay of a self-consistent older store.

### 2.3 Server startup sequence

In `hnd_v02/cometbft_v040_server.py`, the server still constructs `ProtocolConfig` from CLI values, loads and hashes the legacy manifest, creates the application, and starts the ABCI gRPC server. The application Genesis equality check is performed by the ABCI `InitChain` callback, after CometBFT has connected and submitted InitChain; it is not a pre-start authorization gate.

The ABCI gRPC listener uses `add_insecure_port` and is restricted to loopback addresses. Loopback-only binding reduces network exposure but does not authenticate local processes.

## 3. Corrected status matrix

| Control | Current status | Evidence / boundary |
|---|---|---|
| `max_amount` carried in application Genesis | Implemented | `application_genesis_bytes()` |
| Genesis/local `max_amount` equality | Implemented at InitChain | `init_chain()` and negative test |
| Block transaction limit carried and compared | Implemented | `MAX_BLOCK_TRANSACTIONS` and negative test |
| Persisted config values checked on store recovery | Implemented | Store v5 exact schema and `_load_store()` |
| Independent canonical Config-v1 digest and authenticated pin | Not established by these checks | No claim of frozen Config-v1 or trusted digest |
| Config/profile verified before ABCI listener starts | Not implemented | Current server starts gRPC before InitChain |
| VSP/trust manifest/profile/binary/anti-rollback enforced at actual CometBFT launch | Not implemented | Existing VSP verifier and activation preflight are not wired into this server's launch path |
| Local ABCI caller authentication | Not implemented | Insecure loopback gRPC; host isolation remains an assumption |
| Independent anti-rollback against host/database restore | Not implemented by SQLite/file checksums | Requires an independent monotonic trust anchor |

## 4. Corrected risk statement

The specific earlier example — two validators running different `max_amount` values while accepting the same application Genesis configuration — is now guarded by the InitChain equality check, provided they use identical application Genesis bytes. Durable state recovery also rejects a different local `max_amount`.

The remaining issue is broader and more important: the configuration values are not yet part of a frozen, independently authenticated Config-v1 identity that is verified by a supervisor before any consensus process or signer can start. The current InitChain check is a post-connection consistency check, not a pre-start authorization boundary. A separately supplied application Genesis that consistently carries a different config is not rejected by an independently pinned Config-v1 digest in this code path.

## 5. Next implementation gate

Do not reopen the already implemented `max_amount` equality work. The next implementation should focus on one fail-closed launch supervisor with an immutable input bundle and a pure verifier that validates, before starting ABCI, CometBFT or signers:
1. exact HND application Genesis and a frozen Config-v1 digest;
2. VSP envelope, signatures, trust-manifest chain and independent trust-root pin;
3. exact CometBFT v0.40.0 profile digest and approved binary identity;
4. monotonic trust/VSP sequence and predecessor state using an independent anti-rollback anchor;
5. operator acknowledgements and activation-height policy.

The supervisor must pass the verified immutable paths/bytes to the child processes, prevent alternate direct launch paths, and fail closed on missing, malformed, stale, mismatched or unverifiable inputs. Acceptance tests must prove that no listener, consensus process or signer starts for each negative case. This remains a design/implementation gate; this document does not claim it has been built.

## 6. Test and change record

This document was prepared by inspecting the current branch source and existing tests. No tests were run as part of this documentation-only correction. No source code, workflow, Genesis fixture, key, network setting or production configuration was changed.
