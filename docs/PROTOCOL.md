# HND Protocol Specification — Draft

**Status:** Draft for design review; not an implemented protocol  
**Target:** HND-Ledger version 0.2  
**Updated:** 2026-11-03

## 1. Purpose

This document records the protocol decisions that must be settled before implementing version 0.2. It deliberately distinguishes requirements supported by the version 0.1 archive from decisions that remain open.

## 2. Baseline facts from the version 0.1 archive

The archive describes:
- a local educational prototype;
- digitally signed transactions;
- rejection of repeated transactions;
- rejection of conflicting transactions for the same inputs;
- ordered transaction groups under a deterministic adaptive consensus simulation;
- a displayed total supply of 1,000,000 units after a run of 3,000 sequential transfers.

The archive does not specify enough detail to reconstruct the exact wire format, cryptographic suite, account model, block format, validator protocol, quorum, finality, or network behavior.

## 3. Required protocol decisions

No values below should be treated as selected until explicitly approved and tested.

| Topic | Required decision |
|---|---|
| Account model | Account/balance model or UTXO model |
| Address format | Public-key derivation, encoding, checksum, versioning |
| Signature scheme | Established, maintained cryptographic scheme and library |
| Hash function | Standard hash function and domain-separation rules |
| Serialization | Canonical binary or textual encoding; field ordering and versioning |
| Amounts | Integer smallest-unit representation and decimal precision |
| Nonce | Per-account sequence and replay rejection behavior |
| Transaction ID | Exact derivation from canonical signed transaction bytes |
| Block format | Header fields, transaction commitment, parent reference, height |
| Genesis | Initial state, allocations, parameters, and reproducible genesis identifier |
| Supply policy | Fixed genesis allocation, maximum cap, or issuance schedule |
| Fees | Whether fees exist and how they are calculated/distributed |
| Consensus | Validator model, quorum, safety/liveness assumptions, finality |
| Fork handling | Fork-choice rule and recovery from conflicting histories |
| Networking | Peer identity, transport, message format, sync, rate limits |

## 4. Minimum transaction validation requirements

A node must reject a transaction if:
- its encoding or protocol version is invalid;
- the network identifier is wrong;
- its signature does not verify against the canonical payload;
- its sender does not correspond to the signing key;
- the amount is zero, negative, malformed, or overflows the permitted integer range;
- its nonce is stale, repeated, or skips a value where sequential nonces are required;
- the sender lacks sufficient available balance;
- the transaction identifier has already been accepted;
- applying it would violate the supply or state invariants.

The exact nonce and fee rules depend on the account model and must be fixed in the protocol.

## 5. Minimum block validation requirements

A node must reject a block if:
- its encoding, version, height, or parent reference is invalid;
- its identifier does not match its canonical contents;
- its transaction commitment is invalid;
- it contains duplicate or invalid transactions;
- deterministic execution produces an invalid state transition;
- it violates issuance, supply, or other genesis-defined invariants;
- its proposer/validator authorization is invalid under the selected consensus protocol.

## 6. Supply invariant

The version 0.1 archive reports a total displayed supply of 1,000,000 units after a test run. It does not establish whether that value is a hard cap, initial allocation, or merely the displayed total for that test.

Version 0.2 must define the genesis distribution and all permitted issuance/burning operations. The implementation must calculate supply from ledger state and verify the invariant after every committed block.

## 7. Consensus safety gate

A deterministic local simulation is not proof of decentralized consensus. Before a network implementation, the project must document:
- validator identities and admission/removal;
- assumed number or proportion of Byzantine validators;
- quorum intersection and safety argument;
- liveness assumptions and timeout behavior;
- proposal and vote message formats;
- finality definition;
- equivocation and double-sign handling;
- partition recovery and conflicting-chain behavior.

Consensus code must not be implemented from an informal description alone.

## 8. Open design review checklist

- [ ] Select account model.
- [ ] Select and document cryptographic algorithms and vetted libraries.
- [ ] Define canonical serialization and protocol versioning.
- [ ] Define address derivation and transaction identifier.
- [ ] Define nonce, fee, and balance semantics.
- [ ] Define genesis allocation and supply policy.
- [ ] Define block header and transaction commitment.
- [ ] Specify consensus assumptions and finality before implementation.
- [ ] Define adversarial test cases and reproducible fixtures.

## 9. Release warning

This draft is not a production specification and does not authorize issuance, marketing, listing, or trading of an HND token. Do not use it to handle real funds.
