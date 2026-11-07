# HND v0.2 threat model

Status: engineering threat model for the local CometBFT integration; not a security audit.

## Assets

Correct balances/nonces, transaction authenticity and chain separation, deterministic block/state commitments, genesis and supply-cap integrity, validator signing state, database integrity, and private IPC boundaries.

## Trust boundaries

Wallet/private-key holder to transaction decoder; untrusted mempool to proposer; CometBFT peers to consensus engine; Go adapter to Python over Unix IPC; Python application to SQLite; genesis configuration to each joining node.

## Threats and controls

| Threat | Current control | Residual risk |
|---|---|---|
| Forged transaction | Ed25519 verification and sender-key binding | No independent cryptographic audit |
| Cross-chain replay | Chain ID in signed transaction | Chain-ID governance and migration policy remain |
| Transaction replay | Sequential account nonce and replay tests | No public wallet/indexer UX |
| Overspend | Atomic balance validation; PrepareProposal filters signed overspend; three-validator integration confirms no commit | Adversarial proposal/round campaign remains |
| Supply inflation | Genesis cap and invariant; cap included in state commitment v3 | No issuance governance or public allocation policy |
| Non-canonical encoding | Canonical CBOR re-encoding check | Fuzzing/sustained malformed-input campaign remains |
| Block/database tampering | Parent linkage, replay, state-root and block-hash verification | No external trusted checkpoint or rollback detection |
| Malicious proposer | ProcessProposal and FinalizeBlock validate ordered transactions | No adversarial proposer/round campaign |
| Validator equivocation | CometBFT voting/signing protocol | No HND-specific slashing/evidence policy or double-sign campaign |
| Network partition | CometBFT quorum consensus | Partition/healing tests not executed |
| Sybil identities | Explicit test validator identities from genesis | Production validator admission/voting-power governance undefined |
| Key theft | No production key custody claimed | Secure storage, backup, rotation, revocation absent |
| Denial of service | 1 MiB IPC frame, bounded mempool, block limits, loopback ABCI listener | No rate limits, per-peer quotas, or sustained exhaustion tests |
| Unauthorized IPC | Unix socket mode 0600 | Same-user processes and parent-directory permissions remain in trust boundary |
| Public ABCI exposure | Go listener restricted to loopback | Production RPC/P2P firewall and deployment hardening still required |

## Consensus assumptions

CometBFT v0.40.0 is integrated in local CI. Three validators run as separate processes with separate node homes, identities, Python apps, SQLite databases, and IPC sockets, but are co-located on one CI runner. The tests demonstrate ordinary proposal/commit, application-hash agreement, query responses, overspend filtering, and restart recovery. They do not test Byzantine validators, conflicting quorums, partitions, independent operators, or multi-host operation.

## Mandatory release gates

Independent protocol/cryptographic review; adversarial consensus tests; multi-host independently operated validators; validator key custody and anti-double-signing; crash injection, backup/restore and upgrades; resource-exhaustion tests; monitoring and incident response; independent security, economic, and jurisdiction-specific legal review.

This document does not establish decentralization, production security, fault tolerance under adversarial conditions, audit status, legal approval, or readiness for public launch.
