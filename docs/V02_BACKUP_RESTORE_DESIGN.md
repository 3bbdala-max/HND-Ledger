# HND-Ledger v0.2 backup and restore design

**Status: Partial implementation.** The current working branch implements signed backup creation and verification in `hnd_ledger/backup.py`. Restore remains design-only and is not implemented. The test suite has been added but has not yet been executed on this branch head.

This design applies to the single-host SQLite reference store. It does not introduce distributed consensus or production-node guarantees.

## 1. Security and correctness goals

A backup is acceptable only when all of the following hold:

1. It is a consistent SQLite snapshot, including committed WAL state.
2. Its manifest identifies the exact chain, genesis, tip, database format, and database digest.
3. The database passes SQLite integrity checking and full HND block replay after restoration.
4. The restore matches a trusted checkpoint obtained independently of the backup.
5. The destination is not replaced until all validation has succeeded.
6. Failure at any stage leaves the pre-existing destination untouched.

A hash proves byte integrity relative to a known digest. It does not prove who created the backup. A manifest stored beside a database is not an independent trust anchor.

## 2. Backup creation contract

The implemented narrow API is:

- `create_backup(store, destination, signer)`
- `verify_backup(backup_directory, trusted_public_key=..., expected_chain_id=..., expected_genesis_hash=..., expected_tip_height=..., expected_tip_block_hash=...)`

The functions are exported from `hnd_ledger`. The first restore API is `restore_backup(backup_directory, destination_database, **independent_verification_arguments)`.

### Snapshot procedure

1. Open the source database using the store's normal connection configuration.
2. Run a full replay and capture the verified chain tip: chain ID, genesis hash, tip height, tip block hash, and tip header.
3. Use Python SQLite's online backup API (`Connection.backup()`) to copy the live database to a new temporary destination. Do not copy the main SQLite file and WAL files independently.
4. Close both connections and ensure the snapshot is finalized.
5. Open the snapshot read-only where practical; run `PRAGMA integrity_check`, verify metadata, replay every block, and compare the resulting tip to the captured tip.
6. Compute SHA-256 over the finalized snapshot database bytes.
7. Write a canonical JSON manifest to a temporary file, flush it, and atomically rename it into place.
8. Publish the backup only after both the database and manifest are complete. Keep the pair in a unique backup directory to avoid mismatched files.

The implementation must document platform-specific durability limits for fsync and directory sync. It must never overwrite a previously verified backup in place.

## 3. Manifest format

Proposed format identifier: `HND-SQLITE-BACKUP-MANIFEST-V1`.

Required fields:

- `format`: exact format identifier.
- `store_format`: exact SQLite store format identifier.
- `chain_id_hex`: 32-byte chain ID.
- `genesis_hash_hex`: verified genesis block hash.
- `tip_height`: non-negative integer.
- `tip_block_hash_hex`: verified tip block hash.
- `tip_header_hex`: canonical tip header bytes.
- `database_file`: fixed relative filename, never an arbitrary path.
- `database_size`: exact byte length.
- `database_sha256`: lowercase SHA-256 digest of the finalized database file.
- `created_at_utc`: informational timestamp; not trusted time by itself.
- `signature_algorithm`: explicit algorithm identifier when signed.
- `signer_key_id`: fingerprint of the externally trusted signing key.
- `signature_hex`: signature over the canonical manifest payload with the signature field omitted.

The canonical signing payload must be specified byte-for-byte, including UTF-8 encoding, sorted keys, separators, integer rules, and the exact excluded signature fields. Duplicate JSON keys, unknown critical fields, invalid hex, wrong digest widths, noncanonical serialization, and unexpected filenames must be rejected.

## 4. Authenticity and key custody

- The signing key must not be stored in the backup directory or in the SQLite database.
- The signing key should be held outside the application data directory, ideally by an offline operator-controlled key or hardware-backed signer.
- The verifier must receive the expected public key or key fingerprint through an independent trusted channel.
- Key rotation must be explicit and auditable. A backup must not be allowed to nominate its own trusted public key.
- If no trusted signer is configured, the backup may be labelled integrity-checked but unauthenticated. It must not be described as authenticated.

A signature authenticates the manifest under the trusted key. It does not establish legal ownership of the software or the truth of an untrusted timestamp.

## 5. Anti-rollback checkpoint

The restore caller must supply a trusted checkpoint obtained independently of the backup. It must include at least:

- expected chain ID;
- expected genesis hash;
- minimum acceptable tip height;
- expected tip block hash at that height, or a signed checkpoint policy that permits a later verified descendant.

The checkpoint must not be read solely from the backup manifest, because an attacker can replace both the database and its adjacent manifest with an older pair.

