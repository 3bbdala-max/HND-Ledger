# WP4.14 — Remote Signer Recovery Evidence and Anti-Double-Sign Test-Gap Audit

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Reviewed baseline:** `c8b847e171b1952d9ac2fce85fc109d08eca04ce`  
**Status:** Static source/documentation audit only. No source or test changes. No tests executed.

## 1. Executive finding

The four-validator integration harness contains meaningful remote-signer outage/restart checks. It moves the validator's private consensus key and signing-state file into a temporary signer-owned directory, applies restrictive file modes, observes signing-state advancement, stops the signer, and restarts it using the captured post-stop state digest.

These checks demonstrate a controlled recovery scenario when the harness and signer cooperate. They do **not**, by themselves, prove that the signer rejects rollback to an older valid state, prevents two concurrent signer instances from using the same key/state, or enforces production-grade custody and authorization.

## 2. Confirmed harness behavior

In `scripts/cometbft_v040_four_validator_network_smoke.py`:

1. The optional external-signer path moves validator 4's `priv_validator_key.json` and `priv_validator_state.json` into a temporary signer directory.
2. The harness sets both moved files to mode `0600`; the directory is created with mode `0700`.
3. It records the initial signer-state SHA-256 digest.
4. It starts either a Unix-socket signer mode or a Noise transport mode, depending on the supplied external binary.
5. In Noise mode, the harness waits for a connection marker and invokes an unauthorized-identity probe; it expects an explicit rejection marker.
6. It stops the signer during the outage scenario, checks that the state file remains present and that its digest advanced after signing.
7. It restarts the signer in recovery mode, supplying the observed state digest, and waits for reconnection and four-node convergence.
8. The harness later stops the signer before node restart and checks validator consensus-key and P2P node-key file digests against their pre-restart values.

These are valuable integration assertions. They are not a complete signer security certification.

## 3. What the evidence does not establish

| Security property | Evidence in reviewed harness | Remaining proof required |
|---|---|---|
| File permissions | Temporary directory 0700; key/state files 0600 | Production owner/group, ACL, filesystem, backup and host controls |
| State advances after signing | Digest changes after signer operation | Semantic monotonicity and anti-rollback verification, not merely byte change |
| Recovery continuity | Restart receives the post-stop state digest | Rejection of stale, replayed, truncated or substituted state |
| Single active signer | Harness starts one signer and stops it before restart | Atomic exclusive ownership/locking and concurrent-instance negative test |
| Unauthorized Noise peer | Optional probe expects rejection marker | Independent identity provisioning, trust-root rotation, authorization policy and audit |
| Unix socket access | Unix transport is exercised | Socket ownership/mode verification and unauthorized local-process test |
| Key custody | Key is moved into temporary signer directory | Production HSM/OS keystore custody, ceremony, backup and dual control |
| Compromise response | Not exercised | Revocation, isolation, evidence preservation, replacement and validator-set transition |

## 4. Critical anti-double-sign distinction

A SHA-256 digest is an integrity fingerprint of the observed file contents. A comparison against a digest supplied to a restarted process is useful only if the expected digest itself is authenticated and anchored outside the attacker's rollback domain.

The harness demonstrates that the state file changed and that the recovery invocation is given the digest captured by that harness. It does not establish that a production signer independently obtains a trusted monotonic checkpoint, rejects an older but well-formed state file, or atomically commits signing intent before releasing a signature.

For BFT validator safety, anti-double-sign state must not be treated as an ordinary replaceable file. Its persistence and update ordering are safety-critical.

## 5. Required tests before production signer approval

- **RS01 — Stale-state rollback:** restore an earlier valid state snapshot and prove the signer refuses to start or sign.
- **RS02 — Concurrent signer:** launch two signer instances against the same key/state; exactly one may acquire exclusive signing authority.
- **RS03 — Crash boundaries:** terminate the signer before, during and after durable state update; verify no conflicting signature can be emitted after restart.
- **RS04 — Corrupt/truncated state:** reject malformed, partial and checksum-mismatched state without silently creating a fresh state.
- **RS05 — Checkpoint substitution:** replace the supplied recovery digest/checkpoint; reject unless it is authenticated by an independent trust anchor.
- **RS06 — Duplicate request/replay:** repeat identical and conflicting sign requests across restart; enforce CometBFT's required anti-double-sign semantics.
- **RS07 — Unix local authorization:** unauthorized local UID/process cannot connect to or control the signer socket.
- **RS08 — Noise identity lifecycle:** unknown, revoked and expired client identities are rejected; authorized identity rotation is auditable.
- **RS09 — Key/state separation:** signer key and anti-double-sign state cannot be independently swapped between validators.
- **RS10 — Recovery evidence:** produce a signed/auditable record of signer identity, software version, state checkpoint, recovery decision and operator authorization, without exposing private material.

These are proposed acceptance tests, not results.

## 6. Safe implementation sequence

1. Obtain and review the exact remote-signer source and version used by the integration harness; the harness accepts an external binary and cannot prove its internal implementation.
2. Document the signer protocol's signing-state format, atomic-write strategy, locking behavior, and crash semantics.
3. Define the independent monotonic trust anchor and its failure-domain separation.
4. Add negative tests RS01–RS10 against a disposable test signer before considering production credentials.
5. Conduct an independent security review of signer code, binary provenance, build reproducibility and deployment controls.
6. Only then define operational procedures for key generation, backup, rotation, revocation and incident recovery.

## 7. Disposition

The current integration harness provides useful evidence for one controlled remote-signer outage and recovery path. It does not justify a claim of production anti-double-sign protection or production key custody.

Keep production validator keys and real-value signing disabled until stale-state rollback, concurrent signer exclusion, crash-boundary safety, independent checkpoint trust and signer authorization are demonstrated by reproducible negative tests and independently reviewed implementation evidence.
