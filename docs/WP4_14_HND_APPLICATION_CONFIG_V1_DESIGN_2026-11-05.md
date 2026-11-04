# HND Application Configuration v1 — Design Specification

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Status:** Proposed design only — not implemented  
**Scope:** HND deterministic application parameters, Genesis binding, startup validation, durable-state compatibility, and CometBFT boundary.

## 1. Purpose and non-goals

This specification defines a single authenticated configuration identity for every HND v0.2 application instance participating in one network. Its primary objective is to prevent validators from executing the same HND Genesis with different deterministic transaction or proposal rules.

This document does not implement code, select a public monetary policy, authorize a production network, define validator governance, or replace CometBFT's own consensus configuration. Existing test fixture values are not promoted to production values.

## 2. Design principles

1. A consensus-critical value has one authoritative source: the canonical HND application configuration artifact.
2. The configuration is versioned, strictly schema-validated, canonically serialized, domain-separated, and hash-pinned.
3. The HND application Genesis commits to both the allocation manifest and the application configuration.
4. CLI flags may select file paths or operational behavior; they must not silently override consensus-critical values.
5. The ABCI application validates the configuration again during InitChain, not only in the launcher.
6. Durable application state records the configuration digest and refuses restart under a different digest.
7. CometBFT-native consensus parameters remain a distinct, separately pinned artifact.
8. No implicit migration or default adoption is permitted.

## 3. Proposed canonical application configuration

Proposed schema name: `HNDApplicationConfig`  
Proposed schema version: `1`  
Proposed hash domain: `HND-LEDGER/APP-CONFIG/V1\0`

The exact schema should be encoded as a JSON object with exactly these keys:

| Field | Type / rule | Reason |
|---|---|---|
| `config_version` | integer exactly 1 | Configuration schema version |
| `network_id` | existing canonical network ID syntax | Prevent cross-network reuse |
| `protocol_version` | positive integer | Transaction and account identity domain |
| `max_amount` | positive integer | Existing per-transaction cap; deterministic validity |
| `max_block_transactions` | positive integer | Replace hard-coded module constant |
| `max_transaction_bytes` | positive integer | HND application-level transaction envelope bound |
| `amount_max` | positive integer | Portable amount upper bound across implementations |
| `nonce_max` | unsigned 64-bit maximum | Make existing nonce bound explicit and versioned |
| `transaction_encoding` | fixed enum, initially `canonical-json-v1` | Pin parser/serialization contract |
| `recipient_policy` | fixed enum, initially `genesis-registered-only-v1` | Pin account admission rule |

All numeric fields must use JSON integers, never booleans, floats, strings, or exponent notation. Unknown and missing keys must be rejected. Numeric ranges must be validated before the configuration is accepted. The eventual approved values must be chosen explicitly; this design does not assume that the current smoke-test values are network policy.

### 3.1 Rules that are deliberately not in this artifact

- Private keys, seed phrases, MAC keys, credentials, and secrets.
- Local file paths, ports, hostnames, RPC addresses, peer lists, log levels, worker counts, and process IDs.
- Validator private keys or signer endpoints.
- Operational timeouts and retry intervals that do not alter deterministic state validity.
- CometBFT's validator set, voting power, block gas/bytes, evidence parameters, and consensus timeouts. These belong in the separately pinned CometBFT network profile described below.

If a future operational parameter is found to affect deterministic state transitions or block acceptance, it must be reclassified and added through a versioned protocol change.

## 4. Hash construction and Genesis envelope

Let `C` be the strictly validated canonical application config.

`config_hash = SHA256("HND-LEDGER/APP-CONFIG/V1\\0" || canonical_json(C))`

The proposed HND application Genesis payload becomes an exact schema:

```json
{
  "application_config": { "...": "..." },
  "application_config_hash": "<64 lowercase hex>",
  "genesis_hash": "<64 lowercase hex>",
  "manifest": { "...": "..." }
}
```

The payload itself must be canonical JSON. The application verifies all of the following before initialization:

1. Exact top-level key set and exact nested schemas.
2. Canonical encoding, with duplicate JSON keys rejected.
3. Config hash recomputed from the embedded config.
4. Config network ID and protocol version match the CometBFT chain ID and manifest.
5. Manifest hash recomputed and compared with the trusted pinned Genesis identity.
6. Config hash matches the independently pinned expected application-config hash.
7. Any configured local expectation matches the embedded canonical config exactly.

The existing `genesis_hash` currently commits to the allocation manifest only. The protocol migration must define a new aggregate HND network-genesis identity that commits to both manifest hash and application-config hash. Do not silently reinterpret an existing v0.2 manifest hash as the new aggregate hash.

Suggested aggregate domain: `HND-LEDGER/NETWORK-GENESIS/V1\\0`. Its exact canonical payload must be specified before implementation and test vectors generated independently.

## 5. Startup and CLI behavior

The application launcher should accept a path to the approved network configuration artifact and trusted expected digests. It should not accept independently editable values such as `--max-amount` as the source of truth.

Recommended behavior:

