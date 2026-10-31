# HND Ledger — WP1 Design Decision Proposals

**Status:** Recommendations for owner review; none of these proposals is an approved monetary or protocol commitment.  
**Date:** 2026-10-31  
**Applies to:** Phase 0.2 planning only

## 1. Why this document exists

The recovered v0.1 source and specification were reviewed to turn open protocol questions into concrete, reviewable choices. These recommendations are intended to reduce ambiguity before any distributed-network code is written. They do not authorize issuance, sale, exchange listing, custody, payments, or use of real funds.

## 2. Recommended decisions

| ID | Topic | Recommendation for v0.2 | Rationale |
|---|---|---|---|
| D-01 | Account identifier | Derive a versioned account ID from the Ed25519 public key, with an explicit network/version prefix. | Avoids arbitrary human-readable account names and makes key-to-account binding deterministic. |
| D-02 | Key lifecycle | No custodial recovery or administrator override. Keep v0.2 keys user-controlled; defer key rotation/recovery until a separate signed recovery design is reviewed. | Avoids silently creating a central authority able to seize or rewrite accounts. |
| D-03 | Unit precision | Keep integer atomic units in consensus. Do not define a decimal display scale until a clear user-facing requirement exists. | Consensus arithmetic remains exact; display precision can be specified separately and versioned. |
| D-04 | Supply | Treat 1,000,000 as a provisional fixed-supply design target only. No minting or discretionary burning in v0.2. | Preserves the tested transfer-only invariant while avoiding a premature public issuance promise. |
| D-05 | Genesis | Replace the mutable in-memory GENESIS setup with a canonical, versioned genesis manifest containing account IDs and integer allocations; every node must verify the same manifest hash. | Independent nodes need exactly the same initial state. |
| D-06 | Transaction domain | Add protocol version and network/chain identifier to the signed transaction payload before any network deployment. | Prevents a valid signature from being replayed across networks or incompatible protocol versions. |
| D-07 | Fees | No transaction fees in the first distributed test network; explicitly reject fee fields until a fee model is specified. | Keeps state transition and supply accounting simple during early network testing. |
| D-08 | Consensus | Do not reuse the v0.1 proposal counter as network consensus. Select a published, analyzed consensus protocol only after validator assumptions and fault model are documented. | The current simulator does not implement authenticated distributed voting or Byzantine fault tolerance. |
| D-09 | State commitment | Version the canonical state encoding and hash algorithm. Keep the current flat SHA-256 commitment as a prototype-only compatibility reference; evaluate Merkle state roots separately. | Prevents accidental incompatibility and avoids claiming proofs the current implementation cannot provide. |
| D-10 | Governance/upgrades | No on-chain governance in v0.2. Require documented, reviewed, versioned software releases and an explicit upgrade policy before any public network. | Avoids introducing an untested governance and capture surface. |

## 3. Source-review findings that must be addressed before network implementation

The following are observations about the recovered v0.1 source, not claims that the 12 baseline tests cover them.

### F-01 — Python boolean values pass integer amount validation

The current check uses `isinstance(amount, int)`. In Python, `bool` is a subclass of `int`, so `True` can pass the positive-integer check. A protocol implementation should require `type(amount) is int` and enforce an explicit maximum range.

### F-02 — Nonce type and range are not explicitly validated

The current code compares the supplied nonce with the account nonce, but does not first require an exact non-boolean integer within a specified range. The wire protocol must define and validate this.

### F-03 — Transaction signature domain is not network/version bound

The signed v0.1 payload contains sender, recipient, amount, and nonce only. It does not include a chain/network identifier or protocol version. This must be added in a new, versioned transaction format before multi-network use.

### F-04 — Genesis allocation is a local mutable setup operation

The prototype starts with a GENESIS balance and tests move balances directly in memory. This is suitable for a local test harness but not a verifiable genesis process shared by independent nodes.

### F-05 — Account names are local labels, not a cryptographic address scheme

The prototype accepts caller-provided account names and stores a public key on the account. A distributed protocol needs a deterministic account identifier and explicit key-binding rules.

### F-06 — Consensus simulator is not a distributed consensus protocol

The simulator counts identical proposal JSON values in one process. It does not authenticate validators or implement message rounds, leader changes, equivocation handling, network partitions, or finality certificates.

## 4. Proposed implementation order

1. Approve or revise the account ID and key lifecycle rules.
2. Specify the genesis manifest format and validation test vectors.
3. Specify a versioned transaction envelope including network ID and strict integer types/ranges.
4. Add negative tests for booleans, overflow, malformed nonce, wrong network ID, wrong protocol version, and mismatched public-key/account ID.
5. Only then evaluate a distributed consensus protocol and network architecture.
6. Keep all work on `phase-0.2-planning`; do not merge to `main` until explicit release gates are met.

## 5. Explicit non-decisions

This document does not select a consensus algorithm, decimal display precision, validator count, validator reward, transaction fee, public genesis recipients, token price, exchange strategy, or legal structure. Those require separate technical, economic, security, and legal review.

## 6. Release boundary

Phase 0.2 is still planning and controlled engineering. No mainnet, public token issuance, sale, exchange listing, payments, or real-money activity is in scope. Independent security assessment and jurisdiction-specific legal review remain mandatory before any public financial use.
