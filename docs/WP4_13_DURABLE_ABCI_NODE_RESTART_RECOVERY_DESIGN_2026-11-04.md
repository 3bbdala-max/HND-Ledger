# HND v0.2 — WP4.13 durable ABCI state and CometBFT node restart recovery

**Date:** 2026-11-04  
**Workstream:** WP4.13 — crash/restart durability and replay verification  
**Branch:** `phase-0.2-planning`  
**Pinned consensus engine:** CometBFT v0.40.0  
**Status:** Core restart/recovery integration and CI passed; complete negative-control matrix remains open  
**Safety boundary:** Disposable loopback-only four-validator testnet; temporary keys and state only

## 1. Objective

Strengthen the existing four-validator restart scenario by proving, with explicit before/after evidence, that a stopped validator's HND ABCI application recovers its exact committed state from its own durable state file, and that the restarted CometBFT node catches up through normal block replay without silently resetting or diverging the application state.

The existing four-validator harness already stops validator 4 and its ABCI process, allows the remaining three validators to commit, restarts the ABCI app and CometBFT node, and checks four-node convergence. WP4.13 is not a claim that this lifecycle is missing. It adds stricter durability assertions and fail-closed negative controls around that already passing scenario.

## 2. Required pre-stop evidence

Immediately before stopping validator 4 and its ABCI app, record:

- validator 4's CometBFT latest height, block hash, and app hash;
- HND ABCI `Info` last committed height and 32-byte app hash;
- canonical queried balances for the funded sender and recipient, plus total supply;
- a cryptographic digest (SHA-256) of the exact HND durable state file;
- the exact CometBFT home, validator identity, HND state-file path, and signer state/key paths used by validator 4.

The harness must prove that validator 4 has its own state file and that no other replica points to that path. Capture values only from the disposable test environment; never upload key material or raw private state as artifacts.

## 3. Restart sequence and assertions

1. Stop validator 4's signer as required by the selected signer mode, then stop its CometBFT process and HND ABCI process. Confirm each process has exited; do not treat a requested termination as proof of exit.
2. Keep validators 1–3 and their HND applications live. Commit at least one additional block and record the new quorum-side height/hash.
3. Restart HND ABCI application 4 with the exact same manifest, genesis hash, network/protocol settings, and exact same durable state-file path. Do not delete, rename, regenerate, or initialize a replacement state file.
4. Before restarting CometBFT node 4, query its ABCI `Info` and account state. Require exact equality with validator 4's pre-stop HND committed height, app hash, balances, and total supply. Require the state-file SHA-256 to match the pre-stop digest if the application format is expected to remain byte-identical on clean process shutdown; if normal metadata changes are expected, document the exact canonical-state comparison instead and do not weaken the app-hash assertion.
5. Restart CometBFT node 4 with the same home directory, P2P identity, validator identity, and persistent peer configuration. If a remote signer is used, restart it using the same persisted anti-double-sign state and stable authorized transport identity; require a fresh post-restart connection marker.
6. Wait for node 4 to catch up through CometBFT's normal consensus/block replay. Do not use fabricated height changes, direct application-state copying, or an unverified snapshot path.
7. Require all four nodes to converge on height and block hash, and all four HND apps to agree on 32-byte app hash, balances, total supply, and application committed height.
8. Confirm the restarted validator's HND app hash equals the three-node quorum's app hash and the application state restored before CometBFT node restart has advanced only through committed replay.

## 4. Negative controls

Add isolated tests or harness modes that must fail closed when:

- the HND state file is absent or truncated before application startup;
- the restarted app is pointed at a fresh/alternate state path;
- the restarted app receives a mismatched Genesis hash or network ID;
- the restarted node uses a different validator identity or chain Genesis;
- the persisted remote-signer anti-double-sign state is missing or replaced;
- the restarted node fails to catch up within the bounded timeout;
- the recovered application hash or account state differs from the quorum.

Negative controls must use disposable temporary directories and keys. A failure must not be converted into a pass by resetting the state, recreating keys, or silently reinitializing the application.

