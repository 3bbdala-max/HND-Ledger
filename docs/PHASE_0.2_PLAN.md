# HND Ledger — Phase 0.2 Development Plan

**Status:** Planning baseline  
**Target branch:** `phase-0.2-planning`  
**Baseline:** Phase 0.1 local educational prototype  
**Document purpose:** Define the work and acceptance gates for a separately developed Phase 0.2. This plan does not certify production readiness or authorize a public token launch.

## 1. Baseline and preservation

The project archive records Phase 0.1 as a local educational prototype for signed transactions and deterministic adaptive consensus simulation. The archive reports successful tests for the documented local scope, including 1,212 baseline tests, 3,000 sequential transfers, supply invariance at 1,000,000 units, invalid-input rejection, invalid proposal/quorum rejection, tamper detection, and recovery validation.

These are archived results, not tests rerun by this planning document. Phase 0.1 is treated as a closed baseline. No Phase 0.2 work should silently rewrite or weaken its recorded results. Preserve the original archive and, when source code is recovered, identify the exact source revision and test commands that reproduce the baseline.

The archive also records important limits: Phase 0.1 has no production peer-to-peer network, no real distributed fault testing, and no independent security audit. It is not a production blockchain, financial product, exchange asset, or authorization to issue or trade a token.

## 2. Current repository gap

At the time this plan was prepared, the GitHub repository's default branch contained a `docs/` directory and `docs/ARCHITECTURE.md`. The architecture file was a documentation template. No `src/` directory or executable ledger implementation was visible in the repository contents inspected.

Therefore, the first task is source-code recovery and provenance verification—not assuming that the archived prototype is already present in this repository.

## 3. Phase 0.2 objectives

1. Recover and identify the Phase 0.1 source, tests, dependencies, and reproducible run instructions.
2. Convert the archived design into precise, versioned protocol specifications.
3. Design a real multi-node test network with explicit threat assumptions and failure handling.
4. Implement and test networking, transaction propagation, consensus, state synchronization, and node recovery as separate reviewable components.
5. Establish security, operational, and legal review gates before any public deployment or financial use.

## 4. Work packages and acceptance criteria

### WP0 — Source recovery and reproducibility

- Locate the original Phase 0.1 source and test suite.
- Record the source repository, commit identifier, runtime/toolchain versions, dependencies, and license status.
- Reproduce the archived test results in a clean environment where feasible.
- Record any mismatch between the archive and executable results; do not mark an unreproduced result as verified.

**Exit criteria:** A versioned source baseline, documented build/test commands, and a reproducibility report.

### WP1 — Protocol specification

Specify, without implementation ambiguity:

- transaction format, identifiers, signatures, nonce/replay protection, and validation rules;
- account/state model and exact supply/issuance rules;
- block or batch format, canonical ordering, state transition, and state commitment;
- consensus roles, quorum calculation, validator admission/removal, and deterministic decision rules;
- protocol versioning, error codes, and compatibility rules.

**Exit criteria:** Reviewed protocol specification with worked valid/invalid examples and explicit unresolved decisions.

### WP2 — Threat model and network design

Document adversaries and failure modes, including malicious validators, equivocation, replay, Sybil identities, network partitions, delayed messages, node crashes, clock skew, denial of service, key compromise, and state/database corruption.

Define peer discovery, authenticated transport, message limits, rate limits, synchronization, fork/conflict handling, recovery, and safe upgrade procedures. Do not assume that a local simulation proves distributed safety or liveness.

**Exit criteria:** Threat model, network protocol design, and testable safety/liveness properties approved for implementation.

### WP3 — Multi-node implementation

Implement only after WP0–WP2 are reviewed. Keep transaction validation, consensus, networking, persistence, and wallet/key management modular. Use a private test network first; do not connect it to public users or real funds.

**Exit criteria:** Reproducible multi-node test deployment with documented configuration and operational controls.

### WP4 — Verification and security

Build automated tests for:

