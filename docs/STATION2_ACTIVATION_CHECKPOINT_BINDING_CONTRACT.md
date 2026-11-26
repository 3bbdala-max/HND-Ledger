# Station 2 — Activation Checkpoint Binding Contract

Status: DRAFT — normative design; implementation and tests not yet present
Branch: `station2-witness-backend-interface`
Depends on: `REMOTE_MONOTONIC_ANCHOR_PROTOCOL.md`, `STATION2_WITNESS_FINALIZATION_LOCK_CONTRACT.md`

## 1. Purpose and boundary

The generic monotonic anchor stores only a sequence and digest per namespace. It MUST remain a generic primitive. Activation semantics are committed into the digest of a canonical, domain-separated activation checkpoint envelope.

A successful signature over a historical checkpoint does not prove freshness. The finalizer MUST read the current anchor state from the independently administered anchor and compare the exact namespace, sequence, and digest before it changes etcd state.

## 2. Namespace

Use a deterministic namespace derived from immutable network identity and witness identity:

`hnd/station2/v1/<network_id>/<genesis_hash>/<witness_id>`

The implementation MUST validate and canonically encode each component; it MUST NOT accept caller-supplied arbitrary namespace strings that escape the assigned identity. If one global activation lock is required across multiple witnesses, the lock namespace MUST be a distinct, explicitly provisioned global namespace; per-witness namespaces alone do not enforce a network-wide single pending activation.

## 3. Canonical checkpoint envelope

The digest committed to the monotonic anchor MUST be:

`SHA-256("HND-STATION2-ACTIVATION-CHECKPOINT-V1\\0" || canonical_encode(envelope))`

The canonical encoding MUST be a single explicitly versioned deterministic encoding already supported by the repository; duplicate keys, unknown fields, non-canonical encodings, invalid integer ranges, and missing fields MUST be rejected. The encoding identifier and version MUST be fixed by the protocol, not negotiated by an untrusted request.

Required envelope fields:

- `schema`: `hnd.station2.activation-checkpoint.v1`
- `network_id`
- `genesis_hash`
- `witness_id`
- `config_epoch`
- `witness_key_id`
- `witness_key_generation`
- `witness_counter`
- `activation_id`
- `activation_digest`
- `receipt_digest`
- `predecessor_sequence`
- `predecessor_digest`
- `anchor_key_id`
- `anchor_key_epoch`

The envelope MUST NOT include its own digest or signature in the bytes being hashed. The anchor record is `MonotonicRecord(sequence=predecessor_sequence+1, digest=checkpoint_digest)`; advancement MUST use compare-and-advance against the exact previously read record.

## 4. Receipt binding

`receipt_digest` MUST be calculated from the exact immutable signed witness receipt using the same canonical encoding and a separate domain:

`SHA-256("HND-STATION2-WITNESS-RECEIPT-V1\\0" || canonical_encode(receipt))`

The receipt MUST bind network identity, genesis identity, witness identity, configuration epoch, key identity/generation, counter, activation ID, and activation digest. If the current receipt schema does not carry all required identity fields, the checkpoint MUST NOT silently invent them; the receipt schema and signing contract must be amended first.

## 5. Prepare ordering

1. Read the pending etcd intent and validate its immutable activation commitment.
2. Acquire the durable witness pending-operation lock; no second activation may acquire it.
3. Obtain or return the exact original witness receipt.
4. Verify the receipt locally against pinned witness trust.
5. Read the current anchor record in the assigned namespace.
6. Build the canonical checkpoint envelope using the exact receipt digest and predecessor.
7. Call linearizable `compare_and_advance(namespace, expected_current, new_record)`.
8. On success, persist the checkpoint identity in the witness pending record before reporting preparation complete.
9. On an ambiguous response, read the anchor. Accept only an exact matching next record for the same envelope; otherwise quarantine. Never allocate a new receipt/counter to resolve ambiguity.

If the witness receipt is durable but anchor advancement has not occurred, the pending lock remains held. A retry MUST resume the same operation and receipt.

## 6. Finalizer gate

The finalizer's trusted dependency MUST include a verifier backed by the independently administered anchor. The check MUST occur inside the finalization method, immediately before the etcd CAS, not only in a coordinator.

The finalizer MUST:
- validate the exact pending intent and witness receipt;
- recompute the receipt digest and checkpoint digest from canonical bytes;
- read the current anchor state from the configured independent anchor;
- require exact equality of namespace, sequence, and digest to the checkpoint for this activation;
- verify the predecessor and all network/witness/epoch/counter bindings;
- reject unavailable, stale, advanced, forked, or mismatched anchor state;
- only then attempt the etcd CAS from the exact pending bytes.

If another operation can advance the same namespace between anchor read and etcd CAS, the design MUST prevent that race with the durable single-pending lock and namespace ownership. A mere read-then-CAS without exclusive operation ownership is insufficient.

## 7. Completion and recovery

After etcd CAS, the witness completion verifier MUST independently read the authoritative etcd intent using read-only credentials or verify an independently governed finalizer attestation. It MUST compare the exact activation ID, activation digest, receipt digest, witness counter, finalized state, and configured etcd cluster identity.

The witness then atomically records terminal evidence and releases the pending slot. Loss of a response is resolved by rereading the same etcd intent and anchor checkpoint. Any mismatch retains the lock and quarantines the affected activation domain.

No wall-clock timeout, operator-only unlock, or restored local database snapshot may release the lock.

## 8. Critical scope note: one pending operation

A per-witness pending slot prevents two activations for that witness. It does not prove a network-wide single pending activation if multiple witnesses can independently acknowledge different activations. The production design MUST either:
- use a single globally serialized activation namespace/authority; or
- define and prove a quorum protocol that safely serializes activation across all participating witnesses.

Do not claim global serialization from per-witness SQLite locks.

## 9. Required tests

- `BIND-01`: changing any envelope field changes the checkpoint digest.
- `BIND-02`: receipt from another activation cannot satisfy the checkpoint.
- `BIND-03`: receipt digest mismatch is rejected.
- `BIND-04`: predecessor mismatch causes compare-and-advance failure.
- `BIND-05`: finalizer rejects a historical but correctly signed checkpoint.
- `BIND-06`: finalizer rejects when anchor has advanced to a conflicting checkpoint.
- `BIND-07`: finalizer rejects when anchor is unavailable.
- `BIND-08`: ambiguous anchor response is reconciled only by exact readback.
- `BIND-09`: witness lock remains held until independently verified etcd finalization.
- `BIND-10`: multiple witnesses cannot create conflicting network-wide activations under the chosen global serialization/quorum design.
- `BIND-11`: restored etcd snapshot cannot roll back the independently anchored sequence.
- `BIND-12`: non-canonical encoding, duplicate keys, and unknown fields are rejected.

Tests MUST assert durable witness state, anchor sequence/digest, etcd intent, and receipt identity.

## 10. Non-claims

This contract does not establish that the current remote anchor server is production-grade, that its storage is anti-rollback, that client authorization is role-scoped, or that HSM/TPM custody exists. Those remain independent production admission gates.
