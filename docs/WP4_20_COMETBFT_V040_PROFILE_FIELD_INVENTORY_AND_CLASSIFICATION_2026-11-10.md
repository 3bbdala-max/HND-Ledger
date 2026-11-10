# WP4.20 — CometBFT v0.40.0 Profile Field Inventory and Classification

**Date:** 2026-11-10  
**Target repository:** HND-Ledger  
**CometBFT source:** `cometbft/cometbft` commit `0880b4d378f347ab16e54ec677ff50d803f37d62` (release `v0.40.0`)  
**Source files reviewed:** `config/config.go`, `config/toml.go`, `types/params.go`  
**Change type:** Source-derived design inventory; documentation only  
**Disposition:** Field inventory established for the pinned source snapshot. Profile schema, exact canonical values, trusted pin delivery and executable enforcement remain to be implemented and tested.

## 1. Purpose and authority

The project owner approved the VSP v1 design direction that the CometBFT identity bind the Genesis identity, pinned software identity and a deterministic identity for the complete version-specific consensus-affecting runtime configuration.

This document converts that direction into a source-derived field inventory for CometBFT v0.40.0. It does not select production values, create a signed profile, declare a trust root, or claim that any node currently enforces the inventory.

The CometBFT release tag resolves to an annotated tag object; the reviewed source commit is the immutable commit above. Engineering and release records must pin the commit, not rely on the tag string alone.

## 2. Identity layers — do not collapse unlike inputs

The final network release/profile envelope must retain distinct, domain-separated sub-identities:

1. **Consensus-state identity:** CometBFT Genesis chain ID, initial height, complete consensus parameters, and the complete validator roster (public key type/key/address/power). These are sourced from Genesis and CometBFT types, not inferred from TOML.
2. **Consensus-service policy identity:** version-specific runtime settings that affect consensus timing, block production behavior, transaction admission/propagation, peer connectivity, synchronization or recovery. They must be recorded and checked against an approved policy. A difference can affect liveness or inclusion without necessarily changing deterministic block validity.
3. **Node-local deployment identity/policy:** endpoints, filesystem locations, local observability and host-specific routing. These may differ by validator, but must pass separate security policy checks and must not be silently treated as harmless.
4. **Software/build identity:** exact CometBFT source commit, build inputs/toolchain/dependency graph, reproducible build record where available, and resulting binary SHA-256. Version output alone is not sufficient.

The aggregate release manifest may reference all four identities. It must not place private keys, signer credentials, or secret-bearing values into a public profile.

## 3. Consensus-state fields — Genesis authority

CometBFT v0.40.0 `types/params.go` defines `ConsensusParams` with these exact substructures:

| Genesis / consensus field | Classification | Required treatment |
|---|---|---|
| `chain_id` | Consensus-state | Exact match to the independently provisioned network identity |
| `initial_height` | Consensus-state | Bind into the approved Genesis identity |
| `validators[].pub_key` | Consensus-state | Exact public key type and raw key bytes; validate derived address |
| `validators[].power` | Consensus-state | Exact integer voting power; checked total and policy |
| `consensus_params.block.max_bytes` | Consensus-state | Bind exact integer |
| `consensus_params.block.max_gas` | Consensus-state | Bind exact integer, including sentinel semantics |
| `consensus_params.evidence.max_age_num_blocks` | Consensus-state | Bind exact integer |
| `consensus_params.evidence.max_age_duration` | Consensus-state | Bind exact duration representation and nanosecond semantics |
| `consensus_params.evidence.max_bytes` | Consensus-state | Bind exact integer |
| `consensus_params.validator.pub_key_types` | Consensus-state | Bind exact ordered/normalized schema value; do not silently reorder |
| `consensus_params.version.app` | Consensus-state | Bind exact integer |
| `consensus_params.abci.vote_extensions_enable_height` | Consensus-state | Bind exact activation height |
| `consensus_params.authority.authority` | Consensus-state / application-interpreted | Bind exact string; CometBFT treats it as opaque and HND must define its meaning |

The full canonical CometBFT Genesis digest must also be retained. The parsed field checks are additional semantic checks; they do not replace the full-file digest.

**Important source finding:** CometBFT v0.40.0 `ConsensusParams.Hash()` includes only block max bytes and max gas in the header hash. That narrow header hash must not be mistaken for a digest of all consensus parameters or the full Genesis.

## 4. Runtime configuration field inventory

The following inventory is taken from the v0.40.0 `Config` and nested config structs in `config/config.go`. It is a classification, not a declaration that all fields belong in one undifferentiated consensus hash.

### 4.1 Base configuration

