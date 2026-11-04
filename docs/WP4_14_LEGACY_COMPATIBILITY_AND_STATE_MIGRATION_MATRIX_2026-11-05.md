# HND Legacy Compatibility and State Migration Matrix

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Status:** Documentation and migration policy proposal — not implemented  
**Scope:** Legacy v0.2 Genesis, Application Config v1, durable application store v3, and future config-bound store format.

## 1. Decision summary

HND must use a fail-closed compatibility boundary between the existing v0.2 application and the proposed Application Config v1 protocol.

The current v0.2 application has two relevant legacy properties:

- Its application Genesis payload is exactly `{"genesis_hash": ..., "manifest": ...}`. The current `genesis_hash` commits to the allocation manifest; it does not commit to the proposed application configuration.
- Its durable store schema is version 3. The required store keys include network ID, protocol version, legacy Genesis hash, height, ledger snapshot, evidence journal, app hash, and store hash. There is no application-config digest or config-schema version.

Therefore:

1. A legacy manifest hash must never be reinterpreted as a config-bound network-genesis hash.
2. A v0.2 legacy node must not join or validate a Config-v1 network.
3. A legacy store without a config digest must not be loaded as if it matched an arbitrary Config-v1 network.
4. Ordinary startup must not silently migrate or rewrite a legacy store.
5. Any conversion must be explicit, offline, auditable, and independently verified.
6. The first Config-v1 deployment should be a fresh test network. In-place live-network migration is out of scope until a separately approved coordinated-upgrade protocol exists.

No code, state files, or CI workflows are changed by this document.

## 2. Verified legacy baseline

The source reviewed on `phase-0.2-planning` includes:

| Item | Current implementation |
|---|---|
| HND application Genesis top-level keys | Exactly `genesis_hash` and `manifest` |
| Legacy Genesis identity | Manifest hash under `HND-LEDGER/GENESIS\0` |
| Application store version | `APP_STORE_VERSION = 3` |
| Store required fields | `schema_version`, `network_id`, `protocol_version`, `genesis_hash`, `last_committed_height`, `ledger_snapshot`, `evidence_journal`, `app_hash`, `store_hash` |
| Store integrity checksum | SHA-256 over canonical store payload with the `HND-ABCI-STORE-V2\0` domain |
| Config digest in durable store | Absent |
| Config version in durable store | Absent |

The store checksum detects accidental or unauthorized payload changes only to the extent that its inputs remain trustworthy; it is not a keyed authentication mechanism. It does not establish that a store belongs to a particular future application configuration.

The current loader requires the exact v3 key set and exact store version, then validates network ID, protocol version, legacy Genesis hash, snapshot, evidence journal, and app hash. This strictness is useful and must not be weakened to accept missing config fields.

## 3. Compatibility matrix

| Genesis format | Durable state | Binary / protocol | Decision |
|---|---|---|---|
| Legacy v0.2 manifest-only | No store; fresh initialization | Legacy v0.2 binary | Allowed only on the existing legacy test network with its original pinned identity |
| Legacy v0.2 manifest-only | Store v3, matching legacy network and manifest hash | Legacy v0.2 binary | Legacy recovery only; retain existing validation |
| Legacy v0.2 manifest-only | Store v3 | Config-v1 binary | Reject; missing config identity is not a wildcard |
| Config-v1 envelope with config and aggregate network-genesis identity | No store; fresh initialization | Config-v1-capable binary with matching pinned digests | Allowed on a fresh Config-v1 test network |
| Config-v1 envelope | Future config-bound store containing matching config digest and supported schema | Matching Config-v1 binary | Allowed after all startup and state checks pass |
| Config-v1 envelope | Future config-bound store with a different config digest | Any binary | Reject; do not reinterpret state under different deterministic rules |
| Config-v1 envelope | Legacy v3 store without config digest | Config-v1 binary | Reject; require explicit offline migration/rebuild decision |
| Legacy Genesis | Future config-bound store | Legacy binary | Reject; format/protocol mismatch |
| Any Genesis | Unknown or unsupported store schema | Any binary | Reject closed; no best-effort parsing |
| Any Genesis | Store from another network, manifest, or aggregate network identity | Any binary | Reject |

A network's identity is the complete tuple of protocol rules and trusted Genesis commitments, not merely a matching human-readable chain ID.

## 4. Genesis identity rules

### 4.1 Legacy identity remains immutable

The existing legacy `genesis_hash` means the hash of the legacy allocation manifest under the legacy domain. Its historical meaning must remain unchanged.

It must not be:

- relabeled as the Config-v1 network-genesis hash;
- treated as proof that a legacy node has loaded Config-v1 rules;
- inserted into a new envelope as the aggregate identity without an explicit, separately computed commitment; or
- silently upgraded by changing the interpretation of the old hash domain.

