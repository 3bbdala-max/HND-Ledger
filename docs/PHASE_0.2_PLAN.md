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


### WP4.9 — separate-process remote-signer baseline passed — 2026-11-04

- The process-isolated probe `scripts/cometbft_v040_remote_signer_process_probe.go` passed in GitHub Actions run [41738318170](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41738318170), tested commit `5afc626e49076d7555c171dcd4c98199cfd8e622`, step 10: `Run process-isolated pinned CometBFT remote signer probe`.
- The step ran after the pinned CometBFT v0.40.0 build and both signer smoke probes, and before the single-node ABCI, four-validator Genesis/identity preflight, and private four-validator network smoke steps. Both jobs in this run completed successfully.
- The probe launches the signer as a separate child process and connects through a private temporary Unix socket. It checks Ping, public-key retrieval, vote/proposal signing and signature verification, and wrong-chain-ID refusal; temporary resources are cleaned up.
- This closes the separate-process baseline gate for the local Unix-socket test. It does **not** establish encrypted/authenticated transport, remote-host security, HSM isolation, or resistance to a malicious signer. Unix sockets are unencrypted and remain local-test-only here.
- A later workflow run [41738336580](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41738336580) has also passed the isolated HND v0.2 test job and the process-isolated signer step; its private four-validator network integration step was still in progress at the latest check. Do not record that later full workflow as green until its network step and job finish successfully.
- Next gate: run the honest remote-signer as an independently managed process in the four-validator harness, then design/execute withheld-vote and reconnect scenarios. Inspect and validate the pinned Noise signer identity/dialer lifecycle before claiming authenticated transport. Malicious equivocation remains blocked until an auditable, pinned-version-supported injection path is demonstrated.

All changes remain on `phase-0.2-planning`; `main` is unchanged. Public release and real-value activity remain blocked by G2–G4.


### WP4.9 — separate-process probe regression and four-validator integration design — 2026-11-04

- The regression workflow [41738336580](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41738336580), commit `513c8730dbcb8b8a1d06c2f38aef6c50bae1eb6b`, completed successfully. Both jobs passed, including the process-isolated remote-signer probe (step 10), single-node ABCI integration, Genesis/identity preflight, and the full existing private four-validator network smoke (step 13). The isolated HND v0.2 test job also passed.
- Added `docs/WP4_9_FOUR_VALIDATOR_REMOTE_SIGNER_INTEGRATION_DESIGN_2026-11-04.md`. It defines the next implementation gate: validator 4 uses a separate signer process and temporary Unix socket; its disposable signing key and last-sign state remain in signer-owned temporary storage; the node's `priv_validator_laddr` config is set from the exact CometBFT v0.40.0 `BaseConfig.PrivValidatorListenAddr` field; the other three validators remain on local FilePV.
- The design requires Genesis public-key matching, an honest four-node transfer/convergence baseline, signer restart/reconnect, validator catch-up, fail-closed behavior, and cleanup. It does not claim that this design is implemented or passed.
- **Current state:** separate-process standalone signer probe passed; the pre-existing four-validator crash-stop/partition regression passed again in the same CI run; the four-validator remote-signer integration itself remains not yet implemented. Withheld-vote and malicious-equivocation scenarios remain open.

All changes remain on `phase-0.2-planning`; `main` is unchanged. Public release and real-value activity remain blocked by G2–G4.


### WP4.9 — four-validator external remote-signer integration and outage recovery passed — 2026-11-04

- Full GitHub Actions workflow [41741779949](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41741779949) completed with **success** on commit `e30768db086b89fbb58bbb8edf1214c376b0b971`; both `hnd-v02-tests` and `cometbft-single-node-smoke` jobs passed.
- The CometBFT job passed the FilePV signer guard, remote-signer protocol conformance probe, separate-process remote-signer probe, single-node ABCI integration/restart, four-validator Genesis/identity preflight, ordinary four-validator network regression, and the four-validator external remote-signer integration.
- External signer outage recovery emitted `COMETBFT_V040_REMOTE_SIGNER_OUTAGE_RECOVERY_OK`: validator 4's signer process was stopped; the remaining three validators committed the next transfer; the signer was restarted; and all four validators converged at height 4 with matching HND account state.
- Validator 4 process restart/catch-up passed after the test harness removed the stale disposable Unix-socket pathname and waited for the restarted node-side listener before launching a fresh signer process.
- In the same external-signer run, live 3/1 isolation and reconnection passed, the 2/2 no-quorum observation held for 12 seconds with heights/block hashes/application hashes unchanged, and all four validators converged after reconnection. The run emitted `COMETBFT_V040_FOUR_VALIDATOR_NETWORK_OK`.
- This closes the honest external remote-signer integration and bounded crash/restart/partition recovery gate for the tested local Unix-socket configuration.
- **Still open:** deliberate withheld-vote behavior (distinct from signer process outage), correct remote signer's conflicting same-HRS vote/proposal refusal and durable refusal after restart, malicious equivocation injection/evidence capture, authenticated/encrypted remote transport review, production key custody, and independent security review. The current integration does not prove arbitrary Byzantine fault tolerance.
- All keys/state were disposable local test material. No public endpoint, production key, real-value transfer, or mainnet was used. `main` remains unchanged; public release and real-value activity remain blocked by G2–G4.