| TOML key | Classification | Reason / enforcement |
|---|---|---|
| `version` | Software metadata | Compare to expected release semantics; never use as the sole binary identity |
| `home`, `db_dir`, `genesis_file` | Node-local deployment | Resolve paths safely; separately pin actual Genesis bytes |
| `proxy_app`, `abci` | Security-critical local service policy | Enforce approved transport and endpoint; HND ABCI trust boundary |
| `moniker` | Node-local metadata | Not consensus identity |
| `db_backend` | Operational/recovery policy | Pin supported backend and validate compatibility |
| `log_level`, `log_format` | Node-local observability | Keep out of consensus-state identity |
| `priv_validator_key_file`, `priv_validator_state_file`, `node_key_file` | Secret/key custody boundary | Never hash secret contents into public profile; enforce protected paths and signer architecture |
| `priv_validator_laddr` | Security-critical local service policy | Validate remote signer endpoint and transport/authentication |
| `filter_peers` | P2P/security service policy | Explicitly set and validate; affects peer admission |
| `event_bus_buffer_capacity` | Operational service policy | Bound and standardize if it can affect event delivery/backpressure |

### 4.2 RPC configuration

All RPC fields are node-local service/security policy, not consensus-state identity:

- `laddr`, `grpc_laddr`, `pprof_laddr`: listener exposure and bind policy.
- `cors_allowed_origins`, `cors_allowed_methods`, `cors_allowed_headers`: API exposure policy.
- `grpc_max_open_connections`, `max_open_connections`, `max_subscription_clients`, `max_subscriptions_per_client`, `experimental_subscription_buffer_size`, `experimental_websocket_write_buffer_size`, `max_request_batch_size`, `max_body_bytes`, `max_header_bytes`: local resource and denial-of-service controls.
- `unsafe`, `experimental_close_on_slow_client`, `timeout_broadcast_tx_commit`: RPC behavior/security policy.
- `tls_cert_file`, `tls_key_file`: secret-bearing local TLS configuration; paths and certificate identity are deployment-controlled, private key bytes are never profiled.

RPC policy must be validated independently. A local endpoint change must not change the consensus-state digest.

### 4.3 P2P configuration

P2P fields influence network connectivity, peer selection, propagation and operational security. They belong in a separately classified service/network policy component; values that are inherently host-specific must be represented as validated local overrides rather than forced identical.

- **Network policy candidates:** `addr_book_strict`, `max_num_inbound_peers`, `max_num_outbound_peers`, `pex`, `seed_mode`, `allow_duplicate_ip`, `max_packet_msg_payload_size`, `send_rate`, `recv_rate`, `handshake_timeout`, `dial_timeout`, `flush_throttle_timeout`, `persistent_peers_max_dial_period`.
- **Host/network-specific values:** `laddr`, `external_address`, `seeds`, `persistent_peers`, `addr_book_file`, `unconditional_peer_ids`, `private_peer_ids`.
- **Experimental subprofile:** `libp2p.enabled`, `libp2p.bootstrap_peers`, `libp2p.scaler`, `libp2p.limits`. Must be explicitly disabled or fully specified; no silent fallback when the feature is unsupported.
- **Test-only controls:** `test_dial_fail`, `test_fuzz`, `test_fuzz_config`. Production profile must reject enabled fuzz/test behavior.

P2P host addresses and peer lists must not be copied into a shared public consensus digest if they legitimately differ. They still require authenticated per-node deployment policy and peer identity validation.

### 4.4 Mempool configuration

Mempool settings affect admission, rechecking, transaction gossip, batching and inclusion timing. They do not automatically change HND deterministic transaction validity, but divergent policies can create materially different network behavior. Include them in the approved CometBFT service-policy identity or explicitly constrain/allowlist per-node differences:

- `type`, `recheck`, `recheck_timeout`, `broadcast`, `size`, `max_txs_bytes`, `cache_size`, `keep-invalid-txs-in-cache`, `max_tx_bytes`, `max_batch_bytes`, `experimental_max_gossip_connections_to_persistent_peers`, `experimental_max_gossip_connections_to_non_persistent_peers`, `seen_cache_size`, `reap_max_bytes`, `reap_max_gas`, `reap_interval`, `check_tx_retry_delay`, `wal_dir`.

The current HND application does not thereby acquire ownership of CometBFT mempool policy. HND transaction validity remains an application rule; mempool admission and propagation are CometBFT service behavior.

### 4.5 State sync, block sync, consensus and storage

