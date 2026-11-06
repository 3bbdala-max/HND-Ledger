# WP4.14 — Validator Device Loss, Key Compromise, Signer Replacement and Safe Recovery Audit — 2026-11-07

**Repository:** `3bbdala-max/HND-Ledger`  
**Branch:** `phase-0.2-planning`  
**Reviewed baseline:** `b9e3683e392d55f6bb44f8a64a41a7656687d7da`  
**Review type:** Documentation-only static source/design/test audit  
**Disposition:** **NOT APPROVED for production validator key custody, disaster recovery, signer failover, or production signing.**

## 1. Executive result

The repository has a useful architecture design for separating validator consensus keys, anti-double-sign state, P2P identity, signer transport identity, operator credentials and backup-encryption keys. It also has local integration evidence for a controlled remote-signer stop/restart scenario.

However, these must not be confused with a production disaster-recovery capability:

- The CometBFT signer integration harness uses disposable test keys and temporary signer state. It demonstrates a controlled restart path, not a production key recovery ceremony.
- `hnd_v02/anti_rollback_reference.py` explicitly states that its anchor is in-memory and synthetic, uses a fixed synthetic MAC key, and must not be connected to a real signer, filesystem, HSM, TPM, KMS or network service.
- The synthetic anti-rollback model is not wired into the CometBFT signer signature-release path.
- The model's readiness check has a documented time-of-check/time-of-use race: an authorization result can become stale after it samples a committed record or host epoch.
- Existing backup/recovery architecture is design-only. No production HSM/KMS, durable independently administered monotonic anchor, key escrow/replication, restore quorum, or signed production recovery manifest is established by the reviewed evidence.

**Result:** loss of a validator machine, loss of signer state, or suspected key compromise must not be resolved by copying a key/state file to a replacement host and restarting signing. The safe action is to stop signing, preserve evidence, establish which security material remains trustworthy, and follow an authorized recovery or validator key-rotation/removal procedure.

## 2. Reviewed evidence

Repository artifacts:
- `docs/WP4_14_KEY_CUSTODY_BACKUP_RECOVERY_DESIGN_2026-11-04.md`
- `docs/WP4_14_REMOTE_SIGNER_ANTI_ROLLBACK_IMPLEMENTATION_BOUNDARY_AUDIT_2026-11-05.md`
- `docs/WP4_14_REMOTE_SIGNER_RECOVERY_AND_ANTI_DOUBLE_SIGN_TEST_GAP_AUDIT_2026-11-05.md`
- `docs/WP4_14_CONCURRENCY_HOST_FENCING_AND_SIGNER_READINESS_REVIEW_2026-11-05.md`
- `docs/WP4_14_COMETBFT_NATIVE_DATABASE_COMPATIBILITY_ABCI_REPLAY_AND_RECOVERY_MATRIX_AUDIT_2026-11-07.md`
- `docs/WP4_9_COMETBFT_V040_REMOTE_SIGNER_TRANSPORT_SECURITY_REVIEW_2026-11-04.md`
- `hnd_v02/anti_rollback_reference.py`
- `tests/test_v02_anti_rollback_reference.py`
- CometBFT v0.40.0 remote-signer source inspection and four-validator test harness records.

No production secret, private key, credential, signer process, or validator state was accessed.

## 3. Security principals must remain separate

| Identity/state | Purpose | Must not be confused with |
|---|---|---|
| Consensus private key | Signs CometBFT votes and proposals | P2P identity, HND account key, transport key |
| CometBFT anti-double-sign state | Tracks last signed height/round/step and related signer state | Application database, block height alone, ordinary backup checksum |
| P2P node key | Identifies a node to peers | Consensus signer identity |
| Remote-signer transport identity | Authenticates the node/signer connection | Consensus signing key |
| HND account key | Authorizes HND transactions | Validator consensus key |
| Backup-encryption key | Protects exported recovery material | Validator key and encrypted backup |
| Operator identity | Authorizes recovery actions | Any machine/service identity |

A replacement host does not become the same validator merely because it has the same IP address, node name, or copied directory. Validator identity must be anchored to the approved consensus public key and chain/Genesis context. Transport and P2P identity changes require their own controlled transitions.

## 4. Incident classification and safe response

### 4.1 Validator machine lost, but signer key and signer state remain independently protected

Required response:
1. Isolate and fence the lost host and its network credentials.
2. Disable the old node's access to the signer; confirm that no second process can still submit requests.
3. Preserve the last authenticated signer checkpoint and relevant audit records.
4. Provision a clean replacement host from a verified release/build and approved node profile.
5. Re-establish node P2P and transport identities using their own approved lifecycle.
6. Attach the existing signer only after verifying validator public key, chain ID, Genesis hash, signer peer identity, anti-double-sign state freshness and host fencing.
7. Verify no stale authorization or previous host epoch can still be used.
8. Re-enable signing only after two-person review and a recovery record.

