# HND v0.2 — WP4.14 ADR: independent anti-rollback trust anchor

**Date:** 2026-11-04  
**Status:** Proposed architecture contract; not vendor-selected or implementation-approved  
**Branch:** `phase-0.2-planning`  
**Decision scope:** Anti-double-sign state integrity, monotonicity, and recovery authorization

## 1. Decision statement

HND must not treat a state-file hash, manifest, sequence number, or expected digest supplied by the ordinary validator host/orchestrator as an independent anti-rollback control.

The production architecture shall require an **external monotonic trust anchor** whose authoritative state cannot be rewritten by an attacker who controls the ordinary signer host, its local files, backups, or caller-supplied parameters. The anchor must authenticate a versioned commitment to the exact anti-double-sign state and its chain/validator context. Missing, stale, inconsistent, or unverifiable anchor data causes fail-closed behavior.

This ADR deliberately defines an interface and threat boundary only. It does not select a vendor, instantiate a TPM/HSM/KMS, generate keys, or enable signing.

## 2. Security objective and attacker model

### Protected properties

1. A validator must never sign from missing, corrupt, substituted, or older-than-authorized anti-double-sign state.
2. A restore must not silently move the signer to an earlier height/round/step.
3. State must be bound to the intended chain, genesis, validator key, signer identity, and schema.
4. A crash during a state/anchor update must produce either a verifiably committed state or a fail-closed recovery condition—not an ambiguous state that can sign.
5. A restore must be authorized independently from routine host administration.

### Attacker capabilities assumed

The attacker may control the ordinary validator host, local filesystem, process environment, backups available to that host, orchestration arguments, and caller-supplied digests. The attacker may replace both a state file and a local manifest/hash file, replay an old backup, interrupt power/processes at update boundaries, or attempt concurrent restores.

The attacker is **not** assumed to control the independently administered trust-anchor security domain or its protected monotonic state. If that domain is compromised, this design's rollback guarantee no longer holds; that is a separate critical incident requiring isolation and governance response.

## 3. Required authenticated record

The anchor must authenticate a canonical, versioned record containing at least:

- protocol/domain identifier and record schema version;
- chain ID, network ID, and genesis hash;
- validator consensus public-key fingerprint and signer identity;
- anti-double-sign state schema/version;
- last signed height, round, and step (or the exact CometBFT state tuple);
- strictly monotonic state sequence / generation;
- cryptographic digest of the canonical state bytes;
- backup/restore transaction identifier and operation identifier;
- previous committed record digest or authenticated predecessor reference;
- status such as PREPARED or COMMITTED.

Canonical serialization, domain separation, digest algorithm, signature/MAC key custody, and version migration rules must be fixed by an independently reviewed implementation specification. A plain hash is not authentication.

The anchor must enforce monotonic progression and reject duplicate operation IDs with conflicting payloads. It must return authenticated state, not merely echo a value supplied by the caller.

## 4. Candidate trust-anchor models

| Model | Strength | Principal limitation / review question |
|---|---|---|
| HSM protected monotonic counter plus authenticated record | Separate hardware custody and monotonic primitive | Does the device atomically bind the counter to the full state commitment? A counter alone does not prove which state was committed. Vendor semantics and failure recovery must be verified. |
| TPM NV counter / protected TPM state | Hardware-backed local monotonic primitive | Local host administrators and platform lifecycle may still control access, reset, replacement, or provisioning. Establish the actual adversary boundary and physical-presence/authorization policy. |
| Remote append-only witness service | Separate administrative/security domain; can retain authenticated history | Availability, consistency, quorum, service compromise, network partition, and recovery from witness loss must be specified. |
| Multi-witness quorum | Reduces dependence on one witness | More complex consensus, quorum availability, operator separation, split-brain, and disaster recovery; not automatically safer without a precise protocol. |

**No model is selected here.** A hardware counter by itself is insufficient unless the full state digest and transaction status are cryptographically and transactionally bound to its monotonic value. A same-host file, environment variable, CI artifact, or orchestrator-provided digest is explicitly rejected as the production trust anchor.

## 5. Transaction and crash-consistency contract

The implementation must define a recoverable two-phase protocol; it must not assume that filesystem operations alone provide universal power-loss durability.

A candidate abstract protocol is:

1. Read and authenticate the latest anchor record. Verify chain, genesis, validator, schema, sequence, and state digest before allowing the signer to initialize.
2. Construct the next canonical state and a unique idempotent operation ID. The proposed record references the current committed predecessor.
3. Persist the candidate state using a platform-reviewed durable-write procedure (temporary file, complete write, file sync, atomic replacement where supported, and directory sync where supported). Record filesystem and storage assumptions explicitly.
4. Ask the independent anchor to accept a PREPARED record binding the next sequence, state digest, predecessor, and operation ID. The anchor rejects stale sequence, wrong predecessor, or conflicting reuse of the operation ID.
5. Complete the commit protocol so the anchor exposes a COMMITTED record only after the candidate state is durably verifiable. The protocol must define the exact ordering, acknowledgement, idempotent retry, and reconciliation rules for crashes between every step.
6. On restart, reconcile local state against the anchor. A PREPARED-but-not-COMMITTED operation must never authorize signing. A COMMITTED anchor with unavailable or mismatched local state requires restore from an authenticated backup or operator intervention; it must not fall back to an older local copy.
7. Open the signer endpoint only after all checks succeed and the committed state is loaded.

