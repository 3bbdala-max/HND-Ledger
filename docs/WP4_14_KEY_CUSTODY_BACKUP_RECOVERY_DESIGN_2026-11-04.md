# HND v0.2 — WP4.14 key custody, backup, and recovery architecture

**Date:** 2026-11-04  
**Workstream:** WP4.14 — validator and remote-signer key custody  
**Branch:** `phase-0.2-planning`  
**Status:** Design-only gate; no production custody implementation or approval  
**Safety boundary:** No production keys or credentials are generated, uploaded, or stored by this workstream

## 1. Objective and scope

Define a defensible lifecycle for the cryptographic identities that HND would require before any production validator or remote signer can be operated. The architecture must prevent a single operator, compromised host, stolen backup, or accidental state reset from silently taking control of signing authority or causing unsafe re-signing.

This document is an architecture proposal and review checklist. It does not select a vendor, provision an HSM/KMS, create production keys, or authorize real signing. The current CI signer helpers and keys remain disposable, loopback-only test fixtures.

## 2. Key and identity inventory

Treat each key class as a separate security principal with separate lifecycle and access policy.

| Material | Purpose | Custody requirement |
|---|---|---|
| Validator consensus private key | Signs CometBFT votes/proposals | Non-exportable HSM/KMS key where supported, or dedicated offline signer |
| Anti-double-sign state | Persists last-sign height/round/step and prevents conflicting signatures | Durable, integrity-protected, versioned state bound to the exact validator key and chain identity |
| Node P2P identity | Authenticates a CometBFT node to peers | Separate from consensus key; protected, pinned, rotated through a controlled identity transition |
| Remote-signer transport identity | Authenticates the signer endpoint (including Noise peer identity) | Separate from validator consensus and node P2P identities; stable across ordinary process restart |
| Operator/admin credentials | Authorize maintenance and policy changes | Individual identities, MFA, least privilege, short-lived access, audited elevation |
| Backup encryption keys | Protect exported recovery material | Separate custody domain and recovery quorum; never stored beside the encrypted backup |

No key may be reused across these roles merely for convenience. Public keys, peer IDs, key fingerprints, chain ID, Genesis hash, validator address, and key version must be recorded in an authenticated inventory without recording private key bytes.

## 3. Threat model

The design must address:

- compromise of a validator host, remote-signer process, operator workstation, CI runner, or cloud control plane;
- theft, substitution, truncation, rollback, or deletion of anti-double-sign state and backups;
- unauthorized signer or node identity replacement, DNS/IP redirection, and peer impersonation;
- malicious or mistaken administrators, shared credentials, excessive privileges, and unreviewed emergency access;
- HSM/KMS outage, provider lockout, region failure, account suspension, and API credential compromise;
- accidental key rotation, chain-ID/Genesis mismatch, restore to the wrong validator, and split-brain recovery;
- ransomware, destructive filesystem operations, backup corruption, and loss of the only recovery factor;
- supply-chain compromise of signer binaries, dependencies, build artifacts, or deployment configuration.

The architecture must assume that encrypted backups can be copied by an attacker and that a compromised runtime host may observe requests and metadata even when private key material is non-exportable.

## 4. Generation and enrollment

1. Generate production consensus keys inside the selected HSM/KMS or under a documented offline ceremony. Private key material must not pass through ChatGPT, source control, ordinary CI, issue trackers, or general-purpose application logs.
2. Record the public key, derived validator address, key identifier/version, algorithm, creation time, custodian approvals, chain ID, and Genesis hash in the controlled key inventory.
3. Generate node P2P and remote-signer transport identities independently. Record and authenticate their public fingerprints/peer IDs.
4. Pin the expected signer identity at the validator and the expected node identity at the signer. Noise allowlists must be explicit and non-empty. Never rely on encryption without peer identity verification.
5. Bind each signer policy to one validator identity and one chain context. Any change to validator key, chain ID, Genesis hash, signer peer identity, or node identity must require a reviewed migration procedure.
6. Verify the complete enrollment using public-key challenge/signature tests before a validator is admitted. No live signing authority is enabled by an unreviewed configuration change.

## 5. Signing policy and runtime isolation

- The consensus private key is used only by the signer service/HSM boundary. Validator nodes submit bounded, authenticated signing requests; they do not receive exportable private key bytes.
- Enforce chain ID, message type, validator key ID, and monotonic height/round/step checks in the signer policy.
- Anti-double-sign state is authoritative security state, not a disposable cache. A missing, corrupt, stale, rolled-back, or identity-mismatched state file must cause fail-closed startup. Recovery must never silently create a fresh state file.
- State updates must be atomic and durable according to the selected storage/HSM guarantees. The implementation must document fsync/transaction semantics and how rollback is detected.
- Restrict signer network ingress to explicitly authenticated validator identities; use mutually authenticated transport and network segmentation. Unix sockets are suitable only for tightly isolated same-host test/deployment patterns after local access controls are reviewed; they are not a general remote-host security boundary.
- Run signer services with dedicated OS identities, minimal filesystem access, restricted egress, resource limits, and immutable/reproducible deployment artifacts.
- Separate signer administration from validator-node administration. No single routine operator should be able to replace the validator key, alter signer policy, and erase anti-double-sign state without independent approval.

