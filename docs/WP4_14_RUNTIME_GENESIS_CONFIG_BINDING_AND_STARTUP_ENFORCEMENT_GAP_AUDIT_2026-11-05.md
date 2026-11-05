# HND v0.2 — Runtime Genesis/configuration binding and startup enforcement gap audit

**Date:** 2026-11-05  
**Workstream:** WP4.14 — Consensus-critical configuration identity  
**Branch:** `phase-0.2-planning`  
**Reviewed head:** `9ebda4b9d0bed17351f7d3de3f47af33ed98060d`  
**Status:** Documentation-only static audit. No source, test, or workflow files changed.

## 1. Executive finding

The repository contains a detailed Config-v1 candidate design, decision register, candidate vectors, and implementation plan. Those are planning artifacts, not runtime enforcement.

The current executable HND application still uses the legacy Genesis envelope and CLI configuration path:

- application Genesis contains exactly `genesis_hash` and `manifest`;
- `max_amount` is independently supplied through `--max-amount`;
- `ProtocolConfig` is built from CLI arguments;
- the durable application store binds `network_id`, `protocol_version`, and the legacy manifest hash, but not `max_amount` or a Config-v1 digest.

Therefore, a node can start with the same legacy Genesis and a different `max_amount` value without the current Genesis/store identity checks detecting that configuration difference. The mismatch may cause deterministic transaction-validity divergence between validators.

**Disposition: Critical consensus configuration binding gap remains open. Config-v1 is not implemented. Do not treat the candidate specification or smoke-test equality as a production startup guard.**

## 2. Direct runtime evidence

### 2.1 CLI is currently an independent source of consensus policy

In `hnd_v02/cometbft_v040_server.py`:

- `--manifest` is required.
- `--genesis-hash` is required and checked against the manifest-only hash.
- `--network-id` is required.
- `--protocol-version` defaults to 2.
- `--max-amount` is required as a separate CLI argument.
- `ProtocolConfig` is constructed from those CLI values.

No Config-v1 artifact or expected application-config digest is loaded by this entry point.

### 2.2 Current InitChain identity is legacy-only

`HNDABCIApplication.application_genesis_bytes()` emits exactly:

- `genesis_hash`
- `manifest`

`init_chain()` checks:
- CometBFT chain ID equals local `config.network_id`;
- application Genesis has exactly the two legacy fields;
- supplied manifest hash equals the locally pinned legacy hash;
- supplied manifest equals the locally loaded manifest.

It does not receive or compare an authenticated application config object or its digest.

### 2.3 Durable store does not bind max_amount

The current store payload contains:
- store schema version;
- network ID;
- protocol version;
- legacy Genesis hash;
- committed height;
- ledger snapshot;
- evidence journal;
- application hash;
- store integrity hash.

Store recovery checks network ID, protocol version, and Genesis hash. It has no `max_amount` field and no application-config digest to compare with the current process configuration.

The store hash is an integrity checksum, not an authentication secret. It does not repair the missing configuration binding.

### 2.4 Four-validator smoke demonstrates a test setup, not a startup guard

The current four-validator smoke constructs one `ProtocolConfig` and launches all four ABCI processes with the same literal `--max-amount`. This proves that the harness intentionally uses the same test value.

It does not test a node starting with a different `--max-amount` and being rejected before joining consensus. It also does not prove that production operators cannot accidentally or deliberately configure nodes differently.

## 3. Enforcement matrix

| Parameter/artifact | Current source of truth | Current identity check | Config-v1 target |
|---|---|---|---|
| Network ID | CLI + manifest | chain ID, manifest, store | Exact config field + digest + trusted pin |
| Protocol version | CLI/default + manifest | transaction, manifest, store | Exact config field + digest + trusted pin |
| Max transaction amount | CLI `--max-amount` | Positive integer only; not Genesis/store-bound | Config field + digest; CLI override removed or equality-checked |
| Max block transaction count | Module constant | Local code only | Versioned config field |
| Max transaction bytes | Proposal request budget / application behavior | Not fully bound to HND config identity | Versioned config field and explicit enforcement boundary |
| Amount portable maximum | No global protocol maximum in current config | Per-tx cap only | Explicit `amount_max` and bounded arithmetic |
| Nonce maximum | Constant in transaction code | Code version only | Explicit `nonce_max` in config |
| Transaction encoding | Canonical JSON code behavior | Local implementation | Versioned enum in config and strict parser |
| Recipient policy | Genesis-registered account behavior | Local implementation + manifest | Versioned enum in config |
| Genesis allocation manifest | Manifest file + independently supplied hash | Legacy manifest hash, chain/network checks | Retain component hash and bind into aggregate network identity |
| CometBFT consensus profile | Generated CometBFT config defaults + selected smoke edits | No complete approved-profile digest at startup | Separate pinned CometBFT profile and binary identity |
| Validator set | CometBFT Genesis | Genesis validator list / consensus key checks in harness | Separately authenticated validator-set artifact and governance process |

