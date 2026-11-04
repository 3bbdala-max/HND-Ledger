# HND v0.2 — BFT consensus, quorum, and adversarial evidence review

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Review type:** Static source review plus inspection of recorded GitHub Actions evidence  
**Consensus engine:** CometBFT v0.40.0  
**Current branch head before this report:** `28b310df16c26c4ee5659f5fa45c652043d1cd95`

## 1. Executive conclusion

The repository contains substantially more than a four-process smoke test: recorded CI evidence covers a four-validator CometBFT network, crash-stop/restart and catch-up, 3/1 and 2/2 network partitions, a narrowly controlled Byzantine prevote-equivocation test, and delivery of CometBFT duplicate-vote evidence into four live HND ABCI applications.

This is meaningful integration evidence for the tested CometBFT v0.40.0 build and disposable local topology. It is **not** a formal proof of Byzantine fault tolerance, a proof for arbitrary malicious behavior or network schedules, nor production-readiness evidence.

## 2. Quorum arithmetic and fault model

The four-validator smoke harness configures voting power 10 per validator, total voting power 40. CometBFT's commit threshold is strictly greater than two-thirds, therefore a commit needs at least 27 voting power; with equal weights, that means 3 of 4 validators (30/40).

| Scenario | Available power | Expected protocol behavior |
|---|---:|---|
| Four healthy validators | 40/40 | Quorum available |
| One validator stopped/isolated | 30/40 | Remaining three can commit |
| Two validators versus two | 20/40 per side | Neither side has quorum; commit progress stops |
| One validator withholds signatures | At most 30/40 honest power | Remaining three can progress if otherwise connected |
| Two validators faulty or unavailable | At most 20/40 honest power | No quorum; outside the one-third fault bound |

The arithmetic is correct for this equal-weight configuration. A quorum threshold is not itself evidence that all failure modes are safe; correctness still depends on CometBFT's protocol implementation, validator-set consistency, signing safety, and the stated network/fault assumptions.

## 3. Evidence reviewed

### E01 — Four-validator crash-stop, transaction, and catch-up

The recorded four-validator smoke job reports:
- four distinct validator consensus addresses and P2P node IDs in the generated disposable network;
- a transaction committed across the four nodes with matching block and HND application-state observations;
- three validators progressing while one node is stopped;
- the stopped node restarting with its original home and identities and catching up to the shared history.

The script uses temporary local keys and state. The log explicitly scopes this as a local crash-stop integration, not a Byzantine fault proof.

### E02 — 3/1 partition and reconnection

The harness routes every directed P2P pair through loopback relays, disables peer exchange, and checks the exact expected peer-ID set for each partition. In the recorded run, the three-validator side advanced while the isolated validator's height and application state remained unchanged. After reconnection, all four nodes converged on the same block and HND application hash.

This is evidence for the tested topology and scenario, not arbitrary partition schedules or WAN behavior.

### E03 — 2/2 no-quorum control

The recorded job split the four validators into two groups of two. During the 12-second observation interval, all four heights, block hashes, and HND application hashes remained unchanged, and all processes remained alive. After reconnection, the network converged.

The observation interval is bounded. It must not be described as a universal proof that no 2/2 split can ever commit under every configuration or fault schedule.

### E04 — Byzantine prevote equivocation in CometBFT

The pinned CometBFT v0.40.0 source includes `consensus/byzantine_test.go:TestByzantinePrevoteEquivocation`. The test creates four consensus states/reactors, uses a disposable faulty validator to sign two conflicting prevotes for the same height/round/type with different block IDs, and sends both through the ordinary P2P VoteChannel. The test waits for duplicate-vote evidence to appear in committed blocks.

The recorded workflow log shows this upstream test passing. This is a narrow, real P2P equivocation/evidence-path test, not a general malicious-validator campaign.

### E05 — CometBFT evidence reaches four live HND applications

The WP4.11 integration bridges the CometBFT consensus test harness to four running HND ABCI gRPC applications. The recorded workflow log contains:

