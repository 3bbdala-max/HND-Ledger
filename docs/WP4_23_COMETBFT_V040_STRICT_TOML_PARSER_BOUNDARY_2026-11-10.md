# WP4.23 — Strict CometBFT v0.40.0 TOML Parsing Boundary

Date: 2026-11-10  
Status: implementation spike; not a VSP profile digest implementation.

## Implemented boundary

The helper `scripts/cometbft_v040_profile_inspect.go` is executed from the exact pinned CometBFT source checkout (`0880b4d378f347ab16e54ec677ff50d803f37d62`). It:

- parses TOML using the BurntSushi TOML parser pinned by that CometBFT source;
- rejects malformed TOML and duplicate keys through the parser;
- decodes into CometBFT v0.40.0's actual `config.Config` structure using its `mapstructure` tags;
- rejects unknown keys (`ErrorUnused`) and weak type coercion;
- resolves omitted fields only from `config.DefaultConfig()` in the pinned source checkout;
- invokes the pinned configuration's `ValidateBasic()`;
- includes a self-test for unknown fields, duplicate keys, wrong types, oversize input and duration overrides.

The helper emits only non-secret metadata. It does not print config paths, endpoints or signer details.

## Explicit limits

This is a parser/typed-configuration validation boundary, **not** the final VSP runtime profile implementation:

- it does not yet derive the normative shared consensus-service projection or node-local deployment projection;
- it does not compute `cometbft.profile_sha256`;
- it does not authenticate the expected source commit or binary digest by itself; those must come from an independently trusted caller;
- it does not verify TOML file ownership, symlink safety, service account permissions or OS-level bypass prevention;
- it does not change CometBFT startup behavior.

The helper deliberately reports `profile_digest=NOT_COMPUTED_FIELD_CLASSIFICATION_REQUIRED`. Replacing this marker with a digest before the field classification and canonical schema are frozen would create a misleading identity.

## CI invocation

From the pinned CometBFT source checkout:

```sh
go run "$GITHUB_WORKSPACE/scripts/cometbft_v040_profile_inspect.go" --self-test
```

No production keys, network identities, Genesis files or secrets are used.
