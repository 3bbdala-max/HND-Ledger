# HND v0.2 — Genesis manifest reference and validation

**Date:** 2026-10-31  
**Workstream:** WP1 — Genesis manifest  
**Status:** Isolated reference validator and test fixture; no public allocation or supply decision is approved.  
**Branch:** phase-0.2-planning

## 1. Purpose

A node must be able to check that it is using the same initial account allocation as every other node. This work item defines a deterministic manifest shape and a validation function. It does not create balances, mint units, start a ledger, or publish a network.

## 2. Candidate manifest structure

The manifest contains:

- Manifest format version.
- Network identifier and protocol version.
- Declared total supply in integer units.
- A list of allocations, each containing account ID, Ed25519 public key, and positive integer amount.

Allocation records must be sorted by account ID, without duplicates. The validator recomputes each account ID from its public key using the v0.2 account derivation rule. It then sums allocations and requires exact equality with the declared total.

The manifest hash is:

    SHA256(GENESIS_DOMAIN || canonical_json(manifest))

The domain prefix is HND-LEDGER/GENESIS followed by a zero byte. Canonical JSON uses UTF-8, sorted object keys, compact separators, and rejects non-finite numbers.

## 3. Trusted hash requirement

The validator takes expected_genesis_hash as a separate input. A node must obtain this expected value from a trusted configuration, reviewed software release, or another authenticated distribution channel.

A hash placed next to an untrusted manifest does not authenticate that manifest if an attacker can replace both. Every node must pin or otherwise authenticate the expected hash before accepting the manifest.

This validator does not implement publisher signatures, key rotation, governance, or an authenticated update process.

## 4. Local test fixture

The file vectors/v0.2-genesis-devnet-example.json contains a two-account test-only allocation:

| Item | Value |
|---|---:|
| Test fixture total | 1,000,000 units |
| Test account A | 600,000 units |
| Test account B | 400,000 units |
| Manifest hash | 505629671345f9d33ad8a567426be09b6f30dbdf403f2a15ccba576cb2109fbe |

These recipients and amounts are synthetic test data only. The one-million value repeats the prototype's nominal test supply and does not approve a public supply, token distribution, recipient list, or issuance commitment.

## 5. Local test results

Executed locally against the isolated v0.2 reference:

    python -m unittest -v tests.test_v02_transaction_envelope tests.test_v02_genesis_manifest

Result: **35 tests passed, 0 failed**.

The test suite covers derived account IDs, network/version separation, sender-key binding, transaction signature checks, strict numeric types, malformed account keys, genesis allocation order and duplicates, account/public-key matching, exact supply totals, malformed fields, and rejection when the supplied pinned hash does not match.

This is a local run, not a GitHub Actions result, independent node implementation, formal verification, or security audit.

## 6. Limits and next requirements

1. The one-million total and example allocations remain test parameters; they are not public economic decisions.
2. The validator checks the manifest against a trusted hash but does not establish who is authorized to approve or publish that hash.
3. The format does not yet specify a digital signature for the release manifest, a trusted publisher key, or a governance procedure.
4. The validator checks account ID derivation from each included public key, but a complete node must still implement the account registry and state initialization.
5. Supply range and atomic-unit semantics remain open. This reference uses exact Python integers and does not settle a cross-language maximum.
6. Any eventual public genesis needs a reviewed distribution policy, independent implementation tests, security assessment, and jurisdiction-specific legal review.

## 7. Release boundary

This is a deterministic local validation reference only. It does not issue, mint, sell, distribute, or activate any asset. No real funds or public network are in scope. v0.1 and main remain unchanged.
