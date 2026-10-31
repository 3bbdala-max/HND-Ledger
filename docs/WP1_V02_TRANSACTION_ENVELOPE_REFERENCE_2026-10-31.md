# HND v0.2 — transaction envelope reference implementation

**Date:** 2026-10-31  
**Workstream:** WP1 — transaction envelope and strict validation  
**Status:** Experimental reference implementation; proposed parameters are not approved protocol decisions.  
**Baseline:** v0.1 remains unchanged.

## 1. What was added

An isolated Python module was added at `hnd_v02/transaction.py`. It is deliberately separate from `hnd_prototype.py` and does not alter the v0.1 baseline.

The module provides:

- An exact transaction envelope with `protocol_version`, `network_id`, `sender`, `recipient`, `amount`, `nonce`, and `signature`.
- Canonical JSON encoding (UTF-8, sorted keys, compact separators, NaN/Infinity disabled).
- Ed25519 signatures over a domain-prefixed canonical payload. The fixed prefix is `HND-LEDGER/TX\0`.
- A transaction identifier over the same domain-prefixed unsigned payload, so network and protocol version are included.
- Strict integer checks using exact Python types, rejecting bool and float aliases.
- Explicit network/version matching, amount bounds, unsigned-64-bit nonce range, balance checks, strict Base64 decoding, and Ed25519 verification.

The module expects the caller to supply the sender account's stored public key and current balance/nonce. It does not implement a ledger, account database, account-ID derivation, block format, peer network, or consensus.

## 2. Reference parameters and unresolved decisions

This implementation uses the following **candidate engineering rules solely to make an executable test fixture**:

| Parameter | Reference behavior | Project decision status |
|---|---|---|
| Protocol version | Positive integer; test fixture uses `2` | Not approved |
| Network ID | 1–64 ASCII letters/digits plus `. _ : -`, begins alphanumeric | Not approved |
| Amount | Exact positive integer, bounded by caller-provided `max_amount` | Range policy not approved; no project-wide cap embedded |
| Nonce | Exact integer in `[0, 2^64 - 1]` | 64-bit bound is a proposal, not approved |
| Signature | Ed25519 over `HND-LEDGER/TX\\0` plus canonical payload | Requires protocol review and test-vector approval |
| Account ID | Supplied as sender label; public-key binding delegated to caller | D-01 remains open |

In tests, `max_amount=1_000_000` is only a local fixture value. It is not a transaction-limit decision, allocation, or public supply commitment. No decimal precision, genesis allocation, fees, minting, burning, or validator economics are defined here.

## 3. Test results

Executed locally on the reference implementation:

```text
python -m unittest -v tests.test_v02_transaction_envelope
Ran 16 tests
OK
```

Coverage includes valid signatures; rejection of boolean, float, string, zero, negative, and oversized amounts; rejection of malformed, boolean, float, negative, and overflowing nonces; stale nonce; insufficient balance; self-transfer; missing/unknown fields; malformed key/signature; wrong network and protocol version; and signature invalidation when signed fields are changed.

These results establish only that this isolated module passes its own 16 tests in the local environment. They are not GitHub Actions results, a formal verification result, an independent audit, or evidence of production readiness.

## 4. Reproduction

From the repository root:

```bash
python -m pip install -r requirements.txt
python -m unittest -v tests.test_v02_transaction_envelope
```

## 5. Remaining work before this can become normative

1. Decide and specify account-ID derivation and key binding (D-01).
2. Approve the precise network-ID registry/format and protocol versioning policy.
3. Approve the nonce width and transaction amount range, including how the range relates to the eventual atomic-unit scale.
4. Publish byte-for-byte signing and transaction-ID test vectors for independent implementations.
5. Define a verified genesis manifest and state-transition rules before integrating this primitive into a ledger.
6. Keep distributed consensus and networking out of scope until validator assumptions and a reviewed consensus design exist.

## 6. Release boundary

This is an experimental transaction primitive for controlled development. It is not a deployable blockchain, public token, financial product, investment, or authorization to issue, sell, list, custody, transfer, or accept real funds. v0.1 remains unchanged, and `main` must not be updated as part of this work item.
