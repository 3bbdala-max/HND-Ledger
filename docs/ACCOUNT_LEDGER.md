# HND 0.2 — Account Ledger Design (Proposal)

Status: implementation proposal for a deterministic local prototype, not a finalized public-network protocol.

## Scope

This component implements an in-memory account-based ledger. It does not implement blocks, consensus, peer-to-peer networking, persistent storage, or production key management.

## Account model

- An account address is the lowercase hexadecimal SHA-256 digest of the raw 32-byte Ed25519 public key.
- The ledger tracks an integer balance and next expected transaction nonce for each address.
- Unknown recipient addresses may receive funds; an unknown sender has zero balance and cannot spend.
- Genesis balances are test configuration only. No final supply, allocation, or issuance policy is defined here.

## Transaction format

Each transaction contains exactly: network_id, sender, recipient, amount, nonce, public_key, and signature.

The signed payload contains amount, network_id, nonce, recipient, and sender. It is encoded as UTF-8 JSON with sorted keys, compact separators, and Unicode preserved. The public key is checked against sender. The signature and transaction ID use the canonical payload; signature and public_key are excluded from that payload and transaction ID.

## Validation and state transition

Validation checks network, field formats, integer bounds, public-key/address correspondence, signature, duplicate transaction ID, nonce, available funds, and recipient overflow before changing state. A rejected transaction must not partially change balances, nonce, or the duplicate set.

Ed25519 and SHA-256 are provided by the maintained cryptography package; no custom cryptographic primitives are implemented.

## Security boundaries

- Never serialize private keys into transactions, blocks, logs, or repository fixtures.
- The caller is responsible for secure private-key storage and backup.
- The current prototype is single-process and in-memory; it is not safe for concurrent writers or untrusted network exposure.
- Production requires protocol review, persistent-state crash consistency, concurrency control, fuzzing, independent security review, and explicit governance decisions.

## Reproducible local tests

Install with `python -m pip install -r requirements.txt`, then run `python -m pytest -q`.

## Open protocol decisions

The smallest-unit decimal scale, final supply and issuance rules, fee policy, transaction expiry policy, canonical format versioning, persistent database, block format, and consensus mechanism remain undecided.