### WP4.9 — pinned CometBFT Byzantine equivocation/evidence regression passed — 2026-11-04

- The repaired full workflow [41743365510](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41743365510) completed with **success** on commit `fb75406daa532342698488023c84c3f6acf33fec`; both `hnd-v02-tests` and `cometbft-single-node-smoke` jobs passed.
- Step 8, `Run pinned CometBFT Byzantine prevote equivocation and evidence regression`, passed against the pinned CometBFT v0.40.0 source using `go test ./consensus -run '^TestByzantinePrevoteEquivocation$' -count=1 -v`.
- The same full job also passed the FilePV anti-double-sign guard, remote-signer protocol conformance, separate-process signer, connected vote-withholding probe, remote anti-double-sign persistence across restart, single-node ABCI integration, four-validator Genesis/identity preflight, four-validator network integration, and external remote-signer outage/recovery integration.
- **Scope distinction:** this is a pinned upstream CometBFT regression demonstrating that CometBFT's own consensus/evidence test detects the deliberately equivocal validator and validates duplicate-vote evidence in its test network. It is not yet an HND-specific malicious-peer injection test or an end-to-end HND application evidence/penalty policy test. Those remain separate work.
- The workflow repair itself was necessary after a malformed YAML edit caused earlier runs to start zero jobs; the repaired workflow is now confirmed green.
- All work remains on `phase-0.2-planning`; `main` is unchanged. No production keys, public network, or real-value activity were used. Authenticated/encrypted remote transport, production key custody, independent security review, governance, and jurisdiction-specific legal review remain open. Public release remains blocked by G2–G4.

### WP4.9 — remote-signer transport security source review recorded — 2026-11-04

- Added `docs/WP4_9_COMETBFT_V040_REMOTE_SIGNER_TRANSPORT_SECURITY_REVIEW_2026-11-04.md` after reviewing the pinned CometBFT v0.40.0 Unix, TCP secret-connection, and Noise listener implementations.
- Unix sockets are explicitly unencrypted in the pinned source; the listener contains a TODO for MAC authentication. Retain them for tightly isolated same-host tests, not as a general remote-host production transport.
- TCP uses CometBFT SecretConnection for authenticated encryption, but secure deployment still depends on durable identity provisioning, pinning, rotation, and negative tests. Encryption alone does not establish that the peer is the intended signer.
- The Noise listener performs an authenticated Noise handshake and enforces a signer peer-ID allowlist when configured. The source explicitly warns that an empty allowlist accepts any authenticated peer and must not be used in production.
- **No production transport is approved.** Noise is the leading candidate for an HND-specific integration spike, conditional on a verified signer dialer lifecycle, stable peer identity, non-empty allowlist, unauthorized-peer rejection, restart/reconnect tests, and independent review.
- Production key custody, HSM/KMS integration, durable backup/rollback protection, operational procedures, independent security review, governance, and legal review remain open. All work remains on `phase-0.2-planning`; `main` is unchanged.

### WP4.9 — authenticated Noise remote-signer probe added; CI pending — 2026-11-04

- Added `scripts/cometbft_v040_noise_remote_signer_probe.go` using the pinned v0.40.0 public `privval.NewSignerListenerFromAddr`, `NewSignerDialerEndpoint`, and `NewSignerServer` APIs.
- The probe uses disposable Ed25519 identities and loopback only. It exercises an authorized signer through a Noise handshake, Ping, public-key retrieval, vote signing, and signature verification; a separate negative case requires the Noise listener to reject a peer identity absent from its explicit allowlist.
- Added the probe to `.github/workflows/hnd-v02-tests.yml` after the existing separate-process Unix-socket probe.
- Triggered CI run [41790821353](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41790821353) on commit `eec2c78f84c58e5238b67f51baef56f22759344e`. At the time this note was written, the first HND unit-test job was still running; the Noise probe has **not yet been confirmed as compiled or passed**.
- This is an isolated transport integration probe, not yet a Noise-backed four-validator network test, production transport approval, or security certification. Keep the result pending until the complete CI job finishes green and the Noise-specific step is confirmed successful.