A machine-loss event alone does not authorize consensus-key rotation. Conversely, an inaccessible old host must be treated as potentially still alive until network/signer-side fencing proves it cannot sign.

### 4.2 Signer process or signer disk lost; consensus key survives in a protected HSM/KMS

Required response:
- Keep signing disabled until the durable anti-double-sign state and independent monotonic checkpoint are recovered and verified.
- Reconstruct a signer service around the existing non-exportable key only if the custody provider supports authenticated key identity and the anti-double-sign state is proven current.
- Do not initialize a fresh FilePV signing state or reset the last-sign height/round/step.
- Reject restore if the state backup is older than the independent checkpoint, has an unknown schema, belongs to another validator/chain/Genesis, or cannot be authenticated.
- Test the replacement in an isolated environment with signing authority disabled before production cutover.

If the anti-double-sign state cannot be proven current, the validator stays offline. The chain's current block height is not, by itself, a sufficient substitute for the signer's complete last-sign H/R/S state.

### 4.3 Consensus private key suspected stolen or exposed

This is a key-compromise incident, not ordinary hardware recovery.

Required response:
1. Stop or isolate the affected signer immediately and preserve logs, signer state, transport records and host images.
2. Revoke signer access and transport identities. Assume copies of the old private key may remain outside the controlled environment.
3. Assess whether conflicting votes/proposals may already have been signed; inspect chain evidence and signer audit records.
4. Do not re-enable the old key on a new machine, even if the original anti-double-sign state is available.
5. Use the chain's approved governance/validator-set process to remove or replace the validator key at an explicit authorized activation point.
6. Enroll a new consensus key under a new identity and controlled custody ceremony; keep P2P and transport rotation separate.
7. Resume only after validator-set activation and peer/signer identity checks are verified.

A private-key compromise cannot be repaired by restoring an older signing-state backup. Rotation is a consensus/governance transition, not a filesystem operation.

### 4.4 Anti-double-sign state missing, corrupt, rolled back or inconsistent

Required response:
- Fail closed. No new signing state file, default state, manual HRS edit, or checksum reseal is permitted as a recovery shortcut.
- Recover only from a state backup whose authenticity, validator/chain binding, schema, sequence and monotonic freshness are verified against an independently administered anchor.
- If no trusted checkpoint or complete recovery proof exists, leave the validator offline and follow the authorized validator removal/replacement or emergency governance process.
- Preserve the corrupt or stale material for forensic comparison; never overwrite the only copy.

### 4.5 HSM/KMS/provider unavailable

- Treat outage as a liveness failure; do not export keys or switch to a weaker local signer to maintain uptime.
- Keep the signer disabled until provider identity, key version, audit history and recovery state are verified.
- Failover to another region/account/provider is allowed only if key replication and anti-double-sign state consistency are pre-designed, independently tested and protected against concurrent active signers.

## 5. Single-active-signer and fencing requirements

A production deployment must enforce all of the following at the signer boundary, not merely in an operator runbook:

1. One active signing authority per validator key and chain context.
2. A durable, monotonic fencing epoch that the signer itself enforces on every request.
3. Atomic authorization bound to validator public-key fingerprint, network ID, chain ID, Genesis hash, signer identity, operation ID, anchor sequence, host epoch, H/R/S and sign-bytes digest.
4. A single-use or otherwise replay-safe authorization; stale tokens are rejected after takeover or anchor advancement.
5. Durable anti-double-sign state transition before a signature is released to the caller, with documented crash semantics.
6. A fail-closed response to anchor outage, uncertain commit, duplicate signer process, stale backup or identity mismatch.
7. No automatic fallback from remote signer to local FilePV or alternate key.
8. A tested fencing mechanism that revokes the old host even when it later reconnects after a network partition.

The documented synthetic-model TOCTOU finding means a boolean `signing_allowed=true` snapshot is not a sufficient production authorization. The final signer must enforce the current epoch/sequence for the exact request at the point of use.

## 6. Recovery approval and separation of duties

Recommended independent roles:
- **Incident commander:** declares incident and coordinates containment; cannot alone restore signing.
- **Key custodian:** verifies HSM/KMS key identity and backup/decryption custody; cannot alone approve validator-set changes.
- **Signer-state custodian:** verifies anti-double-sign checkpoint and restore sequence; cannot alter consensus key.
- **Governance approver:** authorizes validator removal/replacement or key activation under the network's approved rules.
- **Independent reviewer:** verifies evidence, release identity and recovery record before signing resumes.

At minimum, require two independent approvals for signer-state restore and a separate governance authorization for consensus-key rotation or validator-set change. Emergency access must be individually attributable, time-bounded, logged and reviewed after the incident.

