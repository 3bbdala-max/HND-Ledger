# HND private IPC contract

Status: implemented between the Go CometBFT adapter and Python application.

## Transport and envelope

- UTF-8 JSON Lines over a private Unix-domain stream socket.
- One request and one response per connection.
- Protocol identifier: hnd-ipc/1.
- Maximum frame: 1 MiB.
- Python socket mode: 0600.
- Each request frame has a 5-second read deadline; incomplete or stalled client writes are closed and logged without a protocol response.
- Duplicate JSON keys, unknown top-level fields, malformed frames, invalid request IDs, unsupported protocol versions, and unsupported methods are rejected.
- Byte slices are JSON base64 strings between Go and Python.
- Python handles requests sequentially on the SQLite-owning thread.
- The Unix listener uses a bounded accept backlog of 64 pending connections; this queues short bursts but does not make request dispatch concurrent or establish flood resistance.

Request fields: protocol, id, method, payload.
Success response fields: protocol, id, ok=true, result.
Failure response fields: protocol, id, ok=false, error with code, message, and retryable.

## Method boundary

The dispatcher implements Info, InitChain, Query, CheckTx, InsertTx, ReapTxs, PrepareProposal, ProcessProposal, FinalizeBlock, and Commit. Query supports only /hnd/v1/info and /hnd/v1/account at latest committed state. Snapshot and vote-extension methods are not implemented.

Go performs typed ABCI-to-IPC translation, request correlation, bounded framing, and transport lifecycle. It does not implement HND signature, balance, nonce, supply, or transaction-ordering rules.

## Genesis and restart

Fresh databases require explicit development-genesis initialization or a valid CometBFT InitChain request. Funded genesis uses a canonical JSON v2 envelope containing Base64 canonical-CBOR allocations. Genesis state, genesis hash, and CometBFT marker are persisted atomically. Repeated identical InitChain is idempotent; conflicting genesis identity is rejected. On restart, Python replays and verifies the stored chain before serving committed height/hash.

## Operational limits

The read deadline bounds one incomplete client from holding the sequential dispatcher indefinitely. It is not a complete denial-of-service defense: connection-rate limits, per-peer quotas, sustained/high-volume client stress, and CPU/memory exhaustion testing remain open. A 16-client concurrent connection regression test exists; it checks request/response correlation, not sustained load or overload behavior. Crash injection around SQLite commit and independent multi-host validation also remain open.
