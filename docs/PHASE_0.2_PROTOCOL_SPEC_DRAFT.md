# HND Ledger — Phase 0.2 Protocol Specification (Draft)

**Status:** Engineering draft — not approved for implementation  
**Date:** 2026-10-31  
**Baseline:** Recovered HND v0.1 local educational prototype  
**Branch:** `phase-0.2-planning`

## 1. Purpose and scope

This document separates behavior that is directly evidenced in v0.1 from requirements that must be decided before a distributed implementation is built. It is not a final protocol, production design, financial-product specification, or authorization to issue or trade a token.

The v0.1 code is a single-process ledger with signed transfers and a deterministic quorum simulator. It has no peer-to-peer transport, persistent block format, validator identity model, or distributed finality protocol.

## 2. Evidence-based v0.1 behavior

| Area | Observed behavior |
|---|---|
| Nominal supply | `1,000,000` integer units, enforced by the constructor |
| Account state | balance, nonce, Ed25519 public key |
| Transaction fields | sender, recipient, amount, nonce, signature |
| Signing | Ed25519 signature over canonical JSON payload |
| Canonical JSON | sorted keys, compact separators, UTF-8 |
| Transaction identifier | SHA-256 of canonical payload; signature is not included |
| Replay control | sender nonce plus accepted-transaction set |
| State commitment | SHA-256 of canonical account state, ordered history, and sorted accepted set |
| Persistence | JSON snapshot with state-hash, accepted/history, and supply checks on load |
| Consensus | local proposal-counting simulator with a configured quorum |

These are implementation observations, not a complete wire protocol.

## 3. Transaction envelope — draft requirements

The current prototype's transaction fields are a useful starting point:

- `sender`: account identifier
- `recipient`: account identifier
- `amount`: positive integer in atomic units
- `nonce`: sender's next sequence number
- `signature`: Ed25519 signature

Before implementation, the protocol must normatively specify:
1. Account identifier format and whether it is derived from the public key.
2. Exact integer ranges and rejection of booleans, floats, strings, negative values, and overflow.
3. Whether a transaction includes a chain/network identifier and protocol version to prevent cross-network replay.
4. Whether expiry, fee, memo, or transaction type fields exist; none should be silently assumed.
5. Exact canonical byte encoding and signature domain separation.
6. Whether transaction IDs remain SHA-256 over the unsigned payload or change under a versioned rule.

No backward-incompatible change should be made to v0.1 silently. Any change needs a versioned format and test vectors.

## 4. Account and nonce rules — draft requirements

- Each account has one authoritative public key, balance, and next expected nonce.
- A valid transfer must be signed by the sender's registered key.
- A transfer must not spend more than the sender's available balance.
- A transaction with a stale, repeated, skipped, or malformed nonce must be rejected according to a rule specified before coding.
- Account creation and key rotation require explicit protocol rules; v0.1 currently creates local accounts in memory.
- The protocol must decide whether account identifiers can change keys and how recovery is handled. No recovery mechanism is currently evidenced.

## 5. Supply and genesis — unresolved design

The prototype fixes the nominal supply at 1,000,000 units and begins with the full balance in a `GENESIS` account. Test setup moves units from GENESIS to ALICE and BOB directly in memory.

Before implementation, the project must decide and document:
- The exact genesis allocation manifest and how its authenticity is verified.
- Whether the full supply is assigned to one genesis account or distributed across named initial accounts.
- Whether units have decimal subdivisions; current code uses integer units and does not define display decimals.
- Whether minting, burning, fees, or treasury accounts are permanently prohibited or governed by explicit future rules.
- How every node independently verifies the same genesis state.

Until these choices are resolved, the one-million figure is a prototype parameter, not a public issuance commitment.

## 6. State transition and commitment

The v0.1 state hash commits to sorted account data, ordered transaction history, and the sorted accepted set. Snapshot loading verifies the hash, accepted/history consistency, and total supply.

A distributed protocol still needs to define:
- The exact state serialization and hash algorithm version.
- Whether the state root is a flat hash, Merkle root, or another authenticated structure.
- How a block references its parent and how block height and timestamps are validated.
- How snapshots are authenticated and how a node verifies state after synchronization.
- Rules for duplicate transactions, conflicting transactions, and deterministic transaction ordering.

The current state hash is not a block hash chain and must not be described as proof of a distributed blockchain.

## 7. Consensus and validator model — unresolved design

`AdaptiveConsensusSimulator` counts identical JSON proposals and rejects insufficient or conflicting quorum counts. It does not model authenticated validator identities, votes, message delivery, leader selection, network partitions, equivocation, Byzantine faults, validator membership changes, or finality proofs.

No consensus algorithm is selected by this draft. A future design must define, at minimum:
- Validator identity and admission/removal rules.
- Vote and proposal message formats and signatures.
- Quorum formula and the fault assumptions under which safety/liveness claims hold.
- Leader selection, timeouts, view/round changes, and recovery.
- Duplicate, delayed, reordered, conflicting, and malicious message handling.
- Network partition behavior and explicit finality semantics.
- Validator incentives or the deliberate absence of incentives.

Do not call the v0.1 simulator Byzantine fault tolerant or deploy it as a distributed consensus mechanism.

## 8. Networking and node protocol — not yet specified

No transport or peer protocol exists in v0.1. Before network implementation, define:
- Transport and connection security.
- Peer discovery and authenticated node identity.
- Message framing, version negotiation, size limits, and rate limits.
- Transaction propagation, block propagation, synchronization, and peer scoring.
- DoS controls, resource limits, and safe behavior under malformed input.

## 9. Security and test gates

Implementation must not begin until protocol decisions above are recorded and test vectors are approved. Planned tests should include:
- Canonical encoding and signature test vectors.
- Invalid type, boundary, overflow, replay, and cross-network replay cases.
- Conflicting nonce and double-spend scenarios.
- Deterministic state transition across independent implementations.
- Genesis verification and supply invariants.
- Snapshot corruption and recovery.
- Multi-node message delay, loss, duplication, reordering, partition, and restart.
- Equivocation and Byzantine fault scenarios matching the selected consensus model.
- Fuzzing, dependency review, threat model, and independent security assessment.

## 10. Decision register

The following decisions remain open and must be approved before a protocol implementation is written:

| ID | Decision | Current status |
|---|---|---|
| D-01 | Account ID derivation and key lifecycle | Open |
| D-02 | Atomic-unit scale / decimal display | Open |
| D-03 | Genesis allocation manifest | Open |
| D-04 | Transaction version and network/domain identifier | Open |
| D-05 | Transaction ID and canonical encoding versioning | Open |
| D-06 | Fees, minting, burning, and treasury policy | Open |
| D-07 | State root and block format | Open |
| D-08 | Validator model and consensus algorithm | Open |
| D-09 | Network transport and peer discovery | Open |
| D-10 | Upgrade and governance process | Open |

## 11. Release boundary

Phase 0.2 remains a specification and controlled test phase. No mainnet, public token issuance, sale, exchange listing, payment integration, or use of real funds is in scope. Legal review in the intended jurisdictions and independent security review remain mandatory gates before any public financial use.