| Section / fields | Classification | Required treatment |
|---|---|---|
| `statesync.enable`, `rpc_servers`, `trust_period`, `trust_height`, `trust_hash`, `discovery_time`, `chunk_request_timeout`, `chunk_fetchers`, `max_snapshot_chunks`, `temp_dir` | Sync/recovery policy | Bind trust inputs and policy; server endpoints/temp paths may be per-node; validate trust hash/height as authenticated inputs |
| `blocksync.version`, `adaptive_sync` | Sync protocol policy | Explicit supported version and behavior; no silent default drift |
| `consensus.timeout_propose`, `timeout_propose_delta`, `timeout_prevote`, `timeout_prevote_delta`, `timeout_precommit`, `timeout_precommit_delta`, `timeout_commit`, `skip_timeout_commit`, `create_empty_blocks`, `create_empty_blocks_interval`, `peer_gossip_sleep_duration`, `peer_query_maj23_sleep_duration`, `block_time_tolerance` | Consensus liveness/service policy | Include in a versioned approved consensus-service profile; require exact supported values or explicit approved bounds |
| `consensus.double_sign_check_height` | Signer safety / local security policy | Must be bound to signer safety controls; not a substitute for durable anti-double-sign state |
| `consensus.wal_file` | Node-local durability | Validate protected path, permissions, disk behavior; do not hash path as network identity |
| `storage.discard_abci_responses` | Recovery/availability policy | Explicitly set and test because it changes available replay/recovery evidence |
| `tx_index.indexer`, `tx_index.psql-conn` | Local indexing/data service | Keep out of consensus identity; validate secret handling for connection strings |
| `instrumentation.prometheus`, `prometheus_listen_addr`, `max_open_connections`, `namespace` | Local observability/resource policy | Keep out of consensus identity; enforce bind/access controls |

## 5. Canonicalization and profile composition requirements

The eventual profile schema must not hash raw TOML text. TOML comments, whitespace, key order and path spelling are not semantic identity. Instead:

1. Parse with the exact v0.40.0-compatible TOML parser and reject duplicate keys, unknown keys and type mismatches.
2. Resolve defaults using the exact pinned v0.40.0 source/default configuration, not whichever binary happens to run on the host.
3. Convert values to a typed, versioned canonical profile object with explicit duration units and integer semantics.
4. Require every consensus-state and consensus-service field to be present in the canonical object; missing fields must not silently inherit local defaults.
5. Represent host-specific deployment values in a separate authenticated per-node policy object.
6. Domain-separate and hash the typed objects; aggregate their digests in the signed release/profile manifest.
7. Reject unknown fields and unsupported CometBFT profile schema versions.
8. Verify actual binary digest and source/build provenance independently of the profile document.

The exact canonical schema, allowed values/ranges, profile digest preimage and signed trust-manifest relationship remain implementation freeze items. No numeric values are chosen in this audit.

## 6. Fail-closed checks required before process start

A future preflight must, before ABCI, RPC, P2P or signer listeners start:

- verify independently provisioned release/profile trust;
- verify the exact binary SHA-256 and source/build identity;
- parse and validate the complete CometBFT Genesis and full validator roster;
- compare the local resolved configuration with the approved typed profile;
- validate local-only overrides against their separate deployment policy;
- verify HND Genesis, HND Config identity and durable store binding;
- verify signer identity and durable anti-double-sign state through the signer boundary;
- re-read or securely retain the verified configuration to prevent a check/use race;
- terminate without opening services if any required input is missing, unknown, stale, malformed or mismatched.

A wrapper alone is not an enforcement boundary if the service account can execute the CometBFT binary directly. OS/service restrictions and signer-side verification remain separate required work packages.

## 7. Required next implementation sequence

1. Freeze this field classification after review against the pinned source and the actual generated v0.40.0 TOML.
2. Define the exact typed CometBFT profile schema and numeric/resource bounds; keep unresolved values explicitly unset rather than copying test defaults into a production policy.
3. Define how the consensus-service profile is composed with Genesis consensus-state identity and per-node deployment policy.
4. Add positive and negative canonical profile vectors, including missing/unknown fields and local-only changes that must not alter the consensus digest.
5. Implement a pure profile parser/normalizer/digest function with no process, network, key or persistence side effects.
6. Add binary/source provenance checks and the pre-start gate as separate changes.
7. Add mismatch tests to the disposable four-validator integration harness.
8. Complete durable anti-rollback, OS/service bypass prevention and signer-side checks as separate packages.
9. Obtain independent security review before production activation.

## 8. Explicit non-claims

This source inventory does not mean:
- any production profile values have been selected;
- the current CometBFT binary is pinned by an independently approved artifact digest;
- the runtime enforces these fields;
- the validator operators or infrastructure are independent;
- a trust-root ceremony or catastrophic recovery drill has occurred;
- VSP runtime enforcement or production readiness is complete.

**Disposition: SOURCE-DERIVED FIELD INVENTORY COMPLETE FOR REVIEW — PROFILE SCHEMA AND ENFORCEMENT NOT IMPLEMENTED — PRODUCTION NOT APPROVED.**

## 9. Upstream source references

- `config/config.go`: https://github.com/cometbft/cometbft/blob/0880b4d378f347ab16e54ec677ff50d803f37d62/config/config.go
- `config/toml.go`: https://github.com/cometbft/cometbft/blob/0880b4d378f347ab16e54ec677ff50d803f37d62/config/toml.go
- `types/params.go`: https://github.com/cometbft/cometbft/blob/0880b4d378f347ab16e54ec677ff50d803f37d62/types/params.go
- Release tag reference: https://github.com/cometbft/cometbft/tree/v0.40.0

The field map is based on the pinned source snapshot above, not on a newer CometBFT release.
