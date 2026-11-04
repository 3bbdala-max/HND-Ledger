# HND v0.2 — Cryptographic trust boundaries and key-management review

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Status:** Static source review and security requirements only  
**Reviewed files:** `hnd_v02/anti_rollback_reference.py`, `transaction.py`, `genesis.py`, `cometbft_v040_server.py`, and `recovery_controls.py`  
**Safety boundary:** No production keys, HSM/KMS, authenticated remote anchor, or production signer are present in this reviewed scope.

## 1. Executive result

The repository contains a useful separation between two different cryptographic purposes:

- Transaction signatures use Ed25519 and a protocol-specific signing domain.
- The anti-rollback reference model uses HMAC-SHA256 solely as a synthetic integrity fixture.

These must not be conflated. The fixed HMAC key in the anti-rollback module is embedded in source and explicitly labeled test-only. It provides no secret against anyone who can read the repository and is not a production trust anchor.

The review also found a network transport boundary that is safe only under its documented loopback default: the ABCI gRPC server uses an insecure listener and accepts a caller-supplied bind address. It must not be exposed to an untrusted network in its current form.

## 2. Positive controls observed

### 2.1 Transaction signatures

- Ed25519 is used for transaction signing and verification.
- The signing bytes include the fixed `HND-LEDGER/TX\0` domain prefix.
- The signed payload binds protocol version, network ID, sender, recipient, amount, and nonce.
- Sender account identity is derived from the Ed25519 public key and includes network and protocol version context.
- Signature and public-key Base64 encodings are checked for canonical form and expected byte length.
- Validation checks the sender public key against the sender account ID before signature verification.

These controls support transaction-envelope integrity in the reference implementation. They do not establish secure private-key storage, wallet recovery, hardware isolation, or operational key custody.

### 2.2 Genesis manifest

- The genesis manifest uses a distinct `HND-LEDGER/GENESIS\0` domain prefix.
- The validator requires a caller-supplied expected genesis hash and explicitly documents that the expected hash must come from a trusted configuration or release process.
- The manifest validator checks schema, network and protocol version, allocation ordering, public-key/account-ID correspondence, and total-supply equality.

The trustworthiness of the genesis hash still depends on how the expected value is distributed and verified outside the manifest itself.

### 2.3 Synthetic anti-rollback MAC

- The model uses HMAC-SHA256 and constant-time comparison for the MAC value.
- The source explicitly identifies the fixed key as offline-test-only and prohibits connecting this model to a real signer or trust service.

This is correct labeling for a test fixture, but the MAC must never be presented as production authentication.

## 3. Findings and required controls

### K01 — Embedded synthetic MAC key is public by design

The anti-rollback module defines a fixed MAC key in source. Anyone with repository access can reproduce the MAC for arbitrary records. This is acceptable only because the module is explicitly a synthetic reference model.

**Required control:** keep the fixture isolated and retain explicit tests/docs proving it cannot be imported into a production signer path. A production anchor must use an independently protected key or an authenticated hardware/service primitive, with key generation, provisioning, rotation, revocation, backup, access policy, and audit defined separately.

Do not replace the test key with an environment variable and call that production security. Secret injection alone does not solve trust-anchor independence, access control, rotation, or compromise recovery.

### K02 — HMAC authenticity is not independent anchor trust

Even a correctly keyed HMAC only proves that a record was MACed by an entity with the key. If the same host or administrative domain controls both the record store and MAC key, an attacker controlling that domain can rewrite records and recompute MACs.

**Required control:** define the threat boundary and place the anchor and its authentication authority outside the signer host's ordinary administrative failure domain. Specify authenticated monotonic reads, atomic compare-and-swap, anti-replay behavior, and key custody. A local MAC alone is not anti-rollback protection.

### K03 — Transaction private-key lifecycle is outside the current implementation