### WP4.9 — authenticated Noise remote-signer probe passed — 2026-11-04

- Full GitHub Actions workflow [41791350660](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41791350660) completed with **success** on commit `5359321ae76e3ee029d325f59d111ba9d2ca4159`; both `hnd-v02-tests` and `cometbft-single-node-smoke` jobs passed.
- The Noise-specific step emitted `COMETBFT_V040_NOISE_REMOTE_SIGNER_AUTHORIZED_OK`, `COMETBFT_V040_NOISE_REMOTE_SIGNER_UNAUTHORIZED_REJECTED`, and `COMETBFT_V040_NOISE_REMOTE_SIGNER_PROBE_OK`.
- The probe used disposable identities and loopback TCP. It verified authorized Noise peer authentication, remote-signer Ping/public-key/signature flow, signature validity, and rejection of an identity absent from the configured allowlist.
- The same full workflow passed the pinned Byzantine prevote/evidence regression, FilePV anti-double-sign guard, Unix-socket protocol/process-isolation probes, connected vote-withholding probe, remote anti-double-sign persistence after restart, single-node ABCI integration, four-validator Genesis/identity preflight, four-validator network integration, external remote-signer outage/recovery, 3/1 partition/reconnection, and 2/2 no-quorum/reconnection tests.
- **Scope limitation:** the Noise test is a standalone authenticated remote-signer transport probe. The four-validator integration still uses the separately tested local Unix-socket remote signer; Noise has not yet been integrated into the four-validator harness. No production transport is approved.
- Next gate: integrate the Noise transport into a disposable validator signer in the four-validator harness, then test signer restart/reconnect, unauthorized identity rejection at the integrated boundary, validator catch-up, and failure behavior. Preserve explicit peer-ID allowlisting and disposable keys.
- Production identity provisioning/rotation, HSM/KMS custody, rollback protection, operational controls, independent security review, governance, and jurisdiction-specific legal review remain open. Public release and real-value activity remain blocked by G2–G4.
- All changes remain on `phase-0.2-planning`; `main` is unchanged.


### WP4.9 — Noise-backed four-validator integration design added — 2026-11-04

- Added `docs/WP4_9_FOUR_VALIDATOR_NOISE_REMOTE_SIGNER_DESIGN_2026-11-04.md` after the standalone authenticated Noise probe passed in workflow [41791350660](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41791350660).
- The design is grounded in the pinned v0.40.0 `privval/utils.go` and `privval/noise_listener.go`: the node-side Noise listener uses the CometBFT P2P `node_key.json` identity and allowlists the signer peer ID encoded in `noise://<signer-peer-id>@IP:port`; the remote signer separately pins the expected node peer ID for its outbound Noise handshake.
- The validator consensus FilePV key/state remains signer-owned and distinct from both the node P2P identity and the signer's transport identity. The signer transport identity must remain stable across process restart.
- The design specifies authorized and unauthorized signer tests, signer outage/restart, validator restart/catch-up, 3/1 and 2/2 partition/reconnection, fresh connection markers, and fail-closed checks.
- **Status: design only. Noise has not yet been integrated into the four-validator harness.** Implementation and full CI evidence are the next gate; no production transport is approved.
- All work remains on `phase-0.2-planning`; `main` is unchanged. Production identity provisioning/rotation, HSM/KMS custody, rollback protection, independent security review, governance, and jurisdiction-specific legal review remain open. Public release remains blocked by G2–G4.


### WP4.9 — Noise transport wired into four-validator harness; CI pending — 2026-11-04

- Added `scripts/cometbft_v040_noise_remote_signer_helper.go`, a disposable persistent signer helper with a separate Noise transport identity, a pinned expected validator-node peer ID, and the existing validator FilePV key/state.
- Extended `scripts/cometbft_v040_four_validator_network_smoke.py` with `--noise-remote-signer-binary`. In this mode validator 4's `priv_validator_laddr` is configured as `noise://<signer-peer-id>@127.0.0.1:<port>`; the signer transport identity is generated once and retained across restarts.
- Added an integrated negative probe that dials validator 4 using a fresh unauthorized Noise identity and requires the handshake to fail at the node's configured signer-peer allowlist.
- The harness now runs the existing signer outage/quorum/recovery and validator-4 restart/catch-up sequence through the Noise transport when the new flag is selected. It also retains the existing Unix-socket integration as a separate regression.
- CI workflow now builds the Noise helper and invokes the four-validator harness in Noise mode. The first complete workflow for this integration is pending; no pass is claimed until the new helper build, unauthorized-peer check, and full Noise-backed four-validator run all succeed.
- Current code remains test-only, loopback-bound, with disposable identities. Production transport approval remains blocked pending full CI, durable identity lifecycle design, HSM/KMS custody, independent security review, and release gates G2–G4.