This matrix distinguishes current checks from the proposed target; it does not imply that every operational CometBFT setting belongs in HND application configuration.

## 4. Concrete mismatch scenario

Assume two validators use the same:
- CometBFT chain ID;
- CometBFT Genesis bytes;
- HND allocation manifest;
- legacy manifest hash;
- protocol version.

But validator A starts with `--max-amount 1,000,000`, while validator B starts with `--max-amount 500,000`.

Under the current code:
1. Both can pass the legacy manifest hash check.
2. Both can pass chain ID and manifest checks in InitChain.
3. Their store identity checks do not compare max_amount.
4. A transaction of amount 750,000 can be valid under A's config and invalid under B's config, assuming sufficient balance and all other fields are valid.
5. Proposal acceptance and application execution may therefore differ.

This is a deterministic consensus safety risk, not merely an operational preference mismatch.

## 5. Required startup enforcement contract

Before any validator may join the network, the implementation should:

1. Load one strict Config-v1 artifact; do not construct consensus policy from independent CLI numeric flags.
2. Reject duplicate JSON keys, unknown/missing fields, wrong types, booleans-as-integers, floats, out-of-range integers, and noncanonical encodings.
3. Recompute the application-config digest from exact canonical bytes.
4. Recompute the legacy manifest component hash and aggregate network-genesis hash.
5. Compare all expected digests against independently authenticated deployment pins; do not accept a digest supplied only beside the untrusted artifact.
6. Require the Config-v1 network ID and protocol version to match the CometBFT chain ID and manifest.
7. Pass the validated config object and expected digests into the ABCI application.
8. Recheck the full Genesis envelope and all digests inside InitChain; launcher-only validation is insufficient.
9. Persist config version, application-config digest, and aggregate network-genesis digest in the durable store and its integrity preimage.
10. On restart, fail closed if the stored config identity is absent, unsupported, or differs. Legacy stores require an explicit migration path; no silent fallback.
11. Expose verified digests in safe diagnostics so operators can compare nodes without exposing secrets.
12. Separately verify the pinned CometBFT binary, Genesis, validator set, and consensus profile before launching the node.

## 6. Required negative acceptance tests

These are test requirements, not executed results:

| ID | Mismatch | Required result |
|---|---|---|
| CFG-RUN01 | One node uses a different `max_amount` | Startup fails before ABCI service begins |
| CFG-RUN02 | Config file changed but old config digest supplied | Startup fails |
| CFG-RUN03 | Config and digest changed but trusted pin remains old | Startup fails |
| CFG-RUN04 | Genesis manifest changed but manifest/aggregate pins remain old | Startup or InitChain fails |
| CFG-RUN05 | Chain ID differs from config network ID | InitChain/startup fails |
| CFG-RUN06 | Config protocol version differs from manifest or binary-supported version | Startup fails |
| CFG-RUN07 | Durable store has a different config digest | Recovery fails closed |
| CFG-RUN08 | Legacy store lacks config digest | Explicit migration required; normal startup rejects |
| CFG-RUN09 | Unknown or missing config key, duplicate key, boolean/float integer | Strict parser rejects |
| CFG-RUN10 | One CometBFT consensus-profile field differs | Node preflight rejects before process start |
| CFG-RUN11 | Validator-set public key or voting power differs | Node preflight rejects |
| CFG-RUN12 | Operational endpoint changes without consensus-profile changes | Consensus digest remains stable; operational validation still runs |

## 7. Implementation gate and dependency order

Existing Config-v1 documents correctly keep implementation behind specification and decision gates. Preserve that sequence:

1. Resolve all Config-v1 decision-register items and freeze schema, numeric bounds, canonicalization, and exact hash preimages.
2. Freeze positive and negative golden vectors, including independent expected digests.
3. Define migration behavior for legacy Genesis and durable stores.
4. Implement strict parsing, config loading, Genesis envelope, InitChain checks, durable-store binding, and CLI removal/equality guard as one coordinated change.
5. Implement the separately pinned CometBFT profile and validator-set preflight.
6. Add mismatch tests, four-validator integration tests, restart/migration tests, and cross-language vector tests.
7. Run the complete approved suite and retain logs before any release gate changes.

No current CLI flag, smoke test, candidate vector, or planning document should be treated as approval of production monetary values or protocol parameters.

## 8. Scope and conclusion

This report maps the current runtime implementation against the Config-v1 target. It confirms the previously identified `max_amount` mismatch is not merely an abstract design concern: the current CLI, InitChain envelope, and durable-store schema leave it unbound.

No source, test, or workflow files were modified. No tests or CometBFT network runs were executed. This is not a production-readiness certification.
