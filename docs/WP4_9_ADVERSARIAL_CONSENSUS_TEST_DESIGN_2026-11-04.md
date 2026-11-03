# HND v0.2 — WP4.9 adversarial consensus-message test design

**Date:** 2026-11-04  
**Workstream:** WP4.9 — controlled remote-signer and Byzantine-message fault injection  
**Status:** Design gate only; no adversarial signer test has passed  
**Branch:** `phase-0.2-planning`  
**Pinned consensus engine:** CometBFT v0.40.0

## 1. Purpose and boundaries

WP4.7 established bounded local network-partition behavior. WP4.8 exercised selected anti-double-sign behavior in CometBFT's local `privval.FilePV`. Neither proves how the four-validator network behaves when a validator's signing service is faulty or malicious.

This work package will test that gap using disposable validators, synthetic allocations, and a deliberately faulty test signer. It must not change the HND application transaction rules or introduce a second consensus implementation. CometBFT remains the sole consensus engine; the HND ABCI application remains responsible for deterministic transaction execution and state.

This is a controlled integration test, not a formal Byzantine fault-tolerance proof, security audit, or production-readiness certification.

## 2. Four-validator quorum model

The existing harness uses four validators with voting power 10 each (total power 40). CometBFT requires strictly more than two-thirds of total voting power for a commit:

- 3 validators = 30/40 = 75%: sufficient voting power.
- 2 validators = 20/40 = 50%: insufficient voting power.
- 1 validator = 10/40 = 25%: insufficient voting power.

A validator withholding votes should therefore leave the other three able to progress, provided they remain connected and otherwise healthy. A 2/2 partition remains a separate no-quorum scenario.

The test must read actual validator-set voting power from the running test network rather than relying only on hard-coded labels.

## 3. Remote-signer integration approach

Use only the remote private-validator interface supported by the exact pinned CometBFT v0.40.0 source and binary. Before implementation, inspect the pinned source for the concrete `priv_validator_laddr` / remote signer endpoint, message types, connection direction, framing, chain-ID validation, and retry behavior. Do not copy protocol assumptions from another CometBFT release.

The implementation must:

1. Configure exactly one test validator to use a disposable loopback-only remote signer endpoint; the other three retain independent disposable local signers.
2. Keep the remote signer's private key and monotonic last-sign state inside the signer process, not in the CometBFT node process.
3. Use the pinned CometBFT signer client and protocol messages; do not invent a JSON or HTTP signing API.
4. Bind only to loopback or a temporary Unix-domain socket. No public listener, external network route, cloud KMS, HSM, or production key is permitted.
5. Validate chain ID, validator public key, request type, height, round, step, and canonical sign bytes before a test signer returns any signature.
6. Record sanitized request metadata and outcomes only. Never log private keys, seed material, complete secret-bearing configuration, or raw credentials.
7. Fail closed: signer disconnect, malformed request, unknown request, or state-store error must return a signing error; there must be no fallback to a local key.
8. Remove all temporary keys, state, sockets, processes, and relay resources in guaranteed cleanup code.

## 4. Fault scenarios

### A. Honest remote signer baseline

- Start the four-validator network with validator 4 using the remote signer.
- Confirm the signer public key matches validator 4's Genesis identity.
- Commit a valid synthetic HND transfer.
- Require all four nodes to agree on height, block hash, application hash, and account balances.
- Restart the signer and validator 4 using the same temporary signer state; require safe reconnection and catch-up.

**Pass condition:** The remote-signer path behaves like the existing local signer for the tested normal operation, with no key material exposed to the node logs or CI artifacts.

### B. Withheld-vote fault

- Configure the test signer for validator 4 to withhold vote-signing responses while remaining connected and responsive to non-signing health checks where supported.
- Keep all four validator and ABCI processes alive.
- Submit a valid transaction to the three honest validators.
- Require the three honest validators (30/40 voting power) to commit and agree.
- Require the faulty validator not to sign a vote during the withholding interval.
- Restore normal signing and require validator 4 to catch up to the same committed history.

**Pass condition:** The honest 3/4 quorum makes progress; the withheld signer does not cause conflicting committed state; recovery converges.

### C. Conflicting-sign request / signer refusal

- Send two different vote requests for the same validator, height, round, and vote type, but with different block IDs.
- First run against a correct test signer: the first request may be signed; an identical retry must reuse the same signature; the conflicting request must be refused.
- Repeat after restarting the signer from persisted state; the conflict must still be refused.
- Repeat the equivalent conflicting-proposal test for the same height and round.
- Confirm the signer state is durable before acknowledging a successful signature.