## 5. CI integration and acceptance

Wire the strengthened restart assertions into the existing pinned CometBFT four-validator CI path, including the Unix-socket and authenticated Noise remote-signer variants where applicable.

Accept WP4.13 only when a complete workflow run succeeds and its logs establish:

- explicit pre-stop CometBFT and HND height/hash/app-hash evidence;
- proof that the ABCI process and CometBFT node process actually exited;
- exact HND durable-state recovery before node restart;
- normal CometBFT restart and catch-up using the original node home and validator identity;
- four-way post-catch-up block/app-hash and account-state convergence;
- fail-closed behavior for the required negative controls;
- cleanup of all temporary processes, keys, sockets, and state.

Record the workflow URL, tested commit SHA, observed heights/hashes, and result markers in this document and `docs/PHASE_0.2_PLAN.md`.

## 6. Scope and non-claims

- This remains a bounded local crash/restart/replay regression, not proof of arbitrary Byzantine fault tolerance or global network safety/liveness.
- It does not implement snapshot state sync; normal CometBFT block replay is the tested recovery path.
- It does not establish production database durability, filesystem crash consistency under power loss, backup/restore guarantees, or rollback-resistant key custody.
- It does not approve Unix sockets, TCP, or Noise as a production signer transport.
- Production HSM/KMS or offline key custody, identity lifecycle, backup/restore, operational controls, independent security review, governance, and jurisdiction-specific legal review remain separate gates.
- No public release, token sale, exchange listing, or real-value activity is authorized.

---
This document defines the WP4.13 test gate only. Passing it will not certify production readiness.


## 7. Implementation and CI results — 2026-11-04

The core restart/recovery implementation is now exercised by the pinned CometBFT v0.40.0 workflow.

- Full workflow [41858224733](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41858224733) completed successfully on commit `efa81f43238cc060542c1fd1375f707adee6fc06`. Both `hnd-v02-tests` and `cometbft-single-node-smoke` jobs completed with success.
- The HND isolated test suite reported **143 tests, all passing**.
- The four-validator harness recorded pre-stop CometBFT/HND state, the durable state-file SHA-256, confirmed actual ABCI and CometBFT process exit, restarted the HND app from the same state file, restarted CometBFT with the original node home and identities, and verified normal catch-up and four-replica convergence. Explicit markers were observed in the earlier complete recovery run [41852320612](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41852320612): `HND_WP4_13_PRE_RESTART_EVIDENCE`, `HND_WP4_13_PROCESSES_STOPPED`, `HND_WP4_13_DURABLE_ABCI_RECOVERY_OK`, and `HND_WP4_13_COMETBFT_NODE_RESTART_CATCHUP_OK`.
- The latest full workflow additionally passed the four-validator private network regression, external Unix remote-signer outage/recovery, authenticated Noise remote-signer outage/recovery, and the two missing anti-double-sign-state negative probes. The Unix probe emitted `COMETBFT_V040_REMOTE_SIGNER_MISSING_STATE_REJECTED`; the Noise missing-state probe step completed successfully.
- The HND persistence tests include rejection of truncated persisted state and state files whose network ID or Genesis hash does not match, alongside the existing store-integrity and restart checks.
- The 3/1 and 2/2 partition/reconnection tests completed successfully in the latest run.

### Acceptance boundary

**Core WP4.13 restart/recovery integration: passed for the scenarios exercised above.** Do not interpret this as closure of every negative control in Section 4. Additional explicit coverage remains required for alternate/replaced signer-state files, validator-identity mismatch on restart, bounded recovery-timeout behavior, and deliberately induced post-recovery application divergence as distinct WP4.13 negative cases. Existing unauthorized Noise peer rejection, vote-withholding, and WP4.12 state-divergence tests are related evidence, but are not substitutes for all of those exact recovery-specific cases.

The result remains a loopback-only, disposable CI test. It does not prove power-loss durability, production backup/restore, snapshot state sync, production key custody, or general Byzantine safety/liveness. No production transport or public release is approved.
