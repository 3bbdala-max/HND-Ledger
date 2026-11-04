# HND v0.2 — network equivocation to application evidence integration design

**Date:** 2026-11-04  
**Workstream:** WP4.11 — actual P2P equivocation injection and HND evidence convergence  
**Pinned upstream:** CometBFT v0.40.0  
**Status:** Design gate; HND-specific P2P-to-ABCI evidence injection is not yet implemented or passed  
**Branch:** `phase-0.2-planning`

## 1. Verified baseline

The full workflow [41836087031](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41836087031) passed on commit `2c35ee51e3384de154772c9a25031c27e6a1c908`.

The run confirms:
- HND isolated v0.2 tests passed, including evidence normalization, adapter handoff, persistence/reload, duplicate idempotence, and no balance mutation.
- The adapter test `test_finalize_block_passes_misbehavior_into_persisted_hnd_evidence_journal` passed.
- The pinned upstream CometBFT `TestByzantinePrevoteEquivocation` passed.
- Existing single-node ABCI, four-validator, partition/reconnection, Unix remote-signer, and Noise remote-signer integration steps passed.

These are separate test layers. The upstream Byzantine regression exercises CometBFT's own consensus/evidence pipeline; the HND adapter test supplies a protobuf misbehavior summary directly. Neither by itself proves that an actual conflicting P2P vote pair is detected by CometBFT and then delivered to the running HND application in the same integration scenario.

## 2. Objective

Build a disposable, CI-only test in which a deliberately faulty validator sends two conflicting signed votes through CometBFT's actual P2P VoteChannel. Honest CometBFT nodes must form duplicate-vote evidence, include the ABCI misbehavior summary in a later FinalizeBlock request, and cause each HND application replica to persist the same canonical evidence journal and application hash.

## 3. Required topology and trust boundaries

- Four disposable validators with equal voting power and independent temporary consensus/P2P identities.
- Four separate CometBFT processes and four separate HND ABCI application processes, each with its own durable temporary state file.
- One validator is deliberately faulty only inside this test. Its anti-double-sign guard may be bypassed only in the disposable test harness so two conflicting votes can be signed; never weaken the production signer guard or reuse any real key.
- Inject both signed votes through the ordinary P2P VoteChannel. Direct calls to VoteSet.AddVote or direct insertion of ABCI misbehavior records are not acceptable substitutes.
- Keep P2P and ABCI endpoints bound to loopback; retain logs but never print private keys or seed material.

## 4. Evidence path to prove

1. The faulty validator signs two different prevotes for the same height, round, and vote type.
2. The conflicting signed votes are sent over the actual P2P VoteChannel to honest peers.
3. CometBFT reports the conflict to its evidence pool and forms a verified duplicate-vote evidence object.
4. A later committed block carries the corresponding `RequestFinalizeBlock.misbehavior` summary to each HND ABCI adapter.
5. Each HND application validates and commits the normalized evidence journal record.
6. Query `/evidence` on all four replicas; compare canonical journal bytes, evidence IDs, committed heights, and 32-byte application hashes.
7. Restart at least one HND application and its CometBFT process from durable state; confirm the journal and app hash are unchanged and the node catches up to the same committed state.

## 5. Timing and protocol constraints

- CometBFT evidence may be buffered when the conflicting votes arrive and included only in a later block. The test must wait for the committed evidence rather than assume it appears in the infraction-height block.
- The HND adapter currently enforces that infraction height is strictly earlier than the block being finalized. The harness must wait for a suitable later height.
- The ABCI Misbehavior summary is not the complete signed vote pair. HND records CometBFT's supplied summary and must not claim independent cryptographic verification of the two votes.
- Duplicate evidence delivery must remain idempotent. Conflicting metadata for an existing deterministic evidence ID must fail closed.
- Evidence accounting is audit-only. No slashing, burning, freezing, confiscation, or balance changes are permitted by this workstream.

## 6. Acceptance criteria

WP4.11 passes only if CI proves all of the following in one HND-specific integration run:
- conflicting signed votes traverse the real P2P VoteChannel;
- CometBFT creates and commits duplicate-vote evidence;
- HND receives the corresponding ABCI misbehavior summary through its live adapter;
- all four HND replicas expose the same evidence record and compute the same application hash;
- evidence survives restart and catch-up;
- ordinary account balances and total supply remain unchanged;
- test keys/state are disposable and cleaned up; no private material appears in logs.

A passing upstream CometBFT unit test, a passing HND adapter unit test, or an ordinary four-validator crash/partition test alone does not satisfy this gate.

## 7. Implementation sequence

1. Reuse the pinned CometBFT v0.40.0 source and inspect the existing `consensus/byzantine_test.go` harness and VoteChannel injection helpers.
2. Choose the narrowest maintainable integration seam: a test-only Go harness that injects the conflicting votes into a real CometBFT network while the nodes use the HND ABCI gRPC applications.
3. Add explicit test-only faulty-validator signing behavior, isolated from the production FilePV and remote-signer implementations.
4. Add HND app query/hash checks on every replica and durable restart verification.
5. Add the scenario as a separate named CI step after existing four-validator smoke tests.
6. Record exact run ID, commit, evidence height, journal ID, and per-replica app hashes in a concise machine-readable result.

If the upstream test harness cannot be safely adapted without invasive CometBFT patches, stop and document the limitation rather than bypassing P2P or fabricating ABCI evidence.

---

This design is a test plan, not proof of Byzantine fault tolerance, production security, legal compliance, or authorization to issue or trade HND.


## 8. Pinned-source integration seam verified

A second inspection of the exact CometBFT v0.40.0 source confirms that the upstream regression can be adapted without replacing the P2P path:

- `consensus/byzantine_test.go:TestByzantinePrevoteEquivocation` constructs four consensus states and four consensus reactors, connects them with `p2p.MakeConnectedSwitches`, and signs two conflicting prevotes in the faulty validator's `doPrevote` hook.
- The two signed votes are sent to each connected peer as `p2p.Envelope{ChannelID: VoteChannel, Message: &cmtcons.Vote{...}}`. This is the actual consensus P2P reactor path and must be retained.
- The same test subscribes to each validator's committed-block event stream and waits for duplicate-vote evidence to appear in committed blocks. The evidence is expected after the infraction height, not necessarily in the same block.
- The existing test currently uses `newKVStore`, `abcicli.NewLocalClient`, and an in-memory state store. That is the part to replace for HND integration.
- The pinned `abci/client/grpc_client.go` exposes `abcicli.NewGRPCClient(addr, true)`; the client implements the ABCI Application interface and can be passed to `proxy.NewAppConnConsensus` and `proxy.NewAppConnMempool`. This provides a supported bridge to the running HND Python gRPC ABCI server without changing the vote injection mechanism.
- HND application initialization must receive the configured HND `ChainId` and canonical `AppStateBytes` in `RequestInitChain`; the upstream test's current minimal InitChain request supplies only validator updates and is insufficient for HND.
- After the evidence-bearing block commits, the integration test must query `/evidence` and `Info` from all four HND ABCI endpoints and compare canonical journal contents and `last_block_app_hash`.

**Implementation constraint:** do not simply swap the local KV store for a gRPC client and assume the test is complete. The test must also provide valid HND Genesis bytes, initialize each application independently, close all ABCI clients and processes deterministically, and verify that the four application hashes agree after the same evidence-bearing block.