**Pass condition:** A correct remote signer never returns two signatures for conflicting messages at the same H/R/step. The test must not label a refusal as evidence that CometBFT detected a network-level double vote.

### D. Deliberately faulty signer / equivocation evidence

This scenario is separate from the correct signer's refusal test. A disposable malicious signer will deliberately produce two cryptographically valid conflicting votes using its own temporary test key, bypassing the correct signer's anti-double-sign policy.

- Isolate this experiment from the baseline and withholding tests.
- Inject the conflicting signed votes through a test-only controlled path supported by CometBFT v0.40.0; do not weaken or patch the production HND ABCI application.
- Capture CometBFT's actual duplicate-vote evidence/log/event if the pinned version exposes it.
- Verify that the evidence identifies the validator and conflicting height/round/type and that the two signatures verify against the validator's public key.
- Record the network's observed behavior; do not assume that evidence emission alone means the protocol safely resolves every Byzantine scenario.

**Implementation gate:** Before writing this harness, prove from the pinned v0.40.0 source which public test hooks or peer-message path can inject a signed conflicting vote. If no supported, auditable injection path exists, keep this scenario design-only and report the limitation. Do not patch consensus internals just to force a green CI result.

### E. No-quorum control

- Partition the four validators into 2/2 while all processes remain alive.
- Require neither side to commit during a bounded observation window.
- Reconnect and require convergence.
- Treat this as a separate quorum/liveness control, not proof against arbitrary Byzantine behavior.

## 5. Evidence and acceptance criteria

Every passing CI report must record:

- exact commit SHA and CometBFT v0.40.0 source revision;
- exact validator identities by public-key fingerprint only;
- actual voting power and quorum calculation;
- signer mode for each validator (local or remote);
- sanitized signer request outcomes and time-bounded fault window;
- before/during/after heights, block hashes, application hashes, and relevant balances;
- whether all processes remained alive;
- whether a faulty signer was refused, withheld, or deliberately equivocated;
- cryptographic verification result for any conflicting signed messages;
- observed CometBFT duplicate-vote evidence, if any;
- successful recovery and catch-up;
- cleanup result for all temporary resources.

A CI marker is emitted only after all assertions for its named scenario pass. A design-only or skipped scenario must never emit a success marker.

## 6. Test separation and failure policy

Use separate test functions and temporary homes for:
- honest remote signer;
- withheld-vote signer;
- correct signer conflict refusal;
- malicious conflicting-vote injection;
- 2/2 no-quorum control.

A failure in one scenario must not contaminate the state or keys of another. Timeouts, unexpected commits, signer fallback, wrong public key, invalid signature, missing evidence, log-secret detection, process exit, or cleanup failure must fail the job.

The malicious signer must be incapable of accessing any non-test key. The test network must have no route to a public chain or real-value service.

## 7. Security limitations

Even if all scenarios pass, the evidence will be limited to the pinned CometBFT version and the specific controlled local test conditions. It will not prove:
- safety under arbitrary Byzantine voting power or every possible message schedule;
- correctness of an HSM, cloud KMS, external signer, or multi-operator key custody;
- WAN, long-duration partition, censorship, DDoS, or economic attack resistance;
- production-grade database durability or snapshot/state-sync correctness;
- absence of all implementation vulnerabilities.

Independent security review, remote-signer threat modeling, key-custody design, production persistence, governance, and jurisdiction-specific legal review remain separate release gates.

## 8. Implementation sequence

1. Pin and inspect CometBFT v0.40.0 remote-signer source and exact protocol.
2. Add a protocol conformance probe that uses disposable keys and verifies the signer connection without enabling fault injection.
3. Add the honest remote-signer baseline to the existing four-validator harness.
4. Add the withheld-vote scenario and reconnection/catch-up assertions.
5. Add correct-signer same-HRS conflict-refusal and restart-persistence tests.
6. Separately investigate and, only if supported by an auditable pinned-version hook, implement malicious conflicting-vote injection and evidence checks.
7. Run the complete existing CI regression suite after each change.
8. Update this report and the phase plan with exact commit and workflow evidence; never mark a scenario passed before its workflow completes successfully.

---

This document is a test design, not a security certification, legal opinion, investment document, or authorization to issue or trade HND.
