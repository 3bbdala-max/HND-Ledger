# WP4.14 — Remote signer concurrency and crash test execution matrix

Date: 2026-11-07  
Status: **partial negative probe implemented and executed; full concurrency/crash matrix remains open**  
Target branch: `phase-0.2-planning`  
Scope: documentation only. No source, test, workflow, key, or production configuration changes are authorized by this document.

## 1. Purpose and evidence boundary

The existing process probe demonstrates sequential restart behavior. The existing four-validator integration demonstrates signer outage and recovery. Neither demonstrates two independently running signer processes safely sharing or contending for the same anti-double-sign state, nor does it inject process termination at durable-write boundaries.

This matrix turns the proposed RS-CON and RS-CRASH cases into acceptance criteria for a future isolated test harness. Passing these tests would be necessary evidence for the tested implementation, not production approval. Tests must use disposable identities, temporary directories, and an isolated network.

## 2. Required harness contract

Before implementing the cases, the harness must expose:

- A way to launch two independently supervised signer processes against the same configured validator identity and state location.
- A deterministic barrier so both processes can receive conflicting requests for the same height/round/step before either is allowed to complete.
- A durable-state inspection function that reads the actual persisted signer state after process termination; an in-memory object or synthetic anchor is insufficient.
- A crash injector at named persistence boundaries, with the process forcibly terminated (not a handled exception).
- A restart operation that uses the same identity and the exact persisted state directory.
- Structured logs containing process ID, request tuple, decision, state version/digest, and exit reason. Do not log private key material or authentication secrets.

The harness must fail closed if it cannot prove that the two processes use the same identity and shared state location. Do not simulate concurrency by calling two functions sequentially in one process.

## 3. Concurrency acceptance matrix

| ID | Setup and stimulus | Required assertions |
|---|---|---|
| RS-CON-01 | Start signer A and signer B simultaneously with the same identity and state directory. Submit the same H/R/step and identical vote to both behind a barrier. | At most one durable state transition occurs; both responses are consistent with the implementation's documented idempotent-retry policy; persisted state is valid after both exit. |
| RS-CON-02 | With A and B still live, submit two different votes for the same H/R/step concurrently. | Never produce two accepted signatures; at most one vote is committed; the conflicting request is rejected; durable state identifies the accepted vote unambiguously. |
| RS-CON-03 | Submit requests for adjacent heights concurrently, deliberately vary completion order. | No state regression; each accepted request obeys the monotonic ordering rule; restart preserves the highest durable state. |
| RS-CON-04 | Kill the process that loses the contention race, then restart it against the same state directory and retry both the accepted and conflicting requests. | Accepted retry is handled according to the documented idempotency rule; conflicting vote remains rejected; no second signature is produced. |
| RS-CON-05 | Repeat contention with synchronized bursts and randomized scheduling across multiple iterations. | No duplicate conflicting acceptance, corrupted state, deadlock, or unexplained success; record iteration count, seeds, and all failure artifacts. |

## 4. Crash-boundary acceptance matrix

The implementation team must first map these logical boundaries to the actual persistence code. If a boundary does not exist in the implementation, record it as not applicable with code evidence; do not silently skip it.

| ID | Forced termination point | Required restart assertion |
|---|---|---|
| RS-CRASH-01 | After request validation but before any durable write. | Restart may safely accept the request; no partial state is treated as committed. |
| RS-CRASH-02 | During temporary-file or journal write, before durable flush. | Partial temporary data is ignored or safely recovered; previous committed state remains authoritative. |
| RS-CRASH-03 | After file data flush but before atomic replacement/commit marker. | Restart deterministically selects the last committed state; no partially written record is accepted. |
| RS-CRASH-04 | Immediately after atomic replacement/commit marker, before response is returned. | Retry of the same request is idempotent; conflicting request is rejected. |
| RS-CRASH-05 | After durable state update but before signature response delivery. | Restart does not sign a conflicting vote; same-request retry follows the documented response/recovery behavior. |
| RS-CRASH-06 | During restart/recovery itself, at each recovery write boundary. | A subsequent restart converges to one valid monotonic state or fails closed; it must never silently roll back. |

## 5. Test oracle and evidence bundle

For every case, preserve:

