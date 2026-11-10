# WP4.29 — CometBFT v0.40.0 source field inventory (first-pass reconciliation)

Date: 2026-11-10

## Source identity

All source inspection in this note is pinned to CometBFT commit `0880b4d378f347ab16e54ec677ff50d803f37d62`.

Files inspected:
- `config/config.go` (56,860 bytes)
- `config/toml.go` (28,885 bytes)
- `types/params.go`

The inventory below was extracted from Go `mapstructure` tags in config structs and assignment keys in `defaultConfigTemplate`. This is a reconciliation aid, **not yet the complete normative profile schema**.

## Config structs and tagged fields

| Go struct | Tagged field count | Scope notes |
|---|---:|---|
| BaseConfig | 16 | Includes node-local paths/identity and base process settings |
| RPCConfig | 21 | RPC listener, exposure, limits and TLS |
| P2PConfig | 25 | Peer policy plus nested libp2p/fuzz configuration |
| LibP2PConfig | 4 | Nested P2P policy; requires recursive field/type/default mapping |
| FuzzConnConfig | 0 | No mapstructure tags found by this extraction; inspect all fields and decode behavior manually |
| MempoolConfig | 19 | Mempool policy and resource limits |
| StateSyncConfig | 10 | State-sync policy |
| BlockSyncConfig | 2 | Block-sync policy |
| ConsensusConfig | 16 | Consensus timing and WAL policy |
| StorageConfig | 1 | ABCI response persistence |
| TxIndexConfig | 2 | Indexing and database connection |
| InstrumentationConfig | 4 | Metrics listener and namespace |

The extraction found 120 TOML assignment occurrences in the template. Occurrences are not unique field identities because names such as `laddr`, `max_open_connections`, and `type` recur in different tables.

## Important reconciliation exceptions

- `home` appears in several structs as an internal root-directory field; it is not an ordinary shared TOML policy field.
- `test_dial_fail`, `test_fuzz`, and `test_fuzz_config` exist in P2P configuration structures but are not represented as ordinary keys in the default template.
- Nested libp2p fields are rendered under the P2P experimental/libp2p configuration path and must be represented recursively, not flattened into an ambiguous global key namespace.
- Array/table structures and TOML duration strings need explicit normalization rules; Go `time.Duration` fields are rendered as strings in the template.
- `DefaultConfig()` values alone do not define the complete acceptance boundary. `ValidateBasic()`, custom decoding, environment/CLI overrides, and runtime-derived values must also be examined.
- Consensus Genesis parameters in `types/params.go` are a distinct identity surface from node-local TOML settings. `ConsensusParams.Hash()` must not be treated as a digest of the entire node runtime configuration.

## Acceptance work still required

1. Generate a recursive typed inventory for every exported and decode-relevant field, including nested structs, slices, maps, and array-of-table shapes.
2. Extract the exact default value for every template key from the pinned `Default*Config()` functions and reconcile it against template rendering.
3. Explain every struct field omitted from the TOML template and every template key not directly represented by a simple tagged field.
4. Reconcile aliases, custom decode hooks, environment variables, command-line overrides, and root-path normalization.
5. Classify every field as shared consensus policy, node-local deployment policy, software/build identity, or non-profile/internal.
6. Add generated golden fixtures from the pinned CometBFT binary's own default config output, plus mutation vectors for every field and nested shape.
7. Independently review the generated inventory before setting the schema's completeness marker.

## Disposition

This is a first-pass source reconciliation artifact only. It does **not** add the complete schema, does not authorize a real runtime profile digest, and does not close Station 2.