### WP4.9 — Noise-backed four-validator remote-signer integration passed — 2026-11-04

- Full GitHub Actions workflow [41795296240](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41795296240) completed with **success** on commit `622a6f7a00b74f47f5a9aa0f4fd872a04ff113c9`; both `hnd-v02-tests` and `cometbft-single-node-smoke` jobs passed.
- The Noise-backed four-validator step completed successfully. The job log confirms the integrated Noise transport path ran through signer outage/restart, three-validator quorum progress, signer reconnection, 3/1 partition/reconnection, 2/2 no-quorum observation (12 seconds with heights and hashes unchanged), and final four-validator convergence.
- The same workflow retained and passed the Unix-socket external signer regression, the standalone authorized/unauthorized Noise probe, the pinned CometBFT Byzantine prevote/evidence regression, FilePV anti-double-sign checks, vote-withholding probe, durable anti-double-sign restart test, ABCI integration, and Genesis/identity preflight.
- A prior helper panic on rejected unauthorized Noise handshakes was corrected by avoiding `Close()` on a partially initialized Noise secure session when the handshake returns an error. The resulting full workflow is green.
- **Scope limitation:** this is a disposable, loopback-only four-validator integration using temporary test identities and state. It demonstrates the tested CometBFT v0.40.0 Noise remote-signer lifecycle and bounded crash/restart/partition recovery; it is not a Byzantine fault-tolerance proof, a production deployment, or approval of a production transport/key-custody design.
- **Next gate:** implement an HND-specific malicious-peer equivocation/evidence test using the actual pinned CometBFT P2P VoteChannel path, disposable faulty test identities, and verified evidence lifecycle; do not bypass the reactor with direct VoteSet insertion. Then complete production key-custody/operational threat review and obtain independent security review.
- Production peer identity provisioning/rotation, HSM/KMS or offline key custody, backup/rollback protection, operational controls, independent security review, governance, and jurisdiction-specific legal review remain open. Public release and real-value activity remain blocked by G2–G4.
- All changes remain on `phase-0.2-planning`; `main` is unchanged.


### WP4.10 — ABCI evidence-handling boundary reviewed; design recorded — 2026-11-04

- Pinned CometBFT v0.40.0 source confirms ABCI++ `RequestFinalizeBlock` carries repeated `Misbehavior` summaries (type, validator address/power, infraction height/time, and total voting power). The full signed vote pair remains in CometBFT's internal evidence object; the ABCI summary is not the full cryptographic evidence.
- Inspection of `hnd_v02/cometbft_v040_server.py` and `hnd_v02/abci_app.py` found that the current HND adapter passes only block height and transactions to `finalize_block`; it currently ignores `request.misbehavior`. Thus CometBFT evidence detection is tested upstream, but HND application-level evidence accounting is not implemented.
- Added `docs/WP4_10_ABCI_EVIDENCE_HANDLING_DESIGN_2026-11-04.md` proposing a deterministic, append-only, non-punitive evidence audit journal, including validation, state commitment, persistence, queries, and end-to-end tests.
- No slashing, burning, freezing, confiscation, or balance changes are proposed: HND v0.2 has no defined staking, validator ownership, appeal, or governance penalty policy. Any economic consequence requires a separate protocol decision.
- **Status: source review/design only; no application evidence journal or HND-specific end-to-end evidence test has been implemented or passed.** Next gate is implementing the neutral audit journal and proving ABCI misbehavior reaches and persists in HND application state.
- This is separate from the successful Noise four-validator integration in run [41795296240](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41795296240), which remains a bounded local transport/recovery test, not a Byzantine proof.
- All work remains on `phase-0.2-planning`; `main` is unchanged. Public release and real-value activity remain blocked by G2–G4.


### WP4.10 — evidence journal implementation and CI passed — 2026-11-04

- Implemented deterministic CometBFT misbehavior normalization at the pinned v0.40.0 ABCI adapter boundary and an append-only, audit-only HND evidence journal.
- The journal is included in the application state commitment and durable store, validated on load, deduplicated deterministically, and exposed through read-only `/evidence` query.
- Adapter and application tests verify protobuf misbehavior handoff, persistence/reload, duplicate idempotence, and unchanged account balances.
- Full workflow [41836087031](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41836087031) passed on commit `2c35ee51e3384de154772c9a25031c27e6a1c908`. Both `hnd-v02-tests` and `cometbft-single-node-smoke` jobs succeeded; the latter also reran the upstream CometBFT Byzantine regression and existing four-validator, partition, and signer integrations.
- **Scope limitation:** the upstream Byzantine regression and HND adapter test are separate test layers. The run does not yet prove an actual P2P equivocation event flowing through CometBFT into live HND ABCI applications or evidence-hash convergence across HND replicas.

