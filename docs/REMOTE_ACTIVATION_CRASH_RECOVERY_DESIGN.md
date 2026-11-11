# Remote Anchor and Local Activation: Crash-Recovery Design

**Status:** required design for the next implementation increment. This document does not claim that the current SQLite activation backend or remote-anchor client implements this protocol.

## Why a simple wrapper is unsafe

The remote monotonic anchor and the local profile store are two independent durability domains. A client cannot make a remote compare-and-advance plus a local filesystem/SQLite commit atomic merely by calling them in sequence.

- Remote first, local second: a crash after remote success leaves the remote sequence ahead of the installed profile.
- Local first, remote second: a crash after local success leaves the running profile ahead of the anti-rollback authority.
- Retrying after a timeout is unsafe: the remote write may have committed even though the response was lost.

Therefore, do not implement a wrapper that reports atomic activation while it performs two independent commits.

## Required protocol: durable intent, install, finalize

The remote service must expose a linearizable transaction state per chain/activation ID. The following operations are a proposed v2 API; they are not implemented by the v1 read/CAS client.

1. **Prepare**: compare the exact current Trust Manifest and VSP records; verify both proposed records are exact successors; create a unique activation intent containing activation ID, predecessor records, successor records, profile digest, and operator-ack digest. The intent is durable and immutable. Only one pending intent per chain is allowed.
2. **Install**: the node verifies the profile bytes against the pinned schema and digest, writes them to a content-addressed immutable location, fsyncs the file and containing directory, then atomically switches a small active-profile pointer to the prepared digest. The node records the activation ID in the same local durable transaction as the pointer switch.
3. **Finalize**: the remote service verifies the same activation ID and exact prepared values, advances both monotonic records, and marks the intent finalized in one linearizable durable transaction.
4. **Start**: the process supervisor may start CometBFT, ABCI, and signers only after it reads a finalized remote intent and confirms that the local active pointer, activation ID, and profile digest exactly match it.

## Recovery rules

| Observed state | Required behavior |
|---|---|
| No remote intent; local state is old | Normal old state may start only if it matches remote finalized state |
| Prepared intent; local pointer still old | Do not start; safely abort only through a witnessed abort operation that proves no install occurred |
| Prepared intent; local pointer is new | Do not start; retry finalize using the same activation ID and exact payload, or enter operator recovery |
| Finalized intent; local pointer is old | Do not start; reinstall the exact content-addressed artifact, then verify local activation ID and digest |
| Finalized intent; local pointer is new and exact | Startup may proceed after all other authorization checks |
| Timeout after prepare/finalize | Read by activation ID and reconcile; never create a new activation ID or infer failure from timeout |
| Conflicting intent or digest | Hard fail and require witnessed recovery; never overwrite or roll back |

## Service-side invariants

- Prepare/finalize/abort are linearizable across replicas and durable before success responses.
- Intent IDs are globally unique and idempotent; replay with different payload is rejected.
- Finalize advances both namespaces together and only once.
- Abort is permitted only before local installation is attested; the service cannot infer this from a client assertion alone. A production abort ceremony needs independently witnessed evidence or a design that makes prepared intents permanently recoverable instead of abortable.
- The service retains append-only audit evidence for every transition.
- Disaster recovery preserves finalized sequence values and unresolved intents. Restoring a backup must never silently discard a finalized transition or pending intent.
- HND startup fails closed if the service is unavailable or the intent cannot be reconciled.

## Implementation sequence

1. Specify and implement the remote service state machine and durable storage.
2. Add protocol-versioned client methods for prepare, read-intent, finalize, and witnessed abort.
3. Implement a local content-addressed profile store and activation journal.
4. Implement recovery before enabling process launch.
5. Add crash injection after every durable boundary, concurrent-writer tests, lost-response tests, stale-snapshot tests, and full supervisor tests.
6. Obtain an independent review of the service's linearizability, identity, backup, and recovery model.

Until all six steps pass, the remote client is a transport adapter/reference and station 2 remains open. SQLite remains a test/reference backend, not the production trust anchor.