## 6. Backup and recovery architecture

### Backup policy

- Prefer non-exportable HSM/KMS key replication or vendor-supported backup mechanisms with documented security properties. If export is unavoidable, require a separately approved offline ceremony and threshold-controlled encryption; do not improvise key export.
- Encrypt backups with an independent backup-encryption key. Store encrypted backups and decryption/recovery factors in separate security domains and geographic failure domains.
- Back up anti-double-sign state together with a signed manifest binding it to validator public-key fingerprint, key version, chain ID, Genesis hash, network ID, state schema version, height/round/step, creation time, and backup sequence.
- Use append-only or object-lock retention where available. Record backup hashes, signer identity, approval records, and restore test results.
- Apply least privilege and dual control to backup creation, retrieval, deletion, retention changes, and restore authorization.

### Restore gate

A restore must be a controlled state transition, never a file-copy shortcut:

1. Freeze signing for the affected validator and isolate its old signer instance.
2. Verify the operator approvals and recovery quorum.
3. Authenticate the target chain ID, Genesis hash, validator public key/address, node identity, and signer transport identity against the approved inventory.
4. Verify backup signature, cryptographic digest, schema version, anti-double-sign monotonic state, and backup sequence. Reject rollback to a state older than the last known signing state.
5. Restore into an isolated environment with network signing disabled.
6. Compare restored state against independently held audit records and the last committed chain state. Require explicit sign-off by two independent custodians.
7. Re-enable signing only after a supervised test signature/verification procedure that cannot create a conflicting production vote, and after the incident/recovery record is complete.

If anti-double-sign state cannot be proven current, the validator remains offline. Availability must never take precedence over consensus safety.

## 7. Rotation, revocation, and compromise response

- Define separate rotation schedules and emergency procedures for consensus keys, P2P node identities, transport identities, operator credentials, and backup encryption keys.
- Consensus-key rotation requires a protocol/governance-authorized validator update and an explicit chain-height activation plan; it must not be treated as an ordinary secret replacement.
- Transport identity rotation requires coordinated allowlist/pinning updates, overlap rules, expiry, and rollback prevention.
- On suspected compromise: stop or isolate signing, preserve logs and state snapshots, revoke affected credentials/identities, notify authorized governance and incident responders, assess possible equivocation, and follow a documented validator removal/replacement procedure.
- Never delete anti-double-sign state as an incident workaround. Preserve forensic copies under controlled access.
- Record all key creation, access, policy changes, signing requests, backup/restore, rotation, revocation, and emergency actions in tamper-evident audit logs.

## 8. Required verification before implementation approval

The implementation proposal must include automated or supervised tests for:

- unauthorized operator and unauthorized signer identity rejection;
- missing, truncated, corrupt, substituted, stale, and rolled-back anti-double-sign state;
- wrong validator key, node identity, transport identity, chain ID, Genesis hash, and key version;
- interrupted backup, corrupted ciphertext, missing recovery factor, and failed restore;
- restore of a valid backup in an isolated environment with no signing enabled;
- dual-control enforcement and audit record completeness;
- HSM/KMS unavailability, throttling, credential rotation, region/provider outage, and disaster recovery;
- signer restart, validator restart, reconnect, and catch-up without resetting monotonic signing state;
- emergency key rotation and validator removal under a documented governance procedure.

Every negative case must fail closed and must not generate a fresh signing state as a fallback.

## 9. Decisions intentionally left open

The following decisions require independent security and operational review before any implementation choice:

- HSM/KMS vendor and deployment model (on-premises, cloud HSM, managed KMS, or offline signer);
- supported signature algorithm and exact HSM compatibility with the pinned CometBFT version;
- signer quorum/M-of-N administrative recovery model;
- anti-double-sign state storage technology and rollback-resistant monotonic counter strategy;
- backup retention, geographic separation, recovery-time objective, and recovery-point objective;
- operator roles, separation of duties, legal ownership, incident authority, and audit retention;
- validator admission, key rotation, emergency removal, and governance approval process.

## 10. Acceptance gate and non-claims

WP4.14 may move from design to implementation only after:

1. the threat model and key inventory are reviewed by an independent security specialist;
2. the custody model and restore ceremony are approved by accountable project owners;
3. the selected HSM/KMS or offline signer has documented security guarantees and a tested failure/recovery procedure;
4. anti-double-sign rollback protection is specified and independently reviewed;
5. operational, governance, and jurisdiction-specific legal reviews define who may operate and control validator signing authority.

This design does not prove that any HSM/KMS is secure, does not implement production custody, and does not authorize production signing, mainnet deployment, token sale, exchange listing, or real-value activity. All public-release gates G2–G4 remain closed.

---
This document is a design proposal and review checklist, not a security certification, custody approval, legal opinion, or production deployment instruction.
