# WP4.14 — Protocol Upgrade Activation, Rollback and Mixed-Validator Version Governance Audit — 2026-11-07

**Repository:** `3bbdala-max/HND-Ledger`  
**Branch:** `phase-0.2-planning`  
**Baseline commit reviewed:** `261cbeccea5cc593e58df7d894a7339e827a4ad2`  
**Audit type:** documentation and static source review; existing GitHub Actions evidence inspected  
**Disposition:** **NOT APPROVED — no coordinated in-place protocol upgrade, deterministic migration, mixed-version activation barrier, or post-activation downgrade control is implemented.**

## 1. Scope and method

This audit reconciles the current branch against the existing lifecycle, migration, InitChain, runtime-configuration, release-governance and CometBFT profile audits. Inspected:

- `hnd_v02/abci_app.py`
- `hnd_v02/genesis.py`
- `hnd_v02/cometbft_v040_server.py`
- `docs/WP4_14_NETWORK_LIFECYCLE_UPGRADE_AND_RECOVERY_AUDIT_2026-11-05.md`
- `docs/WP4_14_LEGACY_COMPATIBILITY_AND_STATE_MIGRATION_MATRIX_2026-11-05.md`
- `docs/WP4_14_INITCHAIN_AND_CONSENSUS_PARAMETER_UPDATE_BOUNDARY_AUDIT_2026-11-05.md`
- `docs/WP4_14_RUNTIME_GENESIS_CONFIG_BINDING_AND_STARTUP_ENFORCEMENT_GAP_AUDIT_2026-11-05.md`
- `docs/WP4_14_CONFIG_V1_IMPLEMENTATION_SEQUENCE_AND_CHANGE_GATES_2026-11-05.md`
- `docs/WP4_14_RELEASE_GOVERNANCE_AND_BRANCH_PROTECTION_AUDIT_2026-11-05.md`
- `docs/WP4_14_COMETBFT_PROFILE_IDENTITY_BINDING_AND_STARTUP_FAIL_CLOSED_DECISION_AUDIT_2026-11-07.md`

No source, tests, workflows, Genesis files, deployment configuration, or release artifacts were changed. No new tests or network runs were initiated. Findings below distinguish directly observed implementation behavior from required future design.

## 2. Executive conclusion

The repository currently has several distinct version/identity concepts, but no complete network-wide upgrade state machine connecting them:

1. **Software release version** — the HND binary/source build identity and its dependency/build provenance.
2. **HND application protocol version** — deterministic transaction and state-transition rules, currently represented by the protocol configuration and Genesis manifest.
3. **HND durable-store schema version** — the serialization/recovery format for the persisted application state.
4. **CometBFT software/profile version** — the exact CometBFT source/build identity and its consensus-critical profile.
5. **Network Genesis identity** — the HND manifest/network identity plus the separately pinned CometBFT Genesis, validator-set and profile identities.

These are not interchangeable. A binary upgrade may be compatible without changing the HND protocol; a protocol change may require a deterministic state transition; a store schema change may require migration even when transaction semantics do not change; and a CometBFT upgrade can affect native consensus/database compatibility independently of HND's app protocol.

The inspected HND adapter currently:
- returns only the HND app hash from `InitChain`;
- returns transaction results and app hash from `FinalizeBlock`, without setting consensus-parameter or validator updates;
- has no observed upgrade-plan authorization, activation-height state machine, migration handler, validator readiness barrier, or mixed-version policy;
- rejects incompatible protocol/store identity rather than migrating it in place.

The existing legacy compatibility document explicitly treats legacy-to-Config-v1 conversion as a separately specified and approved operation, and recommends a fresh test network rather than silently reusing legacy state. That is a migration policy recommendation, not an implemented migration tool.

**Disposition:** protocol upgrade governance = NOT IMPLEMENTED; deterministic in-place state migration = NOT IMPLEMENTED; downgrade prevention at an activation boundary = NOT ESTABLISHED; release and profile identity enforcement = DESIGN/PINNING GAPS REMAIN.

## 3. Current implementation evidence

### 3.1 Protocol and store version checks are rejection checks, not upgrade support

The current application configuration and Genesis bind a protocol version. The application store records schema version, network ID, protocol version and the legacy Genesis hash. Restore validates those identity fields and rejects incompatible state.

This behavior is useful fail-closed compatibility checking. It does not define:
- which future protocol version is authorized;
- when it becomes active;
- how a validator proves readiness;
- how state is transformed;
- how validators running old and new binaries behave at the boundary; or
- whether an operator can safely recover after partial rollout.

A store schema version must not be treated as the protocol version. The schema can change for serialization/recovery reasons without changing transaction validity, and a protocol change can require new state semantics without being reducible to a file-format change.

### 3.2 ABCI update boundary

