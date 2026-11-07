# WP4.14 — Remote Signer Serialization Scope and Single-Writer Ownership Audit

**Date:** 2026-11-07  
**Upstream:** CometBFT v0.40.0  
**HND branch:** `phase-0.2-planning`  
**Review type:** Upstream source inspection; documentation only  
**Status:** Single-server request serialization observed; cross-process exclusive ownership not established  
**Change boundary:** No HND source, tests, workflow, dependency, key, or runtime configuration changed.

## 1. Executive finding

CometBFT v0.40.0 `privval.SignerServer` uses an in-process mutex (`handlerMtx`) around the configured validation request handler. In the default server, that handler invokes `SignVote` or `SignProposal` on the server's `privVal`.

This is a useful serialization property for requests processed by one `SignerServer` instance. It does not establish exclusive ownership of the validator key/state across multiple server instances, operating-system processes, hosts, or failover nodes. The mutex is an in-memory field of one server object.

The server loop shown in the inspected source reads a request, processes it under the handler mutex, then writes a response. The listener endpoint also serializes its client-side `SendRequest` calls with an instance mutex. These are distinct, local serialization boundaries; neither is a distributed fencing protocol.

## 2. Source files inspected

Pinned CometBFT v0.40.0 sources:

- `privval/signer_server.go`: https://github.com/cometbft/cometbft/blob/v0.40.0/privval/signer_server.go
- `privval/signer_requestHandler.go`: https://github.com/cometbft/cometbft/blob/v0.40.0/privval/signer_requestHandler.go
- `privval/signer_listener_endpoint.go`: https://github.com/cometbft/cometbft/blob/v0.40.0/privval/signer_listener_endpoint.go
- `privval/file.go`: https://github.com/cometbft/cometbft/blob/v0.40.0/privval/file.go
- `privval/noise_listener.go`: https://github.com/cometbft/cometbft/blob/v0.40.0/privval/noise_listener.go

## 3. Serialization boundaries

### 3.1 Server-side request handler

`SignerServer` contains `handlerMtx` and `validationRequestHandler`. `servicePendingRequest` acquires `handlerMtx`, calls the configured handler with `ss.privVal`, then releases the lock before writing the response.

The default handler dispatches vote and proposal requests to `privVal.SignVote` and `privVal.SignProposal`.

**Supported conclusion:** a single `SignerServer` object serializes calls through its request handler.

**Unsupported conclusion:** multiple `SignerServer` objects or processes sharing a FilePV key/state are serialized. The inspected mutex cannot provide that guarantee.

### 3.2 Client-side endpoint

`SignerListenerEndpoint.SendRequest` acquires `instanceMtx` around connection establishment, request write, and response read. This serializes request/response use through that endpoint instance.

**Supported conclusion:** one endpoint instance does not concurrently multiplex its request/response exchange through this method.

**Unsupported conclusion:** two endpoint instances, two CometBFT nodes, or two external signer processes share a global serialization lock.

### 3.3 FilePV persistence

The FilePV state check and save path remains as described in the companion source audit. Atomic file replacement protects the replacement operation; it does not itself enforce single-writer ownership across independent FilePV instances.

### 3.4 Noise transport

The Noise listener authenticates a connecting peer and, when configured with an allowlist, rejects peers not on that list. Authentication of a peer is not proof that only one authenticated peer can issue signing requests for a validator identity. The allowlist must be paired with an explicit one-writer ownership/fencing rule.

## 4. Threat and deployment matrix

| Deployment shape | What source inspection establishes | Required additional evidence |
|---|---|---|
| One SignerServer instance, one connection/request loop | Handler calls are serialized by its local mutex. | Regression test for serialized vote/proposal requests and server lifecycle. |
| Two SignerServer instances in one process | Each has its own handler mutex. | Shared signer object synchronization or an external single-writer mechanism; test simultaneous calls. |
| Two signer OS processes using the same FilePV state path | No shared Go mutex across processes. | Deterministic two-process race test and OS-level or service-level exclusive ownership. |
| Two hosts or active/standby signers | No distributed fencing shown by these local mutexes. | Durable lease/fencing token or a single authoritative signing service; partition and stale-leader tests. |
| Noise-authenticated multiple clients | Peer authentication/allowlisting can restrict who connects. | Enforce one active authorized writer per validator; prove duplicate authorized clients cannot race. |
| Restart/failover after uncertain commit | Sequential restart probe covers a limited local case. | Crash-boundary tests, durable anchor, fencing, and proof that old signer cannot resume after takeover. |

