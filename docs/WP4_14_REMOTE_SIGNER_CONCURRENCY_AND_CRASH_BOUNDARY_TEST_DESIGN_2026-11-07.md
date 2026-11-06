# WP4.14 — Remote Signer Concurrency and Crash-Boundary Test Design

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Reviewed baseline:** `7eb3d082ad5703f0b32acb709df5fefd0ae38b84`  
**Review type:** static source and test-harness audit  
**Status:** design/evidence gap report only; no tests executed by this review.

## 1. Executive finding

The repository's process-isolated CometBFT v0.40.0 probe tests sequential signer lifecycle behavior: one child signer is started, signs a vote, is stopped, and is restarted using the same key/state paths. The probe verifies identical-request signature reuse and conflicting same-H/R/type request rejection before and after restart.

That is useful anti-double-sign integration evidence. It does **not** test two live signer processes concurrently accessing the same validator key/state, and it does not inject crashes at the persistence boundaries surrounding a signature operation.

The offline anti-rollback reference model has thread-level compare-and-swap tests, but its own module documentation explicitly describes an in-memory synthetic anchor and states that it is not connected to CometBFT, a signer, a filesystem, HSM, TPM, or KMS. Model concurrency tests cannot be promoted into production signer process-concurrency evidence.

## 2. Reviewed evidence

### 2.1 Sequential process probe

In `scripts/cometbft_v040_remote_signer_process_probe.go`, `runRemoteAntiDoubleSignProbe`:

1. Creates one temporary directory, Unix socket, key path, and state path.
2. Starts one signer child process.
3. Sends a vote at a fixed height, round, and type.
4. Repeats the same vote and requires the same persisted signature.
5. Sends a conflicting vote at the same height/round/type and requires rejection.
6. Stops and waits for the first child.
7. Starts one replacement child with the existing state file.
8. Requires the same public key, identical retry signature, and rejection of the conflicting vote after restart.

This exercises sequential restart and persisted FilePV anti-double-sign behavior in a disposable process probe.

### 2.2 What is not in that probe

The reviewed function does not:

- start two signer children simultaneously against the same key/state files;
- race conflicting requests through separate signer processes;
- prove an OS-level exclusive lock or distributed signing lease;
- kill a signer at controlled points during state persistence;
- simulate host power loss or storage-controller write reordering;
- prove an independent checkpoint survives rollback of the signer host and its local storage.

### 2.3 Offline reference model distinction

`hnd_v02/anti_rollback_reference.py` labels itself an offline synthetic protocol model. Its `SyntheticAnchor` uses a thread lock and in-memory state; this is not a durable, independently administered production anchor.

`tests/test_v02_anti_rollback_reference.py` contains a concurrent compare-and-swap model test. That test concerns concurrent operations against the in-memory reference object, not concurrent production signer processes or CometBFT FilePV storage.

## 3. Required process-level acceptance tests

The following tests are proposed. They have not been implemented or executed by this review.

| ID | Scenario | Required assertion |
|---|---|---|
| RS-CON-01 | Two signer processes start against one key/state directory | At most one obtains signing authority; the other fails closed before serving signatures |
| RS-CON-02 | Both processes receive identical H/R/S request concurrently | No conflicting output; result is deterministic and conforms to pinned CometBFT semantics |
| RS-CON-03 | Both processes receive conflicting block IDs for the same H/R/S | At most one value can be signed; the other request is rejected |
| RS-CON-04 | Second process starts after first acquires authority but before first signs | Second process cannot bypass the first process's ownership |
| RS-CON-05 | First process dies while holding ownership | Recovery requires a safe fencing/lease transition; stale process cannot resume signing |
| RS-CRASH-01 | Terminate before signing intent is durably recorded | Restart cannot emit a signature inconsistent with durable state |
| RS-CRASH-02 | Terminate after intent persistence but before signature response | Retry/reconciliation is safe and cannot produce a conflicting signature |
| RS-CRASH-03 | Terminate during state-file write | Partial/truncated state is rejected; no silent reset or fresh-state initialization |
| RS-CRASH-04 | Terminate after state write but before durable flush completes | Recovery behavior is safe under the documented filesystem durability model |
| RS-CRASH-05 | Terminate after durable state update but before response delivery | Exact retry is safe; conflicting request remains rejected |
| RS-CRASH-06 | Restore older valid local state while independent checkpoint is advanced | Signer refuses to sign and emits an auditable fail-closed result |

## 4. Test design constraints

- Use a disposable validator identity and isolated temporary storage. Never use production keys.
- Pin the exact CometBFT source commit and binary digest for every run.
- Synchronize process races with explicit barriers; do not rely on timing sleeps as proof of concurrency.
- Capture each process PID, signer identity, request tuple (chain ID, height, round, step), result, and state digest.
- Preserve test artifacts and logs without including private keys or secret transport identities.
- Distinguish process crash, host reboot, and power-loss simulation; they are not equivalent.
- Define the filesystem and durability assumptions before interpreting fsync or atomic-rename results.
- A local lock alone is not an independent monotonic trust anchor and may not survive host rollback or storage snapshot restoration.
- Require a separate fencing authority or equivalent independently protected monotonic checkpoint before claiming cross-process/cross-host rollback resistance.

## 5. Acceptance evidence package

A passing result should include:

1. Exact source commit, toolchain versions, build command, and signer binary SHA-256.
2. Test harness commit and deterministic synchronization procedure.
3. Per-process start/stop/crash timeline.
4. All signing request tuples and whether a signature was released.
5. Before/after state digests and independently authenticated checkpoint sequence.
6. Explicit negative assertions for both signer processes and recovery attempts.
7. Reproducible CI job output and retained artifacts.
8. Independent review of the implementation and failure-domain assumptions.

A green test is evidence only for the scenarios and assertions actually exercised. It does not automatically certify HSM custody, deployment authorization, or production operations.

## 6. Disposition

| Property | Current evidence |
|---|---|
| Sequential signer restart | Present in process probe |
| Identical retry and conflicting same-H/R/S rejection across restart | Present in process probe |
| In-memory model compare-and-swap concurrency | Present in synthetic reference model tests |
| Two live signer processes sharing one validator state | Not demonstrated |
| Process-level exclusive signing ownership | Not demonstrated |
| Crash injection at persistence boundaries | Not demonstrated |
| Host/storage rollback resistance using an independent durable anchor | Not demonstrated |

**Release decision:** keep production validator signing disabled until process-level concurrency, crash-boundary safety, and independently anchored rollback rejection are implemented, run reproducibly, and independently reviewed.

This document is a test-design and evidence-gap report only. It changes no source, tests, workflows, signer keys, runtime settings, or protocol specification. It is not a security certification or launch approval.
