# WP4.7 — Network Partition and Reconnection Test Design

**Status:** Design only; no partition test is claimed as implemented or passed  
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

WP4.7 remains **design-only** until the isolation primitive is demonstrated to work bidirectionally and repeatably on the selected CI runner. The current WP4.5 crash-stop test remains valid and unchanged. All work stays on `phase-0.2-planning`; `main` is not modified.

---
This document is a test design and acceptance gate, not evidence that a network partition test has passed.