- Load the artifact once; parse strictly; validate schema and ranges.
- Verify the expected config and network-genesis digests supplied by a trusted release/deployment mechanism.
- Construct `ProtocolConfig` and application policy objects only from the validated artifact.
- Reject legacy CLI overrides for consensus-critical fields. During a transition period, if compatibility requires retaining an override, require exact equality with the artifact and fail closed on mismatch.
- Log the verified network ID, protocol version, config version, and config digest. Never log secrets.
- Pass the validated config object and expected digest into the ABCI application.
- During `InitChain`, compare the received app-state config and digest with the already validated local config. Do not trust a launcher-only check.
- Refuse startup if the application binary does not support the config schema/protocol version.

## 6. Durable state and restart compatibility

Add `application_config_hash` and `config_version` to the durable store schema. Include them in the store integrity hash and validate them on every load.

On restart:

- Same network genesis and same application config digest: continue normal recovery checks.
- Different config digest: fail closed; do not load state under new rules.
- Missing config digest in an old store: treat as legacy state requiring an explicit migration tool/procedure, not as a wildcard match.
- Unsupported config version: fail closed.
- A migration must preserve a verified before/after state commitment, define activation height, require coordinated validator rollout, and be tested against crash/restart scenarios.

The durable-state format version must be incremented if the new fields change its required schema. Existing v0.2 stores must not be silently rewritten by ordinary startup.

## 7. CometBFT network profile — separate trust domain

Create a separately versioned network-profile artifact for CometBFT. It should pin:

- Exact CometBFT release/build identity.
- Canonical CometBFT Genesis bytes/hash.
- Chain ID and initial height.
- Validator public identities and voting power.
- Consensus block parameters (maximum bytes and gas).
- Evidence parameters (maximum age/bytes and related policy).
- Consensus version and any other CometBFT-native parameter that changes block validity or validator behavior.

Before starting a validator, a preflight tool must verify the local CometBFT Genesis/config against the approved profile digest. The profile may reference the HND application-config and network-genesis digests, but must not merge operational node endpoints or secrets into HND application state.

Consensus timeouts and networking parameters should be classified explicitly as liveness/operational settings unless the pinned CometBFT version makes a particular value part of block validity or state-transition behavior. Their exact classification must be confirmed against the pinned version's implementation.

## 8. Required implementation sequence

1. Freeze a schema and domain-separation specification; do not code against an unsettled schema.
2. Produce canonical positive and negative config vectors, including expected hashes.
3. Implement strict config parsing and digest verification as a standalone module.
4. Update Genesis construction/validation to bind manifest plus config.
5. Update ABCI InitChain to require and verify the new payload.
6. Update launcher/CLI so consensus-critical values cannot drift independently.
7. Update durable store schema and restart checks.
8. Add CometBFT profile generation and preflight validation.
9. Update disposable one-node and four-validator harnesses to consume the same artifacts.
10. Run the full existing suite plus new mismatch, restart, and multi-validator tests in the authorized environment.
11. Only after evidence review, consider opening the next development gate. Do not deploy or distribute tokens as part of this work.

## 9. Acceptance tests

- **ACFG01:** canonical config vector produces the published expected digest.
- **ACFG02:** changing each consensus-critical field changes the digest.
- **ACFG03:** missing/extra keys, duplicate JSON keys, non-canonical bytes, booleans-as-integers, floats, negative values, and out-of-range values are rejected.
- **ACFG04:** local CLI mismatch is rejected before ABCI server begins listening.
- **ACFG05:** InitChain rejects a missing or mismatched embedded config and config hash.
- **ACFG06:** manifest/config/network-genesis mismatch is rejected independently.
- **ACFG07:** existing durable state with a different config digest cannot be loaded.
- **ACFG08:** legacy store without config digest is rejected by normal startup and handled only by explicit migration.
- **ACFG09:** one validator with altered max amount or block transaction cap fails preflight before four-node launch.
- **ACFG10:** all four validators expose the same verified config digest and commit identical app hashes.
- **ACFG11:** changing only an operational setting does not change the HND application-config digest.
- **ACFG12:** CometBFT profile mutation (validator power, block limit, or evidence bound) fails the independent profile preflight.
- **ACFG13:** supported upgrade activation is coordinated at an explicit height and survives restart on all validators.
- **ACFG14:** independently implemented config serializers reproduce the same canonical bytes and digest.

## 10. Compatibility and risk

This is a protocol-identity change, not a harmless refactor. It changes the application Genesis schema, trusted network-genesis identity, startup inputs, and durable-store schema. Existing v0.2 fixtures, persisted stores, and test harnesses will require an explicit versioned migration or recreation as disposable test data.

Do not patch the current manifest hash in place, do not reinterpret old stores, and do not make a validator silently accept both old and new schemas on a live network. A mixed-version validator set is not an acceptable rollout mode.

## 11. Gate decision

**Design gate: READY FOR IMPLEMENTATION PLANNING, NOT IMPLEMENTATION APPROVAL.**

The design establishes the required trust boundaries and mismatch behavior. Before code changes, freeze the schema, hash domains, exact Genesis envelope, durable-store migration policy, and CometBFT profile fields. No tests have been executed by writing this design. Public deployment, real funds, and token distribution remain unauthorized.