- valid and invalid transactions, signatures, replay, and conflicting spends;
- quorum boundaries, equivocation, malicious proposals, and validator failures;
- partitions, message loss/reordering/delay, reconnect, and state synchronization;
- crash recovery, corrupted storage, backup/restore, and upgrades;
- load, resource exhaustion, and denial-of-service limits.

Require independent security review before any production decision. Record findings and remediation evidence.

**Exit criteria:** Published test report, resolved critical/high findings, and independent audit report. Passing internal tests alone is insufficient.

### WP5 — Governance, legal, and release readiness

Define validator governance, upgrade authority, emergency response, key custody, incident disclosure, and supply-change controls. Obtain qualified legal advice for each intended operating jurisdiction before public distribution, fundraising, exchange listing, or financial use.

**Exit criteria:** Written governance and operational policies, jurisdiction-specific legal review, and an explicit release decision by accountable project owners.

## 5. Release gates

| Gate | Required evidence | Decision |
|---|---|---|
| G0 | Phase 0.1 source recovered and baseline reproducible | Authorize detailed 0.2 design |
| G1 | Protocol specification and threat model reviewed | Authorize multi-node implementation |
| G2 | Private test network and fault tests pass | Authorize external technical review |
| G3 | Independent audit and remediation complete | Consider production-readiness review |
| G4 | Legal, governance, operations, and security approvals | Separate explicit public-release decision |

A failed gate pauses progression. No gate is passed by assumption.

## 6. Non-goals and safeguards

- No mainnet launch, public token sale, exchange listing, investment solicitation, or real-value transfers are part of this planning phase.
- The initial supply figure of 1,000,000 is a recorded design idea/baseline value, not permission to mint, distribute, or market tokens.
- Do not publish private keys, seed phrases, access tokens, credentials, or personal data in source control or issue discussions.
- Do not change the Phase 0.1 archive or the `main` branch as part of this planning document.
- Any material protocol or supply change must be documented, reviewed, and versioned.

## 7. Immediate next actions

1. Recover the Phase 0.1 source code and test suite from the original working location or archive.
2. Add the source to a controlled repository branch only after provenance and secret scanning.
3. Produce a source-to-archive mapping: each archived test claim, its test name, command, and result.
4. Complete WP0 before implementing new network features.

## 8. Decision log

| Decision | Current position |
|---|---|
| Phase 0.1 | Preserve as a closed local educational baseline |
| Phase 0.2 | Planning only; no production claim |
| Repository default branch | Leave `main` unchanged |
| Supply | Preserve 1,000,000 as recorded baseline pending formal protocol decision |
| Public release | Blocked pending technical, independent security, governance, and legal gates |

---
This document is a development plan, not a security certification, legal opinion, investment document, or promise of launch.


## 9. Implementation status update — 2026-10-31

This status note supersedes the earlier "Immediate next actions" snapshot where later verified work has closed those gaps. It does not silently change the original planning baseline or release gates.

- WP0 source recovery/recheck and the recorded local transfer recheck are documented separately.
- WP1–WP3 v0.2 engineering references and isolated test suites are present in this branch.
- WP4.1–WP4.3 ABCI feasibility, application core, and pinned gRPC adapter are documented.
- **WP4.4 single-node integration passed** in GitHub Actions run [41242087625](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41242087625), tested commit `ede5acf8a786d1d29e8af1d9c54b583f4446ec3f`. The disposable CometBFT v0.40.0 node initialized HND, accepted and committed a signed 1,237 HND transfer, changed the synthetic sender balance from 600,000 to 598,763 HND, and recovered the same committed state after application/node restart. See `docs/WP4_4_COMETBFT_V040_SINGLE_NODE_INTEGRATION_2026-10-31.md`.
- The next technical gate is a private multi-validator test network and distributed fault testing. This is not yet evidence of BFT safety/liveness, production readiness, or public-release authorization.
- All changes remain on `phase-0.2-planning`; `main` has not been changed.


## 10. WP4.5 design gate — 2026-11-01

