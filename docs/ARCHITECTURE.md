# HND-Ledger Architecture

**Document status:** Architecture baseline and implementation plan  
**Project version:** 0.1 is the archived educational prototype; 0.2 is not yet implemented  
**Last reviewed:** 2026-11-03

## 1. Scope and evidence

The master archive for version 0.1 describes a local educational prototype for a signed transaction ledger with a simulated deterministic consensus process. It records 1,212 core tests, 3,000 sequential transfer operations, and a displayed supply total of 1,000,000 units after execution.

These are archive-reported results. This repository currently contains no executable source code or test suite with which to independently reproduce them. Therefore, this document does not claim that those tests have been rerun from this repository.

Version 0.1 is not a production network, public cryptocurrency, exchange, or investment product.

## 2. Repository state observed on 2026-11-03

The default branch is `main`. The tracked tree contains only:

```
HND-Ledger/
└── docs/
    └── ARCHITECTURE.md
```

There is currently no `src/` implementation, test directory, dependency manifest, or root README in the tracked tree. The structure below is a proposed target, not a description of files that already exist.

## 3. Proposed logical architecture for version 0.2

The following components are a design target. Each must be implemented and tested before it is described as operational.

### 3.1 Transaction model

A transaction should have a canonical, versioned representation containing at least:
- transaction identifier derived from canonical transaction bytes;
- sender and recipient identifiers;
- positive amount in the smallest indivisible unit;
- nonce or equivalent replay-prevention sequence;
- protocol/network identifier;
- signature and public-key reference.

Exact field encoding, identifier derivation, and signature scheme remain design decisions and must be specified before implementation.

### 3.2 Signature verification

The transaction validation layer must verify that:
- the signature matches the canonical transaction payload;
- the signer controls the sender account;
- the network identifier matches the node's configured network;
- the transaction has not already been accepted;
- the nonce is valid for the sender;
- the amount and resulting balance satisfy protocol rules.

Private keys must never be stored in plaintext in the ledger database or written to logs. Key generation, encrypted storage, recovery, and signing UX require a separate wallet security design.

### 3.3 State and ledger

The state layer maintains account balances and transaction nonces. State changes must be deterministic and atomic: a rejected transaction must not partially modify state.

The ledger layer stores ordered blocks and their transactions. Each block must commit to its parent block identifier and its own transaction data. The exact block encoding and hash function must be fixed in a versioned protocol specification.

### 3.4 Block validation

A block validator should check, at minimum:
- block format and protocol version;
- parent linkage and height progression;
- block identifier/hash integrity;
- transaction validity and uniqueness;
- deterministic execution of state transitions;
- supply and issuance constraints.

A failed validation must leave the previously committed state unchanged.

### 3.5 Consensus

The version 0.1 archive calls its consensus process a deterministic adaptive consensus simulation. It does not provide enough detail to reproduce a production consensus algorithm, including validator selection, quorum rules, fault assumptions, fork handling, finality, or network-message protocol.

**No production consensus algorithm is selected by this document.** Version 0.2 must first specify and threat-model these rules. A local simulation must not be represented as decentralized consensus.

### 3.6 Persistence and recovery

Persistent storage must support atomic commits, integrity checks, and recovery after interruption. On startup, the implementation should verify the stored chain and derived state, or rebuild state from the validated ledger. Recovery tests must include truncated data, corrupted records, interrupted writes, and inconsistent state snapshots.

### 3.7 Networking (future gated component)

A peer-to-peer network is outside the verified scope of version 0.1. Before implementation, define peer authentication, message framing, request limits, transaction/block propagation, denial-of-service controls, synchronization, and fork-choice/finality behavior.

## 4. Proposed transaction flow

1. A wallet constructs a transaction using the agreed canonical format.
2. The wallet signs the transaction locally; the private key does not leave the wallet.
3. A node parses the transaction and validates its format, network, signature, nonce, amount, and available balance.
4. The node rejects duplicates and invalid transactions without changing state.
5. A valid transaction enters the pending pool.
6. A block-production/consensus component proposes an ordered batch under the protocol rules.
7. Every receiving node independently validates the block and deterministically executes its transactions.
8. The node commits the block and resulting state atomically.
9. The client receives a status that distinguishes pending, accepted, and finalized only if the selected consensus protocol supports that distinction.

This is a target flow, not a claim that these components currently exist in the repository.

## 5. Supply policy

The archive records a displayed total supply of 1,000,000 units after the 3,000-operation run. Before implementation, the protocol must define whether this is:
- a fixed genesis allocation;
- a maximum supply cap;
- or an issuance target subject to explicit rules.

Version 0.2 must define decimal precision, smallest unit, genesis allocation, mint/burn permissions, and invariants. No minting or burning behavior should be inferred from the archived total alone.

## 6. Security requirements

- Use a reviewed cryptographic library; do not invent cryptographic primitives.
- Define canonical serialization before signing or hashing.
- Prevent replay across networks and repeated transaction submission.
- Validate all untrusted inputs and enforce size/rate limits.
- Keep secrets out of source control, logs, and error messages.
- Use atomic state transitions and verify persisted state on recovery.
- Add negative tests for malformed data, invalid signatures, replay, nonce conflicts, insufficient funds, overflow, tampered blocks, and interrupted persistence.
- Obtain an independent security review before any public deployment.

## 7. Proposed repository layout

```
HND-Ledger/
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PROTOCOL.md
│   ├── SECURITY.md
│   └── TEST_PLAN.md
├── src/
│   ├── transaction/
│   ├── crypto/
│   ├── state/
│   ├── ledger/
│   ├── validation/
│   └── storage/
└── tests/
    ├── unit/
    ├── integration/
    └── adversarial/
```

This layout is a proposal. Directories should be created only as corresponding modules are implemented.

## 8. Version 0.2 implementation gates

1. **Protocol specification:** settle canonical transaction/block formats, cryptographic algorithms, account model, nonce rules, and supply policy.
2. **Deterministic local ledger:** implement transaction validation, state transitions, block linkage, and persistence without claiming network consensus.
3. **Reproducible tests:** check in tests and fixtures that reproduce the relevant version 0.1 invariants where possible.
4. **Consensus design:** document safety/liveness assumptions, validator model, quorum, finality, forks, and adversary model before coding consensus.
5. **Network testnet:** implement peer communication only after the consensus and threat model are reviewed.
6. **Independent review:** security, operational, and jurisdiction-specific legal review before any production or public-token claims.

## 9. Non-goals and release restrictions

Until all gates are passed, HND-Ledger remains an experimental educational codebase. This repository does not establish authorization to issue, market, list, or trade a token. Do not describe the system as production-ready, independently audited, decentralized, or safe for investment without evidence supporting each claim.
