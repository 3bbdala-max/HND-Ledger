# HND v0.2 — network equivocation to application evidence integration design

**Date:** 2026-11-04  
**Workstream:** WP4.11 — actual P2P equivocation injection and HND evidence convergence  
**Pinned upstream:** CometBFT v0.40.0  
**Status:** Implemented and passed in disposable CI integration; see Section 10  
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
7. Restart at least one HND ABCI application process from its durable state file; confirm the journal, committed height, and app hash are unchanged. (The current WP4.11 harness does not restart a CometBFT node process or test node catch-up.)

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
- evidence survives restart of one HND application process from its durable state file;
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


## 9. HND application bootstrap and integration-test construction decision

The repository inspection confirms the HND server exposes the exact lifecycle needed by a live integration test:

- Each application instance is constructed from the same canonical manifest and genesis hash, but with a distinct disposable state file.
- `HNDABCIApplication.application_genesis_bytes()` produces canonical `{genesis_hash, manifest}` bytes.
- `HNDCometBFTv040Servicer.InitChain` verifies the configured chain ID and those exact bytes before initializing the durable application store.
- `Info` reports `last_block_height` and the committed 32-byte `last_block_app_hash`.
- `Query("/evidence")` returns the committed evidence journal; it is not a direct mutable-state hook.

### Test shape to implement

1. The Python orchestration layer creates a temporary manifest/genesis and starts four HND ABCI gRPC servers on loopback, each with a separate state path.
2. A pinned-source Go test is placed in the CometBFT `consensus` package for the duration of the CI job. It reuses the upstream four-state / four-reactor setup and the exact `VoteChannel` equivocation injection, but replaces each `newKVStore` local ABCI application with `abcicli.NewGRPCClient` connected to one of the four HND servers.
3. Each client is started before use and receives `RequestInitChain{ChainId: HND chain ID, AppStateBytes: canonical HND Genesis bytes, Validators: validator updates}`. The test must stop every client during cleanup.
4. The existing upstream block-event subscription is retained to wait for an evidence-bearing committed block on each validator. No direct evidence insertion or direct VoteSet mutation is allowed.
5. After the committed evidence block, query each ABCI server's `/evidence` endpoint and `Info`. Assert:
   - exactly one canonical evidence journal record per equivocation;
   - identical canonical journal bytes across all four applications;
   - identical committed heights and 32-byte application hashes;
   - the journal record's validator address, evidence type, and infraction height match the faulty validator and injected prevote pair;
   - all ordinary account balances remain unchanged.
6. Restart one HND application process from its existing state file, query it again, and verify that its journal and app hash are unchanged. Then verify that it has caught up to the same committed height/hash before declaring the restart leg successful.

### CI isolation and source pinning

The integration job must verify the CometBFT source tag is exactly `v0.40.0` before adding the temporary same-package test file. It must fail closed if the expected upstream test function or source anchors are absent. The temporary test source must be removed by a shell trap even on failure. The four HND servers, validator keys, node homes, and state files remain under a temporary directory; only loopback listeners are permitted.

**Current status:** the HND server bootstrap and query surfaces are confirmed in repository source. This section specifies the implementation contract; it is not evidence that the integration test has been implemented or passed.


## 10. HND P2P-to-ABCI integration implemented and passed

- Full GitHub Actions workflow [41840460178](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41840460178) completed with **success** on commit `7864986c27f1b6bf0daaa2d13d03365988e9e52d`; both `hnd-v02-tests` and `cometbft-single-node-smoke` jobs passed.
- The dedicated step, `Run HND four-replica P2P equivocation evidence integration`, completed successfully against the pinned CometBFT v0.40.0 source.
- The job log records the faulty validator's two conflicting signed prevotes being sent through the real P2P VoteChannel; CometBFT reports the conflict, verifies duplicate-vote evidence, and commits the evidence-bearing block.
- The HND integration emitted the required marker `HND_WP4_11_P2P_EVIDENCE_REPLICAS_OK` with: `replicas=4`, `evidence_count=1`, `evidence_height=2`, `commit_height=3`, `balances_unchanged=true`, and `restart_verified=true`.
- The result reported the shared 32-byte application hash `bafc894edeb3fd89fb2bf79b7953368787504d39add4e3e6fa3e7abe5e5cf661`. The script's acceptance checks also require identical canonical evidence journal bytes, evidence IDs, heights, and app hashes across all four replicas, followed by durable restart verification of replica 0.
- This closes the WP4.11 **test gate for the implemented disposable integration**: actual P2P equivocation traverses CometBFT's evidence path and its ABCI misbehavior summary reaches the four live HND applications.
- **Scope limitations remain:** the test uses disposable local identities and loopback services; it is not a proof of arbitrary Byzantine fault tolerance, production key custody, production network security, or independent cryptographic verification by HND of the original signed vote pair. HND records the CometBFT-supplied ABCI misbehavior summary. The evidence journal is audit-only; no slashing or balance changes occur.
- All changes remain on `phase-0.2-planning`; `main` is unchanged. Independent security review, production key custody/operations, governance, and jurisdiction-specific legal review remain open. Public release and real-value activity remain blocked by G2–G4.


### WP4.11 restart-scope clarification

The passing integration restarts the first **HND ABCI application process** and verifies restoration of its durable evidence journal, committed height, and application hash. It does not restart the corresponding CometBFT consensus process and does not claim a CometBFT node catch-up test. A node-process restart/catch-up scenario remains a separate future integration test.
