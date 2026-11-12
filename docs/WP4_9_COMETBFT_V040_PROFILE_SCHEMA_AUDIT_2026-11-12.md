# WP4.9 — CometBFT v0.40.0 TOML profile inventory and trust boundary

**Date:** 2026-11-12  
**Workstream:** Station 2 — CometBFT deployment profile binding  
**Pinned CometBFT source:** `0880b4d378f347ab16e54ec677ff50d803f37d62`  
**Status:** Source-driven inventory generator and fail-closed loader implemented; exhaustive scope policy is intentionally unreviewed and production activation remains blocked.

## 1. Why reflection alone is insufficient

CometBFT's `config/config.go` says its configuration structs and the `defaultConfigTemplate` in `config/toml.go` must be kept in sync. The default TOML template is therefore the actual configuration-file boundary, while the exported Go structs and their `mapstructure` tags define the destination fields.

The representations are not always the same as the Go field types. Examples in the pinned source include:

- `time.Duration` fields rendered as TOML strings.
- `statesync.chunk_fetchers` rendered as a string although its Go field is `int32`.
- `statesync.rpc_servers` rendered as a comma-separated string despite its Go slice representation.
- `p2p.libp2p.bootstrap_peers` rendered as an array of inline tables, with optional boolean keys omitted when false.
- The home/root fields and several testing-only fields are not ordinary TOML settings emitted by the default template.

A schema created solely from Go reflection would misstate some wire/file types, could miss template-only behavior, and could incorrectly treat runtime paths as profile fields.

## 2. Source-derived inventory generator

`scripts/cometbft_v040_config_schema_dump.go` now:

1. Calls the pinned CometBFT `config.DefaultConfig()`.
2. Renders that object through CometBFT's own `config.WriteConfigFile` template.
3. Parses the rendered TOML with the BurntSushi TOML dependency pinned in the same CometBFT source module.
4. Recursively reconciles TOML leaf paths with exported source fields and `mapstructure` keys.
5. Records the exact rendered TOML type and default value, Go source path/type, array item schema, TOML tables, and exported source fields not emitted by the default template.
6. Fails when a TOML key cannot be tied to a source field or a source/TOML mismatch remains.

The output contains the rendered-template SHA-256 and the pinned source commit. The generated inventory deliberately does **not** assign `shared`, `node_local`, or `software` scopes. Those labels are HND protocol policy, not facts that can safely be inferred by reflection.

## 3. Separate scope policy and schema loader

`hnd_v02/cometbft_v040_profile.py` now provides `load_cometbft_v040_profile_schema(inventory_raw, scope_manifest_raw)`.

The loader:

- rejects duplicate JSON keys and invalid UTF-8;
- requires the inventory schema version and exact CometBFT source commit;
- verifies the generated inventory's source/template completeness declaration and table-path coverage;
- validates supported TOML types, generated defaults, array item schemas, and optional array-table field defaults;
- requires a separate scope manifest whose inventory SHA-256 matches the exact inventory bytes;
- marks the schema complete only if the scope manifest is explicitly reviewed, has a review reference, and classifies every inventory field exactly once as `shared`, `node_local`, or `software`.

An incomplete, unreviewed, unbound, or partially classified scope manifest cannot be used by the profile parser or profile digest function.

Template: `hnd_v02/cometbft_v040_profile_scope_policy.json`. It is deliberately blank and `reviewed=false`; it is not a deployment schema.

## 4. Supervisor integration

Before witnessed activation, and again after the ABCI listener is bound immediately before CometBFT process creation, the supervisor:

- reads the actual `$HOME/config/config.toml` and `$HOME/config/genesis.json` using no-follow file and directory operations;
- rejects symlink path components, non-regular files, oversized files, and a profile artifact that differs from the actual config file;
- binds Genesis bytes, chain ID, validator roster, and HND application `app_state` to the VSP/application;
- parses the actual TOML against the loaded schema and checks the shared-profile digest;
- checks that the schema inventory, scope manifest, and rendered-template digests match the trusted deployment context.

The deployment context values for those three schema digests must themselves be delivered through the trusted deployment/release configuration. Merely computing a digest is not an authenticity mechanism.

## 5. Current validation boundary

The CI workflow now generates and structurally checks the source-derived TOML inventory from the pinned CometBFT source. The strict schema-loader tests cover the TOML/Go representation differences, array-of-table defaults, incomplete scope manifests, inventory binding, wrong source commits, and duplicate JSON keys.

However, the generator has **not yet been evidenced as executed successfully** on the current PR head. Current CI evidence from earlier ancestor commits consisted only of job-level failures with missing step summaries and missing log blobs; it did not show test commands starting.

The scope manifest remains intentionally unreviewed. No exhaustive source-derived inventory has yet been committed as a validated release artifact, and no owner-approved scope classification is claimed. Accordingly, `ProfileSchema.complete` must remain false for the committed template until the generator is run against the exact pinned source, its output is inspected, all fields are classified, the policy is independently reviewed, and the exact inventory/policy/template hashes are anchored in trusted deployment configuration.

## 6. Remaining gates

1. Execute the inventory generator in CI using the exact pinned source; retain the generated inventory as a reviewable artifact.
2. Inspect every exported source field omitted from the TOML template and each generated TOML field/type/default.
3. Produce the exhaustive scope classification. Consensus-affecting fields must not be labelled from guesswork; this is a protocol-policy review.
4. Bind the reviewed inventory/policy/template hashes into trusted deployment configuration and verify the same values at startup.
5. Execute the expanded Python regression suite on the exact PR HEAD, then execute the pinned CometBFT single-node smoke and the live etcd quorum/recovery suite.
6. Keep production deployment blocked pending an independent witness, root-owned immutable deployment inputs, sole-launch-path OS/service policy, and production key/certificate custody.

No production readiness, public network activation, or Station 2 exit is claimed by this work item.