- Added `docs/WP4_5_PRIVATE_FOUR_VALIDATOR_NETWORK_DESIGN_2026-11-01.md` as the implementation gate for a disposable four-validator CometBFT v0.40.0 network.
- The design requires four independent validator identities, four isolated HND ABCI application processes and state files, common Genesis/validator configuration, transaction agreement, a one-validator stop-and-restart test, and catch-up convergence.
- The design explicitly records unresolved schema, networking, persistence, and state-sync risks. WP4.5 is **design-only** at this point; no four-validator network has been implemented or tested yet.
- Next implementation step: validate CometBFT v0.40.0's exact genesis validator JSON and node-ID/persistent-peer generation using the pinned binary before building the multi-node harness.
- `main` remains unchanged; all work remains on `phase-0.2-planning`.


## 11. WP4.5 validator identity / Genesis preflight added — 2026-11-01

- Added `scripts/cometbft_v040_four_validator_genesis_preflight.py`: creates four isolated CometBFT homes, extracts four independent validator keys and P2P node IDs, constructs a common HND Genesis document, and checks uniqueness and byte-identical Genesis copies.
- Added `scripts/cometbft_v040_genesis_validate.go`: validates the generated Genesis using `types.GenesisDocFromFile` from the pinned CometBFT v0.40.0 source module.
- Added this preflight to the existing CometBFT CI job after the single-node smoke test.
- Pinned source review confirms the Genesis validator schema and the local-network P2P settings needed for multiple peers on loopback (`addr_book_strict=false`, `allow_duplicate_ip=true`).
- The latest CI run for this addition is [41243006658](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41243006658); its HND v0.2 unit-test job has passed, while the CometBFT integration job was still running at the time of this note. Do not mark the new preflight passed until that job completes successfully.
- This is still a Genesis/identity preflight, not a four-running-validator network. The WP4.5 consensus, transaction replication, one-validator outage, and restart/catch-up tests remain open.

## 12. WP4.5 live four-validator integration — passed 2026-11-01

The four-validator implementation and CI smoke test have now passed. This supersedes the earlier WP4.5 design-only and Genesis-preflight-only status notes above; those entries remain as historical progression records.

- Harness: `scripts/cometbft_v040_four_validator_network_smoke.py`.
- CI workflow: [run 41243674122](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41243674122), tested branch commit `d2f2eb609b223f40265ad16d4ae062930657b6ba`.
- CometBFT v0.40.0, four isolated validators, voting power 10 each.
- All four nodes converged from initial height 1; a signed 1,237 HND transfer committed at height 2. Alice ended at 598,763 HND and Bob at 401,237 HND.
- With one validator and its HND app stopped, the remaining three advanced to height 3.
- The stopped app and validator restarted and caught up; all four nodes converged at height 4.
- CI emitted `COMETBFT_V040_FOUR_VALIDATOR_NETWORK_OK`. Temporary test keys and state were not retained as repository artifacts.

**Scope limitation:** This is a local four-validator crash-stop integration test. It is not proof of Byzantine fault tolerance, partition safety, malicious-validator handling, production-grade persistence, or production readiness. Snapshot state sync is not implemented. Independent security review, broader adversarial/fault testing, operational controls, governance, and jurisdiction-specific legal review remain open. Public release remains blocked by the existing G2–G4 gates.

All work remains on `phase-0.2-planning`; `main` is not modified.


## 12. WP4.6 ABCI Genesis identity negative tests — passed 2026-11-01

- Added two adapter-level negative tests: reject an InitChain request with a mismatched CometBFT chain ID, and reject an application Genesis payload whose hash differs from the independently pinned HND manifest hash.
- Both tests assert that failed initialization does not create the application state file.
- Full CI run [41246122343](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41246122343) completed successfully on commit `b89b99abc4c9193c0235b3f5ff52833ef9c0b91e`. The isolated v0.2 test job and the CometBFT integration job both passed; the latter reran the single-node smoke, four-validator Genesis preflight, and four-validator network integration.
- Detailed scope and limitations are recorded in `docs/WP4_6_ABCI_GENESIS_IDENTITY_NEGATIVE_TESTS_2026-11-01.md`.
- These checks cover only the stated initialization identity failures. They do not prove Byzantine fault tolerance, partition safety, resistance to malicious validators, or production security. `main` remains unchanged.


