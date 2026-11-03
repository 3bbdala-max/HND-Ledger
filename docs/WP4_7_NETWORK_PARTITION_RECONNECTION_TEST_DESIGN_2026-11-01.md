# WP4.7 — Network Partition and Reconnection Test Design

**Status:** Implemented; local CI partition and reconnection scenarios passed  
**Target branch:** `phase-0.2-planning`  
**Consensus engine:** CometBFT v0.40.0  
**Predecessor:** WP4.5 private four-validator crash-stop integration; WP4.6 Genesis identity negative tests

## 1. Purpose

The existing four-validator harness proves that three validators can continue after one validator process is stopped, and that the stopped validator can restart and catch up. It does not simulate a live network partition. WP4.7 defines a separate test gate for message isolation while all four validator processes remain alive.

The test must distinguish consensus safety (no conflicting commits) from liveness (a quorum can continue committing) and from eventual convergence after communication is restored.

## 2. Voting-power expectations

The test network has four validators with voting power 10 each, total 40. A commit requires strictly more than two-thirds of total voting power: at least 30.

- A 3/1 partition: the three-validator side has 30 voting power and may continue committing; the isolated validator has 10 and must not independently commit.
- A 2/2 partition: each side has 20 voting power and neither side has a quorum; neither side may commit new blocks while the partition is effective.
- After connectivity is restored, all four nodes must converge on one committed chain and identical HND application state.

These are expected quorum properties to test against the pinned CometBFT version, not a substitute for the observed test results.

## 3. Isolation mechanism gate

Do not simulate a partition by terminating a validator process: that repeats the existing crash-stop test.

Before running consensus assertions, the harness must prove that its isolation mechanism blocks validator-to-validator P2P traffic in both directions while:
- all four CometBFT processes remain alive;
- all four HND ABCI application processes remain alive;
- local RPC and ABCI health checks remain reachable;
- traffic from the isolated node to each peer and from each peer to the isolated node is blocked;
- the harness can reliably remove the block and verify P2P reconnection.

The implementation should use a disposable, reversible network filter or a dedicated TCP relay/proxy topology. It must probe the runner's capabilities first, fail closed if isolation cannot be established, and remove all rules/processes in a guaranteed cleanup path. Never silently downgrade a requested partition test to a process-stop test.

If the CI runner cannot provide a reliable, auditable bidirectional isolation primitive, keep this WP as design-only and use a dedicated test environment rather than reporting a false pass.

## 4. Required scenarios

### A. 3/1 partition

1. Start four independent validators and four independent HND applications from one shared, validated Genesis.
2. Wait for all four nodes to converge at the same height and block hash.
3. Isolate validator 4 bidirectionally from validators 1–3 at the P2P layer. Keep all processes alive.
4. Verify the partition is effective using connection/peer evidence, not only a successful firewall command.
5. Submit a valid signed transfer to the connected three-validator side.
6. Require validators 1–3 to commit it and agree on height, block hash, balances, and app hash.
7. Require validator 4 not to commit beyond the pre-partition height while isolated; query its local committed state and verify it has not applied the transfer.
8. Restore connectivity. Require validator 4 to catch up and all four nodes to converge on the same block and HND state.

### B. 2/2 partition

1. Begin from a fully converged four-validator state.
2. Partition validators into groups {1,2} and {3,4}, blocking P2P traffic bidirectionally across groups while preserving traffic within each group.
3. Confirm no cross-group P2P communication remains.
4. Record each group's height and block hash. Wait longer than several normal block intervals.
5. Require neither group to commit a new block without quorum. If either side advances, capture logs and fail the test for investigation; do not mask the result.
6. Restore all cross-group connectivity.
7. Require the four validators to converge to one height and block hash, with matching HND application hashes and balances.

### C. Cleanup and failure behavior

- Every firewall rule, proxy, subprocess, temporary key, and temporary state file must be scoped to the test and removed in a `finally` cleanup path.
- A timeout, unexpected commit, missing peer evidence, or failed cleanup is a test failure.
- Retain only sanitized CI logs; never upload validator private keys or state directories.
- Include a bounded timeout and diagnostic logs for each node and each partition transition.

## 5. Acceptance evidence

A passing report must include:
- exact tested commit and pinned CometBFT version;
- evidence all four validators and ABCI applications stayed alive during isolation;
- evidence of the effective bidirectional partition and its removal;
- before/during/after heights and block hashes for each partition group;
- transaction inclusion and state agreement in the 3/1 scenario;
- no new commits in either 2/2 group during the observation window;
- successful post-reconnection convergence and identical HND app hashes;
- proof all temporary network rules/proxies were removed.

A workflow merely starting four nodes or successfully adding firewall rules is not sufficient evidence.

## 6. Security limits

These tests exercise selected network-partition behaviors under a controlled local topology. They do not prove safety under arbitrary Byzantine behavior, malicious validator signatures, censorship, equivocation, key compromise, DDoS, Internet-scale packet loss, or software vulnerabilities. They are not an independent security audit or production-readiness certification.

