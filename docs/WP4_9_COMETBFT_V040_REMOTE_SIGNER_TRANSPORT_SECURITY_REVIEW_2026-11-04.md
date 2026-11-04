# WP4.9 — CometBFT v0.40.0 remote-signer transport security review

**Review date:** 2026-11-04  
**Pinned upstream source:** CometBFT `v0.40.0`  
**HND branch:** `phase-0.2-planning`  
**Status:** Source review completed; production transport decision remains open.

## 1. Scope

This review examines the pinned CometBFT remote private-validator transport implementation. It is not a penetration test, cryptographic audit, deployment approval, or proof that any HND production environment is secure.

Files reviewed:
- `privval/noise_listener.go`
- `privval/socket_dialers.go`
- `privval/socket_listeners.go`
- `privval/signer_listener_endpoint.go`
- `privval/signer_dialer_endpoint.go`
- `privval/signer_server.go`

## 2. Transport findings

### Unix domain socket

- `DialUnixFn` dials a local Unix socket directly.
- `NewUnixListener` explicitly returns unencrypted connections.
- The listener source contains a TODO for adding MAC authentication.
- Filesystem permissions and OS isolation therefore become critical controls; socket mode 0600 is appropriate for the disposable local CI harness, but it is not a substitute for cryptographic peer authentication.
- Use only for same-host, tightly isolated deployments where the signer and node trust boundary is understood. Do not expose the socket through a shared writable directory or container volume accessible to untrusted workloads.

### TCP secret connection

- `DialTCPFn` connects and wraps the connection with CometBFT's `MakeSecretConnection`, using a private key supplied to the dialer.
- `NewTCPListener` likewise wraps accepted TCP connections with `MakeSecretConnection`, using the listener's secret-connection key.
- This is authenticated encryption at the connection layer, not ordinary plaintext TCP. The listener and signer must have correctly provisioned and independently verified identities.
- A connection key generated afresh at startup and not durably/predictably pinned creates a bootstrap and identity-continuity problem. Do not treat encryption alone as proof that the connecting signer is the intended signer.
- Do not place private identity material in source control, command-line arguments, logs, or test artifacts.

### Noise listener

- `NewNoiseListener` derives a libp2p identity from the CometBFT private key and wraps an underlying listener with a Noise transport.
- `Accept` performs the Noise inbound handshake and, when the allowlist is non-empty, rejects remote peer IDs not present in that allowlist.
- The source comment explicitly says an empty allowlist accepts any authenticated peer and MUST NOT be used in production; it is intended for tests.
- `ParseNoiseAddr` requires `noise://<peer-id>@host:port`, an explicit port, and an IP literal rather than a DNS hostname.
- The reviewed source establishes a promising authenticated/encrypted listener-side mechanism, but it does not by itself prove that HND has a complete, correctly provisioned, persistent signer dialer lifecycle. That client-side integration, identity rotation, restart behavior, and negative tests must be demonstrated before selecting it for deployment.

## 3. Operational controls required regardless of transport

1. Bind signer listeners only to private interfaces; never expose a signing endpoint to the public Internet.
2. Enforce network ACLs/security groups so only the designated node can reach its signer.
3. Pin and verify both node and signer identities out-of-band; reject unknown identities by default.
4. Keep one signer identity per validator. Do not share one signing key or signer endpoint across validators.
5. Keep signing keys in a dedicated signer process with least-privilege OS identity and restricted filesystem access; prefer HSM/KMS or a reviewed external custody service for production.
6. Persist anti-double-sign HRS/signing state atomically and durably with monitored backups. Backups must not permit rollback to an older signing state.
7. Define key rotation, signer replacement, disaster recovery, revocation, and incident-response procedures before deployment.
8. Apply connection/read/write timeouts, resource limits, rate limits, alerting, and audit logging. Logs must never contain private keys, seed phrases, access tokens, or signature request secrets.
9. Treat signer unavailability as a liveness fault; do not bypass the signer guard or restore a stale state file to regain availability.
10. Test unauthorized peer rejection, wrong identity, replay/reconnect, network interruption, process restart, state-file rollback/corruption, and recovery in an isolated environment.

## 4. Current HND test evidence and limits

- HND's current four-validator integration uses a disposable local Unix socket with restrictive temporary filesystem permissions.
- CI has passed the external signer outage/recovery, validator restart/catch-up, 3/1 partition, and 2/2 no-quorum/reconnection scenarios.
- CI has also passed the separate-process signing probe, vote-withholding probe, and remote FilePV conflicting same-HRS refusal persistence across signer restart.
- These results establish bounded local integration behavior. They do not establish authenticated/encrypted remote-host transport, secure production key custody, HSM/KMS integration, or an independently audited deployment.

## 5. Decision

**Do not approve Unix-socket transport as a general remote-host production design.** It is retained for local isolated testing.

**Do not approve TCP secret connection solely because it encrypts traffic.** Production use requires durable identity provisioning, pinning, rotation and negative tests.

**Noise is the leading candidate for a pinned-peer authenticated remote transport**, subject to an HND-specific end-to-end dialer/listener integration, persistent identity provisioning, allowlist enforcement, unauthorized-peer rejection tests, and independent security review. No production transport is selected or certified by this source review.

## 6. Next verification gate

Implement a disposable-key Noise integration spike on a private CI network:
- derive stable peer identities from test-only keys;
- configure the CometBFT listener with an explicit non-empty signer peer-ID allowlist;
- connect a signer client using the expected peer identity;
- prove the authorized signer can Ping/GetPubKey/SignVote/SignProposal;
- prove a different peer identity is rejected before it can issue signing requests;
- restart both sides and verify identity continuity;
- test connection loss/reconnect and cleanup;
- never print or upload private keys.

If the pinned v0.40.0 signer dialer cannot support this without an unsafe or unreviewed patch, stop and document the limitation rather than weakening authentication.

---

This document is a source-based engineering review, not a security certification, legal opinion, or authorization for mainnet or real-value use.
