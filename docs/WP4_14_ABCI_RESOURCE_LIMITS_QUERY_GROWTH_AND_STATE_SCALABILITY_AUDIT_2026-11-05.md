# HND v0.2 — ABCI resource limits, query growth, and state scalability audit

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Review type:** Static source review  
**Reviewed files:** `hnd_v02/abci_app.py`, `hnd_v02/cometbft_v040_server.py`, `hnd_v02/ledger.py`  
**Change boundary:** Documentation only; no source, test, or workflow files changed.

## 1. Executive result

The ABCI application has a transaction-count cap of 1,000 per block and proposal construction observes CometBFT's supplied `max_tx_bytes` budget. However, the application core does not define its own maximum transaction byte length or aggregate byte limit for `ProcessProposal` and `FinalizeBlock`. Those paths rely on CometBFT's upstream block-size policy being consistently configured and enforced.

The query API returns the complete evidence journal and account queries have no pagination/versioned proof interface. The ledger snapshot stores the full signed transaction history, and state restoration reconstructs the ledger by replaying that full history from Genesis. This creates a predictable state-growth and recovery-cost concern as the chain ages.

**Disposition: functional limits exist, but resource governance and long-horizon state scalability are not demonstrated for production.**

## 2. Positive controls observed

In `hnd_v02/abci_app.py`:
- `MAX_BLOCK_TRANSACTIONS = 1000`.
- Transaction lists must be a Python list, each transaction must be non-empty bytes, and count is capped.
- `PrepareProposal` validates the list and selects transactions within the supplied `max_tx_bytes` budget.
- The proposal selection uses a deterministic candidate ledger and skips invalid or over-budget transactions.
- `ProcessProposal` and `FinalizeBlock` revalidate transactions against committed/candidate state.
- `CheckTx` catches application/ledger/value/type errors and returns a failed admission result rather than mutating committed state.

In `hnd_v02/cometbft_v040_server.py`:
- Query paths are explicitly limited to `/height`, `/account`, and `/evidence`.
- Proof queries are rejected because proof support is not implemented.
- The ABCI listener is constrained to loopback by the server's bind-address validator, but it remains an unauthenticated insecure gRPC endpoint and is not suitable for exposure to untrusted networks.

## 3. Resource-boundary findings

### RSL-01 — No application-level transaction byte cap

The application checks transaction count and non-empty byte strings, but does not define a maximum individual transaction size in `_validate_tx_list` or `check_tx`.

A large transaction can therefore consume parsing, canonicalization, signature-validation, and memory resources before higher-level limits reject it. The actual exposure depends on CometBFT and gRPC transport limits, which must be explicitly pinned and tested rather than assumed.

### RSL-02 — Process/finalize rely on upstream block byte enforcement

`PrepareProposal` uses CometBFT's `max_tx_bytes`. `ProcessProposal` and `FinalizeBlock` enforce the 1,000 transaction count but do not independently sum transaction byte lengths or compare them to a locally pinned maximum.

This may be acceptable only if the exact CometBFT v0.40 configuration enforces the same block-size ceiling before these calls and all validators run identical settings. The application does not currently make that dependency explicit in its own acceptance contract.

### RSL-03 — Unbounded evidence query response

The `/evidence` query serializes the complete evidence journal into one response. There is no cursor, limit, height range, or pagination. As the journal grows, query response size and serialization work grow with it.

### RSL-04 — Full-history persistence and replay cost

The ledger snapshot contains the complete signed transaction history. Restoration replays every historical transaction from Genesis and compares reconstructed balances, nonces, accepted IDs, history, and state hash. ABCI commits serialize and persist a snapshot containing this history.

This gives strong replay-based consistency checks for the current reference model, but its write, disk, and restart costs grow with chain history. No checkpoint/snapshot pruning, bounded archival policy, or long-duration performance benchmark was established in this review.

## 4. Determinism and consensus considerations

Do not solve resource growth by introducing node-local pruning or time-dependent limits into consensus execution. Any consensus-critical transaction size, block byte, evidence retention, or state-pruning rule must be explicit, deterministic, versioned, and identically configured across validators.

A future checkpoint design must preserve a verifiable link to the pinned Genesis and prior committed app hash, and must be tested across independent replicas and restart/recovery. Query pagination should expose a stable committed height or cursor so clients do not mix data from different states.

## 5. Required acceptance work (not applied)

1. Define protocol-level maximum transaction bytes and maximum block transaction bytes; bind them to the network/protocol profile and validate them consistently.
2. Add negative tests for oversized single transactions, aggregate oversized proposals, and direct ProcessProposal/FinalizeBlock boundary inputs.
3. Verify exact CometBFT v0.40 mempool/block byte settings and gRPC receive limits for every validator; record the effective values in an approved immutable network profile.
4. Add paginated evidence queries with deterministic cursor semantics and a committed-height anchor.
5. Define an archival/checkpoint strategy that preserves app-hash verification and recovery guarantees; do not silently discard signed history.
6. Benchmark commit latency, disk growth, memory use, and restart time at representative transaction-history sizes.
7. Add multi-replica and restart tests proving that any checkpoint/retention policy yields identical app hashes and query semantics.

## 6. CI evidence boundary

This report is based on static source inspection. It does not claim that oversized-transaction, unbounded-query, long-history, or checkpoint-performance tests have been executed. Existing successful CI runs do not substitute for those missing targeted acceptance tests.

## 7. Disposition

**Resource limits:** partial.  
**Proposal byte safety:** depends on upstream CometBFT configuration; local application enforcement is incomplete.  
**Evidence query scalability:** not established.  
**Long-term state growth/recovery performance:** not established.  
**Production launch:** NOT APPROVED.

No code, tests, workflow settings, runtime limits, or state files were modified. This report is not a performance benchmark or denial-of-service certification.
