# HND WP4.14 — Exact CometBFT v0.40.0 source-schema and default-profile audit

**Date:** 2026-11-05  
**Repository:** `3bbdala-max/HND-Ledger`  
**Branch:** `phase-0.2-planning`  
**HND reviewed baseline:** `f955c557f93809169fbe128ef8007a8dc9003986`  
**External source pin reviewed:** CometBFT tag `v0.40.0`  
**Status:** Source-level static audit. Documentation-only change. No HND source/tests/workflows changed; no build, test, or node execution performed.

## 1. Executive result

This audit replaces assumptions based on current CometBFT documentation with the actual Go source at the `v0.40.0` tag.

Important correction to the preceding generic profile classification: the v0.40.0 `types.ConsensusParams` schema is not the same as the newer schema shown in current online documentation. The reviewed v0.40.0 source defines:

- `Block`
- `Evidence`
- `Validator`
- `Version`
- `ABCI`
- `Authority`

It does **not** define the newer `Synchrony` or `Feature` fields in this tag's `types/params.go`. Do not put those newer fields into a v0.40.0 Genesis profile.

The source explicitly describes `ConsensusParams` as consensus-critical parameters that determine block validity. They belong to the canonical CometBFT Genesis/consensus state, not to an invented TOML hash.

## 2. Exact v0.40.0 consensus-parameter schema

Source:  
- `https://github.com/cometbft/cometbft/blob/v0.40.0/types/params.go`
- `https://github.com/cometbft/cometbft/blob/v0.40.0/types/genesis.go`

| Genesis path | Meaning | v0.40.0 source default | Profile treatment |
|---|---|---:|---|
| `consensus_params.block.max_bytes` | Maximum encoded block bytes | `22020096 + MaxCommitBytes(MaxVotesCount)` (roughly 53 MiB) | Exact value pinned |
| `consensus_params.block.max_gas` | Block gas limit | `-1` (unlimited) | Exact value pinned; application semantics reviewed separately |
| `consensus_params.evidence.max_age_num_blocks` | Evidence age in blocks | `100000` | Exact value pinned |
| `consensus_params.evidence.max_age_duration` | Evidence age duration | `48h` | Exact duration pinned |
| `consensus_params.evidence.max_bytes` | Evidence bytes per block | `1048576` (1 MiB) | Exact value pinned |
| `consensus_params.validator.pub_key_types` | Allowed validator key types | `["ed25519"]` | Exact ordered list pinned |
| `consensus_params.version.app` | Application version | `0` | Explicit value pinned |
| `consensus_params.abci.vote_extensions_enable_height` | Vote extension activation height | `0` (disabled) | Explicit value pinned |
| `consensus_params.authority.authority` | Opaque authority string | empty | Explicit value pinned; policy must prohibit unapproved authority |

The block max-bytes default is computed using CometBFT's commit-size reservation helper, so do not replace it with an approximate hard-coded 53 MiB. Freeze the actual integer produced by the pinned v0.40.0 build and include a golden vector.

The source validates, among other constraints:
- block max bytes cannot be zero, must be at least -1, and cannot exceed 100 MiB;
- block max gas must be at least -1;
- evidence max age in blocks and duration must be positive;
- evidence max bytes cannot be negative or exceed the block-size bound;
- vote-extension enable height cannot be negative;
- validator key-type list cannot be empty and every type must be recognized;
- authority string is length-limited.

The source also documents that only block max bytes and max gas are included in the CometBFT consensus-parameter hash placed in the block header. This does **not** mean the other consensus parameters can safely differ: they remain consensus-critical state and must be carried/updated consistently through Genesis and application parameter updates.

## 3. Genesis envelope and initialization semantics

Source:
- `https://github.com/cometbft/cometbft/blob/v0.40.0/types/genesis.go`

The v0.40.0 Genesis document fields are:
- `genesis_time`
- `chain_id`
- `initial_height`
- `consensus_params`
- `validators`
- `app_hash`
- `app_state`

