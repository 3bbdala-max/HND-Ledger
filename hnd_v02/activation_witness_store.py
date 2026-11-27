"""Single-host reference store for the Station 2 witness ACK protocol.

This is a test/development reference only. SQLite on one host is NOT an
independent witness failure domain and does not establish production quorum,
anti-rollback recovery, or operational independence.
"""
from __future__ import annotations

import base64
from contextlib import closing
import json
import re
import sqlite3
from typing import Any

from hnd_v02.activation_witness_interface import (
    ActivationWitnessStoreError, WitnessBackendCapabilities,
)

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_SCHEMA = "hnd.station2.witness-ack.v1"
_DOMAIN = b"HND-STATION2-WITNESS-ACK-V1\x00"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)
_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_MAX_INTEGER = (1 << 53) - 1


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("ascii")


class SQLiteActivationWitnessStore:
    """Durable same-host ACK reference with immutable IDs and monotonic counter.

    A repeated activation ID and digest returns the exact original receipt.
    Reusing an ID for a different digest is a hard conflict. Counter allocation
    and receipt persistence occur in one SQLite write transaction.
    """

    def __init__(
        self, database: str, *, witness_id: str, config_epoch: int,
        signing_key: Ed25519PrivateKey,
    ):
        if type(database) is not str or not database:
            raise ActivationWitnessStoreError("HND-WITNESS-STORE-E-DATABASE")
        if type(witness_id) is not str or not _ID.fullmatch(witness_id):
            raise ActivationWitnessStoreError("HND-WITNESS-STORE-E-ID")
        if type(config_epoch) is not int or not 1 <= config_epoch <= _MAX_INTEGER:
            raise ActivationWitnessStoreError("HND-WITNESS-STORE-E-EPOCH")
        if not isinstance(signing_key, Ed25519PrivateKey):
            raise ActivationWitnessStoreError("HND-WITNESS-STORE-E-KEY")
        self.database = database
        self.witness_id = witness_id
        self.config_epoch = config_epoch
        self.signing_key = signing_key
        try:
            with closing(sqlite3.connect(self.database, timeout=10)) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("""
                    CREATE TABLE IF NOT EXISTS witness_counter (
                        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                        counter INTEGER NOT NULL CHECK(counter >= 0)
                    )
                """)
                db.execute("""
                    INSERT OR IGNORE INTO witness_counter(singleton, counter)
                    VALUES (1, 0)
                """)
                db.execute("""
                    CREATE TABLE IF NOT EXISTS witness_receipts (
                        activation_id TEXT PRIMARY KEY,
                        activation_digest TEXT NOT NULL,
                        config_epoch INTEGER NOT NULL,
                        counter INTEGER NOT NULL UNIQUE,
                        receipt_json BLOB NOT NULL
                    )
                """)
                db.execute("""
                    CREATE TABLE IF NOT EXISTS witness_pending (
                        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                        activation_id TEXT NOT NULL UNIQUE,
                        activation_digest TEXT NOT NULL,
                        receipt_json BLOB NOT NULL
                    )
                """)
                # Never infer terminal state for receipts created before this lock existed.
                pending = db.execute(
                    "SELECT activation_id FROM witness_pending WHERE singleton = 1"
                ).fetchone()
                receipts = db.execute(
                    "SELECT COUNT(*) FROM witness_receipts"
                ).fetchone()[0]
                if pending is None and receipts:
                    raise ActivationWitnessStoreError(
                        "HND-WITNESS-STORE-E-LEGACY-STATE-UNRESOLVED"
                    )
                db.commit()
        except sqlite3.Error as exc:
            raise ActivationWitnessStoreError("HND-WITNESS-STORE-E-INIT") from exc

    @property
    def capabilities(self) -> WitnessBackendCapabilities:
        """SQLite is deliberately never admissible as a production witness."""
        return {
            "backend": "sqlite-reference",
            "production_capable": False,
            "quorum_ready": False,
            "anti_rollback_verified": False,
            "protected_key_custody": False,
        }

    def acknowledge(self, activation_id: str, activation_digest: str) -> dict[str, Any]:
        if type(activation_id) is not str or not _ID.fullmatch(activation_id):
            raise ActivationWitnessStoreError("HND-WITNESS-STORE-E-ACTIVATION-ID")
        if type(activation_digest) is not str or not _HEX64.fullmatch(activation_digest):
            raise ActivationWitnessStoreError("HND-WITNESS-STORE-E-DIGEST")
        db = None
        try:
            with closing(sqlite3.connect(self.database, timeout=10, isolation_level=None)) as db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                pending = db.execute(
                    """SELECT activation_id, activation_digest, receipt_json
                       FROM witness_pending WHERE singleton = 1"""
                ).fetchone()
                if pending is not None:
                    if pending[0] != activation_id:
                        raise ActivationWitnessStoreError(
                            "HND-WITNESS-STORE-E-PENDING-CONFLICT"
                        )
                    if pending[1] != activation_digest:
                        raise ActivationWitnessStoreError(
                            "HND-WITNESS-STORE-E-ID-CONFLICT"
                        )
                    receipt = json.loads(bytes(pending[2]).decode("ascii"))
                    if (type(receipt) is not dict
                            or receipt.get("witness_id") != self.witness_id
                            or receipt.get("config_epoch") != self.config_epoch):
                        raise ActivationWitnessStoreError(
                            "HND-WITNESS-STORE-E-ID-CONFLICT"
                        )
                    db.execute("COMMIT")
                    return receipt

                row = db.execute(
                    """SELECT activation_digest, config_epoch, counter, receipt_json
                       FROM witness_receipts WHERE activation_id = ?""",
                    (activation_id,),
                ).fetchone()
                if row is not None:
                    if row[0] != activation_digest or row[1] != self.config_epoch:
                        raise ActivationWitnessStoreError("HND-WITNESS-STORE-E-ID-CONFLICT")
                    raise ActivationWitnessStoreError(
                        "HND-WITNESS-STORE-E-TERMINAL-EVIDENCE-MISSING"
                    )

                current = db.execute(
                    "SELECT counter FROM witness_counter WHERE singleton = 1"
                ).fetchone()
                if current is None or type(current[0]) is not int or current[0] >= _MAX_INTEGER:
                    raise ActivationWitnessStoreError("HND-WITNESS-STORE-E-COUNTER")
                counter = current[0] + 1
                signed = {
                    "schema": _SCHEMA,
                    "activation_id": activation_id,
                    "activation_digest": activation_digest,
                    "witness_id": self.witness_id,
                    "config_epoch": self.config_epoch,
                    "counter": counter,
                }
                signature = self.signing_key.sign(_DOMAIN + _canonical(signed))
                receipt = {
                    **signed,
                    "signature": base64.b64encode(signature).decode("ascii"),
                }
                encoded = _canonical(receipt)
                db.execute(
                    "UPDATE witness_counter SET counter = ? WHERE singleton = 1",
                    (counter,),
                )
                db.execute(
                    """INSERT INTO witness_receipts
                       (activation_id, activation_digest, config_epoch, counter, receipt_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (activation_id, activation_digest, self.config_epoch, counter, encoded),
                )
                db.execute(
                    """INSERT INTO witness_pending
                       (singleton, activation_id, activation_digest, receipt_json)
                       VALUES (1, ?, ?, ?)""",
                    (activation_id, activation_digest, encoded),
                )
                db.execute("COMMIT")
                return receipt
        except ActivationWitnessStoreError:
            try:
                if db is not None and db.in_transaction:
                    db.execute("ROLLBACK")
            except Exception:
                pass
            raise
        except (sqlite3.Error, ValueError, UnicodeError) as exc:
            try:
                if db is not None and db.in_transaction:
                    db.execute("ROLLBACK")
            except Exception:
                pass
            raise ActivationWitnessStoreError("HND-WITNESS-STORE-E-WRITE") from exc