The final implementation must prove that no ordering permits a crash to leave a signer able to sign from state older than the anchor. If the chosen anchor cannot support the required transaction semantics, select a different design rather than weakening the guarantee.

Additional mandatory invariants for the reference protocol:

- Use immutable, generation-addressed state objects or an equivalent copy-on-write scheme. Do not overwrite or delete the last known committed generation while a newer generation is PREPARED.
- Keep the prior committed generation available until the new COMMITTED record has been read back and authenticated from the independent anchor and the new state has been re-read and digest-verified.
- The anchor must provide an atomic compare-and-swap or equivalent serialized transition against the expected predecessor. Concurrent PREPARE/COMMIT attempts for the same validator generation must not fork the authoritative history.
- The signer remains disabled throughout PREPARED, ambiguous-acknowledgement, and reconciliation states. A timeout after a COMMIT request is an unknown outcome, not evidence of failure or success; query the anchor by idempotent operation ID and reconcile before proceeding.
- Garbage collection of older generations is a separate privileged operation and may occur only after a verified committed successor and the approved retention/recovery policy permit it.

## 6. Restore and recovery protocol

- Start in an isolated recovery mode with signing and public signer endpoints disabled.
- Obtain the latest authenticated anchor record directly from the independent trust domain.
- Authenticate/decrypt the backup using recovery factors held separately from the backup and ordinary host.
- Verify the manifest, canonical state digest, chain/network/genesis, validator public-key fingerprint, signer identity, schema, and monotonic sequence.
- Reject any backup older than the anchor, any unknown schema, missing factor, ambiguous transaction, or identity mismatch.
- Require two-person approval (or a reviewed threshold) for restore authorization and record approver identities separately.
- Restore only into an isolated target. Reconcile the anchor transaction to a committed state and verify no second live instance can sign for the same validator identity.
- Re-enable test or production signing only after independent verification and explicit approval. Never regenerate missing FilePV/anti-double-sign state as a recovery shortcut.

## 7. Fail-closed rules

The signer must refuse startup and signing if the anchor is unavailable when policy requires it, unauthenticated, stale, rolled back, inconsistent, unknown-version, or unable to resolve a PREPARED transaction. No local digest fallback, cached older anchor fallback, automatic state regeneration, or private-key fallback is permitted.

Availability loss is an operational outage, not permission to weaken anti-double-sign protection.

## 8. Verification vectors

| ID | Fault injection | Required result |
|---|---|---|
| TA01 | Replace state and local expected digest together | Independent anchor detects mismatch / rejects |
| TA02 | Replay older valid backup | Sequence/predecessor check rejects |
| TA03 | Change chain ID, genesis, validator fingerprint, or signer identity | Context binding rejects |
| TA04 | Tamper with anchor record or signature/MAC | Authentication fails; no signer endpoint |
| TA05 | Crash before candidate state durable write | Previous committed state remains authoritative |
| TA06 | Crash after state write but before PREPARED | Unreferenced candidate cannot sign; safe reconciliation |
| TA07 | Crash after PREPARED but before COMMITTED | PREPARED cannot authorize signing; idempotent recovery required |
| TA08 | Crash after COMMITTED but local state missing/corrupt | Restore exact committed state or remain offline |
| TA09 | Retry same operation ID with same payload | Idempotent result |
| TA10 | Reuse operation ID with different payload / stale predecessor | Anchor rejects |
| TA11 | Anchor outage, timeout, or quorum loss | Fail closed; no local fallback |
| TA12 | Two hosts attempt concurrent restore for one validator | Single authorized generation; second instance denied |
| TA13 | Unknown schema or unsupported migration | Fail closed pending reviewed migration |
| TA14 | Operator attempts restore without second approval | Denied and audited |

Tests must use synthetic state and disposable test identities only. Test results must identify which properties are simulated and which are actually guaranteed by the anchor implementation.

## 9. Audit and operational requirements

Record anchor reads, prepare/commit/abort/reconcile operations, sequence transitions, rejected rollback attempts, restore approvals, signer enable/disable events, identity mismatches, and administrative changes. Events must be timestamped, tamper-evident, access-controlled, and exported to a separate security domain. Never log private keys, recovery shares, passwords, API tokens, or plaintext backup contents.

Define anchor outage procedures, RTO/RPO, quorum-loss response, witness replacement, hardware replacement, secure provisioning, decommissioning, and incident escalation before production approval.

## 10. Decision status and next gates

- **Accepted as a design requirement:** the trust anchor must be independent of the ordinary signer host and must bind monotonic sequence to the authenticated full-state commitment.
- **Rejected:** caller-supplied digest or same-host hash/manifest as the production anti-rollback authority.
- **Deferred:** HSM vs TPM vs remote witness vs quorum selection; exact commit protocol; vendor and algorithm selection.
- **Next gate:** independent security review of attacker model and transaction semantics, followed by a synthetic-only reference model. No hardware adapter or production key operation before approval.
- This ADR does not close WP4.14, authorize production signing, or change G2–G4. No public release or real-value activity is approved.
