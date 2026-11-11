# Remote Activation Recovery Protocol (Station 2)

## Status and scope

This document defines the required recovery behavior for the HND v0.2 activation coordinator. It is a protocol specification, not evidence that a production coordinator or independently operated service has been deployed. The current SQLite intent and monotonic-anchor servers are single-host reference implementations only.

The protocol deliberately does **not** claim a distributed atomic transaction across the intent service, two monotonic namespaces, and the validator's local profile store. It uses a durable intent as a serialization and recovery record, exact read-after-write reconciliation, and one atomic local activation operation.

## Identity and immutable request

Every activation has one caller-generated, globally unique `activation_id`. The prepare request is immutable and binds:

- predecessor and successor sequence/digest for `trust-manifest`;
- predecessor and successor sequence/digest for `vsp-profile`;
- exact profile artifact digest;
- exact operator acknowledgement-set digest.

All retries MUST use the same activation ID and byte-for-byte equivalent canonical request. A changed artifact, acknowledgement set, predecessor, successor, or sequence requires a new activation only after the current intent is safely finalized or resolved under a separately approved recovery procedure. Never create a second ID to escape a timeout or conflict.

## Required order

1. **Verify evidence locally.** Verify the complete trust-manifest chain, VSP signatures and schema, operator acknowledgements, profile bytes, and all predecessor/successor relationships. Compute and pin the immutable request.
2. **Prepare intent.** Call remote `prepare`. If the request times out or the response is lost, read the same activation ID. Continue only if the stored intent exactly matches the request and is `prepared` (or is already `finalized` with the exact same digests, indicating completed work). If absent, retry only the identical request and same ID. A conflicting request is fatal.
3. **Advance trust-manifest anchor.** Read the namespace. If it equals the exact proposed successor, treat the operation as already committed. If it equals the exact predecessor, issue compare-and-advance. After false, timeout, or lost response, read again; accept only the exact successor. Any other value is a hard conflict and requires operator intervention.
4. **Advance VSP anchor.** Apply the identical reconciliation rule to `vsp-profile`. Do not advance it until the trust-manifest anchor is confirmed at the exact successor. If the first anchor advanced but the second did not, retain the same prepared intent and resume this same activation; do not roll back the first anchor.
5. **Commit locally.** Only after both remote anchors read back as the exact successors may the validator call the local `AtomicActivationBackend.compare_and_activate`. That backend MUST atomically validate/install the exact profile and advance both local namespaces in one durable transaction. Sequential file/database writes are not a conforming substitute. If local commit outcome is unknown, read local active state: exact proposed state is idempotent success; exact predecessor permits retry of the same verified operation; partial or any other state fails closed.
6. **Finalize intent.** Call finalize with the same activation ID and exact profile and acknowledgement digests. On timeout, read the same ID. Accept only `finalized` with exact digests; if it remains `prepared`, retry the same finalize request. A mismatch is fatal.
7. **Permit startup.** Startup authorization must verify the completed activation state and must not launch CometBFT, ABCI, or signers while an activation is unresolved or either remote anchor is unavailable. All launch paths must pass through the authorization gate.

## Reconciliation table

| Observed state | Required action |
|---|---|
| Intent absent after timeout | Retry identical prepare with same ID |
| Intent prepared and exact request matches | Resume at first anchor not yet at exact successor |
| Intent finalized and exact request/digests match | Treat as completed; verify local state and both anchors before startup |
| Intent ID exists but request differs | Fail closed; never mutate or reuse the ID |
| Anchor equals exact successor | Treat that anchor write as committed |
| Anchor equals exact predecessor | CAS exact successor using same intent |
| Anchor is behind, ahead, or same sequence with different digest | Fail closed; no overwrite, reset, or guessed repair |
| One anchor advanced and the other did not | Keep intent prepared; resume the second anchor using same ID |
| Local state equals exact proposed state | Treat local commit as idempotently complete |
| Local state equals exact predecessor | Retry same verified atomic local commit |
| Local state is partial or otherwise different | Fail closed; manual witnessed recovery required |
| Finalize response lost | Read same ID; retry finalize only if still prepared with exact digests |
| Intent permanently prepared / service unavailable | Block new activations and startup; preserve evidence for witnessed recovery |

## Safety invariants

- The intent service MUST provide one globally active intent across all replicas, with linearizable prepare/read/finalize and durable commits. A per-process lock or single-host SQLite constraint is insufficient.
- Each anchor namespace MUST provide linearizable compare-and-advance, durable read-after-write, append-only authenticated audit, and an administration/backup domain independent of validator hosts.
- An unknown write outcome is never permission to submit a different successor.
- No rollback, reset, deletion, automatic timeout expiry, or silent clearing of a prepared intent is permitted.
- The validator MUST fail closed when the intent service or either anchor cannot be authenticated and read.
- The local profile installation and both local anti-rollback state changes MUST remain one atomic durable backend operation.
- Logs and recovery records must bind activation ID, request digest, observed records, and decisions without exposing private keys or secret material.

## Stuck-intent and abort policy

There is intentionally no automatic abort endpoint in this protocol. Once either remote anchor has advanced, rolling it back would violate monotonicity. A permanently stuck prepared intent therefore blocks subsequent activation until a separately specified witnessed recovery procedure proves the exact state of both anchors, local activation, and profile artifact. That procedure must require independent governance/witness authorization, append-only audit, and a strictly forward-only successor plan. It must never delete or rewrite history to make the system appear healthy.

## Required fault-injection acceptance tests

Before the coordinator can be accepted, automated tests must inject a crash or lost response after each boundary:

1. before prepare; after durable prepare but before response;
2. before and after each anchor CAS, including timeout after server commit;
3. after trust anchor success but before VSP anchor success;
4. after both anchors succeed but before local activation;
5. after local durable activation but before response;
6. after local activation but before finalize;
7. after durable finalize but before response;
8. during concurrent attempts with distinct activation IDs;
9. during remote service restart, stale replica read, backup restore, and loss of connectivity;
10. with mismatching sequence/digest, malformed intent, missing guard, orphan guard, and partial local state.

Each test must prove that recovery uses the same activation ID and exact digests, never advances an unexpected state, never starts consensus while unresolved, and never silently frees a prepared intent.

## Production exit criteria

Station 2 remains open until all of the following are demonstrated:

- a deployed, independently administered, multi-replica linearizable intent service;
- independently administered, durable, rollback-resistant monotonic anchor service(s);
- a production atomic local activation backend and content-addressed profile installation;
- a crash-safe coordinator implementing this protocol and all fault-injection tests;
- a single enforced CometBFT/ABCI/signer startup authorization path;
- witnessed stuck-intent recovery, key-loss recovery, certificate lifecycle, monitoring, backup/restore drills, and independent security review.
