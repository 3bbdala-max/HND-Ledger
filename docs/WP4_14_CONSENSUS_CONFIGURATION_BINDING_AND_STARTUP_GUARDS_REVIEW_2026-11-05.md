# WP4.14 — Consensus Configuration Binding and Startup Guards Review

**Date:** 2026-11-05  
**Branch reviewed:** `phase-0.2-planning`  
**Scope:** Static source review of HND v0.2 configuration, ABCI Genesis, node startup, and the disposable CometBFT v0.40.0 single-/four-validator harnesses.  
**Change type:** Documentation only. No application code, CometBFT configuration, CI workflow, or production setting was changed.

## 1. Executive finding

The current HND application Genesis authenticates the HND manifest and checks the CometBFT `chain_id` against `ProtocolConfig.network_id`, but it does **not** authenticate the complete set of parameters that determine deterministic HND transaction acceptance and proposal validity.

In particular, `ProtocolConfig.max_amount` is supplied independently to each ABCI process through the required `--max-amount` CLI argument. It is not part of the HND manifest, HND Genesis hash, or ABCI `app_state`. Two validators can therefore use the same HND Genesis while applying different per-transaction amount limits. A transaction with an amount between those limits can be admitted by one validator and rejected by another. This is a consensus-safety configuration defect, not merely an operational preference.

The application also has a hard-coded `MAX_BLOCK_TRANSACTIONS = 1000`, while proposal byte budgets arrive from CometBFT request data. The repository does not define a versioned, authenticated HND consensus-configuration manifest that binds these application limits to the network identity.

CometBFT-native settings (block maximum bytes/gas, evidence limits, timing, validator set and voting power) are a separate configuration domain. The four-validator harness initializes CometBFT homes from the pinned binary's generated defaults, then changes selected TOML networking fields and Genesis identity/validator fields. It does not define and validate a complete, independently approved consensus-parameter policy in the HND manifest.

## 2. Source observations

### 2.1 HND application configuration

- `hnd_v02/transaction.py`: frozen `ProtocolConfig` contains exactly `network_id`, `protocol_version`, and `max_amount`. Its validation checks syntax/positive ranges, but it does not establish a shared network-wide configuration digest.
- `validate_transaction` rejects an amount greater than the local `config.max_amount`. This value directly changes deterministic transaction validity.
- `hnd_v02/cometbft_v040_server.py`: CLI requires `--network-id` and `--max-amount`; `--protocol-version` defaults to 2. The process constructs `ProtocolConfig` from those arguments.
- The server checks that manifest `network_id` matches the CLI network ID, but there is no equivalent Genesis comparison for `max_amount`.
- `hnd_v02/genesis.py`: manifest schema contains `manifest_version`, `network_id`, `protocol_version`, `total_supply`, and `allocations`. Validation binds network and protocol version to the local config, but has no max-amount field.
- `hnd_v02/abci_app.py`: `application_genesis_bytes()` emits only `genesis_hash` and `manifest`. `init_chain()` requires exactly those two fields and verifies the chain ID, pinned manifest hash, and manifest bytes. It cannot detect a mismatch in `max_amount`.
- `MAX_BLOCK_TRANSACTIONS = 1000` is a module-level application constant. `_validate_tx_list` applies it to proposal transaction lists. It is not included in the manifest or application Genesis payload.
- `prepare_proposal` uses the supplied `max_tx_bytes` budget to choose transactions. The ABCI adapter passes CometBFT's `request.max_tx_bytes`; the application does not independently bind that budget to an HND configuration hash.

**Finding CFG01 — Critical:** `max_amount` can differ between validators sharing the same HND Genesis and change CheckTx/FinalizeBlock validity.

**Finding CFG02 — High:** the application transaction-count ceiling is not explicitly versioned or committed by the HND Genesis identity. A code-version mismatch can therefore alter proposal acceptance behavior.

**Finding CFG03 — High:** proposal byte-budget semantics depend on CometBFT request/configuration. The HND application has no authenticated cross-layer declaration of the intended maximum block transaction bytes.

### 2.2 CometBFT-native configuration

- The four-validator preflight and network smoke scripts invoke the supplied CometBFT binary's `init` command for each temporary home.
- The four-validator smoke then changes selected generated `config.toml` fields: ABCI proxy address/protocol, RPC listener, P2P listener, persistent peers, PEX, strict address-book behavior, and duplicate-IP allowance. It does not explicitly set or validate the full CometBFT consensus configuration.
- The smoke modifies CometBFT Genesis `chain_id`, initial height, validators, app hash, and HND app state. The validator set is generated with four validators at voting power 10 each.
- The preflight verifies the generated Genesis using the pinned CometBFT v0.40.0 Go types and copies identical Genesis bytes to all temporary homes. These are useful integration checks, but they do not establish a release-approved policy for every consensus parameter.
- The single-node and four-validator harnesses use disposable local keys and temporary directories. Their values are test fixtures, not public-network parameters.

Keep these domains separate:

| Parameter family | Examples | Primary effect | Required binding |
|---|---|---|---|
| HND deterministic application | `max_amount`, transaction-count cap, numeric bounds, transaction schema/version | Transaction validity and application state | HND application-config hash in authenticated application Genesis |
| CometBFT consensus | block max bytes/gas, evidence max age/bytes, validator set/power, consensus version | Block validity, voting power, evidence acceptance and liveness | Canonical CometBFT Genesis/config policy, independently hashed and pinned for every validator |
| Operational only / security | RPC/ABCI bind addresses, worker count, logging, peer addresses | Reachability, throughput, exposure | Hardened deployment profile; must not be confused with application consensus identity |

