# WP4.14 — Network Lifecycle, Upgrade and Recovery Audit — 2026-11-05

**Target branch:** `phase-0.2-planning`  
**Baseline commit reviewed:** `d62d84daeb042513e01cbf3daae015060e0328e0`  
**Audit type:** static source/test review plus inspection of existing CI evidence  
**Disposition:** **NOT APPROVED — restart recovery is demonstrated for bounded test cases; upgrade governance and rollback-resistant application recovery are not established.**

## 1. Scope and method

Reviewed the current branch source and tests, including:

- `hnd_v02/abci_app.py` — InitChain, Info, durable application store, Commit and restore.
- `hnd_v02/ledger.py` — ledger snapshot validation and reconstruction.
- `hnd_v02/transaction.py` — ProtocolConfig and transaction protocol version validation.
- `hnd_v02/cometbft_v040_server.py` — ABCI adapter, CLI startup and snapshot ABCI methods.
- `hnd_v02/recovery_controls.py` — bounded readiness and replica-convergence controls.
- `scripts/cometbft_v040_single_node_smoke.py`
- `scripts/cometbft_v040_four_validator_network_smoke.py`
- `scripts/cometbft_v040_four_validator_genesis_preflight.py`
- `tests/test_v02_abci_app.py`
- `tests/test_v02_recovery_controls.py`
- `tests/test_v02_four_replica_state_convergence.py`
- `.github/workflows/hnd-v02-tests.yml`

No source, tests, workflow, Genesis, or deployment configuration was changed. No new test execution was initiated as part of this static audit. Existing CI was inspected separately.

## 2. Executive assessment

The repository has a meaningful local application restart design:

- Recovery mode can require an existing application-state file.
- The persisted store binds network ID, protocol version, Genesis hash, committed height, ledger snapshot, evidence journal and app hash under a checksum.
- Restore reconstructs the ledger from Genesis by replaying the complete transaction history and verifies balances, nonces, accepted transaction IDs and state hash.
- The four-validator integration harness stops one validator and its ABCI process, preserves the local application state and CometBFT node identity files, restarts them, and checks recovery and subsequent convergence.

Those controls do **not** yet establish a complete network lifecycle protocol:

1. The HND application store has no independently trusted monotonic anti-rollback anchor. Its SHA-256 store checksum detects accidental modification, not replacement with an older, internally valid store.
2. The HND process reports its local durable height and app hash through ABCI Info. The production server's startup path does not itself compare that tuple against a separately authenticated CometBFT block-store checkpoint before opening the ABCI listener.
3. There is no implemented protocol-version activation height, coordinated upgrade proposal, upgrade handler, or state migration path.
4. The ABCI snapshot methods explicitly return no snapshots / reject offered snapshots / abort chunk application. HND's own ledger snapshot is a replay-verified local state format, not CometBFT state sync.
5. A protocol-version mismatch against an existing HND store is rejected, but that is a fail-closed incompatibility, not an upgrade mechanism.

**Overall:** local crash/restart regression = PASS for the enumerated disposable CI scenario; production rollback resistance = NOT ESTABLISHED; coordinated protocol upgrade = NOT IMPLEMENTED; CometBFT snapshot state sync = NOT IMPLEMENTED.

## 3. Positive evidence and bounded passes

### LC-R1 — Durable application-store recovery checks

**Disposition: PASS for integrity and identity checks implemented.**

The store records `schema_version`, `network_id`, `protocol_version`, `genesis_hash`, `last_committed_height`, `ledger_snapshot`, `evidence_journal`, `app_hash`, and `store_hash`.

On load, the application checks the exact schema and store version, verifies the checksum, rejects a network/protocol/Genesis mismatch, validates height and app-hash fields, restores the ledger by replaying history from Genesis, revalidates the evidence journal, and recomputes the application hash.

Relevant tests cover:
- truncated state file rejection;
- wrong network rejection;
- wrong Genesis rejection;
- wrong protocol version rejection (see current store-load code; no dedicated version-migration test);
- corrupted ledger snapshot and app-hash rejection;
- tampered recovery height rejection through the store checksum;
- missing state rejection when `require_existing_state=True`;
- restart restoration of committed height and app hash.

### LC-R2 — Restart discards uncommitted application state

**Disposition: PASS for the tested local application behavior.**

The application only persists a finalized candidate on Commit. A test finalizes a block without committing, constructs a new application instance from the same file, and confirms the restarted instance remains at the prior committed height and balance.

