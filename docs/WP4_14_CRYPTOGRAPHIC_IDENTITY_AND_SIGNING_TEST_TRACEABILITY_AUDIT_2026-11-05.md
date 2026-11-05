# HND v0.2 — cryptographic identity and signing test traceability audit

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Review type:** Static source and test traceability; CI evidence inspection  
**Change boundary:** Documentation only. No source, test, key, or workflow changes.

## 1. Executive result

The reference transaction layer has meaningful Ed25519 integrity controls and the repository contains disposable CometBFT FilePV/remote-signer smoke tests. These are useful protocol and integration checks, but they do not amount to a production wallet, production key custody, HSM-backed signing, or a complete key lifecycle.

**Disposition: cryptographic primitives partially verified; production key management NOT IMPLEMENTED / NOT APPROVED.**

## 2. Transaction identity and signature controls observed

In `hnd_v02/transaction.py`:
- Ed25519 is used for transaction signatures.
- Signing bytes are domain-separated with `HND-LEDGER/TX\\0`.
- The signed payload includes protocol version, network ID, sender, recipient, amount, and nonce.
- Account IDs are derived from the public key with a separate `HND-LEDGER/ACCOUNT-ID\\0` domain, network ID, and protocol version.
- Base64 public-key/signature encodings are checked for canonical representation and expected byte lengths.
- Validation checks that the supplied public key derives the claimed sender account before signature verification.

In `tests/test_v02_transaction_envelope.py`, observed cases include:
- deterministic account identity and separation across networks/protocol versions;
- sender/key mismatch rejection;
- malformed public key/signature rejection;
- tampering with signed fields;
- network/version mismatch;
- deterministic published transaction vector verification.

The tests use generated in-memory Ed25519 keys. They do not exercise encrypted private-key storage, wallet import/export, hardware keystores, access authorization, revocation, recovery, or key zeroization.

## 3. Genesis trust and identity controls observed

In `hnd_v02/genesis.py`:
- Genesis hashing uses a distinct `HND-LEDGER/GENESIS\\0` domain.
- Validation checks manifest schema, network/protocol context, deterministic allocation ordering, public-key/account-ID correspondence, allocation sum, and a caller-supplied expected hash.
- The source explicitly warns that a hash delivered alongside the same untrusted manifest does not authenticate the manifest's origin.

In `tests/test_v02_genesis_manifest.py`, observed cases cover valid fixture/hash, altered allocation, total-supply mismatch, malformed values, duplicate/unsorted identities, key/account mismatch, wrong network/version, and wrong expected hash.

The expected hash's independent distribution, approval, signing, and operator pinning remain an external governance/custody requirement.

## 4. Validator signing and remote-signer evidence

The workflow includes disposable CometBFT v0.40.0 smoke probes for:
- FilePV vote/proposal anti-double-sign behavior;
- identical retry and conflicting-signature rejection;
- persistence across signer restart;
- process-isolated remote signer;
- Noise-authenticated remote signer and unauthorized peer rejection;
- missing/substituted anti-double-sign state rejection;
- multi-validator integration and signer outage/recovery.

These are integration fixtures. The inspected helpers generate keys in temporary directories and explicitly label themselves test-only. The UNIX socket probe uses a temporary socket with mode 0600. The Noise helper uses test identities and local integration endpoints. None is a deployed HSM/KMS signer or a production custody ceremony.

The state-digest recovery probe compares a file's SHA-256 to an expected digest supplied to the test helper. A digest comparison is not an authenticated independent anti-rollback anchor; if an attacker can replace both state and expected digest through the same trust channel, it does not establish authenticity or freshness.

## 5. Key classes must remain separate

The repository's key-custody design correctly distinguishes:
1. CometBFT validator consensus key;
2. anti-double-sign state;
3. CometBFT P2P node identity;
4. remote-signer transport identity;
5. operator/admin credentials;
6. backup-encryption/recovery keys.

No production inventory, HSM/KMS provisioning, independent backup authority, dual-control recovery quorum, or operational rotation/revocation service was established in this source review.

The four-validator Genesis preflight generates temporary identities in a temporary directory and removes them at completion. It proves uniqueness and common Genesis construction for a disposable preflight, not approval or pinning of production validator identities.

## 6. CI traceability at inspection time

- Run `41982750741`, commit `d165952bdcf2e518f5c505f5e1abd1a5b7f5e466`.
- `hnd-v02-tests`: completed successfully.
- `cometbft-single-node-smoke`: in progress at inspection time.

The workflow's isolated Python test command includes `tests.test_v02_transaction_envelope` and `tests.test_v02_genesis_manifest`. The configured run therefore provides CI evidence for those test modules once the job completed. Do not claim the entire run passed while the integration job remains in progress.

## 7. Required production gates

Before production funds or validator signing:
- implement and independently review a wallet/key custody design;
- choose and validate HSM/KMS or offline signer custody, including access policy and failure modes;
- authenticate Genesis approval and distribute/pin its hash through an independent channel;
- implement key IDs, rotation, revocation, emergency isolation, and historical verification policy;
- bind anti-double-sign state to validator key, chain ID, Genesis hash, signer identity, and a durable independent monotonic trust anchor;
- test restore, rollback, split-brain, host compromise, credential compromise, and signer failover under dual control;
- prohibit private keys and recovery factors from source control, CI logs/artifacts, and ordinary application storage.

## 8. Final disposition

**Reference cryptography:** positive controls present; selected transaction and Genesis tests included in CI.  
**Validator smoke tests:** disposable integration evidence; final run status must be checked.  
**Production key custody / wallet / recovery:** not implemented or verified.  
**Production launch:** NOT APPROVED.

This report is not a cryptographic certification, penetration test, HSM validation, or proof of production-safe signing.
