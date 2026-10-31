# HND v0.1 — Technical Specification

## 1. Scope
HND v0.1 is a local educational prototype for testing a signed transaction ledger and a deterministic adaptive-consensus simulation. It is not a production payment network, exchange, investment product, or deployable public cryptocurrency.

## 2. Fixed parameters
- Initial supply: 1,000,000 HND
- Initial distribution: held by the genesis allocation in the simulator
- No mining
- No discretionary burning
- Every transfer must be digitally signed
- Nonces prevent replay
- A transaction is accepted only once
- Conflicting transactions for the same account nonce are rejected
- The prototype uses deterministic ordering for reproducible tests

## 3. Account state
Each account contains:
- public key
- balance
- next expected nonce

A transfer contains:
- sender
- recipient
- amount
- nonce
- transaction identifier
- signature

Rules:
1. amount > 0
2. sender != recipient
3. nonce equals sender's next expected nonce
4. sender balance is sufficient
5. signature verifies against the sender public key
6. transaction ID matches the canonical transaction payload

## 4. Ledger
The ledger stores:
- ordered accepted transactions
- account balances
- account nonces
- a hash of the previous ledger state

A state transition is deterministic: identical valid inputs produce identical state.

## 5. Adaptive consensus simulation
ACP in v0.1 is deliberately conservative:
- nodes exchange candidate transaction sets
- each node validates transactions independently
- proposals are ranked deterministically
- a block/state update is committed only when the simulator reaches the configured quorum
- conflicting proposals cannot both become the committed state

This is a research simulator, not a claim of Byzantine-fault tolerance for a public network.

## 6. Security tests
Mandatory tests:
- valid transfer
- insufficient balance
- wrong nonce
- replay
- modified transaction
- invalid signature
- conflicting nonce
- duplicate submission
- concurrent transfers
- node restart/recovery
- partial network outage
- malicious proposal simulation

## 7. Acceptance criteria
The prototype passes v0.1 when:
- invalid signatures are never accepted
- replayed transactions are never accepted
- balances never become negative
- total supply remains constant in transfer-only tests
- every committed state is deterministic
- conflicting transactions cannot both be committed
- recovery restores the last valid state

## 8. Production gate
No public deployment, real-money use, token sale, exchange listing, or payment integration should occur until independent security review, legal review in the target jurisdiction, threat modeling, and a substantially more rigorous consensus implementation are completed.