1. Exact source commit SHA and harness version.
2. Test ID, iteration, deterministic random seed (if applicable), and process IDs.
3. Identity fingerprint/public key only; never private key bytes.
4. Request tuples and outcome codes for both processes.
5. Before/after durable-state digests and parsed state versions.
6. Crash injection point, exit status/signal, and restart outcome.
7. Full test command, environment versions, and CI run URL/ID.
8. A machine-readable summary with pass/fail/blocked status and reason.

A pass requires all assertions above and independently inspectable artifacts. A test that only checks return codes without examining persisted state is insufficient.

## 6. Negative controls

The suite must prove it can detect unsafe behavior by including controlled harness mutations or fixtures that cause:

- A stale state snapshot to be written after a newer state.
- Two processes to bypass the shared serialization/compare-and-swap boundary.
- A truncated or malformed persisted record.
- A retry that changes the vote payload for an already-used H/R/step.

Each negative control must be rejected or detected. Do not weaken production checks to make a negative control pass.

## 7. Execution sequence and gates

1. Identify the actual signer persistence functions and document each durable boundary with file/line references.
2. Implement the harness in a separate reviewed change; this document does not authorize that implementation.
3. Run each case independently, then run the stress repetitions.
4. Publish raw artifacts and CI evidence tied to the exact tested commit.
5. Obtain independent security review of the implementation and test oracle.
6. Reassess production custody, host rollback resistance, backup/restore, access control, and operational monitoring separately.

**Gate:** Until the concurrency and crash cases are implemented and pass against the real signer persistence path, remote-signer concurrency/crash safety remains unproven. The existing successful CI run is not a substitute for these tests.

## 8. Current status

- The original cases in Sections 3–4 remain the full acceptance plan; they are not all implemented or executed.
- Existing anti-rollback reference model uses an in-memory synthetic anchor, not a durable external anchor.
- No protocol freeze, production signing authorization, token issuance, or public-network launch approval is granted.

## 9. Addendum — partial negative reproduction (2026-11-07)

A separate disposable Go probe was added at `scripts/cometbft_v040_remote_signer_process_probe.go` and wired into `.github/workflows/hnd-v02-tests.yml`.

Evidence:
- Tested commit: `f769dcb2890085497bbd275e325e974eff793b6e`
- CI run: `42323914517` — both workflow jobs completed successfully.
- Step: `Reproduce shared FilePV multi-process dual-sign risk (expected unsafe behavior)` — completed / success.
- Evidence record: `docs/WP4_14_SHARED_FILEPV_MULTIPROCESS_DUAL_SIGN_REPRODUCTION_2026-11-07.md`.

The probe launches two separate OS signer processes against the same key and state paths. Both load the same initial state before either signing request. Process 0 signs a vote; process 1 then signs a conflicting vote at the same height, round, and vote type using its stale in-memory state. Both returned signatures are independently verified against the validator public key.

This is a **negative security reproduction**, not a passing safety test. It establishes that the tested shared FilePV path does not enforce cross-process exclusive ownership. Requests are sequential after both processes load state, so this is not claimed as the simultaneous-request RS-CON-02 acceptance test, a multi-host fencing test, or a crash-boundary test. The comprehensive RS-CON and RS-CRASH matrix remains open.



## 10. Same-host advisory lock mitigation added (2026-11-07)

The disposable Unix and Noise signer helpers now acquire a non-blocking
OS-level advisory lock derived from the signer anti-double-sign state path
before loading FilePV state. Lock files use no-follow open semantics, mode
0600, regular-file validation, and current-UID ownership checks. The old
shared-FilePV negative probe has been converted to verify the intended
same-host behavior:

1. signer process A acquires the state-path lock and signs a vote;
2. signer process B using the same key/state path is rejected while A is live;
3. after A exits, B may acquire the lock only using the new persisted state
   digest;
4. B must reject a conflicting vote at the same H/R/type.

A parallel Noise-helper lock-contention probe is also wired into CI.

**Evidence status:** implementation and workflow wiring are committed, but
fresh CI results are pending. This mitigates only cooperating helper
processes on the same host and local filesystem. It is not a distributed
lease, a durable fencing token, or a protection against other software that
does not honor the lock. The RS-CON and RS-CRASH matrix, multi-host failover,
and signer-side authorization linearization remain OPEN.
