# WP4.14 — Cross-Validator Application Configuration Consistency Audit — 2026-11-05

## Scope

Static source/test review on `phase-0.2-planning`, baseline commit `643302d76624dcae15a233cbcc5f3f1ebe7879a4`. Inspected:

- `hnd_v02/transaction.py` (`ProtocolConfig`)
- `hnd_v02/genesis.py`
- `hnd_v02/abci_app.py` (InitChain and durable-store identity)
- `hnd_v02/cometbft_v040_server.py` (CLI startup)
- `scripts/cometbft_v040_four_validator_genesis_preflight.py`
- `scripts/cometbft_v040_four_validator_network_smoke.py`
- `tests/test_v02_abci_app.py`
- `tests/test_v02_four_replica_state_convergence.py`
- `tests/test_v02_cometbft_v040_adapter.py`

No code, tests, workflows, or deployment settings were modified. No new tests or nodes were run for this audit.

## Executive result

**NOT APPROVED — validator configuration identity is incomplete.**

The repository has meaningful shared-Genesis checks and a four-node smoke harness that supplies the same command-line values to all four test processes. However, the HND application does not authenticate a complete consensus-critical configuration identity. The same manifest and manifest hash can be paired with different local `ProtocolConfig.max_amount` values. That parameter directly changes transaction acceptance and is not committed by the current Genesis manifest hash or the InitChain payload.

## Positive controls

1. `ProtocolConfig` validates network ID syntax, positive protocol version, and positive integer `max_amount`.
2. Genesis validation checks the manifest network ID and protocol version against local config, validates allocation key/account relationships and supply sum, and checks the manifest against an expected hash.
3. InitChain checks CometBFT `chain_id`, the expected manifest hash, and exact canonical manifest equality.
4. Store recovery checks schema version, network ID, protocol version, manifest Genesis hash, store checksum, reconstructed ledger state, and app hash. This catches a number of accidental or mismatched recovery inputs.
5. Four-validator Genesis preflight creates distinct consensus keys and P2P node IDs and copies byte-identical CometBFT Genesis documents into four temporary homes.
6. Four-validator network smoke starts four temporary ABCI processes with the same explicit CLI arguments, gives them the same manifest/hash, and checks common chain identity, block progress, account balances, and app-hash convergence after a transfer.
7. Four-replica application tests verify equal app hashes for identical local inputs and detect a deliberately divergent app state.

## Findings

### CFG-A1 — Consensus-critical `max_amount` is not bound to Genesis/config identity

**Severity: High.**

`ProtocolConfig` consists of `network_id`, `protocol_version`, and `max_amount`. The Genesis manifest and `genesis_manifest_hash` commit to the manifest fields only: manifest version, network ID, protocol version, total supply, and allocations. The application InitChain payload contains only `genesis_hash` and `manifest`.

The CometBFT server CLI separately accepts `--network-id`, `--protocol-version`, and required `--max-amount`, constructs a local `ProtocolConfig`, and starts the ABCI application after checking the manifest network ID. It does not verify a config digest or require `max_amount` to match an authenticated network artifact.

**Impact:** two validators can use the same chain ID, manifest, and expected manifest hash but different `max_amount` values. The transaction validator will accept different amount ranges. The four-node smoke script passes identical values by construction, but this does not prove that production nodes reject an operator's mismatched value.

**Required:** define a versioned canonical application-config object and digest. Include every deterministic acceptance parameter (at minimum network ID, protocol version, max amount, transaction-count ceiling, and any application-enforced byte/format limits) in a pinned application Genesis identity. Reject CLI overrides unless they exactly match that authenticated config. Do not silently fall back to local defaults.

### CFG-A2 — Existing tests do not exercise cross-config mismatch rejection

**Severity: High.**

The AB CI tests exercise wrong chain ID, wrong pinned manifest hash, noncanonical InitChain bytes, and wrong network/Genesis store recovery. The four-replica convergence test constructs all replicas from the same single `ProtocolConfig` object. No inspected test starts two applications with the same manifest and expected Genesis hash but different `max_amount`, then proves startup/InitChain rejects one.

**Impact:** the current test suite demonstrates convergence under identical config, not fail-closed behavior under differing consensus-critical config.

