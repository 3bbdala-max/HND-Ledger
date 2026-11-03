# HND v0.2 — WP4.9 four-validator remote-signer integration design

**Date:** 2026-11-04  
**Status:** Implementation design; not yet implemented or passed  
**Branch:** `phase-0.2-planning`  
**Pinned engine:** CometBFT v0.40.0

## 1. Purpose

Extend the already-passing process-isolated remote-signer probe into the existing disposable four-validator network harness. Exactly one validator (validator 4) will use an external signer process; validators 1–3 retain their existing local FilePV path. The first milestone is an honest signer baseline only. Withheld-vote behavior is a separate later milestone.

## 2. Pinned-source configuration facts

Inspection of the exact upstream CometBFT v0.40.0 `config/config.go` confirms that `BaseConfig.PrivValidatorListenAddr` is mapped to the TOML key `priv_validator_laddr`. Its source comment describes it as the TCP or UNIX socket address on which CometBFT listens for an external PrivValidator process.

The remote-signer source inspection in `docs/WP4_9_COMETBFT_V040_REMOTE_SIGNER_SOURCE_INSPECTION_2026-11-04.md` establishes the connection direction and API: the CometBFT node owns the listener endpoint; the external signer dials it using `SignerDialerEndpoint` and serves requests with `SignerServer`. This is distinct from the HND ABCI gRPC server.

For the first integration, use a temporary Unix-domain socket only. This keeps the test local and avoids making any claim about encrypted or authenticated network transport.

## 3. Process and key boundaries

- Generate the four validator identities and common Genesis exactly as the existing harness does.
- For validator 4, move the disposable `priv_validator_key.json` into a signer-owned temporary directory before starting CometBFT. The node process must not receive the signing key file.
- Configure validator 4's CometBFT home with `priv_validator_laddr = "unix://<private-temp-socket>"`. Keep its P2P `node_key.json`, database, RPC and ABCI configuration in the node home.
- Start the validator-4 CometBFT node with the pinned binary.
- Start a separate signer child process that loads validator 4's disposable FilePV key and durable last-sign state, creates the pinned `SignerDialerEndpoint`, and serves through `SignerServer` using the exact chain ID.
- Validators 1–3 continue using their own independent local FilePV keys and state.
- Verify that the remote signer's public key fingerprint matches validator 4's Genesis public key before waiting for consensus.
- Do not silently fall back to a local signer if the child exits or the socket disconnects. The test must fail closed.

## 4. Honest-baseline acceptance criteria

1. All four validators and all four ABCI processes start; signer child process is separately tracked and remains alive.
2. Validator 4's signer public key equals the validator-4 Genesis key; the other three validator identities remain unique.
3. All four nodes converge on the same initial height and block hash.
4. A valid synthetic HND transfer is committed; all four nodes agree on height, block hash, application hash and sender/recipient balances.
5. Stop and restart the remote signer child without deleting its key or last-sign state; reconnect safely and confirm that no conflicting signature is produced.
6. Restart the validator-4 CometBFT node only after the signer reconnection lifecycle is explicitly tested; require catch-up and identical committed HND state.
7. Assert every expected process is alive during the relevant observation windows, and ensure deterministic cleanup of nodes, app processes, signer process, socket, relays, keys and state.
8. CI output contains only public-key fingerprints and sanitized outcomes; never print private key material or signer state contents.

## 5. Test sequencing

- Milestone A: static config/identity preflight for `priv_validator_laddr` and signer-owned key placement.
- Milestone B: one remote signer + one CometBFT node handshake and signing smoke in the harness shape.
- Milestone C: honest four-validator remote-signer transfer and state-convergence baseline.
- Milestone D: signer-process restart/reconnect and validator restart/catch-up.
- Milestone E: separately controlled withheld-vote behavior, then 3/1 and 2/2 controls.
- Milestone F: correct-signer same-HRS conflict refusal and persisted-state checks.
- Malicious equivocation injection remains a separate design gate until an auditable injection path supported by pinned CometBFT v0.40.0 is demonstrated.

## 6. Explicit limitations

A Unix socket is not encrypted. Process separation in a local CI runner does not prove host-level isolation, secure boot, HSM custody, authenticated WAN transport, or production key management. This integration is not a Byzantine fault-tolerance proof or an independent security audit. The existing 3/1 and 2/2 partition tests remain separate and must continue to pass unchanged.

No production key, public endpoint, public network, or real-value HND activity is permitted. All changes remain on `phase-0.2-planning`; `main` remains untouched.

---

This is an implementation design, not a security certification, legal opinion, or authorization to issue or trade HND.
