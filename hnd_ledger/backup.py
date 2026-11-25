"""Signed, integrity-checked backups for the single-host SQLite reference store.

The signature authenticates the manifest only when the caller supplies a public
key obtained independently. Rollback protection requires an independent exact
checkpoint supplied to verify_backup().
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .storage import STORE_FORMAT, SQLiteChainStore, StorageError, _parse_state

MANIFEST_FORMAT = "HND-SQLITE-BACKUP-MANIFEST-V1"
DATABASE_FILENAME = "database.sqlite3"
MANIFEST_FILENAME = "manifest.json"
MAX_MANIFEST_BYTES = 65_536
MAX_BACKUP_DATABASE_BYTES = 4 * 1024 * 1024 * 1024


class BackupError(ValueError):
    """A backup cannot be created or verified safely."""


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def _public_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    # Directory fsync is supported on common POSIX filesystems. Some platforms
    # do not permit opening directories; the backup remains valid but durability
    # of the rename is then subject to the platform's filesystem guarantees.
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def create_backup(
    store: SQLiteChainStore,
    destination: str | os.PathLike[str],
    signer: Ed25519PrivateKey,
) -> dict[str, Any]:
    """Create a new, never-overwritten signed backup directory.

    The SQLite online backup API captures a consistent committed snapshot,
    including committed WAL content. The destination must not already exist.
    """
    if not isinstance(store, SQLiteChainStore):
        raise BackupError("store must be a SQLiteChainStore")
    if not isinstance(signer, Ed25519PrivateKey):
        raise BackupError("signer must be an Ed25519 private key")

    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise BackupError("backup destination already exists")
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    if not parent.is_dir():
        raise BackupError("backup parent must be a directory")

    staging = Path(tempfile.mkdtemp(prefix=".hnd-backup-", dir=parent))
    source = None
    snapshot = None
    try:
        source = store._connect()
        snapshot_path = staging / DATABASE_FILENAME
        snapshot = sqlite3.connect(snapshot_path)
        source.backup(snapshot)
        snapshot.close()
        snapshot = None
        source.close()
        source = None

        # Verify the exact snapshot, not the live source database.
        snapshot_store = SQLiteChainStore(
            snapshot_path, store.chain_id, store._genesis_balances
        )
        if not snapshot_store.verify():
            raise BackupError("SQLite snapshot failed integrity or chain replay")
        tip = snapshot_store.get_tip()

        # Consolidate any validation-created WAL into the main database file.
        connection = sqlite3.connect(snapshot_path)
        try:
            checkpoint = connection.execute(
                "PRAGMA wal_checkpoint(TRUNCATE)"
            ).fetchone()
            if checkpoint and checkpoint[0] != 0:
                raise BackupError("could not checkpoint snapshot WAL")
            mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()
            if not mode or str(mode[0]).lower() != "delete":
                raise BackupError("could not finalize standalone snapshot database")
        finally:
            connection.close()

        wal_path = Path(str(snapshot_path) + "-wal")
        shm_path = Path(str(snapshot_path) + "-shm")
        if wal_path.exists() and wal_path.stat().st_size:
            raise BackupError("snapshot WAL remains after finalization")
        if shm_path.exists() and shm_path.stat().st_size:
            raise BackupError("snapshot SHM remains after finalization")
        wal_path.unlink(missing_ok=True)
        shm_path.unlink(missing_ok=True)

        database_size = snapshot_path.stat().st_size
        if database_size <= 0 or database_size > MAX_BACKUP_DATABASE_BYTES:
            raise BackupError("snapshot database size is outside permitted limits")
        _fsync_file(snapshot_path)
        database_digest = _sha256_file(snapshot_path)
        public_key = _public_bytes(signer)
        unsigned = {
            "format": MANIFEST_FORMAT,
            "store_format": STORE_FORMAT.decode("ascii"),
            "chain_id_hex": store.chain_id.hex(),
            "genesis_hash_hex": store._genesis_hash.hex(),
            "tip_height": tip["height"],
            "tip_block_hash_hex": tip["block_hash"].hex(),
            "tip_header_hex": tip["header"].hex(),
            "database_file": DATABASE_FILENAME,
            "database_size": database_size,
            "database_sha256": database_digest,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "signature_algorithm": "Ed25519",
            "signer_key_id": hashlib.sha256(public_key).hexdigest(),
        }
        manifest = dict(unsigned)
        manifest["signature_hex"] = signer.sign(_canonical_json(unsigned)).hex()
        manifest_path = staging / MANIFEST_FILENAME
        with manifest_path.open("xb") as stream:
            stream.write(_canonical_json(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(staging)

        # A same-filesystem directory rename publishes the completed pair at once.
        if target.exists() or target.is_symlink():
            raise BackupError("backup destination appeared during creation")
        os.rename(staging, target)
        _fsync_directory(parent)
        return manifest
    except BackupError:
        raise
    except (OSError, sqlite3.Error, StorageError, ValueError, TypeError) as exc:
        raise BackupError("backup creation failed; destination was not published") from exc
    finally:
        if snapshot is not None:
            snapshot.close()
        if source is not None:
            source.close()
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("manifest contains duplicate JSON keys")
        result[key] = value
    return result


def verify_backup(
    backup_directory: str | os.PathLike[str],
    *,
    trusted_public_key: bytes,
    expected_chain_id: bytes,
    expected_genesis_hash: bytes,
    expected_tip_height: int,
    expected_tip_block_hash: bytes,
) -> dict[str, Any]:
    """Verify signature, bytes, replay, and an independently supplied exact checkpoint.

    The expected checkpoint and public key must come from outside the backup
    directory. This first version intentionally rejects descendant checkpoints.
    """
    directory = Path(backup_directory)
    if directory.is_symlink() or not directory.is_dir():
        raise BackupError("backup path must be a real directory, not a symlink")
    if not isinstance(trusted_public_key, bytes) or len(trusted_public_key) != 32:
        raise BackupError("trusted Ed25519 public key must be exactly 32 bytes")
    if not isinstance(expected_chain_id, bytes) or len(expected_chain_id) != 32:
        raise BackupError("expected chain ID must be exactly 32 bytes")
    if not isinstance(expected_genesis_hash, bytes) or len(expected_genesis_hash) != 32:
        raise BackupError("expected genesis hash must be exactly 32 bytes")
    if not isinstance(expected_tip_block_hash, bytes) or len(expected_tip_block_hash) != 32:
        raise BackupError("expected tip hash must be exactly 32 bytes")
    if isinstance(expected_tip_height, bool) or not isinstance(expected_tip_height, int) or expected_tip_height < 0:
        raise BackupError("expected tip height must be a non-negative integer")

    try:
        entries = {item.name for item in directory.iterdir()}
        if entries != {DATABASE_FILENAME, MANIFEST_FILENAME}:
            raise BackupError("backup directory contains missing or unexpected files")
        manifest_path = directory / MANIFEST_FILENAME
        database_path = directory / DATABASE_FILENAME
        if manifest_path.is_symlink() or database_path.is_symlink():
            raise BackupError("backup files must not be symlinks")
        if not manifest_path.is_file() or not database_path.is_file():
            raise BackupError("backup files must be regular files")
        manifest_bytes = manifest_path.read_bytes()
        if not manifest_bytes or len(manifest_bytes) > MAX_MANIFEST_BYTES:
            raise BackupError("manifest size is outside permitted limits")
        manifest = json.loads(
            manifest_bytes.decode("ascii"), object_pairs_hook=_reject_duplicate_keys
        )
        if not isinstance(manifest, dict):
            raise BackupError("manifest root must be a JSON object")
        required = {
            "format", "store_format", "chain_id_hex", "genesis_hash_hex",
            "tip_height", "tip_block_hash_hex", "tip_header_hex",
            "database_file", "database_size", "database_sha256",
            "created_at_utc", "signature_algorithm", "signer_key_id",
            "signature_hex",
        }
        if set(manifest) != required:
            raise BackupError("manifest fields do not match the required format")
        if _canonical_json(manifest) != manifest_bytes:
            raise BackupError("manifest is not canonically encoded")
        if manifest["format"] != MANIFEST_FORMAT:
            raise BackupError("unsupported backup manifest format")
        if manifest["store_format"] != STORE_FORMAT.decode("ascii"):
            raise BackupError("unsupported SQLite store format")
        if manifest["database_file"] != DATABASE_FILENAME:
            raise BackupError("unexpected database filename")
        if manifest["signature_algorithm"] != "Ed25519":
            raise BackupError("unsupported manifest signature algorithm")
        for field in ("chain_id_hex", "genesis_hash_hex", "tip_block_hash_hex"):
            value = manifest[field]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or value != value.lower()
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise BackupError(f"manifest {field} must be 32-byte lowercase hex")
        if (
            isinstance(manifest["tip_height"], bool)
            or not isinstance(manifest["tip_height"], int)
            or manifest["tip_height"] < 0
        ):
            raise BackupError("manifest tip height must be a non-negative integer")
        if (
            not isinstance(manifest["tip_header_hex"], str)
            or len(manifest["tip_header_hex"]) % 2
            or manifest["tip_header_hex"] != manifest["tip_header_hex"].lower()
        ):
            raise BackupError("manifest tip header must be lowercase hex")
        try:
            bytes.fromhex(manifest["tip_header_hex"])
        except ValueError as exc:
            raise BackupError("manifest tip header is not valid hex") from exc
        if (
            not isinstance(manifest["database_sha256"], str)
            or len(manifest["database_sha256"]) != 64
            or manifest["database_sha256"] != manifest["database_sha256"].lower()
            or any(character not in "0123456789abcdef" for character in manifest["database_sha256"])
        ):
            raise BackupError("manifest database digest must be lowercase SHA-256 hex")
        if not isinstance(manifest["created_at_utc"], str):
            raise BackupError("manifest creation timestamp must be text")
        if manifest["signer_key_id"] != hashlib.sha256(trusted_public_key).hexdigest():
            raise BackupError("backup signer does not match the independently trusted key")

        signature_hex = manifest["signature_hex"]
        if (
            not isinstance(signature_hex, str)
            or len(signature_hex) != 128
            or signature_hex != signature_hex.lower()
            or any(character not in "0123456789abcdef" for character in signature_hex)
        ):
            raise BackupError("manifest signature has invalid encoding")
        unsigned = dict(manifest)
        del unsigned["signature_hex"]
        try:
            Ed25519PublicKey.from_public_bytes(trusted_public_key).verify(
                bytes.fromhex(signature_hex), _canonical_json(unsigned)
            )
        except (ValueError, TypeError, InvalidSignature) as exc:
            # InvalidSignature is deliberately normalized to one public error.
            raise BackupError("manifest signature verification failed") from exc

        size = database_path.stat().st_size
        if (
            isinstance(manifest["database_size"], bool)
            or not isinstance(manifest["database_size"], int)
            or manifest["database_size"] != size
            or size <= 0
            or size > MAX_BACKUP_DATABASE_BYTES
        ):
            raise BackupError("database size does not match the signed manifest")
        digest = _sha256_file(database_path)
        if not isinstance(manifest["database_sha256"], str) or digest != manifest["database_sha256"]:
            raise BackupError("database digest does not match the signed manifest")

        if manifest["chain_id_hex"] != expected_chain_id.hex():
            raise BackupError("backup chain ID differs from independent checkpoint")
        if manifest["genesis_hash_hex"] != expected_genesis_hash.hex():
            raise BackupError("backup genesis differs from independent checkpoint")
        if manifest["tip_height"] != expected_tip_height:
            raise BackupError("backup tip height differs from independent checkpoint")
        if manifest["tip_block_hash_hex"] != expected_tip_block_hash.hex():
            raise BackupError("backup tip hash differs from independent checkpoint")

        # Validate a disposable copy so verification never mutates the supplied backup.
        with tempfile.TemporaryDirectory(prefix="hnd-backup-verify-") as temporary:
            staged = Path(temporary) / DATABASE_FILENAME
            shutil.copyfile(database_path, staged)
            connection = sqlite3.connect(staged)
            try:
                rows = dict(connection.execute("SELECT key, value FROM metadata"))
            finally:
                connection.close()
            if rows.get("chain_id") != expected_chain_id:
                raise BackupError("database metadata chain ID mismatch")
            if rows.get("genesis_hash") != expected_genesis_hash:
                raise BackupError("database metadata genesis hash mismatch")
            balances, _ = _parse_state(rows["genesis_state"])
            store = SQLiteChainStore(staged, expected_chain_id, balances)
            if not store.verify():
                raise BackupError("database failed SQLite integrity or full chain replay")
            tip = store.get_tip()
            if (
                tip["height"] != expected_tip_height
                or tip["block_hash"] != expected_tip_block_hash
                or tip["header"].hex() != manifest["tip_header_hex"]
            ):
                raise BackupError("database replay tip differs from signed manifest/checkpoint")
        return manifest
    except BackupError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, sqlite3.Error, KeyError, TypeError, ValueError, StorageError) as exc:
        raise BackupError("backup verification failed") from exc



def restore_backup(
    backup_directory: str | os.PathLike[str],
    destination_database: str | os.PathLike[str],
    *,
    trusted_public_key: bytes,
    expected_chain_id: bytes,
    expected_genesis_hash: bytes,
    expected_tip_height: int,
    expected_tip_block_hash: bytes,
) -> dict[str, Any]:
    """Restore a verified backup to a new database path without overwriting data.

    The destination must not exist. Validation and SQLite replay happen in a
    temporary directory on the destination filesystem. A hard-link publication
    makes the final name appear atomically and fails if another process created
    the destination first. Existing databases and their WAL files are untouched.
    """
    manifest = verify_backup(
        backup_directory,
        trusted_public_key=trusted_public_key,
        expected_chain_id=expected_chain_id,
        expected_genesis_hash=expected_genesis_hash,
        expected_tip_height=expected_tip_height,
        expected_tip_block_hash=expected_tip_block_hash,
    )

    target = Path(destination_database)
    if target.name in ("", ".", ".."):
        raise BackupError("destination must name a database file")
    if target.exists() or target.is_symlink():
        raise BackupError("restore destination already exists; refusing to overwrite")
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    if not parent.is_dir():
        raise BackupError("restore parent must be a directory")

    staging_directory = Path(tempfile.mkdtemp(prefix=".hnd-restore-", dir=parent))
    staged_database = staging_directory / DATABASE_FILENAME
    try:
        source_database = Path(backup_directory) / DATABASE_FILENAME
        shutil.copyfile(source_database, staged_database)

        connection = sqlite3.connect(staged_database)
        try:
            rows = dict(connection.execute("SELECT key, value FROM metadata"))
        finally:
            connection.close()
        if rows.get("chain_id") != expected_chain_id:
            raise BackupError("staged database chain ID differs from checkpoint")
        if rows.get("genesis_hash") != expected_genesis_hash:
            raise BackupError("staged database genesis differs from checkpoint")
        balances, _ = _parse_state(rows["genesis_state"])

        restored_store = SQLiteChainStore(
            staged_database, expected_chain_id, balances
        )
        if not restored_store.verify():
            raise BackupError("staged restore failed SQLite integrity or chain replay")
        tip = restored_store.get_tip()
        if (
            tip["height"] != expected_tip_height
            or tip["block_hash"] != expected_tip_block_hash
        ):
            raise BackupError("staged restore tip differs from independent checkpoint")

        # Every store operation closes its own connection. Consolidate WAL and
        # switch to DELETE mode before publishing a single standalone file.
        connection = sqlite3.connect(staged_database)
        try:
            checkpoint = connection.execute(
                "PRAGMA wal_checkpoint(TRUNCATE)"
            ).fetchone()
            if checkpoint and checkpoint[0] != 0:
                raise BackupError("could not checkpoint staged restore WAL")
            mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()
            if not mode or str(mode[0]).lower() != "delete":
                raise BackupError("could not finalize staged restore database")
        finally:
            connection.close()

        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(staged_database) + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                raise BackupError("staged restore has a non-empty SQLite sidecar")
            sidecar.unlink(missing_ok=True)

        _fsync_file(staged_database)
        # os.link is atomic and, unlike os.replace, never overwrites an existing
        # destination. Staging is on the same filesystem as the final path.
        os.link(staged_database, target)
        _fsync_directory(parent)
        return manifest
    except BackupError:
        raise
    except FileExistsError as exc:
        raise BackupError("restore destination appeared during restore; nothing overwritten") from exc
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError, StorageError) as exc:
        raise BackupError("restore failed before publication; destination was not replaced") from exc
    finally:
        if staging_directory.exists():
            shutil.rmtree(staging_directory, ignore_errors=True)
