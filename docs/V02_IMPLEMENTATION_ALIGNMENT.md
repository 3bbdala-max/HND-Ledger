# HND v0.2 Implementation Alignment Register

**Status:** Engineering work register; not a security approval or release authorization.  
**Baseline:** `main` at the time this register was prepared.  
**Working branch:** `work/v02-implementation-alignment`  
**Purpose:** Track implementation mismatches against `docs/PROTOCOL.md` and `docs/CRYPTO_FORMAT.md` before extending the ledger.

## 1. Evidence inspected

The following files were read from `main`:

| Path | Observed role |
|---|---|
| `hnd_ledger/crypto.py` | Ed25519 key generation, address derivation, signing, verification |
| `hnd_ledger/ledger.py` | In-memory account balances, transaction validation and transfer |
| `tests/test_ledger.py` | Ten pytest cases for basic local-ledger behavior |
| `requirements.txt` | Broad version ranges for cryptography and pytest |
| `.github/workflows/tests.yml` | Python 3.12 CI workflow running pytest |
| `docs/PROTOCOL.md` | v0.2 protocol design baseline |
| `docs/CRYPTO_FORMAT.md` | Canonical encoding and cryptographic format design |

This register is based on source inspection only. It does not claim that tests were executed in this review.

## 2. Confirmed implementation gaps

| ID | Specification requirement | Current source observation | Required correction | Required evidence |
|---|---|---|---|---|
| ALIGN-001 | Deterministic CBOR arrays for signed objects | `Transaction.signing_bytes()` uses sorted compact JSON | Replace signing and ID encoding with the exact fixed-array deterministic CBOR profile | Golden CBOR byte vectors and round-trip/rejection tests |
| ALIGN-002 | Account ID uses `HND-ACCOUNT-V2\0` domain prefix | `address_from_public_key()` hashes the public key directly | Apply the exact domain-separated formula | Fixed public-key-to-account test vector |
| ALIGN-003 | Transaction signature covers the specified domain-separated signing message | Current signing bytes are JSON without the specified signing prefix | Implement the exact signing message from CRYPTO_FORMAT | Fixed signing-message bytes and valid/invalid signature vectors |
| ALIGN-004 | Transaction ID hashes the complete signed transaction | Current `txid` hashes signing payload only and excludes public key/signature | Hash the complete canonical eight-field signed transaction | Fixed signed-transaction and txid vectors |
| ALIGN-005 | Amount and nonce use specified unsigned 64-bit bounds | Current amount limit is `2**256 - 1`; nonce has no upper bound | Enforce the protocol's exact ranges, including bool rejection | Boundary tests at zero, max, max+1, and boolean values |
| ALIGN-006 | Self-transfer is rejected | Current ledger accepts self-transfer and advances nonce | Reject self-transfer before state mutation | Rejection test proving balances and nonce unchanged |
| ALIGN-007 | Chain ID is exactly 32 bytes and protocol version is explicit | Current network identifier is a non-empty string; transaction has no protocol-version field | Introduce the fixed versioned transaction schema and 32-byte chain ID | Schema and wrong-version/wrong-chain tests |
| ALIGN-008 | Genesis and block formats are defined | Current package exposes only a transaction ledger; no block or genesis module was found in the inspected package listing | Implement genesis fixture, block header/body, commitments, and chain linkage only after canonical primitives are frozen | Genesis/block golden vectors and tamper/parent/height tests |
| ALIGN-009 | Persistent atomic commit and recovery | Current ledger state is held in in-memory dictionaries and a set | Add a durable storage boundary with atomic commit semantics and recovery verification | Restart, interrupted-write, corruption, and replay tests |
| ALIGN-010 | CI dependencies and actions are reproducible | Requirements use open version ranges; workflow actions use mutable major tags | Pin dependencies and actions to reviewed immutable versions/SHAs; add lock/hash and supply-chain evidence | Lock file with hashes, workflow pin review, SBOM and provenance plan |

## 3. Important protocol consistency checks

Before implementation is declared conformant, resolve these specification-level details explicitly:

1. The protocol text says transaction IDs derive from the complete signed transaction. The cryptographic profile defines the complete eight-element array. Tests must ensure the signature and public key are included exactly once.
2. The protocol text defines nonce as an unsigned 64-bit sequence and says the next accepted nonce is exact. The implementation must define how a sender at the maximum nonce is handled; it must reject any increment that would overflow.
3. The genesis identifier section says its exact array shape must be frozen in a committed fixture. That fixture is a prerequisite for genesis compatibility claims.
4. The state commitment includes accounts with non-zero balance or non-zero next nonce. State encoding must sort raw 32-byte account IDs, not their hexadecimal display strings.
5. The stated maximum supply and decimal precision imply 100,000,000,000,000 smallest units. The genesis allocation fixture must sum exactly to this amount before it is treated as a valid network genesis. No allocation addresses are inferred here.

## 4. Safe implementation sequence

### Gate A — Canonical primitives
- Add and pin a maintained deterministic CBOR dependency.
- Implement strict fixed-array encoders/decoders for account, transaction, state, block, and genesis structures.
- Implement domain-separated account IDs, signing bytes, transaction IDs, state commitments, block IDs, and genesis IDs.
- Commit golden vectors before changing higher-level ledger behavior.

### Gate B — Transaction and account state
- Change the transaction model to the exact version-2 schema.
- Enforce chain ID, version, field lengths, integer bounds, signature validity, sender-key binding, nonce, sufficient funds, no self-transfer, and checked arithmetic.
- Preserve atomic rejection: no state changes on any failed validation.

### Gate C — Genesis and blocks
- Freeze genesis fixture and identifier.
- Implement deterministic block encoding and parent/height validation.
- Execute transactions in order and verify the resulting state commitment.
- Commit blocks atomically only after all checks pass.

### Gate D — Durable storage and recovery
- Select and document a storage design appropriate to the local prototype.
- Implement atomic commit, crash recovery, corruption detection, and deterministic rebuild/verification.
- Do not treat local storage as a distributed anti-rollback authority for validator signing.

### Gate E — Reproducible evidence
- Run tests in clean CI on the exact commit under review.
- Record commit SHA, runtime, dependency lock, command, exit code, and artifacts.
- Add negative, property-based, deterministic replay, and crash-injection coverage.
- Keep consensus and production signer fencing as separate security gates.

## 5. Non-goals and restrictions

- This work does not enable public-network deployment, token issuance, exchange listing, or handling real funds.
- No production validator keys or real funds are to be used.
- No consensus algorithm or validator governance is selected by this register.
- No license is selected by this register. Ownership and licensing require a separate documented review.
- No claim of conformance, production readiness, decentralization, or independent audit may be made until supported by reproducible evidence.

## 6. Completion rule

An ALIGN item is closed only when:
1. the source change is committed;
2. the corresponding positive and negative tests are committed;
3. the tests pass on the exact commit SHA;
4. the evidence is recorded in the project register; and
5. any protocol change is reflected consistently in both protocol documents and versioning.

A green workflow on a different commit does not close an item.