No private key, seed phrase, recovery share, HSM credential or unredacted signer secret belongs in source control, CI artifacts, chat, ordinary logs or a shared backup folder.

## 7. Backup manifest and freshness contract

A future authenticated backup manifest should bind at least:
- network ID, chain ID and exact Genesis hash;
- validator consensus public-key fingerprint and key version;
- signer software/source/build digest and signer transport identity;
- anti-double-sign state schema/version and cryptographic digest;
- exact H/R/S state and any additional CometBFT FilePV metadata required by the pinned version;
- independent anchor sequence, fencing epoch and checkpoint digest;
- monotonic backup sequence and authenticated backup creation record;
- encrypted backup object digest and encryption-key identifier/version;
- restore approval identifiers and custody audit references.

Wall-clock timestamp, filename, local filesystem mtime, unkeyed SHA-256 checksum, or a user-supplied digest must not be treated as proof of freshness. The expected checkpoint must be authenticated and held outside the backup's rollback domain.

The repository has not yet implemented this production manifest/anchor contract. This section is a design requirement, not an existing format.

## 8. Required production recovery test matrix

All tests below are proposed acceptance gates, not tests claimed to have run.

| ID | Scenario | Required result |
|---|---|---|
| KEYREC-01 | Lose validator node host; signer/HSM and state remain protected | New host cannot sign until old host is fenced and identity tuple verified |
| KEYREC-02 | Old host reconnects after replacement is active | Old host's fencing epoch rejected at signer boundary |
| KEYREC-03 | Lose signer process but retain HSM key and trusted state | Restore without exporting key or resetting HRS |
| KEYREC-04 | Lose signer state; retain key but no trusted checkpoint | Fail closed; no fresh FilePV state |
| KEYREC-05 | Restore older valid state backup | Reject against independent monotonic checkpoint |
| KEYREC-06 | Substitute state from another validator | Reject key/validator identity mismatch |
| KEYREC-07 | Substitute state from another chain or Genesis | Reject network/chain/Genesis mismatch |
| KEYREC-08 | Start two signers concurrently with same key | Exactly one acquires enforced signing authority; loser cannot sign |
| KEYREC-09 | Partition old signer from anchor, then reconnect | Old epoch cannot sign after takeover |
| KEYREC-10 | Crash before/during/after durable state commit and before signature response | No conflicting signature after restart; ambiguous outcomes reconcile safely |
| KEYREC-11 | Anchor unavailable during signing authorization | No signature emitted |
| KEYREC-12 | Stale authorization token used after anchor sequence advances | Signer rejects it |
| KEYREC-13 | Suspected consensus-key compromise | Old key remains disabled; replacement requires governance activation |
| KEYREC-14 | HSM/KMS region outage and failover | No dual active signer; key version and anti-double-sign state remain consistent |
| KEYREC-15 | Backup encryption key lost or rotated | Recovery follows tested quorum/rotation; no plaintext key export shortcut |
| KEYREC-16 | One custodian attempts restore alone | Restore authorization rejected |
| KEYREC-17 | Revoked Noise peer attempts reconnect | Peer rejected before signing request processing |
| KEYREC-18 | Restore package altered, truncated or replayed | Manifest/signature/digest/freshness validation rejects it |
| KEYREC-19 | Signer binary or policy digest differs from approved release | Signer remains disabled |
| KEYREC-20 | Restore drill on isolated environment | Full evidence record produced without production signing or secret exposure |

For every case capture exact binary/source identity, public-key fingerprints only, chain/Genesis identity, H/R/S state, anchor sequence/epoch, signer decision, process identity, audit record and whether a signature was emitted. Do not publish private key bytes or recovery shares in test artifacts.

## 9. Current evidence and CI boundary

The inspected source and prior reports establish a synthetic anti-rollback model and disposable remote-signer integration paths. They do not establish production HSM/KMS custody, durable external anchor, signer-boundary fencing, key-compromise recovery, or production dual-control enforcement.

At the start of this audit, CI run `42304791005` was observed on reviewed baseline commit `b9e3683e392d55f6bb44f8a64a41a7656687d7da` and was still in progress. No final result is asserted here. Even a successful existing CI run would not by itself prove KEYREC-01–KEYREC-20 or production key custody.

## 10. Decision

**NOT APPROVED** for:
- production validator consensus-key custody;
- production HSM/KMS signer activation;
- production signer failover or disaster recovery;
- restoration from an unverified anti-double-sign backup;
- reactivation after suspected consensus-key compromise without validator-set governance transition;
- production signing or public-network launch.

The next authorized engineering phase should define the durable independent anchor and signer-boundary authorization contract, choose and document the custody architecture, and then implement the KEYREC tests against the actual CometBFT signer process. Source/test changes require explicit owner approval; this audit made none.

**Change scope:** one documentation file only. No source, tests, workflows, credentials, private keys, signer state, or live validator data changed.
