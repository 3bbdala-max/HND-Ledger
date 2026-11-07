# External checkpoint authority contract — HND-Ledger v0.2

Status: implementation contract only. No provider, endpoint, credential, or production authority is configured.

## 1. Security boundary

The authority is a separately administered service in a different rollback and credential domain from every validator's SQLite database, local backups, host filesystem, and CI environment. A process-local object, SQLite table, sidecar file, shared disk, or service account controlled by the validator does not qualify.

The authority stores one monotonic record per (chain_id, genesis_hash). It must remain authoritative across service restarts, host replacement, backup restoration, and disaster recovery. Restoring an older authority snapshot must be prevented by an independently protected monotonic mechanism or by an explicitly documented manual quorum recovery process.

## 2. Record and API semantics

The signed record is the canonical `SignedRollbackCheckpoint` envelope defined by `src/hnd_ledger/rollback_checkpoint.py`. The service stores the exact envelope bytes and indexes the decoded chain ID, genesis hash, sequence, height, and digest. It must reject non-canonical envelopes and invalid signatures before persistence.

A minimal transport-neutral API has these operations:

- **Read(chain_id, genesis_hash):** return the exact latest signed envelope, or an explicit NOT_FOUND. Never return an older cached record as current.
- **Create(expected_absent, candidate):** accept only sequence 1 for an unanchored chain.
- **CompareAndSwap(expected_sequence, expected_digest, candidate):** atomically accept exactly one successor. The candidate sequence must equal current sequence + 1, its chain ID and genesis hash must match, and its height must strictly advance.
- **GetAudit(sequence range):** return append-only acceptance/rejection events sufficient to reconstruct who submitted, what was accepted, and when.

An exact retry of an already accepted candidate after a lost acknowledgement must return idempotent success. A different candidate with a stale expected sequence or digest must return conflict. Unknown outcomes must be resolved by reading the latest record; clients must never guess that a timed-out write failed.

The authority must enforce one record stream per chain/genesis and serialize concurrent writers with a durable transaction or equivalent linearizable compare-and-swap. A plain read followed by an unprotected write is not sufficient.

## 3. Authentication, authorization, and key custody

- Validator-to-authority transport must use authenticated TLS; mutual TLS or an equivalently strong workload identity is required.
- Authorization is scoped to an explicit chain ID and genesis hash. A validator identity cannot create arbitrary chains or change the pinned authority identity.
- Checkpoint signing keys must be held by a dedicated KMS/HSM or separately controlled signing service. Private key bytes must not enter validator configuration, environment dumps, repository contents, SQLite, crash reports, or CI logs.
- Validators pin the authority verification public key or a separately authenticated authority identity. Trust bootstrap must be out-of-band and documented.
- Key rotation requires a versioned transition record signed by the old trusted key and accepted by an explicit validator policy. Unknown, revoked, expired, or silently substituted keys fail closed.
- Audit logs must be append-only and exported to a separately administered retention system.

## 4. Consensus-safe publication policy

A validator must not publish a checkpoint merely because its local ABCI application reports a block committed. The authority must verify consensus commit evidence for the exact chain, height, block ID, and application commitment, or accept a threshold-signed attestation from an explicitly configured validator quorum.

A single validator's unilateral ability to advance a shared chain checkpoint creates a rollback-denial and checkpoint-poisoning risk. The production policy must define:
- finality/commit evidence format and verification;
- validator set identity and key-rotation rules;
- quorum threshold and duplicate/replay handling;
- checkpoint cadence and maximum unanchored interval;
- authority outage behavior and operator alerting.

The service must not accept a height or application hash supplied by an unauthenticated caller as proof of consensus finality.

## 5. Failure and recovery contract

- **Authority unavailable or timeout:** startup and block-write gate remain closed. Do not downgrade to local-only mode.
- **Authority ahead of local DB:** refuse consensus service; restore the checkpointed state or use a separately designed trusted state-sync procedure.
- **Local DB ahead of authority:** classify as LOCAL_AHEAD_UNVERIFIED. Replay and verify the complete suffix from the accepted checkpoint, require an auditable recovery authorization, and only then attempt the next CAS.
- **CAS conflict:** reread and authenticate the current record. If it is the exact candidate, treat as idempotent success; otherwise stop and investigate competing writers.
- **Crash after local SQLite commit but before remote acknowledgement:** remain recovery-required on restart. Never silently lower the remote checkpoint or assume that a local block is externally anchored.
- **Authority data loss:** do not restore an older authority snapshot as if current. Recovery requires an independent audit/backup quorum and a documented re-establishment ceremony.

The gate must be enforced at the CometBFT lifecycle boundary before the node serves consensus, and the block-commit path must not report the chain operational until the configured anchoring policy has been satisfied. A helper that is called once and then returns is not a fencing token: the authority state can change immediately afterward. Production integration therefore needs a lease/fencing epoch or an equivalent serialized commit coordinator, with explicit crash semantics.

## 6. Required provider conformance tests

A production adapter is not accepted until it passes tests against the real independently deployed service, not only an in-memory mock:

1. Persistence across service restart and host replacement.
2. Concurrent CAS from independent clients: exactly one successor wins.
3. Exact retry after accepted-write/lost-acknowledgement.
4. Rejection of stale sequence, stale digest, same-sequence conflict, wrong chain, and wrong genesis.
5. Authentication and authorization failures, including revoked client identity.
6. Signature tampering, non-canonical envelope, wrong signer, key rotation, and revoked key.
7. Network partition, timeout, delayed response, and ambiguous write outcome.
8. Authority restore/backup drill proving an old snapshot cannot silently replace the latest accepted sequence.
9. Independent-operator disaster-recovery exercise with auditable authorization.
10. Consensus evidence verification, including replayed commit evidence and conflicting validator attestations.

## 7. Current implementation boundary

The repository currently contains canonical checkpoint records, Ed25519 signing/verification, a provider-neutral authority protocol, publication and assessment helpers, and in-memory test doubles. These are useful primitives and test scaffolding only. There is no durable authority adapter, production authentication, KMS/HSM integration, consensus-proof verifier, fencing mechanism, or CometBFT startup/commit integration. No production anti-rollback guarantee is claimed.

The next implementation step is to select and provision an independently administered authority and key-custody model. Until that prerequisite exists, implementing a pretend remote service inside the validator repository would weaken rather than improve the stated security boundary.