**Finding CFG04 — High:** the harness inherits multiple CometBFT settings from generated defaults rather than checking a complete explicit consensus policy. A binary upgrade or altered generated defaults could change those settings without changing the HND manifest hash.

**Finding CFG05 — Medium:** validator membership and voting power are in CometBFT Genesis, not the HND manifest. This is valid as a layered architecture only if the exact CometBFT Genesis bytes/hash and validator-set governance are separately pinned and distributed as trusted network configuration.

### 2.3 Startup and mismatch behavior

- The ABCI server independently loads the manifest, checks its supplied manifest hash, constructs local `ProtocolConfig`, and starts the gRPC service.
- The application rejects a chain ID, manifest, or pinned manifest-hash mismatch during `InitChain`.
- It does not receive or verify a configuration digest from CometBFT Genesis, nor does it prove that all validators started with identical `max_amount` or application constants.
- The harness passes the same literal `--max-amount` to its four local ABCI processes. This demonstrates a consistent test invocation, not a production startup guard against operator misconfiguration.
- `--listen` can override the loopback default and the gRPC server uses an insecure listener. This is a transport-security issue already tracked separately; it must not be mistaken for consensus configuration binding.

**Finding CFG06 — Critical:** startup currently verifies manifest identity but not the complete deterministic application configuration identity.

## 3. Required target design (not implemented)

1. Define a versioned, strict-schema `HNDApplicationConfig` containing every parameter that can change deterministic transaction validity, state transitions, or proposal acceptance.
2. At minimum include: protocol version, network ID, max transaction amount, numeric/base-unit bounds, maximum transaction count per block, maximum transaction byte size (if application-enforced), canonical transaction format/version, and any future fee/issuance/recipient rules.
3. Canonically serialize and domain-separate hash this configuration. Include the full config and its digest in the authenticated HND application Genesis payload. The pinned HND Genesis identity must commit to both the allocation manifest and application configuration.
4. Require every ABCI process to load the expected config from the same pinned artifact; reject CLI overrides for consensus-critical values, or accept them only when they exactly match the authenticated config.
5. During `InitChain`, reject missing, extra, malformed, non-canonical, or mismatched config fields/digests. Expose the verified config digest in diagnostics without making diagnostics part of consensus state.
6. Add a separate CometBFT network profile containing exact consensus parameters, validator set and voting power, evidence parameters, and CometBFT version. Hash the canonical Genesis/config artifacts and verify the expected hashes before node start.
7. Classify every setting as deterministic validity, consensus safety, liveness/performance, or security/operations. Do not place secrets, local paths, ports, peer endpoints, or private keys into the HND application Genesis.
8. Define a coordinated protocol upgrade procedure. A validator must not silently adopt new defaults or a new config version while remaining on the old network identity.

## 4. Acceptance tests required

- **CFG-T01 — max amount mismatch:** start two application instances with the same manifest but different max amounts; startup/InitChain must reject the mismatched config rather than allow divergent transaction validity.
- **CFG-T02 — application config digest:** one-byte change to any consensus-critical config field changes the digest and is rejected against the pinned expected digest.
- **CFG-T03 — canonical schema:** reject missing fields, unknown fields, wrong types, duplicate JSON keys, non-canonical JSON, and invalid numeric boundaries.
- **CFG-T04 — transaction ceiling:** all validators reject the same proposal immediately above and accept the same proposal at the configured transaction-count boundary.
- **CFG-T05 — proposal byte limit:** exercise exact-boundary, one-byte-over, empty, and oversized transaction cases using the same authenticated policy and CometBFT request budget.
- **CFG-T06 — binary/config mismatch:** node startup fails closed when the application protocol/config version is unsupported or inconsistent with the pinned network profile.
- **CFG-T07 — CometBFT profile digest:** mutate block/evidence/validator-power consensus parameters in a test Genesis; preflight must detect the digest mismatch before node start.
- **CFG-T08 — validator set consistency:** all four nodes must report the expected validator set and voting powers; a missing, extra, or altered validator must fail preflight.
- **CFG-T09 — restart persistence:** restart each application with a different critical config and prove it refuses to load existing state.
- **CFG-T10 — four-node divergence test:** deliberately configure one validator with a different critical application parameter and prove the test harness fails before network launch, not after a divergent block.
- **CFG-T11 — non-consensus settings:** demonstrate that changing only a declared operational setting (for example log level or local port) does not change the HND application config digest.
- **CFG-T12 — upgrade compatibility:** test explicit config-version migration/activation at a specified height; no implicit default adoption.

## 5. Evidence and limitations

This is a static source review of the current `phase-0.2-planning` branch. No Python test suite, CometBFT process, or new integration test was run for this report. Existing four-validator smoke code was inspected; its historical CI success is not a new test result and does not close the configuration-binding findings.

No application source, test, or GitHub Actions workflow was modified. No public deployment, token distribution, real funds, or production gate is authorized by this review.

## 6. Gate decision

**Configuration-binding gate: FAIL / OPEN.** Do not treat the current shared manifest hash as proof that validators share identical deterministic application rules. Keep public network and production gates closed until CFG01 and CFG06 are fixed and CFG-T01 through CFG-T10 pass in a reproducible multi-validator test.