## 7. Decision

The relay-based isolation topology has been implemented and exercised by the local CI harness. The recorded WP4.7 scenarios pass on the tested commit below. The stricter exact-peer-set assertion is also included in that tested commit. This establishes selected crash-stop and network-partition behavior in a controlled local topology; it is not a Byzantine fault-tolerance proof, an independent security audit, or production-readiness evidence. All work stays on `phase-0.2-planning`; `main` is not modified.

## 7.1 Selected isolation topology for the local CI harness

The current four-validator smoke harness places every node on 127.0.0.1 with distinct listening ports. A host firewall rule that drops traffic by destination or source P2P port alone is not sufficient to prove a peer-specific partition: outbound TCP connections use ephemeral source ports, and a broad port rule can also block healthy intra-group links.

The implementation must therefore use a directed TCP relay for each ordered validator pair:

- Create 12 loopback-only relay listeners, one for each source-to-target pair.
- Configure each validator's persistent_peers entries to use its own directed relay endpoint, while each relay forwards only to the intended target's P2P listener.
- Disable peer exchange (pex = false) in these disposable test homes so nodes cannot bypass the relays through learned direct addresses.
- Keep RPC and ABCI endpoints on their existing local addresses; they are not routed through the P2P relays.
- A partition disables and closes both directed relays for every cross-group pair. Intra-group relays remain enabled.
- Reconnection re-enables the affected relays; the test must observe peer IDs returning through /net_info and then verify block and application-state convergence.

The relay implementation must bind only to 127.0.0.1, reject new cross-partition connections, close already-established cross-partition sockets when a partition is applied, use bounded socket timeouts, and shut down every listener/thread/socket in finally. The harness must fail closed if any node can establish a P2P connection outside its configured relay route.

This is the selected implementation approach, not evidence that WP4.7 has passed. The 3/1 and 2/2 scenarios remain unimplemented until the relay topology and bypass checks are exercised in CI.

## 8. Implementation and CI evidence

**Tested commit:** `4c19be099860cb801bfcfe88bb2f558e4ce75b1b`  
**GitHub Actions run:** [41721112365](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41721112365)  
**CometBFT:** v0.40.0  
**Workflow conclusion:** `success` for both `hnd-v02-tests` and `cometbft-single-node-smoke`.

The harness uses 12 directed loopback TCP relays, disables PEX, and routes persistent peer connections through the dedicated relay for each ordered validator pair. The `partition_ready` check requires the observed peer-ID set to equal the exact expected in-group peer set, rejecting missing peers and unexpected cross-group peers. The test also asserts that all four CometBFT processes and all four HND ABCI application processes remain alive during both partition scenarios.

### 8.1 Observed 3/1 scenario

- Voting power: 10 per validator; total 40.
- Before partition, the four-node network was converged.
- With validator 4 isolated, the three-validator quorum advanced from height 3 to height 4.
- The isolated validator remained at height 3; its block hash, application hash, and Alice account balance remained unchanged.
- All four node and ABCI processes remained alive.
- After reconnection, all four validators converged at height 7 with the same block hash and HND application hash.
- CI marker: `COMETBFT_V040_3_1_PARTITION_OK`; reconnection marker: `COMETBFT_V040_PARTITION_RECONNECTION_OK` (`scenario=3/1`).

### 8.2 Observed 2/2 scenario

- The two groups each held voting power 20 of 40.
- During the 12-second observation window, every validator's height, block hash, and HND application hash remained unchanged.
- All four node and ABCI processes remained alive.
- After reconnection, all four validators converged at height 9 with matching block hash and application hash.
- CI marker: `COMETBFT_V040_2_2_PARTITION_OK`; reconnection marker: `COMETBFT_V040_PARTITION_RECONNECTION_OK` (`scenario=2/2`).

### 8.3 Workflow-level results

The same workflow also passed the pinned CometBFT single-node ABCI integration smoke test and the four-validator Genesis/identity preflight. The four-validator network smoke test reported four validators, voting power 10 each, transfer of 1,237 HND at height 2, Alice balance 598,763 HND and Bob balance 401,314 HND after the subsequent 77 HND partition-scenario transfer, and successful convergence after the earlier single-validator stop/restart scenario.

The 2/2 test demonstrates no commits during the bounded 12-second observation interval under this harness; it does not establish a universal safety theorem. The current cleanup path closes node processes, ABCI processes, relays, and log handles in `finally`, but this run does not independently prove host-level absence of every transient socket after process exit.

## 9. Security scope and remaining gaps

WP4.7 is now implemented and CI-passing for the two specified partition shapes. It does not test malicious validator behavior, equivocation, double-signing, conflicting votes, compromised keys, Byzantine message fabrication, censorship, DDoS, WAN packet loss, or long-duration partitions. It does not establish BFT safety beyond the tested scenarios. Those remain separate security work packages. The file-based application store, lack of snapshots/state sync, and absence of independent security review remain release blockers.

---
This report records bounded integration-test evidence only. It is not a security certification, financial-product approval, or release authorization.
