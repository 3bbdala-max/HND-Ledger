# HND v0.2 implementation status

**Status:** first local-ledger implementation draft; not production-ready.

## Implemented in this branch

- Python package scaffold targeting Python 3.11+.
- Ed25519 transaction signing and signature verification using the maintained `cryptography` library.
- Canonical CBOR serialization using `cbor2` canonical mode, with re-encoding checks on decode.
- Domain-separated account identifiers and transaction signing messages.
- Chain-ID binding, sender/public-key binding, uint64 amount and nonce validation.
- Atomic local balance transfer with exact sequential nonces, insufficient-funds rejection, recipient overflow checks, and supply-cap invariant.
- Initial pytest coverage for signatures, tampering, chain mismatch, canonical encoding, replay, nonce, insufficient funds, and supply invariants.

## Not yet implemented

- Block production, block persistence, recovery, or state commitments.
- Genesis allocation format and production genesis file.
- Validator registration, validator networking, consensus, or independent validator operation.
- Peer-to-peer networking, wallet application, RPC/API, explorer, or public network.
- External security audit, economic review, legal review, or authorization to issue or trade a token.

## Verification status

The repository contains an initial automated test suite. The suite has **not** yet been run in a controlled environment and no passing CI result has been observed. Do not interpret the presence of tests as evidence that they passed.

## Important scope limitation

This is a local prototype foundation only. It does not establish decentralization, Byzantine fault tolerance, production security, or readiness for public launch.