A separate failure-injection test simulates process loss immediately after the atomic file replacement and confirms that a new instance reads the committed height and hash from the replaced file. The test is a process-level simulation, not a power-loss or storage-device fault test.

### LC-R3 — One-validator outage/restart and four-validator convergence

**Disposition: PASS for the existing disposable harness scenarios; not a production network guarantee.**

The four-validator smoke harness:
- checks unique HND state paths;
- captures validator 4's CometBFT status, ABCI Info, balances, application-state file digest, consensus identity and P2P identity;
- stops the remote signer (when enabled), CometBFT node and ABCI process and confirms process exit;
- checks the durable HND state file remains unchanged while offline;
- restarts the HND ABCI process with `--recovery`;
- verifies the application state digest and validator identities;
- restarts CometBFT and waits for RPC readiness;
- verifies the recovered HND height is not below its pre-stop height, the app hash equals the captured pre-stop app hash, and balances are unchanged;
- waits for catch-up and checks all four validator fingerprints for matching height, block hash and application hash.

The harness also covers signer outage/recovery and existing partition/reconnection scenarios. These are bounded local crash-stop integration tests using temporary homes and disposable keys.

### LC-R4 — Recovery timeout and divergence detection

**Disposition: PASS for the deterministic unit fixtures.**

The recovery-control tests verify that a bounded readiness timeout terminates a fixture process without changing a caller-owned state file. They also verify that height, block-hash and application-hash divergence is rejected by the comparison helper.

These tests do not independently prove that every possible production restart topology or network partition is safe.

## 4. Findings and gaps

### LC-F1 — Application-state rollback is not protected by an independent monotonic anchor

**Severity: Critical for production recovery assurance.**

The HND store checksum is an unkeyed SHA-256 digest over the serialized store payload. It protects against accidental corruption and detects edits that do not also recompute the checksum. It does not authenticate freshness.

An older, internally valid application-state file from the same network, protocol version and Genesis can be restored together with its matching checksum. The HND loader verifies internal consistency, but it has no independently persisted high-water mark or trusted monotonic counter proving that the loaded committed height is at least the highest previously finalized height.

The remote-signer anti-double-sign recovery controls are a separate subsystem. Their test-orchestrator digest checks do not provide an independent anti-rollback anchor for the HND application-state file.

**Impact:** replacement of the HND application store with an older valid copy is not rejected by an HND-specific freshness control. If the CometBFT home/block store is also rolled back or replaced, this application layer does not independently detect that coordinated rollback. Do not infer that CometBFT consensus would accept an arbitrary fork; this finding is specifically the absence of an HND authenticated freshness anchor.

**Required:** bind each committed application height and app hash to a separately protected monotonic trust anchor or equivalent rollback-resistant mechanism. Recovery must compare the loaded store against that anchor before serving ABCI requests. Test old-but-valid store substitution, replacement of both application and node data directories, crash boundaries, and anchor unavailability. Define safe recovery if the anchor is ahead of the local store.

### LC-F2 — HND startup does not independently reconcile its restored height/hash with an authenticated CometBFT checkpoint before listening

**Severity: High.**

The HND `Info` response exposes the local durable `last_committed_height` and `last_block_app_hash`. The four-validator test harness explicitly compares CometBFT status and HND Info before shutdown and after restart/catch-up. However, the HND server CLI constructs and loads the application, then starts the ABCI gRPC listener; there is no HND startup argument or authenticated checkpoint input for the expected CometBFT height, block hash and app hash.

CometBFT owns its native block store and consensus recovery. Its handshake/replay behavior must be assessed against the exact pinned CometBFT v0.40.0 source and configuration; it must not be conflated with an HND application-level anti-rollback mechanism. This audit does not claim that CometBFT will accept an application-height mismatch or that an arbitrary stale node can finalize a fork.

**Impact:** the HND application by itself does not establish the cross-store recovery invariant at its own startup boundary. Current integration evidence shows that the controlled harness checks the invariant after the processes restart; it is not a production startup attestation or independently authenticated checkpoint.

**Required:** define a documented, fail-closed startup reconciliation contract for CometBFT native state and HND application state. Record expected height, block ID/hash and app hash from a trusted local CometBFT store or protected checkpoint; reject unsafe ahead/behind/mismatched combinations before enabling normal service. Add process-level tests for app-store rollback, app-store-ahead, CometBFT-store rollback, height match with app-hash mismatch, and interrupted handshake/replay.

### LC-F3 — No coordinated protocol upgrade or state migration mechanism

**Severity: Critical for any protocol-version change after launch.**