- marker: `HND_WP4_11_P2P_EVIDENCE_REPLICAS_OK`;
- replicas: 4;
- evidence count: 1;
- infraction height: 2;
- evidence-bearing commit height: 3;
- balances unchanged: true;
- HND ABCI application restart verified: true;
- identical reported application hash: `bafc894edeb3fd89fb2bf79b7953368787504d39add4e3e6fa3e7abe5e5cf661`.

The integration uses CometBFT's actual duplicate-vote evidence path, then checks the normalized ABCI misbehavior summary in the HND evidence journal across replicas.

**Important boundary:** the ABCI misbehavior summary is not the original pair of signed votes. HND records CometBFT's supplied summary; the HND application does not independently verify the original two vote signatures from that summary. Evidence journaling is audit-only; it does not slash validators or change account balances.

## 4. CI provenance and limits

Inspected workflow: [GitHub Actions run 41840460178](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41840460178).

The two jobs returned completed/success:
- `hnd-v02-tests`
- `cometbft-single-node-smoke`

The `cometbft-single-node-smoke` job log includes the four-validator network smoke, partition scenarios, upstream Byzantine equivocation test, and HND P2P evidence integration markers. The recorded workflow was run on commit `7864986c27f1b6bf0daaa2d13d03365988e9e52d`, not on the current documentation-only branch head. These results must be cited as historical evidence for that tested commit, not as a fresh CI run on this report commit.

## 5. Remaining BFT and production gaps

| ID | Gap | Required next evidence |
|---|---|---|
| BFT01 | Equivocation test covers a specific prevote scenario | Add adversarial cases for conflicting precommits, invalid signatures, wrong validator/chain/height/round, delayed and duplicated messages, and proposer faults |
| BFT02 | One faulty validator is tested through a controlled upstream harness | Test Byzantine withholding, malformed messages, selective peer behavior, and combinations with one crash/partition, without changing production consensus code |
| BFT03 | 2/2 no-quorum test observes only 12 seconds | Preserve bounded test language; add repeated runs and timing-boundary cases |
| BFT04 | Local loopback nodes share one host | Test separate hosts/failure domains, latency, packet loss, firewall policy, and operational isolation |
| BFT05 | HND stores CometBFT's evidence summary | Define whether an independent audit trail of raw evidence is required; if so, design authenticated evidence retention without claiming HND currently verifies the raw vote pair |
| BFT06 | Validator-set lifecycle is not established | Specify authenticated validator admission/removal, voting-power changes, key rotation, and emergency revocation |
| BFT07 | Production signer/keys and recovery trust remain open | Complete key custody, anti-double-sign durability, fencing, backup/restore, and independent signer review |
| BFT08 | Application state recovery and sync are limited | Design and test trusted snapshots/state sync, corruption recovery, and long-duration node catch-up |
| BFT09 | Current integration does not establish deployment hardening | Secure RPC/ABCI boundaries, P2P configuration, observability, resource limits, upgrades, and incident response |
| BFT10 | No independent protocol/security audit | Obtain independent review of CometBFT configuration, HND ABCI determinism, signer integration, and deployment model |

## 6. Findings and status

1. **Consensus selection:** CometBFT remains the sole consensus engine; HND must not implement a parallel consensus mechanism.
2. **Quorum behavior:** the recorded 3/1 and 2/2 tests match the configured 4 × 10 voting-power model.
3. **Equivocation evidence:** a real CometBFT P2P VoteChannel test and the HND ABCI evidence handoff have recorded passing CI evidence.
4. **Scope:** these are controlled integration results, not proof of arbitrary Byzantine fault tolerance, economic security, decentralization, or production resilience.
5. **Release gate:** production/mainnet, public token issuance, real funds, exchange/payment integration, and production validator onboarding remain unauthorized and blocked pending the outstanding engineering, security, operational, and legal gates.

## 7. Review execution statement

This review inspected repository source, design records, current branch metadata, and the recorded GitHub Actions job/logs. It did not run a new local test suite or launch a new four-node network. The CI results above are attributed to their exact historical workflow/commit.

---
This document is an engineering evidence review, not a security certification, financial-product approval, or release authorization.