### 4.2 Config-v1 identity

The Config-v1 design proposes a separately domain-separated application-config digest and a new aggregate network-genesis identity committing to both the manifest identity and application-config identity.

Before implementation, the aggregate preimage must be frozen with:
- exact field names and types;
- exact canonical serialization rules;
- explicit domain-separation bytes;
- strict lowercase-hex digest syntax;
- positive and negative golden vectors; and
- independently generated expected digests.

The config digest and aggregate network-genesis digest must be pinned through a trusted release/deployment process. A digest supplied only by the same untrusted source as the artifact is not an independent trust anchor.

### 4.3 No cross-version hash equivalence

Even if two networks happen to use the same allocation manifest, a legacy manifest hash and a Config-v1 aggregate network-genesis hash are different identity types. Equality of a component hash does not establish equality of the full network rules.

## 5. Durable-store versioning and migration boundary

The existing v3 store is not config-bound. The future store schema must add, at minimum:

- a durable schema version incremented from v3;
- application config schema version;
- application config digest;
- aggregate network-genesis identity (or an explicitly defined equivalent trusted identity);
- the existing network, protocol, height, snapshot, evidence, app-hash, and integrity fields.

The new store integrity checksum must cover every new identity field. The loader must reject missing, unknown, malformed, or unsupported fields.

The future loader must compare the stored config digest and network identity against independently validated startup expectations before restoring the ledger snapshot. A checksum-valid store with a mismatched config digest must still be rejected.

Do not implement a permissive loader that accepts both v3 and the new format in the same ordinary startup path unless an explicit migration mode is selected and separately authorized. Prefer a separate offline migration utility with read-only access to the source and a new output destination.

## 6. Offline migration / rebuild procedure

Migration is a controlled conversion, not a routine restart operation. It must not be automatic.

### Phase A — Freeze and capture

1. Stop all legacy application and validator processes in the test environment.
2. Make a byte-for-byte copy of the legacy store and relevant legacy Genesis artifacts.
3. Record SHA-256 hashes of every source artifact before processing.
4. Record legacy network ID, protocol version, legacy manifest hash, committed height, app hash, and software commit.
5. Preserve the original source artifacts as immutable evidence; never overwrite them.

### Phase B — Verify source

1. Run the legacy version's strict store verification against a read-only copy.
2. Verify the ledger snapshot, evidence journal, height, and app hash using the legacy implementation.
3. Reject truncated, malformed, checksum-invalid, or internally inconsistent sources.
4. Record the exact verification command, tool version, output, and operator approval.
5. Do not infer a valid state from a successful JSON parse or store checksum alone.

### Phase C — Choose the target network explicitly

There are only two acceptable outcomes:

**Outcome 1: Fresh Config-v1 test network (preferred).**  
Create a new Config-v1 Genesis and a new initial state from an explicitly approved allocation manifest. Do not carry forward the legacy chain height or claim continuity with the old network. Use synthetic/test allocations unless a separate economic and governance approval exists.

**Outcome 2: Offline state conversion for controlled testing.**  
Only after the conversion semantics are specified and approved, convert a verified legacy snapshot into a new-format state. The conversion specification must define how height, balances, account identities, evidence history, app hash, and Genesis commitments are represented. The output must be marked as migrated test state and must not imply that the old and new networks are consensus-continuous.

A conversion must never silently discard evidence entries, alter balances, invent issuance, or change account identities. If any source field cannot be represented exactly, abort and use a fresh network instead.

### Phase D — Produce and verify output

1. Write the converted state to a new, empty destination; never write over the source.
2. Record source hashes and output hashes in a migration manifest.
3. Verify the new store using the Config-v1 implementation and pinned target digests.
4. Compare all defined invariants, including account balances, total balance conservation, evidence records, height semantics, and app hash semantics.
5. Restart the Config-v1 application from the output and verify deterministic recovery.
6. Have an independent verifier reproduce the output commitments from the source and frozen migration specification.
7. Keep the source and output artifacts together with a signed or otherwise independently authenticated migration record.

No migration utility is approved or implemented by this document.

## 7. Activation and rollout strategy

### 7.1 Initial rollout

- Build and test Config-v1 on a new isolated test network.
- Use a new chain ID and new aggregate network-genesis identity.
- Start with a clean state directory and fresh store.
- Require every validator to run a binary that supports the exact same Config-v1 schema and pinned CometBFT profile.
- Reject mixed legacy and Config-v1 validators.
- Do not reuse legacy peer addresses, validator identities, keys, or state directories by default.

### 7.2 Possible future coordinated upgrade

An in-place upgrade of an already-running network requires a separate protocol specification. At minimum it must define:

- a unique activation height and pre-activation / post-activation rules;
- an authenticated upgrade plan committed by the network;
- validator readiness and coordinated binary rollout;
- deterministic state transition and migration semantics;
- behavior for validators that miss the activation height;
- recovery from partial rollout and crashes;
- upgrade-height and config-digest commitments;
- replay protection across the boundary; and
- independently tested rollback/recovery procedures.

Until that specification is approved and implemented, no activation-height upgrade is permitted. A local operator must not independently decide to switch a running network to Config-v1.

## 8. Rollback and downgrade policy

Before Config-v1 activation on a fresh test network, an operator may discard the test network and recreate it from its pinned Config-v1 Genesis. This is a test-environment reset, not a protocol rollback.

After a Config-v1 network has committed state under the new rules:

- do not start a legacy binary against its state directory;
- do not strip config fields to make the state appear v3-compatible;
- do not restore a legacy snapshot as if it were a valid continuation;
- do not permit a subset of validators to downgrade independently; and
- do not silently change the aggregate Genesis or config digest.

Any recovery that changes protocol rules after committed Config-v1 state requires a coordinated fork/recovery plan, explicit operator/governance authorization, and a separately pinned recovery identity. If no safe recovery plan exists, halt rather than create a mixed-rules network.

## 9. Test and fixture migration requirements

The implementation must add explicit fixtures for:
- canonical legacy Genesis payload;
- canonical Config-v1 Genesis payload;
- valid v3 legacy store;
- valid future config-bound store;
- legacy store presented to Config-v1 loader;
- Config-v1 store presented to legacy loader;
- wrong config digest;
- wrong aggregate network-genesis digest;
- unsupported config/store versions;
- unknown and missing fields;
- altered migration source and output artifacts;
- migration interruption at each write boundary;
- restart after completed migration;
- two validators with different config digests;
- two validators with same config digest but different CometBFT profile digests.

Golden vectors must be generated independently and checked into the repository. Tests must verify that canonical serialization and digest values match across supported implementations.

## 10. Acceptance tests

| ID | Required behavior |
|---|---|
| MIG01 | Legacy v0.2 Genesis hash retains its original manifest-only meaning |
| MIG02 | Config-v1 Genesis computes a distinct config-bound aggregate identity |
| MIG03 | Config-v1 startup rejects a v3 store with no config digest |
| MIG04 | Legacy startup rejects a future store schema it does not support |
| MIG05 | Config-v1 startup rejects a store with a mismatched config digest |
| MIG06 | Config-v1 startup rejects a mismatched aggregate network-genesis identity |
| MIG07 | Missing, extra, duplicate, or malformed identity fields fail closed |
| MIG08 | A verified legacy source remains byte-for-byte unchanged after offline conversion |
| MIG09 | Migration output is written to a separate destination and records source/output hashes |
| MIG10 | Migration aborts if source snapshot, evidence, or app-hash verification fails |
| MIG11 | Migration interruption cannot cause ordinary startup to accept a partial output |
| MIG12 | A completed output passes Config-v1 restore and restart verification |
| MIG13 | Validators with different application config digests refuse to form a valid mixed network |
| MIG14 | Validators with different pinned CometBFT profile digests fail preflight |
| MIG15 | No automatic fallback or downgrade occurs after Config-v1 state has been committed |

These are acceptance requirements, not evidence that the tests currently exist or have passed.

## 11. Implementation order and exit criteria

1. Freeze Config-v1 config schema, config hash, and aggregate network-genesis preimage.
2. Freeze the future durable-store schema and version number.
3. Define exact migration manifest and offline tool behavior.
4. Add canonical positive/negative golden vectors.
5. Implement strict config-bound Genesis validation.
6. Implement strict config-bound durable-store write/load and restart checks.
7. Implement explicit offline migration only if conversion semantics are fully specified.
8. Add all MIG01–MIG15 tests and run them in the authorized environment.
9. Verify a fresh isolated multi-validator Config-v1 test network.
10. Conduct an independent review before any wider test distribution.

Exit criteria: all required tests pass with recorded logs; independent review confirms the identity and migration boundaries; no legacy/config-v1 mixed mode exists; and no production, public-network, or economic launch gate is inferred from test success.

## 12. Current gate decision

**Decision: compatibility policy documented; implementation remains blocked pending schema freeze and independent test vectors.**

This document does not authorize:
- editing application code;
- changing CI workflows;
- migrating any existing state;
- reusing the legacy network as a Config-v1 network;
- opening G2–G4;
- public token distribution, production deployment, or real-value operation.

The next safe work item is a Config-v1 canonical identity and golden-vector specification, followed by a review of its exact hash preimages before implementation.