### WP4.11 — HND P2P equivocation/evidence convergence design — 2026-11-04

- Added `docs/WP4_11_HND_NETWORK_EQUIVOCATION_EVIDENCE_INTEGRATION_DESIGN_2026-11-04.md`.
- The next gate requires a disposable four-validator scenario using the actual CometBFT P2P VoteChannel, a test-only faulty validator, live HND ABCI app processes, evidence queries on all replicas, identical application hashes, and restart/catch-up verification.
- Direct VoteSet insertion or direct fabrication of ABCI misbehavior records is explicitly disallowed as a substitute for the real network path.
- **Status: design only; HND-specific P2P-to-ABCI evidence injection has not yet been implemented or passed.**
- No slashing or balance changes are authorized by this workstream. The evidence journal remains audit-only.
- All changes remain on `phase-0.2-planning`; `main` is unchanged. Public release and real-value activity remain blocked by G2–G4.


### WP4.11 — HND P2P equivocation-to-ABCI evidence integration passed — 2026-11-04

- Full workflow [41840460178](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41840460178) passed on commit `7864986c27f1b6bf0daaa2d13d03365988e9e52d`; both CI jobs succeeded.
- The HND-specific integration reuses the pinned CometBFT v0.40.0 Byzantine test harness and retains the real P2P VoteChannel conflicting-prevote injection and CometBFT evidence-pool path while connecting four independent live HND ABCI applications.
- The integration emitted `HND_WP4_11_P2P_EVIDENCE_REPLICAS_OK`: four replicas, one evidence record, infraction/evidence height 2, committed height 3, unchanged balances, and successful restart verification.
- The reported common application hash was `bafc894edeb3fd89fb2bf79b7953368787504d39add4e3e6fa3e7abe5e5cf661`; the test acceptance checks compare canonical evidence journal bytes, evidence IDs, committed heights, and 32-byte app hashes across all four replicas.
- **WP4.11 test gate: passed for this disposable CI scenario.** This does not establish production Byzantine fault tolerance or HND-side independent cryptographic verification of the signed vote pair; HND persists CometBFT's ABCI misbehavior summary as audit evidence only.
- No slashing, burning, freezing, confiscation, or balance changes are implemented. Test keys and state are disposable and loopback-only.
- Next engineering gate: multi-node deterministic state-hash consistency and broader fault-injection coverage, followed by production key-custody/operations design and independent security review. Governance and jurisdiction-specific legal review remain mandatory before any public release or real-value activity.
- All changes remain on `phase-0.2-planning`; `main` is unchanged. G2–G4 release gates remain closed.


### WP4.12 — four-replica deterministic state/hash consistency passed — 2026-11-04

- Added `tests/test_v02_four_replica_state_convergence.py` and wired it into the HND v0.2 CI job. Four independent HND application instances start from the same Genesis/manifest and independent durable state files; identical ordered transactions are applied and committed; FinalizeBlock hashes, Commit hashes, heights, account balances, total supply, and 32-byte Info app hashes are compared.
- The test restarts one HND application process from its durable state and verifies restoration of the committed height and app hash.
- A negative control commits different but individually valid same-height transactions on one replica versus the other three. The comparator must report `app_hash_mismatch`, despite equal heights; it must not label the replicas converged.
- Full workflow [41843665525](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41843665525) completed with **success** on commit `4c551b26886e967200c6a21669d3b00c72e398e9`. Both `hnd-v02-tests` and `cometbft-single-node-smoke` jobs passed. The isolated Python suite reported 139 tests without failures, and all CometBFT integration steps in the same workflow completed successfully.
- **WP4.12 acceptance gate: passed for the specified application-layer consistency/divergence regression and this CI run.** The test does not itself run four CometBFT consensus processes or prove network consensus, Byzantine fault tolerance, automatic repair, or production durability.
- Next gate: implement and verify full CometBFT node-process restart and catch-up from durable HND ABCI state, then broaden multi-node fault injection. Production key custody/operations, independent security review, governance, and jurisdiction-specific legal review remain open. G2–G4 release gates remain closed.
- All changes remain on `phase-0.2-planning`; `main` remains unchanged.


### WP4.13 — durable ABCI state and CometBFT node restart recovery design — 2026-11-04

