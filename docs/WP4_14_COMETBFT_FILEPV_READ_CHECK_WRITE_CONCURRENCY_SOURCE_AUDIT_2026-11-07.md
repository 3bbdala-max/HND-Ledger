# WP4.14 — CometBFT FilePV Read-Check-Write Concurrency Source Audit

**Date:** 2026-11-07  
**Target:** CometBFT v0.40.0 `privval.FilePV` and `libs/tempfile.WriteFileAtomic`  
**HND branch:** `phase-0.2-planning`  
**Review type:** Upstream source inspection; documentation only  
**Status:** High-severity concurrency risk requiring an executable reproduction and a separately reviewed remediation  
**Change boundary:** No HND source, tests, workflow, CometBFT dependency, key, or runtime configuration changed.

## 1. Executive finding

The upstream CometBFT v0.40.0 `FilePV` implementation performs an in-memory H/R/S check, signs, updates its in-memory last-sign state, and persists that state through `FilePVLastSignState.Save()`. Persistence delegates to `tempfile.WriteFileAtomic`, which writes a temporary file and atomically renames it over the target.

The inspected code does **not** establish a lock or compare-and-swap spanning the complete logical sequence:

1. read current persisted state;
2. check H/R/S and vote bytes;
3. sign the request;
4. commit the new state.

The mutex visible in `WriteFileAtomic` protects only its process-local temporary-file name generator. It is not a lock on the validator state file and does not serialize two FilePV instances or two OS processes.

**Risk statement:** two independent processes (or concurrent calls sharing an unsynchronized FilePV instance) must not be assumed safe merely because the final file replacement is atomic. If both processes load the same old state before either commits, each can make its decision from a stale snapshot. The source review identifies this race window; it does not claim that a conflicting double-sign has already been reproduced in HND CI.

## 2. Upstream source path inspected

Pinned source URLs:

- `privval/file.go`: https://github.com/cometbft/cometbft/blob/v0.40.0/privval/file.go
- `libs/tempfile/tempfile.go`: https://github.com/cometbft/cometbft/blob/v0.40.0/libs/tempfile/tempfile.go

### 2.1 FilePV state check

`FilePV.signVote` and `FilePV.signProposal` read `pv.LastSignState` into a local value and call `CheckHRS`. The check rejects H/R/S regressions and reuses the prior signature for the same H/R/S only when the stored sign bytes match (with the documented timestamp-only exception).

The inspected `FilePV` struct contains `Key` and `LastSignState`; no per-instance mutex is declared in this struct. The inspected signing methods do not acquire a lock around the H/R/S check, signature operation, and state save.

### 2.2 State commit

After signing, `saveSigned` updates the in-memory Height, Round, Step, Signature and SignBytes, then calls `LastSignState.Save()`. `Save()` serializes that state and calls `tempfile.WriteFileAtomic`.

### 2.3 What atomic replacement does and does not guarantee

`WriteFileAtomic` creates a unique temporary file using exclusive creation, writes the bytes, closes the file, and renames it over the target path. Its package-level mutex is used only when generating temporary-file suffixes.

This helps prevent readers from observing a partially written target file under the filesystem's rename semantics. It does **not** implement a state-file lock, validate that the file has not changed since it was read, or perform a compare-and-swap against the previous H/R/S record.

Atomic file replacement is therefore not equivalent to atomic read-check-sign-write serialization.

## 3. Concurrency interleaving to reproduce

Use two independent OS processes A and B, both loading the same disposable validator key and the same initially committed state S0.

| Order | Process A | Process B |
|---|---|---|
| 1 | Loads S0 | |
| 2 | | Loads S0 |
| 3 | Checks request X at H/R/S against S0 | |
| 4 | | Checks conflicting request Y at the same H/R/S against S0 |
| 5 | Signs X using its in-memory state | |
| 6 | | Signs Y using its in-memory state |
| 7 | Atomically replaces state file with Sx | |
| 8 | | Atomically replaces state file with Sy |