The inspected `HNDCometBFTv040Servicer.InitChain` passes `chain_id` and HND `app_state_bytes` to the application, then returns the HND app hash. It does not pass the full CometBFT InitChain consensus parameters, validator set or initial height into HND validation.

The inspected `FinalizeBlock` response sets `tx_results` and `app_hash`; it does not set `consensus_param_updates` or `validator_updates`.

CometBFT v0.40.0 has explicit ABCI response channels for initialization and runtime consensus-parameter/validator updates. HND not using those channels today means no HND-requested updates were observed in this adapter; it does **not** mean CometBFT consensus parameters are universally immutable. Any future use of those response fields is consensus-critical and requires an explicit versioned governance and test plan.

### 3.3 Existing migration policy is intentionally conservative

The legacy compatibility/state migration matrix requires source verification, a separately specified conversion, writing to a new destination, source/output hashes, invariant checks, deterministic restart verification and independent reproduction. It rejects silent balance/evidence/account-identity changes and does not authorize a migration utility.

It also distinguishes a fresh Config-v1 network from an in-place network upgrade. A fresh network must not claim consensus continuity with the legacy network. The document explicitly says a future in-place upgrade needs its own protocol specification and coordinated rollout.

### 3.4 Current release/identity controls do not yet establish upgrade authorization

The CometBFT profile audit recommends separate HND application-config and CometBFT profile digests, trusted pin distribution, exact CometBFT source/build identity, Genesis and validator-set commitments, and fail-closed startup before listeners/signing. Those are recommendations with owner approvals and implementation still pending.

A local configuration file or checksum stored beside the file it authenticates is not an independent authorization source. A branch name, release tag or successful CI run is not a signed upgrade authorization.

## 4. Required upgrade identity model

Every proposed upgrade must identify each layer separately and bind them in a signed, versioned release/upgrade manifest:

| Identity | Required contents | Must not be confused with |
|---|---|---|
| HND software release | source commit, reproducible build inputs, artifact digest, dependency lock/SBOM and build provenance | HND protocol version |
| HND application protocol | protocol version, deterministic rule-set identity, canonical config digest | binary semver or store schema |
| HND store schema | schema version, serialization/canonicalization rules, migration source/target versions | network height or protocol activation |
| CometBFT release/profile | exact source commit and binary digest, consensus-critical profile digest, supported native DB compatibility | HND application-config digest |
| Network identity | chain/network ID, HND Genesis component hash, aggregate network identity, validator-set artifact and CometBFT Genesis/profile identity | a local operator's config copy |
| Upgrade authorization | unique plan ID/hash, target identities, activation height, migration specification digest, authorized signer/governance decision | CI green status |

All digests must use documented canonical preimages and domain separation. The trust root that verifies the manifest must be provisioned independently of the files being authenticated.

## 5. Required deterministic activation protocol

The following is a design requirement, not current behavior.

### 5.1 Upgrade plan

An upgrade plan must be immutable once approved and contain at least:
- unique plan ID and plan format version;
- source and target HND software release identities;
- source and target HND protocol versions and config digests;
- source and target store schema versions;
- source and target CometBFT binary/profile identities;
- source and target Genesis/network identity rules;
- exact activation height (or a separately specified deterministic epoch mechanism);
- migration specification digest and expected pre/post-state commitments;
- validator-set/governance authorization reference;
- readiness evidence policy and minimum participation threshold;
- defined behavior for missing, late, incompatible or dissenting validators;
- recovery and halt conditions.

The plan hash must be computed from a canonical, domain-separated encoding. No values such as activation height, quorum/readiness threshold, delay, timeout or validator power are selected by this audit. They require explicit protocol-owner/governance decisions and security analysis.

### 5.2 Readiness and preflight

Before activation, each validator must independently verify:
1. signed plan and trust root;
2. target binary digest and build provenance;
3. HND application-config and protocol identity;
4. CometBFT source/build and profile identity;
5. target Genesis and validator-set identity;
6. migration code/specification digest and source-state preconditions;
7. durable signer anti-double-sign state and recovery readiness;
8. sufficient disk capacity, backup integrity and restore rehearsal;
9. deterministic dry-run output matching the plan's expected commitments.

Readiness must be represented by authenticated evidence tied to the exact plan hash and validator identity. A dashboard, self-reported version string, or unsigned local file is not sufficient.

### 5.3 Activation-height behavior

Define consensus behavior for every height around activation:
- before activation: only the old protocol rules are valid;
- activation boundary: all validators must derive the same transition inputs, migration result, new protocol identity and app hash;
- after activation: only the new rules are valid.

The protocol must specify whether the transition is performed inside deterministic block execution, by a separately committed transition record, or through another formally defined mechanism. It must not depend on wall-clock time, local rollout order, filesystem discovery, environment variables, or operator timing.

