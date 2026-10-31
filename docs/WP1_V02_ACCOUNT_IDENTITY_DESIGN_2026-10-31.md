# HND v0.2 — Account identity design and validation

**Date:** 2026-10-31  
**Workstream:** WP1 — Account identity (D-01)  
**Status:** Isolated reference implementation and characterization tests; the normative protocol decision remains open.  
**Branch:** phase-0.2-planning

## 1. Objective

Replace caller-chosen account labels with deterministic account identifiers derived from Ed25519 public keys. Bind each identifier to the configured network and protocol version so that the same key has different identifiers on different networks or protocol versions.

## 2. Candidate account identifier format

The reference implementation uses:

    hnd<protocol_version>:<network_id>:<64 lowercase hexadecimal characters>

The final digest is SHA-256 over:

    ACCOUNT_ID_DOMAIN || canonical_json({
        "network_id": network_id,
        "protocol_version": protocol_version,
        "public_key": lowercase_hex(raw_32_byte_ed25519_public_key)
    })

The domain prefix is the byte sequence HND-LEDGER/ACCOUNT-ID followed by a zero byte. Canonical JSON uses UTF-8, sorted object keys, compact separators, and rejects non-finite numbers.

The candidate address is deterministic for one public key under the same network/version configuration, and changes when the public key, network ID, or protocol version changes.

## 3. Transaction binding

The v0.2 reference module now:

- Derives the expected sender ID from the supplied Ed25519 public key and rejects a mismatch before signature acceptance.
- Requires sender and recipient identifiers to have the configured network/version prefix and a 64-character lowercase hexadecimal digest.
- Makes the signing helper refuse to sign a transaction if the sender field does not belong to its private key.
- Keeps recipient existence and recipient-key registry verification as a ledger/account-registry responsibility. The current module does not contain an account database and cannot prove that a recipient account has been registered.

The sender's public key must be obtained from the account registry, not trusted from an unverified transaction field. The public key used for validation must be the key registered to the sender account.

## 4. Local test results

The isolated v0.2 suite was run locally after these changes:

    python -m unittest -v tests.test_v02_transaction_envelope

Result: **22 tests passed, 0 failed**.

Coverage includes deterministic derivation, different-key separation, network/version separation, malformed public keys and addresses, sender/public-key mismatch, attempted identity substitution, strict amount and nonce checks, network/version binding, signature verification, and a deterministic public test vector.

This is a local test run on the recovered working copy. It is not a GitHub Actions result, independent implementation review, formal verification, or security audit.

## 5. Deterministic test vector

The file vectors/v0.2-transaction-envelope-example.json records:

- A sender public key and recipient public key.
- Their derived account IDs on hnd-devnet-alpha, protocol version 2.
- The exact canonical signed payload and signing preimage.
- An Ed25519 signature and SHA-256 transaction ID.

The vector is for testing only. The deterministic key material is publicly reproducible test data and must never be used for any real account or funds.

## 6. Limitations and unresolved decisions

1. D-01 remains a proposed design until the project owner formally approves the address format and cryptographic parameters.
2. The address has no checksum or typo-detection encoding. A future presentation format may add one, but that would require versioning.
3. The reference module does not implement account registration, recipient existence checks, key rotation, recovery, balances, atomic state updates, or persistence.
4. A key change produces a new account ID. No migration or recovery path is defined. Loss of a private key would therefore mean loss of control under this candidate model; this must be addressed before any real use.
5. The format and algorithms require independent review and cross-implementation test vectors before becoming normative.

## 7. Release boundary

This work is an experimental local reference only. It does not create a blockchain network, a public token, or a deployable financial product. It does not authorize issuance, trading, custody, payments, or use of real funds. The v0.1 baseline and the main branch remain unchanged.
