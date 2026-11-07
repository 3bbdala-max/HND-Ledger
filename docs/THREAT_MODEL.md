# HND v0.2 threat model

**Status:** engineering threat model updated for the local CometBFT integration; not a security audit.

## Assets to protect

- Correct account balances and sequential nonces.
- Transaction authenticity and chain separation.
- Deterministic block ordering, parent linkage, and state commitments.
- Supply-cap invariant and integrity of genesis configuration.
- Validator signing state and node data availability.
- Private keys, database files, and local IPC boundaries.

## Trust boundaries

- Wallet/private-key holder to transaction decoder.
- Untrusted transaction pool to block proposer.
- CometBFT peer and validator messages to the consensus engine.
- Go ABCI adapter to Python engine through a Unix-domain socket.
- Python application to persistent SQLite database.
- Genesis configuration to every node joining a network.

## Threats and current controls

| Threat | Current control | Residual risk |
|---|---|---|
| Forged transaction | Ed25519 verification and sender-key binding | No independent cryptographic audit |
| Cross-chain replay | Chain ID included in signed transaction payload | Protocol migration and chain-ID governance still need policy |
| Transaction replay | Sequential account nonce; replay tests | No external transaction index or wallet UX |
| Overspend | Balance check before state mutation; atomic candidate execution | Adversarial consensus scenarios not yet tested |
| Supply inflation | Genesis allocation cap and state invariant; cap included in state commitment v3 | No issuance governance, mint/burn policy, or public genesis policy |
| Non-canonical encoding | Canonical CBOR re-encoding check | Fuzzing and sustained malformed-input campaigns remain |
| Block/database tampering | Parent linkage, transaction replay, state-root and block-hash verification on restore | No external trusted checkpoint or rollback detection |
| Malicious proposer | ProcessProposal and FinalizeBlock deterministically validate ordered transactions | No adversarial proposer/round test campaign |
| Validator equivocation | CometBFT supplies consensus voting and signing protocol | No HND-specific evidence/slashing policy or double-sign recovery campaign |
| Network partition | CometBFT handles quorum-based consensus | Partition/healing tests not yet executed |
| Sybil identities | Test cluster uses explicit validator identities from genesis | Production validator admission and voting-power governance undefined |
| Key theft | No production key custody is claimed | Secure storage, backup, rotation, revocation, and operator procedures absent |
| Denial of service | 1 MiB IPC frame limit, bounded mempool, block limits, sequential local IPC handling | No rate limits, per-peer quotas, or sustained CPU/memory exhaustion tests |
| Unauthorized local IPC access | Unix socket mode 0600 | Same-user processes and parent-directory permissions remain in the local trust boundary |
| Public ABCI exposure | Go listener accepts loopback TCP addresses only | CometBFT RPC/P2P production firewall and deployment hardening still required |
| Supply-chain compromise | CometBFT version pinned; Go/Python dependencies bounded and CI-tested | Reproducible builds, SBOM, signing, and independent dependency audit absent |

## Consensus safety assumptions

CometBFT v0.40.0 is integrated as the consensus engine in local CI. Three validators run as separate processes with separate node homes, validator identities, Python applications, SQLite databases, and IPC sockets. They are nevertheless co-located on one CI runner and controlled by one workflow.

The integration demonstrates ordinary proposal, commit, application-hash agreement, and restart recovery for the tested configuration. It does **not** test Byzantine validators, conflicting quorums, network partitions, independent operators, or multi-host operation. The standard CometBFT/Tendermint voting-power fault assumptions must be reflected in the eventual validator policy and verified against the exact pinned release.

## Mandatory release gates

1. Versioned protocol and genesis formats, test vectors, and migration policy.
2. Independent implementation and cryptographic review.
3. Adversarial consensus tests: equivocation, conflicting proposals, replay, partitions, delay, loss, and Byzantine voting power.
4. Multi-host and independently operated validator tests.
5. Key custody, rotation, anti-double-signing, backup, restore, and incident-response procedures.
6. Resource-exhaustion tests, monitoring, alerting, and RPC/P2P network hardening.
7. Independent security, economic, and jurisdiction-specific legal review before any public issuance or deployment.

## Non-claims

This document does not establish that HND is decentralized, secure, fault tolerant under adversarial conditions, audited, legally approved, economically viable, or ready for public launch.