A validator that is not ready must not silently continue signing under old rules at or after activation. Its exact safe behavior (halt, reject signing, or another protocol-defined action) must be explicit and tested. No old/new binary combination may be assumed safe merely because both can parse the same store.

## 6. Mixed-version validator policy

Mixed-version operation is a major consensus risk whenever the versions can disagree on transaction validity, state transitions, app hashes, evidence handling, parameter interpretation or validator updates.

Required policy:
- **Before activation:** specify whether target binaries may run in compatibility mode and prove that they produce exactly the old protocol's deterministic outputs.
- **At activation:** reject or halt any validator that cannot verify and execute the authorized transition.
- **After activation:** old binaries must reject the new protocol state or stop signing; they must never silently fall back to old rules.
- **Different HND config digests:** reject before joining consensus.
- **Different CometBFT profile/binary identities:** reject unless a separately approved and proven compatibility matrix explicitly permits the combination.
- **Different store schema:** require the exact approved migration path; no implicit conversion on ordinary startup.
- **Unknown future versions or missing plan fields:** fail closed.

Do not invent a universal validator readiness percentage. Governance must decide the threshold in light of the consensus fault model and the network's validator-power rules. The implementation must bind the threshold and the eligible validator set into the approved plan so operators cannot change it locally.

## 7. Migration atomicity and recovery

A protocol upgrade that changes durable state needs a deterministic, idempotent migration specification.

Minimum requirements:
1. Validate source network, Genesis, protocol, config/profile digests, schema version, height and app hash before migration.
2. Verify the source state against the appropriate authenticated checkpoint/anti-rollback anchor.
3. Use a deterministic migration input and exact target software/schema identity.
4. Preserve all balances, supply invariants, nonces, transaction IDs, evidence records and other consensus-relevant data unless an explicitly authorized protocol rule defines a change.
5. Write to a new staged destination; never mutate the only source copy in place.
6. Record source digest, target digest, plan hash, migration implementation digest and expected resulting app hash.
7. Make migration idempotent or make a second invocation fail safely without altering the first valid output.
8. Use an atomic commit marker/state transition so ordinary startup rejects partial migration output.
9. Exercise crash injection before, during and after each durable write/rename/fsync boundary.
10. Retain source and target artifacts for forensic comparison and independent reproduction.
11. Require independent verification of the output and a clean restart from the migrated store before activation.
12. Define what happens when the anti-rollback anchor is ahead of the available state, unavailable, or disagrees with the migration result.

A checksum alone is not proof of authenticity or freshness. Restoring an older but internally valid store must not be accepted as a valid post-upgrade state.

## 8. Rollback, downgrade and emergency recovery

Use precise terminology:

- **Software rollback before activation:** may be allowed only if the old binary is still compatible with the unchanged committed protocol and store state, and the signed release policy authorizes it.
- **Test-network reset:** deleting a disposable test network and recreating it from its pinned Genesis is not a protocol rollback.
- **Post-activation downgrade:** starting an old binary against state committed under new rules is prohibited unless a separately specified and authorized recovery protocol proves compatibility.
- **Consensus-state rollback:** reverting committed chain state to an earlier height or restoring a stale CometBFT/HND data directory is not an ordinary software rollback and must not be presented as one.
- **Emergency fork/recovery:** any change to already committed protocol rules requires an explicit governance decision, a separately pinned recovery identity, deterministic state/replay rules, validator coordination and independent review.

The safe default after an ambiguous or partially committed upgrade is to halt affected validators rather than create two groups signing under different rules. Never automatically downgrade protocol state to make an old binary start.

CometBFT native database compatibility, block-store replay, application replay, snapshots and state sync must be assessed against the exact pinned CometBFT source/build. HND's current ABCI snapshot methods do not implement application snapshot transfer; they return no snapshots, reject offered snapshots and abort chunk application. Do not claim snapshot-based upgrade recovery exists.

## 9. Governance and release evidence

Before an upgrade can be scheduled:
- record the owner/governance decision and its authority;
- publish the immutable upgrade plan and its canonical hash;
- require two-person approval for release/activation authorization, with roles and key custody defined;
- sign a release manifest binding source commit, artifact digest, SBOM, build provenance, HND protocol/config identity, store schema, CometBFT profile, Genesis, validator set and activation metadata;
- distribute trust pins independently and document key rotation/revocation;
- publish operator runbooks, readiness evidence requirements, backup/restore drills, monitoring and incident escalation;
- define who may pause before activation and who may authorize emergency recovery after activation.

CI success is evidence about the workflow and exact tested commit only. It is not governance approval, artifact provenance by itself, validator readiness, production signing approval or authorization to issue/distribute tokens.

## 10. Required negative and integration test matrix