- Added `docs/WP4_13_DURABLE_ABCI_NODE_RESTART_RECOVERY_DESIGN_2026-11-04.md`.
- This strengthens, rather than replaces, the existing passing four-validator restart/catch-up scenario. The new gate requires explicit pre-stop height/block/app-hash and account-state capture, durable HND state-file identity/digest, proof of actual process exit, exact HND state restoration before CometBFT restart, then normal CometBFT node restart using the original home/validator identity and block replay catch-up.
- It also defines fail-closed negative controls for missing/truncated/alternate state files, mismatched Genesis/network identity, replaced signer state, timeout, and post-recovery divergence.
- **Status: design only; implementation and CI validation pending.** Existing WP4.5/WP4.9 restart tests remain valid for their previously documented scope; WP4.13 adds stronger durability evidence and negative controls.
- No production durability, power-loss recovery, snapshot state sync, production key custody, or Byzantine fault-tolerance claim is made. Public release and real-value activity remain blocked by G2–G4.
- All work remains on `phase-0.2-planning`; `main` remains unchanged.


### WP4.13 — core durable restart/recovery integration passed; remaining negative controls tracked — 2026-11-04

- Full CI workflow [41858224733](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41858224733) passed on commit `efa81f43238cc060542c1fd1375f707adee6fc06`; both workflow jobs succeeded and the isolated HND suite reported 143 passing tests.
- The four-validator CometBFT v0.40.0 harness verified pre-stop evidence, actual HND ABCI and CometBFT process exit, durable HND state-file recovery, node restart with the original home and identities, normal block-replay catch-up, and four-replica convergence. Explicit WP4.13 recovery markers were recorded in [run 41852320612](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41852320612).
- The latest full workflow passed both external signer recovery paths (Unix and authenticated Noise), including fail-closed negative probes for missing anti-double-sign state. HND state-load tests also reject truncated state and mismatched network/Genesis state.
- **Status:** Core WP4.13 restart/recovery integration passed for the tested scenarios. The full recovery-specific negative-control matrix is not yet closed: explicit tests for alternate/replaced signer state, validator identity mismatch on restart, bounded recovery timeout, and deliberately induced post-recovery application divergence remain to be added. Existing related Noise authorization, vote-withholding, and WP4.12 divergence tests are not counted as substitutes for those exact cases.
- Detailed evidence and scope boundaries: `docs/WP4_13_DURABLE_ABCI_NODE_RESTART_RECOVERY_DESIGN_2026-11-04.md`.
- All work remains on `phase-0.2-planning`; `main` is unchanged. No production keys, public network, or real-value activity were used. Production key custody, independent security review, governance, and jurisdiction-specific legal review remain open.

### WP4.14 — production key custody, backup, and recovery architecture — design gate opened — 2026-11-04

- Next workstream is design-only. It will specify production-grade validator and remote-signer key lifecycle, HSM/KMS or offline custody options, peer/validator identity pinning, backup encryption and access separation, recovery drills, rotation, revocation, incident response, and auditability.
- No production private keys, seed phrases, cloud credentials, HSM credentials, or real signer material are to be generated, uploaded, or stored in this repository.
- No key export, production signing, or custody integration will be implemented before the architecture, threat model, and independent security review are complete.
- Added `docs/WP4_14_KEY_CUSTODY_BACKUP_RECOVERY_DESIGN_2026-11-04.md` with the key inventory, threat model, signer isolation, HSM/KMS/offline custody options, backup/restore ceremony, rotation/revocation, incident response, and verification gates.
- **Status:** design gate only; no production custody implementation or approval. Public release and real-value activity remain blocked by G2–G4.


### WP4.13 — negative recovery controls design recorded — 2026-11-04

- Added `docs/WP4_13_NEGATIVE_RECOVERY_CONTROLS_DESIGN_2026-11-04.md` after reviewing the current signer helper and four-validator recovery harness.
- The design specifies four distinct negative controls: alternate signer anti-double-sign state substitution, valid-but-unexpected consensus/P2P identity substitution, bounded recovery timeout, and deliberate post-recovery replica divergence.
- **Status: design only. No new negative-control implementation or CI pass is claimed.** The existing WP4.13 happy-path integration remains passed for its documented scope; WP4.13 remains open until the exact controls are implemented and CI-tested.
- The design explicitly distinguishes a CI-run expected digest from production anti-rollback protection. Production rollback resistance still requires an independently trusted anchor, such as an HSM/KMS monotonic counter or separately protected signing-state service.
- All changes remain on `phase-0.2-planning`; `main` is unchanged. G2–G4 remain closed.


### WP4.13 — signer-state substitution guard implemented; CI pending — 2026-11-04