**Required:** add negative test CFG-T01: same manifest/hash, different max_amount must fail before ABCI service startup or before any block can be accepted. Add mutation tests for every consensus-critical config field and verify a one-field change changes the config digest.

### CFG-A3 — Four-validator smoke's identical startup arguments are harness guarantees, not node-enforced guarantees

**Severity: Medium-High.**

The smoke harness defines a single `cfg` and passes the same `--network-id`, `--protocol-version`, and `--max-amount` arguments to all four ABCI subprocesses. It copies the same CometBFT Genesis bytes to all four homes. This is useful integration evidence, but the node binary does not independently verify a complete HND application-config digest against CometBFT Genesis.

**Impact:** a manually launched or separately provisioned validator can diverge from the harness assumptions while retaining the same manifest identity.

**Required:** move the invariant into node startup itself, not only the test harness. Preflight must compare the expected application-config digest and CometBFT profile digest before starting any ABCI listener or validator signer.

### CFG-A4 — Durable application store does not record complete application-config identity

**Severity: Medium-High.**

The application store records network ID, protocol version, manifest Genesis hash, ledger snapshot, evidence journal, app hash, and store checksum. It does not record a Config-v1 digest or CometBFT profile identity.

**Impact:** recovery can reject mismatched network/protocol/manifest identity but cannot independently detect a changed `max_amount` when the other recorded identity fields remain the same.

**Required:** store the verified config digest and profile identity in a versioned store schema. Recovery must fail closed if either differs. Define an offline migration process; do not silently rewrite legacy stores.

### CFG-A5 — CometBFT network profile identity is not integrated with HND application identity

**Severity: Medium.**

The four-validator harness creates common CometBFT Genesis and checks validator identities, but the HND application does not receive or verify a separately pinned digest covering the resolved CometBFT consensus profile and build identity. Byte-identical files in the harness are not equivalent to a production release process that authenticates the expected profile.

**Required:** define two distinct identities: (1) HND application config identity, and (2) CometBFT network-profile identity. Pin both in release/preflight artifacts and verify both before startup. Keep local ports, paths, private keys, and peer endpoints outside the application consensus config.

## Required acceptance tests

- **CFG-T01:** same manifest/hash, different `max_amount`; mismatched node fails closed before listening/signing.
- **CFG-T02:** one-byte/one-field mutation of each consensus-critical config field changes the config digest and fails pinned identity verification.
- **CFG-T03:** reject missing, extra, wrong-type, duplicate-key, and noncanonical config fields.
- **CFG-T04:** all validators agree on exact transaction-count and transaction-size boundaries.
- **CFG-T05:** same config digest and authenticated CometBFT profile digest on four independently started nodes.
- **CFG-T06:** change only an operational setting (port/log level) and show the application config digest remains unchanged.
- **CFG-T07:** restart with a different critical config and prove existing state cannot be loaded.
- **CFG-T08:** mutate validator set, voting power, or consensus parameters and prove preflight fails before node start.
- **CFG-T09:** explicit versioned upgrade activation; no silent default/config adoption.

## Gate decision

| Gate | Result |
|---|---|
| Shared manifest/chain identity checks | PASS for implemented checks |
| Same-config four-node smoke harness | PASS as harness behavior; prior CI evidence only |
| Complete consensus-critical application config identity | FAIL / NOT IMPLEMENTED |
| Mismatched-config rejection test | NOT PRESENT in inspected tests |
| Durable-store config digest binding | NOT IMPLEMENTED |
| Authenticated CometBFT profile digest | NOT IMPLEMENTED |
| Production validator configuration consistency | NOT ESTABLISHED |

**Overall: configuration-consistency gate remains OPEN / FAIL.** Do not claim that all production validators are guaranteed to execute identical monetary and transaction-acceptance rules until the config identity, startup enforcement, store binding, and negative mismatch tests are implemented and pass.

## Evidence boundary

This report is a static review. It does not claim that a four-node network was newly launched or that a new test was executed. Existing four-validator smoke code is evidence of a controlled harness with identical parameters; historical CI success is not a substitute for mismatch testing.

No source, test, workflow, or deployment file was changed.
