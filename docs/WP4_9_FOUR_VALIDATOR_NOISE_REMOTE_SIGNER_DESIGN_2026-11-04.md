# WP4.9 — Noise-backed four-validator remote-signer integration design

**Date:** 2026-11-04  
**Pinned upstream:** CometBFT v0.40.0  
**Branch:** `phase-0.2-planning`  
**Status:** Design based on pinned-source inspection; implementation and CI execution pending.

## 1. Purpose and boundary

Move the existing disposable validator-4 external signer integration from a local Unix socket to the pinned CometBFT v0.40.0 Noise listener/dialer path. The objective is to test authenticated transport inside the existing four-validator crash/restart/partition harness, not to approve a production deployment.

All keys, state files, ports, and network endpoints remain disposable and loopback-only. Do not change `main`, use production keys, or expose a signer listener publicly.

## 2. Pinned-source contract

The exact v0.40.0 `privval/utils.go` implementation establishes:

- `NewSignerListenerFromAddr(listenAddr, nodeKey, logger)` recognizes `noise://<signer-peer-id>@host:port`.
- The listener uses the CometBFT node's P2P identity key (`node_key.json`) as the Noise listener identity.
- The parsed signer peer ID becomes a non-empty allowlist passed to `NewNoiseListener`.
- The listener is bound with TCP on the parsed IP literal and port, then wrapped by the Noise listener and the normal `SignerListenerEndpoint`.
- The validator consensus signing key is not the Noise transport identity. It remains owned by the remote FilePV process.

The already-passing standalone probe confirms the complementary client path: a signer identity key is converted with `lp2p.PrivateKeyFromCosmosKey`, a libp2p Noise transport performs `SecureOutbound` while expecting the exact node peer ID, and the secured `net.Conn` is passed to `NewSignerDialerEndpoint`.

## 3. Four-validator test topology

- Validators 1–3 retain their existing local FilePV configuration.
- Validator 4's consensus key and last-sign state are moved into a private temporary signer directory with restrictive permissions.
- Validator 4's CometBFT node retains its own P2P `node_key.json`; this is required by the node-side Noise listener and is not the validator consensus key.
- A separate disposable signer transport identity is generated once for validator 4. Its peer ID is derived from that key and embedded in validator 4's `priv_validator_laddr` as `noise://<signer-peer-id>@127.0.0.1:<port>`.
- The signer process loads the same transport identity on each restart, derives the validator consensus public key from its FilePV, and dials the node using Noise `SecureOutbound(..., expectedNodePeerID)`.
- The signer client must never accept an arbitrary node identity. It pins the expected node peer ID derived from validator 4's existing `node_key.json`.

## 4. Required test sequence

1. Generate four independent validator identities and a common Genesis as the current harness does.
2. Preserve validator 4's P2P node key in its CometBFT home; move only its consensus FilePV key/state into signer-owned temporary storage.
3. Generate and persist a separate signer Noise identity; compute its peer ID and configure the node listener with that exact peer ID.
4. Start all four ABCI apps and CometBFT nodes; start validator 4's Noise signer process.
5. Require a fresh connection marker from the signer process and verify that all four validators converge.
6. Commit a signed transfer and verify balances/application hashes converge across all four validators.
7. Stop the signer process while leaving validator 4 and all other processes alive; prove the remaining three validators can commit.
8. Restart the signer with the same transport identity and FilePV state; require a new connection marker and four-validator convergence.
9. Stop/restart validator 4 itself; verify the node listener returns, the signer reconnects using the pinned node identity, and validator 4 catches up.
10. Re-run the existing 3/1 and 2/2 partition/reconnection tests while Noise is active. The 2/2 side must not advance during the bounded observation.
11. Add a negative integration case using a second disposable signer transport identity. The node must reject it at the Noise allowlist boundary; it must not reach a successful Ping or signing request.
12. Verify transport identity continuity after signer restart and cleanup all temporary keys, state, sockets, logs, relays, and processes.

## 5. Fail-closed conditions

Fail the test if any of the following occurs:

- the configured signer peer ID is absent, empty, malformed, or differs from the signer process identity;
- the signer does not pin the expected node peer ID;
- the unauthorized identity obtains a usable signer connection;
- a stale connection marker is mistaken for a new process connection;
- validator 4 commits using a local fallback key or bypasses the external signer;
- a restart uses a new identity unexpectedly or an old/rolled-back FilePV state;
- any validator or ABCI process exits unexpectedly;
- partition peer sets differ from the exact expected groups;
- any private key or state secret appears in CI logs or artifacts.

## 6. Acceptance evidence

A successful CI run must show distinct markers for authorized Noise connection, unauthorized signer rejection, successful transfer convergence, signer outage/quorum progress, signer restart recovery, validator restart/catch-up, 3/1 isolation/reconnection, and 2/2 no-quorum/reconnection. Record the exact tested commit and workflow run.

## 7. Security limits

Passing this disposable loopback test would demonstrate integration behavior for the tested CometBFT v0.40.0 APIs and test configuration only. It would not certify identity provisioning, rotation, HSM/KMS custody, rollback-resistant durable storage, WAN exposure, denial-of-service resistance, production monitoring, arbitrary Byzantine fault tolerance, or legal readiness. Independent security review and the existing G2–G4 release gates remain mandatory.

---

This document is a test design, not an implementation result, security certification, legal opinion, or authorization for public release.