A strict checkpoint requires exact equality of height and hash. A descendant policy requires replay to prove that the restored chain contains the trusted checkpoint as an ancestor. The first implementation should use strict equality; descendant support should be a separately reviewed extension.

## 6. Restore procedure

1. Accept a backup directory and independently supplied trusted public key and checkpoint.
2. Reject path traversal, symlinks where unsupported, unexpected filenames, oversized files, and malformed manifests.
3. Verify canonical manifest encoding and signature before trusting manifest fields.
4. Verify database size and SHA-256.
5. Copy the database into a unique staging directory on the same filesystem as the target.
6. Open the staged database, run SQLite integrity checking, validate exact store metadata and chain ID, and replay all blocks from Genesis.
7. Compare genesis and tip with the signed manifest.
8. Compare the restored chain with the independent trusted checkpoint. Reject rollback.
9. Close every connection and ensure no staging WAL/SHM sidecars remain in an ambiguous state.
10. Atomically replace the target only after validation succeeds. Preserve the previous target until replacement is complete; use a recoverable rename protocol and document filesystem assumptions.
11. Reopen the installed target in a fresh process and repeat integrity, replay, and checkpoint checks before reporting restore success.

Never delete or replace the only valid database before the staged restore has passed all checks.

## 7. Required automated tests

- Online backup includes committed data when the source uses WAL.
- Backup manifest records the exact chain ID, genesis, tip, file size, and digest.
- Database byte corruption is rejected.
- Manifest field tampering is rejected.
- Signature tampering and an untrusted signing key are rejected.
- Wrong chain ID and wrong genesis are rejected.
- Truncated database and invalid SQLite database are rejected.
- A validly signed but older backup is rejected by the independent checkpoint.
- Exact checkpoint succeeds.
- Restore replay catches a block/header/transaction mismatch.
- Path traversal and unexpected backup filenames are rejected.
- Failure before atomic replacement leaves the old target unchanged.
- Process termination during staging leaves the old target usable and staging artifacts identifiable.
- A clean child process can reopen and verify the restored target.
- Backup and restore work with a non-empty WAL and concurrent readers; concurrent writes must be either serialized or explicitly rejected by the API contract.

Tests must use temporary directories and subprocesses where process isolation matters. They must not rely on wall-clock timing or claim to simulate physical power loss unless a real fault-injection harness is used.

## 8. Implemented backup and restore subset

The current implementation exposes:

- `create_backup(store, destination, signer)`: uses SQLite's online backup API, verifies the captured snapshot by integrity check and full replay, finalizes it as a standalone database, and publishes a new directory containing only the database and signed manifest.
- `verify_backup(...)`: checks canonical manifest encoding, duplicate keys, the independently trusted Ed25519 public key, the database size and SHA-256 digest, SQLite integrity, full chain replay, and an independently supplied exact chain/genesis/tip checkpoint.

The destination must not already exist. The manifest signer key is never written into the backup. The caller must preserve the public key and checkpoint independently. The timestamp is informational, not a trusted timestamp. The current verifier deliberately requires an exact tip checkpoint; it does not accept descendants.

The restore API deliberately requires a **new, non-existing destination path**. It verifies the signed backup against an independently supplied public key and exact checkpoint, copies the database to a staging directory on the destination filesystem, replays it, finalizes SQLite WAL state, and publishes the final filename with an atomic hard-link operation that refuses to overwrite an existing path.

This is atomic publication of a new database file, not replacement of a live database. Existing database files and their sidecars are never intentionally overwritten. The implementation does **not** yet implement in-place replacement, crash-recovery orchestration for a multi-file live database, key rotation, a production key-management interface, or cross-platform guarantees on filesystems that do not support hard links. It must not be used as a substitute for an independently stored recovery plan.

## 9. Restore-specific limitations

- Restore is to a new path only; it will reject an existing destination.
- The caller remains responsible for ensuring the target path is not being used by another application and for selecting the correct independent chain checkpoint.
- The trusted public key and checkpoint must be retained outside the backup directory.
- A successful function return means the staged database passed the implemented local checks and was atomically published under a new filename. It does not prove power-loss durability on every filesystem or production disaster-recovery readiness.
- Process-kill and filesystem fault-injection tests remain outstanding.

## 10. Acceptance gates

The feature is not complete until:

- implementation and tests are committed;
- the full suite passes on the exact commit in a clean environment;
- backup and restore are exercised in a separate process;
- corruption, tampering, rollback, and interrupted restore cases pass;
- a reviewer can reproduce the result using documented commands;
- a sample signed backup is verified using a public key distributed independently from the backup.

Until the remaining restore gates pass, the complete backup/restore feature remains incomplete and must not be presented as a disaster-recovery capability.
