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