The transaction module accepts an `Ed25519PrivateKey` object supplied by its caller. It does not implement key generation ceremony, encrypted persistence, hardware-backed storage, access authorization, backup/recovery, rotation, revocation, or zeroization.

**Required control:** document this as an explicit boundary. Before real funds or validator duties, design a wallet/signer subsystem with threat model, hardware or OS keystore strategy, transaction display/approval, recovery ceremony, key rotation and revocation, audit, and independent security review. Do not serialize private keys into ordinary application state or logs.

### K04 — ABCI gRPC transport is unauthenticated and unencrypted

The server starts an insecure gRPC listener. Its default bind address is loopback, and the module warns against exposing the endpoint to an untrusted network. However, the CLI accepts a custom `--listen` value, which can bind beyond loopback without adding TLS, client authentication, or an authorization layer.

**Required control:** until secure transport and access control are implemented, enforce loopback-only binding rather than relying only on operator caution. If remote access is required, use a separately reviewed authenticated encrypted transport, explicit client identity/authorization, network restrictions, and negative tests for unauthorized callers. Do not expose the current endpoint publicly.

### K05 — Genesis pinning depends on an external trust ceremony

The validator correctly notes that a hash supplied alongside an untrusted manifest does not authenticate that manifest. The command-line interface accepts the manifest and expected hash as separate inputs, but code alone cannot prove that the expected hash came from an independent trusted channel.

**Required control:** define how the genesis hash is approved, signed, distributed, independently cross-checked, and pinned by each operator before startup. Preserve the approval evidence and ensure the manifest and expected hash cannot be replaced together by the same untrusted delivery path.

### K06 — No key-rotation or compromise-response protocol is present in reviewed scope

The reviewed anti-rollback fixture has one fixed key; the transaction code has no key lifecycle service; and the gRPC service has no client identity lifecycle. No production key rotation or revocation protocol was identified in these files.

**Required control:** specify versioned key IDs, activation/retirement windows, emergency revocation, signer isolation, audit evidence, and recovery after suspected compromise. Define which signatures remain historically verifiable after rotation and how compromised keys are prevented from authorizing new operations.

## 4. Required security tests and deployment checks

| ID | Test / inspection | Required result |
|---|---|---|
| KEY01 | Search production entry points for imports or use of the synthetic anti-rollback model | No production signer path depends on the fixed fixture key |
| KEY02 | Attempt remote connection to the default ABCI listener | Listener remains loopback-only |
| KEY03 | Attempt to configure a non-loopback listener in the current build | Startup rejects it until authenticated transport is implemented |
| KEY04 | Submit a transaction signed for a different network or protocol version | Signature/domain/account validation rejects it |
| KEY05 | Alter any signed transaction field after signing | Ed25519 verification rejects it |
| KEY06 | Supply a manifest and matching hash from the same untrusted source | Deployment process does not treat this alone as trusted provenance |
| KEY07 | Exercise key rotation/revocation in the future signer subsystem | Old key cannot authorize new operations after effective revocation; historical verification remains defined |
| KEY08 | Compromise/recovery tabletop exercise | Operators can isolate signer, revoke credentials, preserve evidence, and restore under dual control |

These are required checks, not test results. The current repository does not yet contain a production key-management subsystem to execute KEY07/KEY08 against.

## 5. Deployment gate

Until K04 is resolved, the ABCI endpoint must remain loopback-only and isolated from untrusted networks. Until K01–K03 and K05–K06 are resolved through a real trust architecture, no production signer, real funds, validator key, or production anti-rollback claim is permitted.

## 6. Evidence status

This was a static source review. No source code was changed and no tests or network scans were executed. Findings K01–K06 describe code boundaries and required controls; KEY01–KEY08 are future verification requirements.

The Ed25519 transaction primitive and domain separation are positive reference-code controls, not a complete wallet or custody solution. The synthetic HMAC fixture is not production security. The ABCI server must not be exposed to an untrusted network in its current insecure configuration.
