# WP4.30 — Recursive CometBFT v0.40.0 typed configuration inventory

**Source pin:** `cometbft/cometbft@0880b4d378f347ab16e54ec677ff50d803f37d62`  
**Reviewed source files:** `config/config.go`, `config/toml.go`  
**Scope:** source-derived struct/tag/type/default reconciliation; documentation only  
**Status:** expanded recursive inventory; not yet the frozen executable profile schema

## 1. Why this reconciliation exists

WP4.20 and WP4.29 classified configuration areas and recorded first-pass counts. This note expands that work using the actual Go struct declarations and default constructors at the pinned source commit. It distinguishes TOML keys from Go-only fields and nested structures. It does not claim that a runtime profile is complete or that any node enforces it.

The source itself warns that changes to config structs and comments must be reflected in `defaultConfigTemplate` in `config/toml.go`. Therefore neither struct tags nor template assignment occurrences alone are a complete schema oracle.

## 2. Top-level structs and tagged field types

The following lists the Go field, Go type, and TOML mapstructure key as declared in `config/config.go`. The root-directory `home` field is repeated in several nested structs for internal decoding and must not be treated as multiple TOML keys in separate tables.

### BaseConfig (16 fields)
| Go field | Go type | TOML key |
|---|---|---|
| Version | string | version |
| RootDir | string | home |
| ProxyApp | string | proxy_app |
| Moniker | string | moniker |
| DBBackend | string | db_backend |
| DBPath | string | db_dir |
| LogLevel | string | log_level |
| LogFormat | string | log_format |
| Genesis | string | genesis_file |
| PrivValidatorKey | string | priv_validator_key_file |
| PrivValidatorState | string | priv_validator_state_file |
| PrivValidatorListenAddr | string | priv_validator_laddr |
| NodeKey | string | node_key_file |
| ABCI | string | abci |
| FilterPeers | bool | filter_peers |
| EventBusBufferCapacity | int | event_bus_buffer_capacity |

### RPCConfig (21 fields)
| Go field | Go type | TOML key |
|---|---|---|
| RootDir | string | home (internal root) |
| ListenAddress | string | laddr |
| CORSAllowedOrigins | []string | cors_allowed_origins |
| CORSAllowedMethods | []string | cors_allowed_methods |
| CORSAllowedHeaders | []string | cors_allowed_headers |
| GRPCListenAddress | string | grpc_laddr |
| GRPCMaxOpenConnections | int | grpc_max_open_connections |
| Unsafe | bool | unsafe |
| MaxOpenConnections | int | max_open_connections |
| MaxSubscriptionClients | int | max_subscription_clients |
| MaxSubscriptionsPerClient | int | max_subscriptions_per_client |
| SubscriptionBufferSize | int | experimental_subscription_buffer_size |
| WebSocketWriteBufferSize | int | experimental_websocket_write_buffer_size |
| CloseOnSlowClient | bool | experimental_close_on_slow_client |
| TimeoutBroadcastTxCommit | time.Duration | timeout_broadcast_tx_commit |
| MaxRequestBatchSize | int | max_request_batch_size |
| MaxBodyBytes | int64 | max_body_bytes |
| MaxHeaderBytes | int | max_header_bytes |
| TLSCertFile | string | tls_cert_file |
| TLSKeyFile | string | tls_key_file |
| PprofListenAddress | string | pprof_laddr |

### P2PConfig (25 fields)
| Go field | Go type | TOML key |
|---|---|---|
| RootDir | string | home (internal root) |
| ListenAddress | string | laddr |
| ExternalAddress | string | external_address |
| Seeds | string | seeds |
| PersistentPeers | string | persistent_peers |
| AddrBook | string | addr_book_file |
| AddrBookStrict | bool | addr_book_strict |
| MaxNumInboundPeers | int | max_num_inbound_peers |
| MaxNumOutboundPeers | int | max_num_outbound_peers |
| UnconditionalPeerIDs | string | unconditional_peer_ids |
| PersistentPeersMaxDialPeriod | time.Duration | persistent_peers_max_dial_period |
| FlushThrottleTimeout | time.Duration | flush_throttle_timeout |
| MaxPacketMsgPayloadSize | int | max_packet_msg_payload_size |
| SendRate | int64 | send_rate |
| RecvRate | int64 | recv_rate |
| PexReactor | bool | pex |
| LibP2PConfig | LibP2PConfig | libp2p (nested) |
| SeedMode | bool | seed_mode |
| PrivatePeerIDs | string | private_peer_ids |
| AllowDuplicateIP | bool | allow_duplicate_ip |
| HandshakeTimeout | time.Duration | handshake_timeout |
| DialTimeout | time.Duration | dial_timeout |
| TestDialFail | bool | test_dial_fail |
| TestFuzz | bool | test_fuzz |
| TestFuzzConfig | *FuzzConnConfig | test_fuzz_config (pointer/table) |