The current protocol version is a local `ProtocolConfig` value and is also part of the Genesis manifest and transaction envelope. The application store records the protocol version and rejects a store whose version differs from the current configuration. Ledger restore likewise requires the snapshot protocol version to match the configured version.

No inspected source implements:
- an upgrade plan or governance authorization;
- an activation height or agreed upgrade time;
- a validator-wide software/config readiness barrier;
- a version-transition state machine;
- an upgrade handler;
- a deterministic state migration;
- a dual-version compatibility window;
- rollback rules after activation;
- an upgrade-specific four-validator test.

**Impact:** changing the configured protocol version against an existing store is rejected as a mismatch; it does not migrate state. Changing Genesis to a new protocol version also changes the network's pinned identity. Simply deploying new binaries or changing CLI flags cannot safely coordinate a network-wide protocol transition.

**Required:** define a versioned upgrade protocol with an authenticated upgrade plan, activation height, required software/config digest, deterministic migration, validator readiness checks, explicit pre-activation abort behavior and post-activation rollback policy. A node on the wrong version must fail closed rather than silently continue with different transaction rules.

### LC-F4 — Snapshot state sync is not implemented by the HND ABCI adapter

**Severity: High for large networks and disaster recovery.**

The HND CometBFT ABCI adapter currently:
- returns an empty snapshot list;
- rejects offered snapshots;
- returns empty data for snapshot chunk loading;
- aborts snapshot chunk application.

Separately, `HNDLedger.restore` rebuilds the ledger from Genesis by replaying every transaction in the stored history and verifies the resulting balances, nonces, accepted set and state hash. This is a local application-store restore format, not a CometBFT snapshot provider/consumer and not CometBFT state sync.

**Impact:** the current documented recovery path is dependent on local durable application state plus CometBFT's native block-store recovery/replay. There is no HND-provided snapshot state-sync path for a fresh or rebuilt validator. Full-history replay also has a scaling cost as transaction history grows.

**Required:** either implement and test a versioned, authenticated snapshot protocol (including app hash, height, Genesis/config identity, chunk integrity and deterministic restore), or explicitly constrain the supported recovery model to retained local state and full replay. Do not describe the current ledger JSON snapshot as network state sync.

### LC-F5 — HND recovery checksum does not bind all consensus-critical runtime configuration

**Severity: High; overlaps the prior cross-validator config audit.**

The store binds network ID, protocol version and Genesis hash, but not a complete deterministic application-config digest. In particular, the previously audited `max_amount` setting is supplied independently on the command line and is not part of the current Genesis identity/store checksum.

A restart with a changed protocol version is rejected by the stored protocol-version check. A restart with the same network/protocol/Genesis but a different unbound acceptance parameter such as `max_amount` is not detected by the current store identity fields.

**Required:** close the config identity gap described in `WP4_14_CROSS_VALIDATOR_APPLICATION_CONFIG_CONSISTENCY_AUDIT_2026-11-05.md` before treating a recovered node as protocol-equivalent to its peers.

### LC-F6 — Test evidence does not cover multi-validator mixed-version upgrade or coordinated rollback

**Severity: High.**

The four-validator harness demonstrates one-validator crash/restart with the same code/config and checks convergence. The tests do not establish behavior when:
- multiple validators are offline simultaneously and return at different heights;
- validators return with different HND protocol versions;
- validators return with identical Genesis but different consensus-critical application config;
- one or more validators have an older valid HND store;
- the HND application store and CometBFT native store are restored from inconsistent backup points;
- an upgrade activates while validators are partitioned or offline.

**Required:** add deterministic four-validator negative integration scenarios for mixed-version startup, stale-state replacement, mismatched app/config digests, staggered restart across an activation height, and recovery from mismatched backup checkpoints. Record the exact observed CometBFT and HND heights/hashes for each validator.

## 5. CometBFT and HND responsibility boundary

| Area | HND implementation evidence | What this does not prove |
|---|---|---|
| Consensus block ordering and commit | Delegated to CometBFT | HND does not independently implement BFT consensus |
| HND transaction/state validation | Deterministic application logic and app hash | Identical runtime config across production nodes is not yet authenticated |
| Local application restart | Durable HND store plus replay-verified ledger restore | No independent freshness anchor against valid older-store replacement |
| CometBFT native restart/catch-up | Exercised by disposable integration harness | Not a general proof for all backup/restore or multi-node outage cases |
| Snapshot state sync | HND ABCI snapshot methods reject/abort | No HND snapshot distribution or restore implementation |
| Protocol upgrade | No activation/migration handler found | No safe network-wide version transition established |

