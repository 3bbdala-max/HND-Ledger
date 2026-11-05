# HND v0.2 — Transaction replay protection and cross-node duplicate execution review

**Date:** 2026-11-05  
**Workstream:** WP4.14 — Transaction identity and replay boundaries  
**Branch:** `phase-0.2-planning`  
**Reviewed head:** `353bdf656cbf89a16d95ea8988298dd96b1eb865`  
**Status:** Documentation-only static source/test review. No source, test, or workflow files changed.

## 1. Executive result

The HND transaction envelope has several sound replay controls:

- Ed25519 signs a domain-separated canonical payload.
- The signed payload binds protocol version, network ID, sender, recipient, amount, and sender nonce.
- Account IDs are derived from the public key together with network and protocol context.
- The ledger rejects previously accepted transaction IDs and requires the exact next nonce.
- Accepted transaction history, nonce state, and balances are persisted together and are reconstructed by replaying signed history from the pinned Genesis.

A transaction replayed after successful commitment therefore fails the duplicate-ID and/or stale-nonce checks. Replaying it against another network or protocol version fails the envelope/account domain checks.

The key boundary is that **CheckTx admission is node-local and provisional**. The same signed transaction can be admitted independently by multiple validators before either has committed it. This is not itself a double-spend: the committed ledger transition and sender nonce are checked again against the decided block state. The repository has unit tests for local replay and nonce rejection, but the inspected tests do not directly exercise the same signed transaction being admitted at multiple ABCI replicas, committed once, and then replayed after restart on every replica.

## 2. Cryptographic transaction identity

### 2.1 Signed fields and domain separation

`transaction.py` uses the `HND-LEDGER/TX\\x00` signing domain and canonical JSON. The signed payload contains:

- `protocol_version`
- `network_id`
- `sender`
- `recipient`
- `amount`
- `nonce`

Changing any of these fields invalidates the signature or causes an earlier validation failure. The sender account ID is derived from the Ed25519 public key and includes network and protocol-version context.

### 2.2 Transaction ID

`transaction_id()` hashes the canonical unsigned payload under the transaction signing domain. It intentionally excludes the `signature` field. This gives the transaction a stable identity based on its signed meaning rather than the serialized signature bytes.

The signature is still mandatory and verified before the ledger applies the state transition. The ID's omission of the signature must not be misread as omission of signature verification.

## 3. Replay controls in the ledger and ABCI application

- `HNDLedger.apply_transaction()` rejects a transaction ID already in `accepted`.
- It also validates the sender's exact expected nonce. A different transaction with the same old nonce is rejected even if its transaction ID differs.
- Successful application increments the sender nonce, updates balances, records the transaction ID, and appends the signed envelope to history.
- Snapshot restoration rebuilds state from Genesis by replaying history, then compares reconstructed balances, nonces, accepted IDs, and state hash with the stored snapshot.
- ABCI `CheckTx` applies to an isolated in-memory mempool view.
- `process_proposal` validates the ordered transaction list against committed state.
- `finalize_block` re-applies each transaction sequentially against candidate committed state. A rejected transaction does not mutate the candidate used for subsequent transactions.
- `Commit` persists the resulting ledger and resets the mempool view to the committed state.

Thus a second copy of the same transaction in a block is rejected after the first copy advances the nonce/accepted set. A previously committed transaction replayed later is rejected against the persisted ledger.

## 4. Existing test evidence found

The current tests include:

- transaction signature/domain and field-tampering checks;
- wrong network/protocol account-ID rejection;
- exact nonce type/range and expected-nonce checks;
- ledger rejection of the same transaction ID;
- rejection of a distinct transaction reusing an old nonce;
- duplicate transaction rejection at block construction;
- snapshot round-trip by replaying signed history;
- snapshot history/balance tampering rejection;
- ABCI mempool reset after Commit;
- four-replica state convergence for common ordered block inputs.

These are test definitions inspected in the repository. No test command was run for this report.

## 5. Important boundary: local admission versus distributed commitment

Two or more validators may each return CheckTx success for the same signed bytes while the transaction is not yet committed. Their mempool views are independent. CheckTx success is not a globally reserved nonce and does not establish a committed transfer.

The safety decision occurs when the transaction list is validated and applied against the committed state. Every honest replica must process the same decided ordered block and use the same consensus-critical configuration. The HND nonce and accepted-ID checks then prevent a second state transition for the same sender nonce.

This application-level control does not replace CometBFT consensus safety, validator-set integrity, or identical protocol configuration. It also does not prove protection against a compromised validator or divergent binaries.

## 6. Targeted test gap and acceptance matrix

The following end-to-end cases are not directly established by the inspected test definitions. Add them only after explicit authorization to modify tests.

| ID | Scenario | Required outcome |
|---|---|---|
| TXRP01 | Submit identical signed bytes to CheckTx on all four independent ABCI replicas before commitment | Local CheckTx may accept on each; no claim of global reservation |
| TXRP02 | Commit the identical transaction once in the same ordered block on all replicas | Each replica reaches identical balances, nonce, accepted-ID set, and app hash |
| TXRP03 | Include the identical transaction twice in one decided block | First execution succeeds; second execution returns a failed transaction result and does not change state again |
| TXRP04 | Replay the committed signed bytes in a later block | Rejected due duplicate ID and/or stale nonce; balances and app hash do not reflect a second transfer |
| TXRP05 | Restart every replica after TXRP02, then replay the same signed bytes | Rejected after recovery; committed state hashes remain unchanged |
| TXRP06 | Submit a different valid transaction from the same sender with the already consumed nonce | Rejected; no balance or nonce mutation |
| TXRP07 | Alter network ID, protocol version, recipient, amount, sender, or nonce without re-signing | Rejected by domain/account/signature/nonce validation |
| TXRP08 | Submit a correctly signed transaction under a different network/protocol configuration | Rejected by network/protocol binding and account identity |
| TXRP09 | Re-broadcast after losing the CheckTx response | Same bytes produce at most one committed state transition; client reconciles by committed state before creating a replacement |
| TXRP10 | Re-broadcast after losing the Commit response | Client queries committed state/height and does not assume timeout means failure or success |

For TXRP01–TXRP05, preserve the exact same signed bytes across nodes and restarts. Do not generate a new transaction for each replica; that would fail to test replay identity.

## 7. Client and wallet requirements

1. Retain the exact signed transaction bytes and transaction ID before broadcast.
2. Treat CheckTx success as provisional admission only.
3. On timeout, rebroadcast the same signed bytes rather than signing a replacement with the same nonce and different fields.
4. Query committed account nonce/state and transaction evidence before creating a replacement.
5. Never advance the nonce based solely on a CheckTx response.
6. Keep private-key custody, recovery, revocation, and user authorization separate from the transaction replay mechanism; those are not implemented by this ledger primitive.

## 8. Release conclusion

Static inspection supports local transaction replay protection through transaction ID, sender nonce, signature/domain binding, and replay-verified committed history. It does not establish the complete four-validator end-to-end replay scenario in TXRP01–TXRP10, nor does it prove CometBFT consensus safety.

No code or tests were changed, and no tests were executed. This report is a scoped replay-protection review, not a production security certification.