## 5. Required single-writer invariants

Before production use, the signer design must define and prove:

1. Exactly one active writer is authorized for each validator consensus identity.
2. Every signing request passes through the same serialization authority.
3. Failover increments or changes a durable fencing generation before the new writer signs.
4. A previous writer with a stale generation is rejected even if it reconnects after a network partition.
5. Ownership state is bound to chain ID, network/Genesis identity, validator public key, and signer-state identity.
6. Restart after an ambiguous persistence/response boundary fails closed until authoritative state is reconciled.
7. Backup restoration cannot silently restore an older anti-double-sign generation.
8. The audit trail records ownership changes and signing decisions without exposing private keys or authentication secrets.

A local mutex, PID file, TCP/Noise allowlist, or atomic rename alone does not satisfy all these invariants.

## 6. Required future tests

| ID | Test | Pass condition |
|---|---|---|
| RS-OWN-01 | Start two SignerServer instances in one process against the same identity and state. | No conflicting signatures; one explicit ownership authority serializes both. |
| RS-OWN-02 | Start two independent signer processes against the same state path. | Second writer is rejected or safely serialized before any signature is emitted. |
| RS-OWN-03 | Connect two separately authenticated/allowlisted clients concurrently. | Only the authorized active writer can cause signing; duplicate client access cannot bypass ownership. |
| RS-OWN-04 | Partition old writer from coordinator, promote standby, then reconnect old writer. | Old writer's stale fencing generation is rejected; no dual-active interval. |
| RS-OWN-05 | Crash after durable state commit but before response; then perform failover. | New writer reconciles state and refuses conflicting request; retry is deterministic. |
| RS-OWN-06 | Restore a stale backup while a newer ownership generation exists. | Restore is rejected or signer remains disabled pending controlled recovery. |

All tests must collect every emitted signature from every process and verify the signed payloads cryptographically. Inspecting only the final state file is insufficient.

## 7. HND evidence classification

- Single `SignerServer` handler mutex: **PRESENT IN UPSTREAM SOURCE**.
- Client endpoint instance mutex: **PRESENT IN UPSTREAM SOURCE**.
- Cross-process FilePV serialization: **NOT ESTABLISHED**.
- Distributed active/standby fencing: **NOT ESTABLISHED BY THESE LOCAL MUTEXES**.
- Noise peer authentication: **PRESENT; NOT EQUIVALENT TO SINGLE-WRITER OWNERSHIP**.
- HND concurrent multi-process ownership tests: **NOT YET IMPLEMENTED OR EXECUTED**.
- Production signer ownership/failover safety: **NOT APPROVED**.

## 8. Gate

The next implementation review must choose one authoritative single-writer architecture and test its failure modes. The implementation should not be improvised as a small mutex patch: multi-process and multi-host failover require explicit ownership, fencing, durable state, and crash semantics.

This is a source-scope audit, not evidence of an observed production double-sign. It does not approve production signing, token issuance, protocol freeze, or public network launch.


## Addendum — same-host signer helper ownership lock (2026-11-07)

The disposable HND signer helpers now acquire a non-blocking OS advisory
`flock` on a lock file derived from the anti-double-sign state path before
loading FilePV state or starting a signer server. The lock file is opened with
no-follow semantics, restricted to mode 0600, checked as a regular file, and
checked for current-UID ownership. A second helper process using the same
state path is rejected while the first owner holds the lock. The Noise helper
uses the same same-host lock rule.

This is a **same-host/local-filesystem mitigation in the test helper**, not a
CometBFT upstream guarantee and not a distributed fencing protocol. It does
not protect against a process that bypasses the helper, a hostile privileged
local actor, filesystems with unsuitable lock semantics, or two hosts that
do not share a reliable lock authority. It also does not solve AUTH-TOCTOU
signature-release linearization or stale-host fencing.

The previous negative dual-sign reproduction is being converted into a
positive lock-contention test: first process acquires the lock and signs;
second process is rejected while the lock is held; after clean owner exit,
the second process may acquire the lock only with the newly persisted state
digest and must reject a conflicting H/R/S vote. Unix and Noise helper lock
probes are now wired into CI; their new results are pending.