### Remaining top-level config structs
| Struct | Fields and types (TOML keys follow each Go field's mapstructure tag) |
|---|---|
| MempoolConfig (19) | Type string; RootDir string (internal home); Recheck bool; RecheckTimeout time.Duration; Broadcast bool; WalPath string; Size int; MaxTxsBytes int64; CacheSize int; KeepInvalidTxsInCache bool; MaxTxBytes int; MaxBatchBytes int; ExperimentalMaxGossipConnectionsToPersistentPeers int; ExperimentalMaxGossipConnectionsToNonPersistentPeers int; SeenCacheSize int; ReapMaxBytes uint64; ReapMaxGas uint64; ReapInterval time.Duration; CheckTxRetryDelay time.Duration |
| StateSyncConfig (10) | Enable bool; TempDir string; RPCServers []string; TrustPeriod time.Duration; TrustHeight int64; TrustHash string; DiscoveryTime time.Duration; ChunkRequestTimeout time.Duration; ChunkFetchers int32; MaxSnapshotChunks uint32 |
| BlockSyncConfig (2) | Version string; AdaptiveSync bool |
| ConsensusConfig (16) | RootDir string (internal home); WalPath string; private walFile string (no TOML tag); TimeoutPropose time.Duration; TimeoutProposeDelta time.Duration; TimeoutPrevote time.Duration; TimeoutPrevoteDelta time.Duration; TimeoutPrecommit time.Duration; TimeoutPrecommitDelta time.Duration; TimeoutCommit time.Duration; SkipTimeoutCommit bool; CreateEmptyBlocks bool; CreateEmptyBlocksInterval time.Duration; PeerGossipSleepDuration time.Duration; PeerQueryMaj23SleepDuration time.Duration; DoubleSignCheckHeight int64; BlockTimeTolerance time.Duration |
| StorageConfig (1) | DiscardABCIResponses bool |
| TxIndexConfig (2) | Indexer string; PsqlConn string |
| InstrumentationConfig (4) | Prometheus bool; PrometheusListenAddr string; MaxOpenConnections int; Namespace string |

The earlier count of 120 tagged fields is the sum of the top-level struct field counts above; it does not include recursive nested LibP2P members or distinguish internal root-directory fields.

## 3. Recursive nested structures

| Struct | Fields |
|---|---|
| LibP2PConfig | Enabled bool; BootstrapPeers []LibP2PBootstrapPeer; Scaler LibP2PScaler; Limits LibP2PLimits |
| LibP2PBootstrapPeer | Host string; ID string; Private bool; Persistent bool; Unconditional bool |
| LibP2PScaler | MinWorkers int; MaxWorkers int; ThresholdLatency time.Duration; Overrides []LibP2PScalerOverride |
| LibP2PScalerOverride | Reactor string; MinWorkers int; MaxWorkers int; ThresholdLatency time.Duration |
| LibP2PLimits | Mode string; MaxPeers int; MaxPeerStreams int |
| FuzzConnConfig | Mode int; MaxDelay time.Duration; ProbDropRW float64; ProbDropConn float64; ProbSleep float64 |

FuzzConnConfig fields have no individual mapstructure tags in this pinned source. Their containing P2P field is tagged as `test_fuzz_config`. Treat this as a custom nested decode shape that requires direct decoder/template verification; do not invent flattened keys.

## 4. Source defaults confirmed from constructors

These are source constructor defaults, not necessarily all rendered TOML values. Pointer defaults, omitted fields, template conditionals and runtime-derived values still need reconciliation.

| Constructor | Source-derived defaults of profile significance |
|---|---|
| DefaultBaseConfig | proxy_app tcp://127.0.0.1:26658; ABCI socket; log_level info; log_format plain; filter_peers false; db_backend goleveldb; db_dir data; event_bus_buffer_capacity 0; genesis/key/state/node-key paths are source constants |
| DefaultRPCConfig | laddr tcp://127.0.0.1:26657; CORS origins empty; methods HEAD/GET/POST; gRPC laddr empty; gRPC and HTTP max connections 900; unsafe false; subscription clients 100; subscriptions/client 5; subscription and websocket buffers source constant 200; broadcast commit timeout 10s; batch size 10; body 1,000,000; header 1 MiB; TLS paths empty |
| DefaultP2PConfig | laddr tcp://0.0.0.0:26656; external address empty; addr book source path; strict true; inbound 40; outbound 10; persistent-peer dial period 0; flush throttle 10ms; packet payload 1024; send/receive 5,120,000; PEX true; seed mode false; duplicate IP false; handshake 20s; dial 3s; test dial/fuzz false |
| DefaultLibP2PConfig | enabled false; bootstrap peers empty; scaler and limits use their own constructors |
| DefaultFuzzConnConfig | mode FuzzModeDrop (0); max delay 3s; ProbDropRW 0.2; ProbDropConn 0; ProbSleep 0 |
| DefaultMempoolConfig | type flood; recheck true; recheck timeout 1s; broadcast true; WAL path empty; size 5000; max tx bytes total 1 GiB; cache 10000; max tx 4 MiB; experimental gossip limits 0; seen cache 100000; reap max bytes/gas 0; reap interval 500ms; CheckTx retry delay 5s |
| DefaultStateSyncConfig | trust period 168h; discovery 15s; chunk timeout 10s; chunk fetchers 4; max snapshot chunks 100000; remaining fields zero values |
| DefaultBlockSyncConfig | version v0; adaptive sync false |
| DefaultConsensusConfig | WAL data/cs.wal/wal; propose 3s + delta 500ms; prevote 1s + delta 500ms; precommit 1s + delta 500ms; commit 1s; skip timeout false; empty blocks true; empty-block interval 0; peer gossip sleep 100ms; maj23 sleep 2s; double-sign check height 0; block time tolerance 60s |
| DefaultStorageConfig | discard ABCI responses false |
| DefaultTxIndexConfig | indexer kv; psql connection empty |
| DefaultInstrumentationConfig | Prometheus false; listen :26660; max connections 3; namespace cometbft |

Not yet extracted into a normative fixture: DefaultLibP2PScaler, DefaultLibP2PLimits, all default constructor values for the source fields whose zero value is implicit, all template conditional rendering, environment/CLI overrides, and the final generated TOML byte fixture with binary SHA-256.

## 5. Decoder, template and path-resolution exceptions

The next implementation must explicitly reconcile:

1. The anonymous squashed BaseConfig and repeated nested `home` fields. A naive flattening to `rpc.home`, `p2p.home`, etc. is not a correct TOML schema.
2. Private `ConsensusConfig.walFile`, which is an internal override, not a TOML key.
3. FuzzConnConfig's untagged nested fields and test-only switches. Production schema must reject test/fuzz modes when enabled.
4. Nested LibP2P arrays/tables and their typed members; no ambiguous flattening of arrays of tables.
5. `time.Duration` string parsing, units, bounds and canonical integer-nanosecond representation.
6. Source constants, computed defaults, pointer defaults, omitted values, and template conditionals.
7. Root path, `CMTHOME`, `--home`, environment and CLI override precedence, including which values are read before config parsing.
8. Every field's validation in `ValidateBasic()`, custom decoding hooks, and any runtime-derived value.
9. The actual default TOML rendered by the pinned CometBFT binary, including its SHA-256 and source/build provenance.

## 6. Required executable acceptance before marking schema complete

- Generate a deterministic field manifest from the pinned source with struct path, Go type, TOML key, nested shape, default expression/value, validation rule, and classification.
- Compare generated TOML against the pinned binary's own `init` output byte-for-byte, then parse and normalize it.
- Assert every known key is mapped exactly once, every nested table/array shape is typed, and every omitted/internal field has an explicit disposition.
- Add one mutation vector per profile field and per nested collection member; changing any shared-policy field must change the shared-profile digest.
- Prove node-local endpoint/path changes do not alter the shared consensus digest but do alter or fail the per-node deployment policy as appropriate.
- Prove unknown keys, missing required fields, invalid duration lexemes, duplicate keys, invalid array-table shapes, fuzz flags, and unsupported source commits fail closed.
- Generate golden canonical JSON and digest vectors independently from at least one second implementation.
- Require independent source/schema review before setting the production schema completeness marker.

## 7. Disposition

This document materially expands the source-derived typed inventory and constructor-default evidence, but it is still not the executable complete schema. The current `ProfileSchema.complete` flag is only an assertion supplied by the schema author; it is not itself proof that the source inventory is complete. The profile digest must remain unavailable to production activation until a generated, reviewed manifest and golden fixtures exist.

This document does not implement durable anti-rollback, real operator enrollment, unanimous acknowledgement collection, atomic profile activation, CometBFT startup enforcement, signer-side profile enforcement, independent custody, or catastrophic-key recovery. Those remain separate Station 2 gates.