- The Unix remote-signer recovery helper now requires an expected SHA-256 digest in recovery mode and checks the actual anti-double-sign state file before calling `privval.LoadFilePV` or opening its signer endpoint.
- The four-validator restart harness captures the signer-state digest before shutdown and supplies it during the normal recovery path.
- CI now includes a negative probe that creates a distinct, parseable signer state by signing a disposable vote, then verifies that recovery rejects that substituted state before starting the signer.
- **Status: implementation committed; validation pending.** This is a same-run test-harness integrity check, not production anti-rollback protection. It does not protect against an attacker who can also replace the expected digest, and it currently covers the Unix helper path; Noise signer recovery and the other three negative controls remain outstanding.
- WP4.13 remains open until the new CI run passes and the remaining negative controls are implemented and verified. `main` remains unchanged.


### WP4.13 — Noise signer state-digest guard added; CI pending — 2026-11-04

- Extended the same expected-state-digest preflight to the authenticated Noise signer helper. Both Unix and Noise recovery paths now reject a state-file digest mismatch before loading the FilePV or starting the signer endpoint.
- The four-validator harness supplies the captured pre-stop signer-state digest to the appropriate recovery helper for either transport.
- CI includes a dedicated Noise digest-mismatch preflight probe in addition to the Unix probe. The Unix integration probe uses a distinct parseable FilePV state generated by a disposable vote; the Noise helper probe exercises the same digest-check function with distinct fixture contents.
- **Status: implementation committed; validation pending.** No new negative-control CI pass is claimed until the latest run completes. The digest anchor remains test-orchestrator supplied and is not production anti-rollback protection.


### WP4.13 — validator identity substitution controls added — 2026-11-04

- The four-validator restart harness now snapshots validator 4's semantic consensus public-key identity and CometBFT P2P node ID before shutdown.
- Before restarting the node, it deliberately substitutes validator 1's valid consensus key and separately its valid P2P node key into validator 4's disposable home. The identity preflight must reject each mismatch; the original files are restored in a `finally` block and checked again before node restart.
- **Status: implementation committed; CI pending.** These are test-harness preflight negative controls, not a production key-custody or filesystem tamper-proofing system. The current checks establish that unexpected identities are detected before restart.


### WP4.13 — integrated recovery and negative-control gate passed — 2026-11-04

- The final bounded-readiness implementation and the recovery negative-control matrix passed workflow [41883929479](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41883929479) on commit `f723cf981841a9c228bf1944a078a13b151de605`.
- Both `hnd-v02-tests` and `cometbft-single-node-smoke` jobs succeeded; the isolated Python suite reported **146 tests, all passing**.
- CI logs confirmed durable ABCI recovery, CometBFT restart/catch-up, alternate consensus/P2P identity rejection, Unix and authenticated Noise remote-signer outage/recovery, 3/1 and 2/2 partition/reconnection, and four-validator convergence.
- Integrated negative controls cover bounded readiness timeout without modifying durable state, height/block-hash mismatch, post-recovery application-hash divergence, truncated/mismatched persisted state, and missing/substituted remote-signer anti-double-sign state.
- **Status: WP4.13 CI acceptance gate passed for the enumerated disposable local test scenarios.** This supersedes the earlier WP4.13 entries above that state validation is pending or the controls are design-only; those entries remain as chronological implementation history.
- Scope remains local crash-stop integration, not proof of arbitrary Byzantine fault tolerance, power-loss durability, production backup/restore, or production key anti-rollback. WP4.14 custody/backup/recovery remains a separate design and implementation gate. G2–G4 remain closed; no public release or real-value activity is approved.


### WP4.14 — implementation readiness and verification plan recorded — 2026-11-04

- Added `docs/WP4_14_IMPLEMENTATION_READINESS_AND_TEST_PLAN_2026-11-04.md`.
- Converts the custody architecture into four staged work areas: independent review/decision freeze, synthetic local reference model, isolated provider-adapter evaluation, and supervised disaster-recovery rehearsal.
- Adds architecture decisions and a verification matrix covering missing/corrupt state, manifest tampering, chain/validator mismatch, rollback, atomic-write crash points, dual control, provider outage, rotation, and split-brain restore.
- Highlights the key limitation in the current test harness: a digest supplied by the same orchestrator is not an independent anti-rollback trust anchor.
- **Status: planning artifact only. WP4.14 is not implementation-approved.** Independent security review and explicit architecture decisions are prerequisites. No production keys, credentials, HSM/KMS resources, or production signing are created. G2–G4 remain closed.

### WP4.14 — independent anti-rollback trust-anchor ADR recorded — 2026-11-04

