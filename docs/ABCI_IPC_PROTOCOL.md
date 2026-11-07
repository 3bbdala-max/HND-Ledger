# HND private IPC contract for the CometBFT adapter

**Status:** protocol proposal for implementation; no IPC server or Go adapter exists yet.

## Transport

- One local Unix-domain stream socket between the Go adapter and the Python engine.
- The socket path is configured explicitly and must be owned by the HND service account with restrictive filesystem permissions.
- No TCP listener is permitted in the initial implementation.
- The connection carries UTF-8 JSON Lines: one request object per line and exactly one response object per request.
- The initial maximum encoded request or response line is 1 MiB. The Python engine must also enforce the stricter ledger transaction and block limits independently.
- A malformed frame, unsupported protocol version, duplicate JSON key, unknown method, or mismatched request ID is a protocol error. The adapter fails closed; it must not invent a successful ABCI response.

## Envelope

Every request has exactly these top-level fields:

```json
{
  "protocol": "hnd-ipc/1",
  "id": "adapter-generated-request-id",
  "method": "Info",
  "payload": {}
}
```

A successful response has exactly:

```json
{
  "protocol": "hnd-ipc/1",
  "id": "adapter-generated-request-id",
  "ok": true,
  "result": {}
}
```

A rejected operation has exactly:

```json
{
  "protocol": "hnd-ipc/1",
  "id": "adapter-generated-request-id",
  "ok": false,
  "error": {
    "code": "INVALID_REQUEST",
    "message": "stable, non-secret diagnostic",
    "retryable": false
  }
}
```

The adapter must match response `protocol` and `id` to the outstanding request. Error messages must not include private keys, raw secret material, or unbounded user-controlled content.

## Serialization rules

- The Go adapter serializes the pinned CometBFT v0.40.0 ABCI request payload using the generated struct JSON tags and Go's standard JSON encoder.
- Byte slices therefore use JSON base64 strings; Python validates and decodes them strictly.
- The Python engine returns response fields using the same JSON field names and base64 representation expected by the adapter's typed response decoder.
- Integers must be JSON integers, never booleans or floating-point values. Python rejects booleans where integer fields are required.
- JSON objects must not contain duplicate keys. Python must reject duplicate keys rather than accepting the last value.
- Unknown top-level envelope fields and unknown method-specific payload fields are rejected.
- No JSON number may exceed the target Go signed/unsigned field range.

## Method boundary

The initial implementation must provide explicit, tested mappings for:

| IPC method | Python responsibility |
|---|---|
| Info | Return the last durably committed height and app hash |
| InitChain | Validate chain ID and canonical genesis application state; initialize a new database exactly once |
| CheckTx | Verify canonical transaction bytes, chain ID, and signature only |
| InsertTx | Validate and add a transaction to the bounded disposable mempool |
| ReapTxs | Return an ordered mempool selection bounded by the caller's byte limit |
| PrepareProposal | Return a deterministic valid ordered selection against committed state |
| ProcessProposal | Validate the complete ordered proposal without mutating committed state |
| FinalizeBlock | Execute the decided ordered transaction list speculatively and return per-transaction results and app hash |
| Commit | Persist the pending finalized block atomically and return the committed application result |
| Query | Support only documented read-only paths; reject unknown paths |
| ExtendVote / VerifyVoteExtension | Return the explicitly configured disabled/empty behavior; do not accept custom extensions |
| Snapshot methods | Return no-snapshot behavior until a deterministic snapshot format is designed and tested |

The Go adapter is responsible only for typed ABCI-to-IPC translation, request correlation, bounded framing, and transport lifecycle. It must not validate signatures, balances, nonces, supply, or transaction ordering itself.

## Genesis and restart rules

Genesis initialization is a blocking design gate, not a convenience default:

1. Define a versioned canonical HND genesis schema, including the chain identifier, supply cap, and initial allocations.
2. Define how CometBFT's `RequestInitChain.ChainId`, `AppStateBytes`, and `InitialHeight` map to that schema. Reject mismatches and unsupported initial heights.
3. On a fresh database, create the genesis state only after successful validation of the InitChain request.
4. On restart with an existing database, replay and verify the persisted chain before reporting Info. InitChain must verify that the supplied genesis identity matches the stored genesis; it must never overwrite existing state.
5. Info before first InitChain must return an explicit uninitialized result that the adapter maps according to the pinned CometBFT startup contract; it must not fabricate a committed genesis hash.
6. A crash before Commit must leave no durable block. A crash after durable Commit must recover the exact committed height and app hash.

The current `LedgerApplication` constructor requires an already-open `LocalChain`; it does not yet implement this lazy genesis lifecycle. The implementation must add and test that lifecycle before connecting a CometBFT node.

## Required tests before enabling the socket server

- Golden JSON request/response vectors for every method.
- Duplicate keys, unknown fields, invalid base64, invalid UTF-8, oversized line, malformed JSON, mismatched IDs, and unsupported protocol versions.
- Disconnects during request and response, reconnect, concurrent ABCI connections, and bounded mempool behavior.
- Fresh InitChain, duplicate InitChain, mismatched genesis on restart, Info before InitChain, and Info after restart.
- FinalizeBlock followed by process termination before Commit; Commit followed by process termination and replay.
- Full one-node CometBFT handshake and deterministic application-hash comparison.

## Version pin

The adapter must compile against the exact `github.com/cometbft/cometbft v0.40.0` module and include a compile-time assertion that its application implements `types.Application`. Do not build against the moving default branch.
