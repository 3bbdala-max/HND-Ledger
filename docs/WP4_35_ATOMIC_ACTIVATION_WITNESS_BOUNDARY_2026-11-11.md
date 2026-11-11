# WP4.35 — Station 2 Atomic Activation and Witness Boundary

Date: 2026-11-11
Status: Engineering design; not an implementation or production approval.

## Purpose

Define the safe integration boundary between the etcd v3 atomic activation backend, the activation coordinator, the durable activation-intent record, and the independent monotonic witness. This document prevents an unsafe shortcut: treating the existing etcd backend as if it already implements the complete Station 2 protocol.

## Verified current implementation

The current code has four distinct persistence operations:

1. `RemoteActivationIntentClient.prepare/read_intent/finalize` uses a remote HTTPS service for an immutable activation ID and its lifecycle state.
2. `ActivationCoordinator._advance` advances `trust-manifest` and `vsp-profile` independently through `MonotonicStateAnchor.compare_and_advance`.
3. `EtcdV3AtomicActivationBackend.compare_and_activate` compares the current state/profile and writes the successor active-state and profile keys in one etcd transaction.
4. The coordinator finalizes the remote intent only after it observes the local active state.

The legacy `EtcdV3AtomicActivationBackend.compare_and_activate` transaction contains two puts: active-state and active-profile. PR #49 now also adds a separate candidate method, `compare_and_activate_with_intent`, which compares and writes five etcd keys in one transaction: active-state, active-profile, both monotonic namespace records, and an immutable `pending_witness` activation intent. That candidate method computes and stores an activation digest, but it does not write a witness acknowledgement or finalize the intent.

The current `ActivationCoordinator` still calls the legacy two-key transaction path and advances the two monotonic namespaces sequentially before it. It does not call `compare_and_activate_with_intent`. Therefore the five-key transaction exists and has passing stubbed transaction tests, but is not yet the coordinator's active protocol. The complete Station 2 operation is not yet integrated or proven end-to-end.

## Required target protocol

A production-capable activation must use one immutable `activation_id` and bind all records to the same canonical activation digest.

The durable etcd transaction must compare the exact predecessor state and exact predecessor profile (or key absence for bootstrap), and then atomically write:

- the successor active state;
- the successor pinned profile artifact;
- both successor anti-rollback namespace records;
- the immutable activation intent in a committed/pending-witness state;
- the canonical activation digest and transaction metadata needed for recovery.

The transaction must be a single etcd Raft commit. It must not claim final activation until the independent witness has acknowledged the same activation digest and sequence pair.

The candidate etcd intent reader currently accepts only `pending_witness`. It deliberately rejects a `finalized` state because the record schema does not yet carry a verifiable witness receipt. No code path may promote the intent to finalized until an authenticated receipt format, trust-key configuration, signature verification, and a compare-and-swap finalization transaction are implemented and tested.

The independent witness must:
- be outside the etcd cluster's administrative and restore domain;
- enforce linearizable, durable compare-and-advance semantics;
- bind the witness identity/configuration epoch to the activation digest;
- reject stale, conflicting, skipped, or regressed sequences;
- return an authenticated acknowledgement that can be verified during startup.

After etcd commit, the coordinator requests witness advancement for the exact committed digest. A lost response is reconciled by reading the same witness record; it must never create a new activation ID or roll back a committed etcd transaction. Only after witness acknowledgement is verified may the activation intent be marked finalized. A crash at any boundary must leave startup blocked until same-ID reconciliation proves the exact etcd state and witness acknowledgement.

## Ordering and failure rules

| Boundary | Durable fact | Required recovery |
|---|---|---|
| Before etcd transaction | No activation commit | Keep old state; retry only same immutable intent if still valid |
| etcd transaction response lost | Commit outcome unknown | Read etcd by activation ID and exact digest; do not repeat with a new ID |
| etcd committed, witness not advanced | State is pending witness | Keep startup blocked; advance/reconcile witness for the same digest |
| Witness advanced, response lost | Witness outcome unknown | Read witness; accept only exact activation digest and sequence pair |
| Witness ahead or conflicts | Integrity disagreement | Fail closed and require operator investigation; never roll back either side |
| Both durable, finalization response lost | Commit may already be complete | Read both records; finalize idempotently only if exact values match |
| Old etcd snapshot restored | etcd may be stale behind witness | Witness detects rollback; quarantine and require authenticated recovery |

## Required implementation changes

1. Extend the activation transaction contract with an immutable activation-intent record and both anti-rollback namespace records. Do not overload the current `ActivationState` with unvalidated arbitrary metadata.
2. Integrate the candidate five-key etcd transaction into the coordinator, including exact predecessor comparisons and same-ID read-after-unknown-outcome reconciliation. Reject unknown/missing keys and malformed records.
3. Replace the coordinator's two sequential anchor writes with the target transaction boundary. Keep the independent witness operation separate and explicitly post-commit; the witness is not an etcd key and must not be represented as one.
4. Add same-ID reconciliation for: unknown etcd commit result, etcd committed/witness pending, witness committed/response lost, and finalization response lost.
5. Add a three-member etcd integration environment with pinned image digest and verified v3 JSON gateway configuration. Tests must exercise quorum loss, leader change, concurrent compare-and-swap, member replacement, process crash, and old-snapshot restore.
6. Add an independent witness implementation and negative tests for stale epoch, rollback, wrong activation digest, wrong namespace sequence, duplicate IDs with changed payload, and lost acknowledgement.
7. Make startup authorization consume a verified committed activation record plus witness acknowledgement; absence, mismatch, timeout, stale witness, or uncertain recovery must block every CometBFT/ABCI launch path.

## Non-goals and safeguards

- This design does not provision etcd, certificates, witness hardware, or production keys.
- A three-member etcd cluster alone does not prevent rollback if all members are restored from an old snapshot.
- A SQLite reference backend is not a production monotonic witness.
- HTTPS endpoint reachability is not proof of mTLS deployment or certificate custody.
- A passing unit test or single-node smoke test does not prove multi-member quorum or restore safety.
- No Config-v1 owner decisions DEC-01 through DEC-14 are made by this document.

## Acceptance criteria

Station 2 cannot be declared complete until the target transaction, independent witness, same-ID crash reconciliation, three-member etcd integration suite, and mandatory startup authorization gate are implemented and independently reviewed. Until then PR #49 remains a draft candidate and this document is design-only.

## Relationship to prior work

- WP4.33 defines the Station 2 exit runbook.
- WP4.34 defines the independent monotonic anchor architecture.
- PR #49 adds an etcd v3 active-state/profile transaction backend, but does not yet implement this complete protocol.
