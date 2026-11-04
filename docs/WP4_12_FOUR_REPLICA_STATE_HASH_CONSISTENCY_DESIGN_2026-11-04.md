# HND v0.2 — four-replica deterministic state/hash consistency

**Date:** 2026-11-04  
**Workstream:** WP4.12 — application-state convergence and divergence detection  
**Branch:** `phase-0.2-planning`  
**Status:** Four-replica state/hash consistency regression and full CI workflow passed — 2026-11-04

## 1. Objective

Verify that four independent HND application instances initialized from the same canonical Genesis and given the same ordered committed transactions produce identical committed heights, account state, and 32-byte application hashes. Also prove that a valid but different state transition on one replica at the same height is detected as an application-hash mismatch.

## 2. Test contract

The new `tests/test_v02_four_replica_state_convergence.py` test:

1. Creates four HND application instances with the same network configuration, manifest, and Genesis hash, each using an independent durable state file.
2. Applies two identical sequentially signed transactions to all four replicas at heights 1 and 2.
3. Compares FinalizeBlock hashes, Commit hashes, committed heights, and 32-byte Info application hashes after each block.
4. Confirms the account balances and total supply are identical.
5. Restarts one application from its durable state file and checks its height and application hash.
6. Deliberately commits two different but individually valid same-nonce transactions to otherwise matching states at height 3: three replicas receive one transaction and replica 4 receives the other.
7. Requires the comparator to return `app_hash_mismatch` while all four heights remain equal. This is a negative control: divergence must not be mistaken for convergence.

## 3. Interpretation and limits

- This is an application-layer deterministic execution regression. It does not run four CometBFT consensus processes and does not prove network consensus, Byzantine fault tolerance, or automatic repair of a divergent replica.
- The negative control intentionally creates a forked application state in disposable test files. It demonstrates detection through differing committed application hashes; it does not define a production slashing, rollback, or state-repair policy.
- The existing four-validator CometBFT integration independently checks equal app hashes during successful common-chain transaction execution and after partition/reconnection. This test complements that network test by deliberately creating a same-height application divergence.
- The 32-byte application hash commits to the HND ledger state and evidence journal; the test compares the exact committed value reported by each app.

## 4. Acceptance criteria

- Identical Genesis and identical ordered valid transactions produce equal FinalizeBlock and Commit hashes across all four applications.
- Heights, account balances, and total supply agree after each common block.
- An application restart restores the exact committed height and app hash.
- A same-height valid divergent transaction produces a different app hash and is explicitly classified as `app_hash_mismatch`.
- The test runs in the isolated HND v0.2 CI test job.

No production release, real-value activity, or automatic economic penalty is authorized by this workstream.


## 5. CI result — passed 2026-11-04

- Full GitHub Actions workflow [41843665525](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41843665525) completed with **success** on commit `4c551b26886e967200c6a21669d3b00c72e398e9` on `phase-0.2-planning`.
- Both jobs passed: `hnd-v02-tests` and `cometbft-single-node-smoke`.
- The isolated HND test job passed, including the four-replica convergence/divergence regression; the recorded test suite reported 139 isolated Python tests with no failures.
- The CometBFT integration job also completed all steps successfully, including the four-validator network, external signer outage/recovery, authenticated Noise-backed four-validator signer integration, and the WP4.11 P2P evidence integration.
- **WP4.12 acceptance gate: passed for the implemented application-layer regression and this CI run.** This does not make the negative-control fork a network consensus test, nor does it prove arbitrary Byzantine safety/liveness, full CometBFT process restart/catch-up, production persistence, or production readiness.
- Next gate: explicitly test full CometBFT node-process restart and catch-up from durable HND ABCI state, then broaden fault injection. Production key custody, independent security review, governance, and jurisdiction-specific legal review remain open. No public release or real-value activity is authorized.
