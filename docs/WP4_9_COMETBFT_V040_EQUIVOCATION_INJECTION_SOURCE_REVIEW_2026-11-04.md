# HND v0.2 — CometBFT v0.40.0 equivocation-injection source review

**Date:** 2026-11-04  
**Workstream:** WP4.9 — malicious conflicting-vote injection and evidence capture  
**Pinned source:** CometBFT `v0.40.0`  
**Status:** Source path identified; end-to-end test harness not yet implemented or passed.

## 1. Finding

The pinned CometBFT source has a normal peer-message path for receiving signed votes. The consensus reactor handles `*VoteMessage` on `VoteChannel` and enqueues it to the consensus state's peer message queue. This is the preferred test path: a disposable malicious peer should send two independently signed, conflicting votes for the same validator, height, round, and vote type through the ordinary P2P vote channel.

The test must not call private consensus methods through reflection, patch CometBFT internals, or inject evidence directly into production application state.

## 2. Source-grounded processing path

1. `consensus/reactor.go`: the `VoteChannel` handler accepts `*VoteMessage`, records peer vote metadata, and enqueues the message with the source peer ID.
2. `consensus/state.go`: the peer message handler passes the vote to `tryAddVote`.
3. `consensus/state.go`: `tryAddVote` calls `addVote`; on `*types.ErrVoteConflictingVotes`, it calls `cs.evpool.ReportConflictingVotes(voteErr.VoteA, voteErr.VoteB)` for a remote validator. Conflicts attributed to the local validator are logged and are not reported as remote evidence.
4. `evidence/pool.go`: `ReportConflictingVotes` buffers the conflicting pair. Its source comment explicitly says votes are not verified at this buffering point; evidence formation and verification occur later as consensus state advances and the evidence pool updates.
5. The eventual evidence must be observed in the evidence pool / proposed or committed block path and validated against the validator set. Merely seeing the conflict-buffer call is not a complete pass.

## 3. Important distinction

- `State.AddVote` is an asynchronous input method that queues a vote; it does not synchronously return the evidence result.
- `types.VoteSet.AddVote` is a lower-level collection operation. Calling it directly can demonstrate conflict detection but bypasses the full peer-message handling and evidence-pool reporting path.
- `EvidencePool.ReportConflictingVotes` buffers a pair and does not itself verify signatures.
- Therefore the acceptance test must exercise the ordinary P2P peer path and separately verify both signatures, evidence identity, validator address, height, round, vote type, and the final evidence lifecycle.

## 4. Proposed isolated test harness

- Start a disposable four-validator local network with synthetic keys and no external network route.
- Choose one remote validator identity and create two conflicting vote messages with the same H/R/type and different BlockIDs.
- Sign both messages with that validator's disposable test key, verifying both signatures locally before transmission.
- Connect a test peer through CometBFT's supported P2P switch/reactor interface and deliver the two messages on the standard vote channel.
- Confirm the receiving node processes the conflict and that the evidence pool buffers the pair.
- Advance consensus safely so evidence can be formed; inspect the resulting duplicate-vote evidence and verify both embedded signatures and validator identity.
- Confirm no conflicting commit is accepted merely because the evidence is reported; record actual node behavior and all heights/hashes.
- Keep the malicious key and peer isolated to this one test. Clean up all temporary keys, homes, sockets, processes, and peer resources.

## 5. Remaining implementation gate

The source review identifies the production message-processing route, but does not yet prove that the repository's current integration harness can attach a synthetic peer to the running reactor and reliably deliver the messages. Before implementation, inspect the pinned P2P switch test APIs and existing CometBFT reactor tests, then build the smallest disposable peer-level proof. If a supported test seam cannot be established without patching consensus internals, retain this scenario as design-only.

## 6. Security boundary

This is a controlled local test design, not a formal BFT proof, security audit, or production certification. No production key, public endpoint, public chain, real-value transaction, or live network is permitted. No HND release or trading authorization follows from a passing test.

## 7. Pinned upstream regression discovered and wired into CI

The exact pinned CometBFT v0.40.0 source already contains `consensus/byzantine_test.go:TestByzantinePrevoteEquivocation`. This is stronger than a speculative harness: it creates four validator consensus states and connected P2P switches, disables normal anti-double-sign checks only for the disposable Byzantine mock validator, signs two different prevotes (proposal block and nil) at height 2, and sends both signed messages to every peer on the real `VoteChannel`.

The test subscribes to each validator's committed-block events and waits for duplicate-vote evidence to appear in a block. It checks the evidence type, Byzantine validator address, and equivocation height. The test also uses a lazy proposer to exercise evidence timestamp handling.

The HND CI workflow now runs this exact test from the checked-out CometBFT `v0.40.0` source using:

```sh
go test ./consensus -run '^TestByzantinePrevoteEquivocation$' -count=1 -v
```

This is a pinned upstream consensus/evidence regression, not a claim that the HND application has its own custom malicious-peer test yet. It validates the upstream CometBFT path on which HND depends. The four-validator HND integration remains a separate test and must pass independently.