## 13. WP4.7 network partition/reconnection design gate — 2026-11-01

- Added `docs/WP4_7_NETWORK_PARTITION_RECONNECTION_TEST_DESIGN_2026-11-01.md` with explicit live 3/1 and 2/2 partition scenarios, quorum expectations for the four equal-power validators, bidirectional isolation evidence, reconnection convergence, and cleanup criteria.
- **Design only; no partition test has been run or passed.** WP4.5's validator stop/restart test remains a crash-stop test and must not be described as partition testing.
- Implementation is gated on proving a reversible, auditable network isolation mechanism on the CI runner while all validator and ABCI processes remain alive. If the runner cannot provide this, the test must fail closed or move to a dedicated environment; do not downgrade it to a process-stop test.
- `main` remains unchanged.


## 14. Current verified status — 2026-11-04

This section supersedes earlier design-only status statements where later evidence has passed. Earlier sections remain as a dated implementation history.

### WP4.7 — live network partition and reconnection

- Implemented 12 directed loopback-only TCP relays for the four-validator local harness; PEX is disabled and validator P2P peer IDs are checked against the exact expected peer set.
- **3/1 scenario:** the 3-validator side advanced while the isolated fourth validator remained unchanged; after reconnection all four converged.
- **2/2 scenario:** neither half advanced during the 12-second observation window; after reconnection all four converged.
- The tests require all four CometBFT and all four HND ABCI processes to remain alive during partition.
- Strict-peer-check CI evidence: [run 41721112365](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41721112365), commit `4c19be099860cb801bfcfe88bb2f558e4ce75b1b`.
- Regression evidence with the signer guard added: [run 41723251514](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41723251514), commit `027a0db12ac391462ff97027df138491a3e83102`.

WP4.7 is implemented and CI-tested for these bounded local scenarios. It is not a Byzantine fault-tolerance proof.

### WP4.8 — CometBFT FilePV signer guard

- Added `scripts/cometbft_v040_privval_signing_smoke.go`, using the pinned CometBFT v0.40.0 `privval.FilePV`.
- The test verifies same-HRS signature reuse, rejection of conflicting votes and proposals, rejection of height/round regressions, valid prevote-to-precommit step progression, and persistence of the signing guard across signer reload.
- CI emitted `COMETBFT_V040_PRIVVAL_SIGNER_GUARD_OK`.
- Detailed report: `docs/WP4_8_COMETBFT_VALIDATOR_SIGNER_GUARD_2026-11-04.md`.

This verifies selected local FilePV behavior only. It does not validate malicious remote signers, Byzantine network behavior, or consensus safety under arbitrary faults.

### Durable application-store hardening

- Application store schema advanced to version 2.
- Added a deterministic SHA-256 integrity checksum over canonicalized store metadata and snapshot fields.
- Added duplicate JSON object-key rejection and tests for height metadata tampering and invalid checksums.
- Schema v1 stores are not automatically migrated by the current loader.
- The unkeyed checksum is an integrity check, not an authenticity mechanism or MAC.

### Full CI evidence

The full workflow [41723251514](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41723251514) completed successfully on commit `027a0db12ac391462ff97027df138491a3e83102`:

- 133 Python tests passed.
- CometBFT v0.40.0 build and signer guard smoke passed.
- Single-node ABCI integration and restart passed.
- Four-validator Genesis/identity preflight passed.
- Four-validator crash-stop/restart, 3/1 partition, 2/2 partition, and reconnection convergence passed.

All these tests use disposable local test identities and synthetic HND allocations. They do not authorize public token issuance or real-value activity.

### Next work package — WP4.9 adversarial consensus-message test design

The next technical gate is a controlled remote-signer / Byzantine-message fault-injection design:

1. Use only CometBFT v0.40.0's documented remote-signer interfaces, isolated to loopback or a temporary Unix socket.
2. Use disposable test keys and a deliberately faulty test signer, never a production key.
3. Exercise one validator withholding votes and, separately, a signer attempting to issue conflicting votes at the same height/round/type.
4. Record whether honest validators remain on one committed history, whether CometBFT reports duplicate-vote evidence, and whether the remaining quorum can make progress.
5. Keep 2/2 no-quorum behavior as a separate safety/liveness observation; do not treat it as proof against arbitrary Byzantine behavior.
6. Require deterministic cleanup and CI logs that do not contain private keys.

This is **planned work**, not implemented or passed. Snapshot/state-sync, production database durability, remote signer/HSM security, operational key custody, independent security review, governance, and jurisdiction-specific legal review remain open gates.

All work remains on `phase-0.2-planning`. The `main` branch is unchanged. Public release and real-value activity remain blocked by the G2–G4 gates.


### WP4.9 — pinned remote-signer source inspection — 2026-11-04

- Inspected the exact upstream CometBFT `v0.40.0` `privval` implementation and recorded findings in `docs/WP4_9_COMETBFT_V040_REMOTE_SIGNER_SOURCE_INSPECTION_2026-11-04.md`.
- Confirmed the remote private-validator protocol uses length-delimited protobuf `privval.Message` envelopes, not gRPC. The node-side listener accepts the external signer connection; the signer-side dialer connects to it.
- Distinguished the HND ABCI gRPC server/probe from the separate private-validator signing protocol.
- Recorded transport security distinctions: Unix sockets are unencrypted; TCP uses CometBFT secret connections; the pinned source also exposes a Noise listener with signer peer-ID allowlisting. No public endpoint or production key is used for the initial probe.
- **Status: source inspection complete; the disposable-key protocol probe passed in CI run `41737868856` (step 9, `Run pinned CometBFT remote signer protocol conformance probe`). A second probe, `scripts/cometbft_v040_remote_signer_process_probe.go`, has now been added and wired immediately after it in CI to launch the signer as a separate child process; this process-isolation probe is pending its own CI execution.** The same run also passed the FilePV anti-double-sign smoke, single-node ABCI smoke, and four-validator Genesis/identity preflight. The private four-validator network smoke was still running at the latest check, so the full workflow is not yet green. The probe exercises the pinned client/server API over a private temporary Unix socket and verifies public-key retrieval, vote/proposal signatures, and wrong-chain-ID refusal. Because Unix sockets are unencrypted and the signer runs in the same test process for this first probe, this is protocol/API conformance only—not proof of authenticated transport or process isolation. Next gate: run the signer in a separate test process and then integrate it into the honest four-validator baseline.
- CI runs #100 and #101 both completed the isolated HND v0.2 tests successfully. Their single-node/4-validator job had passed the signer anti-double-sign smoke, single-node ABCI smoke, and Genesis/identity preflight; the private four-validator network smoke was still running at the latest status check. No full-workflow success is claimed.

### WP4.9 — adversarial consensus-message test design added — 2026-11-04

- Added `docs/WP4_9_ADVERSARIAL_CONSENSUS_TEST_DESIGN_2026-11-04.md`.
- The design separates the honest remote-signer baseline, withheld-vote liveness test, correct-signer same-HRS conflict refusal, malicious equivocation injection, and 2/2 no-quorum control.
- The existing four-validator voting power is 10 each (40 total): three validators provide 30/40 (75%), which is above the strict two-thirds threshold; two validators provide 20/40 (50%), which is insufficient.
- The design requires the remote-signer wire protocol and connection behavior to be verified against the exact pinned CometBFT v0.40.0 source before implementation. No assumed protocol or unverified test hook may be introduced.
- **Status: design only. No WP4.9 remote-signer or Byzantine-message scenario has been implemented or passed.** The next implementation gate is a pinned-source remote-signer protocol conformance probe using disposable keys, followed by the honest remote-signer baseline.
- Any malicious conflicting-vote injection must use an auditable test path supported by the pinned version; if none exists, that scenario remains design-only rather than modifying consensus internals to manufacture a pass.
- All changes remain on `phase-0.2-planning`; `main` is unchanged. Public release and real-value activity remain blocked by G2–G4.