The schedule is a hypothesis derived from the absence of a shared read-check-write serialization primitive in the inspected path. It must be tested against the exact build and filesystem. The final file may contain only one of Sx or Sy, while both processes may already have returned signatures. A last-writer-wins file outcome would not undo a signature already emitted.

The test must capture both signatures and verify whether both distinct vote payloads were accepted for the same validator H/R/S.

## 4. Required reproduction cases

| ID | Test | Required oracle |
|---|---|---|
| FPV-RACE-01 | Two processes load the same initial state, then concurrently sign conflicting votes at one H/R/S using a barrier. | Exactly one conflicting request may produce an accepted signature. If both return signatures, test fails even if the final state file is parseable. |
| FPV-RACE-02 | Same schedule with conflicting proposals at one H/R/S. | No two conflicting proposal signatures. |
| FPV-RACE-03 | Two processes concurrently submit identical sign bytes at one H/R/S. | Behavior matches an explicit idempotency contract; no state corruption or unexplained divergent result. |
| FPV-RACE-04 | Same-process concurrent goroutines call signing methods on one FilePV instance. | No data race, inconsistent state, panic, or conflicting acceptance. Run with Go race detector where supported. |
| FPV-RACE-05 | Repeat across many fresh state directories and randomized scheduling. | Record all iterations and fail on any conflicting dual signature. |
| FPV-RACE-06 | Kill one process after signature creation and race the other process before/after state rename. | Crash/restart never enables a conflicting signature; all emitted signatures are included in the oracle. |

The harness must not merely compare the final state file. It must collect every signature returned to either process and cryptographically verify each signature against its exact canonical vote/proposal bytes and validator public key.

## 5. Remediation properties to evaluate (not a patch specification)

A safe remediation must serialize the entire decision and commit boundary, not just the final write. Candidate designs require upstream-compatible review and may include:

- a single-writer signer service that is the exclusive owner of the key and durable state;
- an OS-level inter-process lock with well-defined crash release and filesystem semantics, combined with state re-read while holding the lock;
- a transactional storage backend providing atomic conditional update / compare-and-swap over the H/R/S predecessor;
- a hardware-backed or remote signing service that enforces monotonic H/R/S and idempotency within the trusted signing boundary.

Any lock-based design must define lock ownership, stale-lock recovery, process death, network filesystems, container/host boundaries, permission model and fencing. A lock file that can be copied or bypassed is not a robust distributed fencing mechanism.

Any remote signer design must prove that all requests for one validator identity converge on one authoritative serialization point and that failover cannot create two active writers.

Do not treat a mutex inside one process as protection against two independent processes. Do not treat atomic rename as a substitute for serialization. Do not add a production lock or alter CometBFT source without a separate implementation review and explicit source-change authorization.

## 6. HND evidence implications

The current HND process probe demonstrates sequential restart behavior. The current four-validator external/Noise signer integrations demonstrate outage and recovery in disposable test environments. These tests do not establish simultaneous multi-process access to the same FilePV state.

The prior HND concurrency matrix `WP4_14_REMOTE_SIGNER_CONCURRENCY_CRASH_EXECUTION_MATRIX_2026-11-07.md` should therefore be extended by the FPV-RACE cases above when implementation authorization is granted.

Successful CI runs that execute the current sequential probes must not be described as proof that concurrent FilePV writers are safe.

## 7. Gate and disposition

- Upstream FilePV read-check-write serialization: **NOT ESTABLISHED BY INSPECTED SOURCE**
- Atomic file replacement: **PRESENT; LIMITED TO FILE REPLACEMENT**
- Multi-process conflicting-sign reproduction: **NOT YET EXECUTED**
- HND remote-signer shared-state concurrency: **NOT PROVEN**
- Production signer concurrency safety: **NOT APPROVED**
- Required next evidence: deterministic two-process reproduction, signature-level oracle, crash/restart coverage, reviewed serialization design, and CI on the exact resulting implementation commit.

This audit is a source-level risk finding, not a claim that a production network has been attacked or that a double-sign has already occurred.