## 6. Required acceptance tests

The following tests are required before lifecycle/upgrade readiness can be approved:

- **LC-T01 — Old valid application store:** restore a prior valid store with a valid checksum after a higher height was committed; require an independent freshness check to reject it.
- **LC-T02 — App ahead/behind:** exercise HND height below and above CometBFT native height and verify the documented fail-closed/replay policy.
- **LC-T03 — Same-height app-hash mismatch:** require rejection before normal service when HND and CometBFT checkpoints disagree.
- **LC-T04 — Coordinated backup rollback:** restore HND and CometBFT directories from different backup points; require safe detection and explicit recovery procedure.
- **LC-T05 — Mixed protocol versions:** start four validators with one old-version node and prove deterministic rejection or the explicitly authorized compatibility behavior.
- **LC-T06 — Upgrade activation:** test agreed activation height, exact software/config digest, deterministic migration and all-validator convergence.
- **LC-T07 — Offline validator across upgrade:** keep one or more validators offline across activation; verify they cannot rejoin with stale software/state and silently participate.
- **LC-T08 — Snapshot state sync:** if supported, test snapshot offer/list/chunk/apply, integrity failures, wrong Genesis/config, wrong app hash and interrupted chunk transfer. If unsupported, document the retained-state/full-replay recovery limitation as a formal operational constraint.
- **LC-T09 — Rollback/abort semantics:** test failure before activation, during migration, after activation, and when the independent trust anchor is unavailable.
- **LC-T10 — Four-node recovery matrix:** test 1/4, 2/4 and 3/4 stopped validators, staggered restart, state checkpoint mismatch and mixed software versions in disposable homes.

Each test must capture the workflow URL, tested commit, per-validator CometBFT height/block ID/app hash, HND Info height/app hash, software/config identity and explicit rejection/success markers.

## 7. Existing CI evidence reviewed

The latest workflow visible at audit time was:

- [Workflow run 42013230251](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42013230251)
- Tested commit: `d62d84daeb042513e01cbf3daae015060e0328e0`
- Both jobs completed successfully: `hnd-v02-tests` and `cometbft-single-node-smoke`.
- The CometBFT integration job completed the single-node smoke, four-validator Genesis preflight, four-validator network smoke, external signer outage/recovery, and authenticated Noise signer outage/recovery steps.

This CI run validates the current branch's existing code and tests. It does not validate this newly written audit report as a software test, and it does not cover the missing negative tests listed above.

## 8. Gate disposition

| Gate | Result |
|---|---|
| Local HND store integrity and replay validation | PASS for implemented checks |
| Missing-state fail-closed recovery mode | PASS for implemented behavior |
| Local uncommitted-state discard on restart | PASS for tested behavior |
| One-validator restart and four-validator catch-up | PASS for existing disposable CI scenario |
| Timeout and convergence negative controls | PASS for unit fixtures |
| Independent HND application anti-rollback anchor | NOT IMPLEMENTED |
| Startup cross-check against authenticated CometBFT checkpoint | NOT ESTABLISHED |
| Coordinated protocol upgrade / activation height | NOT IMPLEMENTED |
| Deterministic state migration | NOT IMPLEMENTED |
| HND ABCI snapshot state sync | NOT IMPLEMENTED |
| Multi-validator mixed-version/rollback recovery matrix | NOT TESTED |
| Production lifecycle and recovery readiness | NOT APPROVED |

## 9. Limitations and non-claims

- This is a static source/test audit with inspection of existing CI metadata; no new network was launched and no new test was executed for this report.
- Existing integration evidence uses disposable local validators, temporary identities and test state.
- No claim is made that CometBFT upstream lacks its own handshake, block-store replay, or consensus safety mechanisms. Those mechanisms are separate from HND's application-store freshness and upgrade governance.
- No claim is made that an arbitrary stale validator can force a fork or that CometBFT will accept mismatched application state. The demonstrated gap is that HND itself has no independent monotonic application-state anchor or coordinated upgrade protocol.
- A replay-verified HND ledger snapshot is not a CometBFT state-sync snapshot.
- No production backup/restore, power-loss durability, independent security review, production key custody, legal compliance, or public-release approval is established.

**Final decision:** retain the existing bounded restart/recovery regression as a useful PASS. Keep the overall network lifecycle, rollback-resistance, protocol-upgrade and disaster-recovery gates OPEN / NOT APPROVED until LC-T01–LC-T10 are implemented and evidenced, with the config-identity gap closed as well.
