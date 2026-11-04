# HND v0.2 — Internal Synthetic Model Review Notes

**Date:** 2026-11-04  
**Branch:** `phase-0.2-planning`  
**Status:** Internal engineering observations only — NOT an independent security review, audit, or approval  
**Reviewed baseline:** `de87cc910d3e1e75069eddbd9847f0e5650ab6f1`  
**Scope:** Static review of `hnd_v02/anti_rollback_reference.py` and `tests/test_v02_anti_rollback_reference.py`

## 1. Purpose and boundary

These notes record implementation-level questions found during an internal inspection of the offline synthetic anti-rollback reference model. They are intended to improve the next engineering iteration and help an independent reviewer focus attention. They do not replace the Stage A review, and they do not imply that the synthetic model is suitable for production.

The model correctly labels itself as in-memory, test-only, and non-production. Its fixed MAC key, in-memory anchor, and process-local state are expected limitations of a bounded simulator. The observations below concern whether the simulator exercises the protocol properties it claims to model.

## 2. Findings requiring follow-up

### IMR-01 — Host fencing is process-local, not anchor-coordinated

**Priority:** High for the completeness of the fencing simulation; not a production vulnerability claim.

`OfflineAntiRollbackModel.fence_and_takeover()` increments `self._host_epoch` and changes `self._active_host` only on that Python object. The epoch is not persisted in `SyntheticAnchor`, included in an authenticated anchor record, or checked against a shared authoritative generation during signing. A second `OfflineAntiRollbackModel` instance using the same `SyntheticAnchor` starts with its own default `synthetic-host-1` active.

Consequently, the current single-instance test proves only that one object rejects its locally remembered former host after takeover. It does not prove that a stale second process/object is fenced when two model instances share the same anchor.

**Required follow-up:** Extend the synthetic protocol so the anchor owns a monotonically increasing fencing generation and active host/session identity (or an equivalent compare-and-swap lease). Every prepare and signing-eligibility check must validate the current shared fencing generation. Add a two-model test: both instances start against one anchor; one performs takeover; the stale instance must be unable to prepare or pass signing eligibility, including after simulated reconnection. Keep the mechanism synthetic and offline.

### IMR-02 — Anchor compare-and-swap does not independently validate predecessor digest

**Priority:** Medium for simulator protocol coverage.

`OfflineAntiRollbackModel.prepare()` computes `predecessor_digest` from the current anchor record, but `SyntheticAnchor.compare_and_swap()` checks only the expected sequence and the next sequence number. It does not compare the supplied predecessor digest with the digest of the current anchor record. A caller constructing a record directly could therefore submit an inconsistent predecessor link while satisfying the sequence check.

**Required follow-up:** Have the synthetic anchor validate the predecessor digest against its current record (using the same canonical definition as the protocol) before accepting PREPARED. Add a negative test for a correct sequence with a deliberately incorrect predecessor digest. Ensure the initial record uses the explicitly specified all-zero predecessor sentinel.

### IMR-03 — Round and step inputs are not range/type checked

**Priority:** Low-to-medium for input-contract completeness.

`prepare()` validates that height is a non-negative integer and rejects booleans, but does not apply equivalent validation to `round` and `step`. Negative values, booleans, or non-integer values can enter the synthetic anchor record.

**Required follow-up:** Validate round and step as non-negative integers, explicitly reject booleans, and add negative tests. Confirm the accepted value ranges and semantics against the pinned CometBFT v0.40.0 signing-state mapping during Stage A review.

## 3. Existing evidence that remains valid

The existing CI run [41908521855](https://github.com/3bbdala-max/HND-Ledger/actions/runs/41908521855) passed both workflow jobs on the handoff commit. That result remains valid for the tests actually present at that commit. These notes do not retroactively change that CI result; they identify additional cases not yet exercised by the current synthetic model suite.

## 4. Recommended disposition

1. Keep Stage A OPEN until a qualified independent reviewer completes and signs the review.
2. Treat IMR-01 and IMR-02 as required synthetic-model follow-up before claiming that the model exercises shared fencing and predecessor-chain enforcement.
3. Add IMR-03 validation as a bounded input-hardening improvement.
4. After implementation, run the full CI workflow and record the exact tested commit and run URL.
5. Do not use these synthetic changes to authorize Stage C/D, live HSM/KMS integration, production keys, production signing, public deployment, or real-value token activity.

---
**Boundary statement:** These are internal code-review observations by the project team. They are not an independent security opinion, proof of production security, or authorization to proceed beyond the approved offline test scope.
