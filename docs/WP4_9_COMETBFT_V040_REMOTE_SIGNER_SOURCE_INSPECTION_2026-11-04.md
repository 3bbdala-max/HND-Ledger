# HND v0.2 — CometBFT v0.40.0 remote-signer source inspection

**Inspection date:** 2026-11-04  
**Pinned upstream tag:** `cometbft/cometbft@v0.40.0`  
**Scope:** Source-level protocol and transport inspection only. No HND remote-signer integration test has been implemented or passed by this document.

## 1. Files inspected

The following files were read from the exact upstream tag `v0.40.0`:

- `privval/doc.go`
- `privval/signer_client.go`
- `privval/signer_server.go`
- `privval/signer_endpoint.go`
- `privval/signer_listener_endpoint.go`
- `privval/signer_dialer_endpoint.go`
- `privval/signer_requestHandler.go`
- `privval/msgs.go`
- `privval/socket_dialers.go`
- `privval/socket_listeners.go`
- `privval/noise_listener.go`
- `privval/retry_signer_client.go`
- `privval/utils.go`

## 2. Confirmed protocol facts

1. The remote private-validator interface is **not gRPC**. It exchanges CometBFT protobuf `privval.Message` envelopes using length-delimited protobuf framing through `libs/protoio.NewDelimitedReader` and `NewDelimitedWriter`.
2. The request/response envelope variants include:
   - `PingRequest` / `PingResponse`
   - `PubKeyRequest` / `PubKeyResponse`
   - `SignVoteRequest` / `SignedVoteResponse`
   - `SignProposalRequest` / `SignedProposalResponse`
3. `SignerClient` sends requests through `SignerListenerEndpoint`. That endpoint **listens** for an external signer process to dial in.
4. `SignerServer` services requests received by `SignerDialerEndpoint`. The signer process therefore dials the node's listener; the connection direction must not be reversed in the harness.
5. The default read/write timeout is 5 seconds. The listener endpoint sends periodic pings at approximately two-thirds of that timeout (3 seconds with defaults).
6. The default request handler validates the supplied chain ID for public-key, vote-signing, and proposal-signing requests, then delegates signing to the configured `types.PrivValidator`.
7. The retrying client retries transport/connection errors, but returns a `RemoteSignerError` directly rather than retrying a signer-declared refusal.
8. The message reader applies a maximum remote-signer message size. Tests should use the official client/server abstractions rather than implementing their own unbounded framing.

## 3. Transport choices and security distinctions

- **Unix domain socket:** `NewUnixListener` is unencrypted. It is appropriate only for an isolated local test with a private temporary directory and restrictive socket permissions. Do not treat it as authenticated remote transport.
- **TCP:** `NewTCPListener` wraps connections in CometBFT's authenticated secret connection. In the inspected `NewSignerListener` helper, the secret-connection key is generated at runtime and the source contains a TODO about persisting it for external signer authentication. Do not build a long-lived production design on this helper without resolving that identity lifecycle.
- **Noise:** `NewSignerListenerFromAddr` supports `noise://<signer-peer-id>@<IP-literal>:<port>`. The node key establishes the Noise identity and the signer peer ID is allowlisted. This is the stronger candidate for a later authenticated remote-signer deployment, but it is outside the initial local conformance probe.

For the first CI conformance probe, use a temporary Unix socket only if the harness can enforce local process isolation and cleanup. Otherwise use a loopback TCP listener with the pinned CometBFT listener/dialer abstractions and explicitly account for the secret-connection identity setup. Never expose the endpoint publicly.

## 4. Important distinction: ABCI gRPC is not PrivValidator gRPC

The HND Python server `hnd_v02/cometbft_v040_server.py` and `scripts/cometbft_v040_grpc_probe.go` implement/probe the **ABCI application transport**. They do not implement the remote private-validator protocol. Their use of gRPC is correct for ABCI and must not be copied as the remote-signer wire protocol.

## 5. Correct implementation shape for the next probe

Use the exact pinned Go module APIs:

- Node-side: a `SignerListenerEndpoint` with a listener created for a temporary local endpoint, then `NewSignerClient` (and, if needed, `NewRetrySignerClient` with bounded retries).
- Signer-side: `SignerDialerEndpoint` with the matching pinned dialer, then `NewSignerServer` with a disposable `FilePV` or a test-only `types.PrivValidator` wrapper.
- Exercise `Ping`, `GetPubKey`, one valid vote-sign request, and one valid proposal-sign request. Assert the returned signatures verify against the expected disposable public key.
- Add explicit wrong-chain-ID and signer-refusal assertions.
- Keep the signer key and last-sign state in the signer process/home; never put secret key material in node logs or CI artifacts.
- Ensure all temporary sockets, directories, processes, and state files are removed on success, failure, and timeout.

A Unix-socket probe can establish protocol framing and API compatibility, but it does not establish authenticated transport security. That is a separate test and release gate.

## 6. Not yet established

This source inspection does not establish:

- that HND has a working remote signer implementation;
- that the four-validator network passes with a remote signer;
- that a withheld signer leaves the other three validators progressing;
- that a malicious conflicting vote can be injected through a supported public test hook;
- that production key custody, authenticated transport, or failover is safe.

The malicious equivocation scenario remains blocked until an auditable injection path is identified in the pinned source and exercised without modifying consensus internals.

## 7. Exact upstream source references

- [CometBFT v0.40.0 privval package](https://github.com/cometbft/cometbft/tree/v0.40.0/privval)
- [signer client](https://github.com/cometbft/cometbft/blob/v0.40.0/privval/signer_client.go)
- [signer server](https://github.com/cometbft/cometbft/blob/v0.40.0/privval/signer_server.go)
- [endpoint framing](https://github.com/cometbft/cometbft/blob/v0.40.0/privval/signer_endpoint.go)
- [listener endpoint](https://github.com/cometbft/cometbft/blob/v0.40.0/privval/signer_listener_endpoint.go)
- [dialer endpoint](https://github.com/cometbft/cometbft/blob/v0.40.0/privval/signer_dialer_endpoint.go)
- [request handler](https://github.com/cometbft/cometbft/blob/v0.40.0/privval/signer_requestHandler.go)
- [transport utilities](https://github.com/cometbft/cometbft/blob/v0.40.0/privval/utils.go)

---

This is a source inspection record, not a security certification, audit, or release approval.