These are required acceptance tests, **not tests currently demonstrated as passing**.

| ID | Scenario | Required result |
|---|---|---|
| UPG-01 | Alter one byte of signed plan or plan hash | Verification fails before startup/signing |
| UPG-02 | Unauthorized signer or revoked trust root | Plan rejected |
| UPG-03 | Target binary has same version string but different digest | Preflight rejects |
| UPG-04 | HND protocol/config digest differs on one validator | Validator rejected before consensus |
| UPG-05 | CometBFT profile or validator-set artifact differs | Validator rejected before consensus |
| UPG-06 | Old binary starts at/after activation height | Refuses signing and does not execute old rules |
| UPG-07 | New binary starts before authorized activation | Executes only the specified pre-activation rules |
| UPG-08 | Validator misses activation height or readiness threshold is unmet | Deterministic, documented halt/rejection behavior |
| UPG-09 | Duplicate, conflicting, late or unauthorized upgrade plan | Rejected deterministically |
| UPG-10 | Two validators run old/new versions around activation | No divergent accepted block/app hash; incompatible node stops |
| UPG-11 | Migration run twice | Same deterministic output or safe explicit already-migrated rejection |
| UPG-12 | Crash at every migration write boundary | No partial output accepted as committed state |
| UPG-13 | Source store is stale but internally valid | Independent freshness check rejects it |
| UPG-14 | Migration source height/hash/config/profile differs from plan | Migration aborts without altering source |
| UPG-15 | Migration changes balances, supply, nonces, IDs or evidence unexpectedly | Independent invariant verification fails |
| UPG-16 | Old store schema or unknown future schema presented | Explicit migration required / fail closed |
| UPG-17 | CometBFT DB opened by unsupported target version | Startup rejects or follows documented upstream-supported migration |
| UPG-18 | Restore from backup before and after activation | Only plan-authorized, height-consistent recovery accepted |
| UPG-19 | Software rollback attempted after protocol state committed | Rejected unless explicit compatible recovery authorization exists |
| UPG-20 | CI green but release manifest unsigned or governance approval absent | No activation authorization |

The matrix must run across at least four independent validator instances with deliberately mismatched versions, configs, profile pins, migration states and restart timing. Preserve exact logs and resulting commitments.

## 11. CI evidence and its limits

At audit time, the latest observed workflow run was:

- Run: [42299736603](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42299736603)
- Branch: `phase-0.2-planning`
- Head commit: `261cbeccea5cc593e58df7d894a7339e827a4ad2`
- `hnd-v02-tests`: success
- `cometbft-single-node-smoke`: success

Both jobs completed successfully on the exact baseline commit. The CometBFT job included the existing single-node and four-validator smoke, equivocation/evidence integration, remote-signer authentication/recovery and anti-double-sign persistence steps.

This run does not show UPG-01 through UPG-20 were implemented or executed. The workflow has no demonstrated activation-height, mixed-binary protocol migration or post-activation downgrade matrix in the evidence inspected here. No CI result for a future report commit is claimed by this document.

## 12. Decision register

| Decision | Recommendation | Status |
|---|---|---|
| Separate software, HND protocol, store schema and CometBFT profile identities | Mandatory | Design requirement; implementation not established |
| Signed immutable upgrade plan and independent trust root | Mandatory | Owner/governance approval pending |
| Activation height and exact transition semantics | Mandatory before any in-place upgrade | Not specified/implemented |
| Validator readiness threshold and fault-model mapping | Mandatory; do not guess a value | Owner/governance decision pending |
| Mixed-version and old-binary behavior | Mandatory | Not implemented |
| Deterministic migration specification and atomic recovery | Mandatory if state changes | Not implemented |
| Post-activation downgrade prohibition and emergency fork procedure | Mandatory | Policy not enforced in code |
| CometBFT native DB/replay compatibility matrix | Mandatory for CometBFT upgrades | Exact-version independent review required |
| UPG-01–UPG-20 tests | Mandatory acceptance evidence | Not demonstrated |

## 13. Final gate

**Decision: NOT APPROVED for in-place protocol upgrade, post-activation rollback/downgrade, public-network activation, production signing or token issuance.**

The safe next sequence is:
1. obtain explicit owner/governance decisions on the protocol transition model and authority;
2. freeze the release/upgrade manifest and canonical plan-hash specification;
3. freeze migration and recovery semantics, including the activation-height state machine;
4. review exact CometBFT v0.40.0 native DB/replay compatibility and any target-version change;
5. implement only after explicit source/test/workflow authorization;
6. execute the full negative and four-validator mixed-version matrix;
7. obtain independent security review and signed release approval.

This report is documentation-only. It does not authorize source changes, tests/workflow changes, a protocol activation, migration of live state, public launch, production signing or token distribution.
