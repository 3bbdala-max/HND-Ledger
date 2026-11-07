# HND v0.2 threat model

**Status:** initial engineering threat model for review; not a security audit.

## Assets to protect

- Correct account balances and sequential nonces.
- Transaction authenticity and chain separation.
- Block ordering, parent linkage, and deterministic state commitments.
- Supply-cap invariant and integrity of the genesis configuration.
- Availability and recoverability of node data.

## Trust boundaries

- Wallet/private-key holder to transaction decoder.
- Untrusted transaction pool to block proposer.
- Untrusted peer or validator to block verifier.
- Local process to persistent SQLite database.
- Genesis configuration to every node joining a network.

## Threats and required controls

| Threat | Required control | Current local prototype |
|---|---|---|
| Forged transaction | Ed25519 verification and sender-key binding | Implemented in transaction module |
| Cross-chain replay | Chain ID included in signed payload | Implemented |
| Transaction replay | Exact sequential account nonce | Implemented in local state |
| Overspend | Check balance before state mutation | Implemented |
| Supply inflation | Genesis and state supply invariant | Local cap check only; public genesis unresolved |
| Non-canonical encoding | Canonical CBOR re-encoding check | Implemented for transaction decode |
| Block tampering | Parent hash, transaction replay, state-root and block-hash checks | Implemented in local recovery |
| Database rollback | Trusted checkpoint or external finalized height | Not implemented |
| Malicious proposer | Independent deterministic validation by every node | Not implemented |
| Equivocating validator | Signed votes and equivocation evidence | Not implemented |
| Network partition | Explicit quorum and safety rules | Not implemented |
| Sybil identities | Permissioned validator admission or costly Sybil resistance | Not implemented |
| Key theft | Secure key storage, rotation, revocation | Not implemented |
| Denial of service | Limits, rate control, bounded decoding and resource budgets | Not implemented |
| Software supply-chain compromise | Pinned dependencies, reproducible builds, review | Not implemented |

## Consensus safety assumptions

No consensus protocol is currently selected or implemented. A future protocol must state:
- The validator admission model and validator-set transition rules.
- The maximum Byzantine validator weight it tolerates.
- The quorum threshold and why two conflicting quorums cannot both finalize.
- Message authentication, round/height binding, replay protection, and equivocation handling.
- Liveness assumptions, including network synchrony and validator availability.
- Restart, state-sync, and validator-key rotation behavior.

## Mandatory release gates

1. Protocol and genesis formats frozen with test vectors.
2. Independent implementation review and adversarial test suite.
3. Consensus safety proof or established protocol with parameters justified.
4. Multi-process, multi-host tests with network delay, partitions, crashes, and equivocation.
5. External cryptographic and application security review.
6. Backup, upgrade, recovery, monitoring, and incident-response procedures.
7. Separate legal and economic review before any public issuance or distribution.

## Non-claims

This document does not establish that HND is decentralized, secure, fault tolerant, audited, legally approved, or ready for public launch.
