# HND v0.2 — four-replica deterministic state/hash consistency

**Date:** 2026-11-04  
**Workstream:** WP4.12 — application-state convergence and divergence detection  
**Branch:** `phase-0.2-planning`  
**Status:** Initial deterministic application-layer regression added; CI validation pending

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