- Added `docs/WP4_14_ADR_ANTI_ROLLBACK_TRUST_ANCHOR_2026-11-04.md`.
- Establishes that a caller-supplied digest or same-host hash/manifest cannot serve as the production anti-rollback authority when the ordinary signer host is in the attacker model.
- Defines the required independent monotonic anchor contract: authenticated canonical record binding chain/network/genesis, validator and signer identities, state schema, height/round/step, sequence, full-state digest, predecessor, and idempotent transaction ID.
- Compares HSM monotonic counter, TPM NV counter, remote append-only witness, and multi-witness quorum without selecting a vendor. Explicitly notes that a counter alone does not prove atomic binding to the full state commitment.
- Specifies PREPARED/COMMITTED transaction semantics, crash reconciliation, fail-closed restore, dual control, and synthetic verification vectors TA01–TA14.
- Requires immutable state generations, retention of the prior committed generation until authenticated anchor read-back, serialized compare-and-swap transitions, and disabled signing during ambiguous commit/reconciliation states.
- **Status: proposed design requirement only. Independent security review and a synthetic reference model are still required.** No hardware, production keys, credentials, or production signing are used. G2–G4 remain closed.

### WP4.14 — Stage A security review register prepared — 2026-11-04

- Added `docs/WP4_14_STAGE_A_SECURITY_REVIEW_REGISTER_2026-11-04.md`.
- Records 14 open review topics, including anchor compromise and disaster recovery, first-time enrollment, commit atomicity, concurrent restore/fencing, schema migration, cryptographic agility, CometBFT state semantics, backup authenticity, audit independence, and provider assumptions.
- Defines ten mandatory state-machine invariants and the independent-review questions and exit criteria required before Stage A can close.
- Clarifies that an internal review register and green CI are not an independent security audit. The independent review has **not** been performed.
- **Status: Stage A remains open; Stage B's bounded offline synthetic reference model has been implemented and its dedicated tests passed in CI.** This does not constitute Stage A approval, does not establish completion of all C01–C18 cases, and does not authorize Stage C/D. Only offline synthetic preparation is permissible; no production key/custody operations or signing. G2–G4 remain closed.


## 14. WP4.14 synthetic reference model and CI acceptance evidence — 2026-11-04

This update records the completion of CI run [41890718611](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41890718611) for tested commit `1610824860081bd803a1b87fa3b89237b36f6ed1`.

- Both jobs, `hnd-v02-tests` and `cometbft-single-node-smoke`, completed successfully.
- The isolated v0.2 test suite, including the offline synthetic anti-rollback reference-model tests, passed.
- The CometBFT job passed the pinned Byzantine equivocation/evidence checks, signer and remote-signer probes, unauthorized Noise peer rejection, vote-withholding probe, anti-double-sign persistence/recovery checks, single-node ABCI smoke, four-validator Genesis/identity preflight, private four-validator network integration, external remote-signer outage recovery, and authenticated Noise remote-signer integration/recovery.
- Full step-by-step evidence and explicit scope limitations are recorded in `docs/WP4_14_CI_TECHNICAL_ACCEPTANCE_EVIDENCE_2026-11-04.md`.

**Acceptance boundary:** This is a green automated CI result for the exact tested commit. It does not establish production BFT guarantees, production key custody, hardware monotonicity, an independent anti-rollback trust anchor, independent security-audit completion, or legal/operational release readiness.

**WP4.14 disposition:** Stage B's synthetic offline reference-model test suite has passed CI. Stage A independent security review remains OPEN; the internal review register is not an independent audit. Stages C and D remain unauthorized/not started. No production keys, live HSM/KMS, provider credentials, or production signing endpoint may be introduced. G2–G4 remain closed.

All work remains on `phase-0.2-planning`. The `main` branch remains unchanged.

### WP4.14 — follow-up four-validator partition test stabilization passed — 2026-11-04

- CI run [41897803356](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41897803356) completed successfully on commit `097646a1795d59abc6044bf8993ebcbd68d2c882`; both `hnd-v02-tests` and `cometbft-single-node-smoke` passed.
- The 2/2 partition harness now waits for a stable four-validator height/block-hash snapshot before beginning its no-quorum observation window, avoiding a false failure caused by a block already in flight at the instant relays are isolated.
- The run passed the authenticated Noise four-validator integration, 3/1 partition and reconnection, 2/2 partition and reconnection, and final convergence checks.
- Detailed follow-up evidence is recorded in `docs/WP4_14_CI_TECHNICAL_ACCEPTANCE_EVIDENCE_2026-11-04.md`.

**Acceptance boundary:** This validates the corrected bounded CI scenario only. It does not prove arbitrary Byzantine safety/liveness, production key custody, independent monotonic anti-rollback, or production readiness. Stage A independent review remains OPEN; Stages C/D remain unauthorized/not started; G2–G4 remain closed. All changes remain on `phase-0.2-planning`; `main` remains unchanged.