If `consensus_params` is omitted, `GenesisDoc.ValidateAndComplete()` fills it with `DefaultConsensusParams()`. This is exactly why a release profile must not silently rely on omitted fields: a different binary/source revision could supply different defaults. The release Genesis should explicitly contain the complete approved parameter object, then be validated and hashed as exact bytes under the chosen canonicalization rule.

The current HND four-validator harness starts from the supplied binary's generated Genesis and updates chain ID, initial height, validators, app hash, and app state. It does not explicitly assign an approved `consensus_params` object. Thus, the smoke inherits the exact consensus parameter defaults from whichever binary is supplied at runtime.

The harness copies the same Genesis bytes to all four temporary homes, which is useful evidence of equality within that test run. It is not a separately pinned, reviewed production Genesis profile.

## 4. Exact TOML service defaults from v0.40.0 source

Sources:
- `https://github.com/cometbft/cometbft/blob/v0.40.0/config/config.go`
- `https://github.com/cometbft/cometbft/blob/v0.40.0/config/toml.go`

The source's `DefaultConsensusConfig()` sets:

| TOML key | Default | Operational classification |
|---|---:|---|
| `consensus.timeout_propose` | 3s | Liveness/timing |
| `consensus.timeout_propose_delta` | 500ms | Liveness/timing |
| `consensus.timeout_prevote` | 1s | Liveness/timing |
| `consensus.timeout_prevote_delta` | 500ms | Liveness/timing |
| `consensus.timeout_precommit` | 1s | Liveness/timing |
| `consensus.timeout_precommit_delta` | 500ms | Liveness/timing |
| `consensus.timeout_commit` | 1s | Liveness/timing |
| `consensus.skip_timeout_commit` | false | Liveness/timing |
| `consensus.create_empty_blocks` | true | Block-production policy |
| `consensus.create_empty_blocks_interval` | 0 | Block-production policy |

The source's `DefaultMempoolConfig()` sets (among other fields):
- `recheck = true`
- `recheck_timeout = 1s`
- `broadcast = true`
- `max_txs_bytes = 1 GiB`
- `max_tx_bytes = 4 MiB`

The source's `DefaultP2PConfig()` sets (among other fields):
- `addr_book_strict = true`
- `max_num_inbound_peers = 40`
- `max_num_outbound_peers = 10`
- `pex = true`

These are generated node-service settings, not substitutes for Genesis consensus parameters. They should be version-pinned and compared against a reviewed deployment profile because changes can affect liveness, propagation, admission, and exposure. They must be classified individually; do not assert that every one is a block-validity rule.

## 5. Exact comparison with the HND four-validator harness

The current HND script `scripts/cometbft_v040_four_validator_network_smoke.py`:

- creates four temporary CometBFT homes with the supplied binary;
- creates unique consensus validator keys and P2P node IDs;
- constructs one validator list with power 10 per validator;
- copies one Genesis byte sequence to all four homes;
- rewrites `proxy_app`, `abci`, RPC/P2P listener addresses, `persistent_peers`, `pex=false`, `addr_book_strict=false`, and `allow_duplicate_ip=true`;
- starts four HND ABCI processes with the same test `--max-amount`;
- launches CometBFT nodes and checks convergence/recovery scenarios.

It does not:
- assert a complete expected `consensus_params` object before writing Genesis;
- pin the exact generated `consensus_params` values to a reviewed release manifest;
- compare every resolved TOML key against a versioned allowlist/profile;
- verify the supplied binary's SHA-256 against a trusted release pin;
- fail node startup when one validator has a different service-profile digest.

The helper `scripts/cometbft_v040_genesis_validate.go` parses Genesis through the v0.40.0 Go types and checks that there are four validators. Parsing and validator count are not equivalent to comparison against an approved parameter profile.

## 6. Profile design correction

Maintain distinct artifacts and hashes:

1. **CometBFT Genesis digest** — exact Genesis bytes including complete consensus params, validator set, chain ID, initial height, and HND app state.
2. **HND application Config-v1 digest** — deterministic application rules, including the unresolved `max_amount` binding documented in the companion HND audit.
3. **CometBFT binary identity** — exact version/tag and independently pinned binary SHA-256.
4. **CometBFT service-profile digest** — approved timeout, mempool, P2P, storage, and operational settings after explicit classification.
5. **Validator-set digest** — public keys, addresses, voting power, and activation/rotation metadata.
6. **Node-local deployment manifest** — listener addresses, peer routes, local paths, log/instrumentation policy, and secret references; this must permit approved per-node differences.

A profile verifier must compare the actual parsed Genesis and resolved TOML values, not merely hash a desired template while launching from a separately mutable file. Any unknown or unclassified TOML key should fail closed until reviewed for the pinned version.

## 7. Required tests (proposed, not run)

| ID | Test | Expected result |
|---|---|---|
| CMT040-SCHEMA01 | Remove one v0.40.0 consensus-param field | Profile validation rejects missing explicit field |
| CMT040-SCHEMA02 | Change block max bytes or max gas | Genesis/profile digest mismatch |
| CMT040-SCHEMA03 | Change any evidence limit | Genesis/profile digest mismatch |
| CMT040-SCHEMA04 | Change validator key-type list | Genesis/profile validation rejects |
| CMT040-SCHEMA05 | Enable vote extensions at a different height | Genesis/profile mismatch and explicit feature review required |
| CMT040-SCHEMA06 | Change authority string | Genesis/profile mismatch |
| CMT040-SCHEMA07 | Omit consensus_params and rely on defaults | Release preflight rejects omitted profile object |
| CMT040-SCHEMA08 | Use a binary whose computed MaxCommitBytes default differs | Binary/profile identity check rejects |
| CMT040-SVC01 | Change one consensus timeout | Service-profile check reports/rejects unapproved deviation |
| CMT040-SVC02 | Change local RPC/P2P port only | Genesis and consensus-profile digests remain unchanged; local policy validates |
| CMT040-SVC03 | Change mempool admission/recheck/broadcast setting | Service-profile deviation detected |
| CMT040-SVC04 | Change PEX/peer limits/address-book policy | Service-profile/local network policy detects deviation |
| CMT040-SVC05 | Change binary bytes but preserve version string | SHA-256 pin rejects before launch |
| CMT040-4V01 | One of four validators uses a different Genesis/profile digest | Preflight rejects before node launch |
| CMT040-4V02 | Four validators use identical approved Genesis, binary, and profile | All preflights pass; then integration run may proceed |

## 8. Implementation sequence

1. Extract the exact default TOML generated by the pinned v0.40.0 binary and freeze it as a fixture with binary checksum.
2. Add an explicit complete `consensus_params` object to the approved Genesis template.
3. Extend the Go Genesis preflight to compare every consensus parameter, validator public key/type, voting power, chain ID, and initial height with the approved release manifest.
4. Add a strict TOML parser/validator for the exact v0.40.0 config schema; classify every field and reject unknowns.
5. Add a binary version and SHA-256 preflight.
6. Add mismatch tests before changing the existing smoke harness to require the verifier.
7. Keep HND Config-v1 binding and durable-store migration as a separate mandatory application gate.

## 9. Scope and disposition

This report is grounded in the CometBFT source files at the exact `v0.40.0` tag and the current HND scripts on `phase-0.2-planning`. It corrects the schema drift risk from relying on current/main documentation.

No HND code, tests, or workflows were changed. No Go build, Python test, binary inspection, or CometBFT network run was performed. Default values above are source-code defaults; the actual binary checksum and generated runtime TOML for the user's deployment remain to be collected and pinned.

**Disposition:** the current four-validator smoke remains valuable local integration evidence, but its inherited Genesis defaults and selected TOML edits do not constitute a production-frozen profile. Keep production launch blocked until explicit v0.40.0 Genesis parameters, binary identity, service-profile verification, and four-node mismatch tests are implemented and evidenced.
