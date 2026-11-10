"""SQLite-backed durable reference adapter for HND monotonic state.

This adapter demonstrates process-restart durability and atomic compare-and-advance
on one host. It is NOT an independent trust domain: an attacker able to restore,
replace, or rewrite the database/host can roll it back. Production deployments
must use a separately administered hardware-backed or remote quorum anchor.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from hnd_v02.monotonic_anchor import (
    MonotonicRecord, MonotonicAnchorError, MonotonicAnchorConflict,
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_ALLOWED = frozenset({"trust-manifest", "vsp-profile"})


class SQLiteMonotonicAnchor:
    """Single-host durable adapter; SQLite FULL synchronous transactions.

    Each operation opens its own connection. BEGIN IMMEDIATE serializes writers;
    compare_and_advance commits one namespace update atomically. Database backup
    rollback remains possible, so this class must not be used as the sole
    production anti-rollback trust anchor.
    """

    def __init__(self, database_path: str | Path, *, timeout: float = 5.0):
        self.path = str(database_path)
        if self.path == ":memory:":
            raise MonotonicAnchorError("HND-SQLITE-ANCHOR-E-MEMORY-NOT-DURABLE")
        if type(timeout) not in (int, float) or timeout <= 0:
            raise MonotonicAnchorError("HND-SQLITE-ANCHOR-E-TIMEOUT")
        self.timeout = float(timeout)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(
            self.path, timeout=self.timeout, isolation_level=None
        )
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self):
        try:
            with self._connect() as db:
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("""
                    CREATE TABLE IF NOT EXISTS monotonic_state (
                        namespace TEXT PRIMARY KEY,
                        sequence INTEGER NOT NULL CHECK(sequence >= 0),
                        digest TEXT NOT NULL CHECK(length(digest) = 64)
                    ) WITHOUT ROWID
                """)
        except sqlite3.Error as exc:
            raise MonotonicAnchorError("HND-SQLITE-ANCHOR-E-INITIALIZE") from exc

    @staticmethod
    def _validate(namespace, record):
        if type(namespace) is not str or namespace not in _ALLOWED:
            raise MonotonicAnchorError("HND-SQLITE-ANCHOR-E-NAMESPACE")
        if type(record) is not MonotonicRecord:
            raise MonotonicAnchorError("HND-SQLITE-ANCHOR-E-RECORD")
        if type(record.sequence) is not int or not 0 <= record.sequence <= (1 << 53) - 1:
            raise MonotonicAnchorError("HND-SQLITE-ANCHOR-E-SEQUENCE")
        if type(record.digest) is not str or not _HEX64.fullmatch(record.digest):
            raise MonotonicAnchorError("HND-SQLITE-ANCHOR-E-DIGEST")

    def read_state(self, namespace: str) -> MonotonicRecord | None:
        if type(namespace) is not str or namespace not in _ALLOWED:
            raise MonotonicAnchorError("HND-SQLITE-ANCHOR-E-NAMESPACE")
        try:
            with self._connect() as db:
                row = db.execute(
                    "SELECT sequence, digest FROM monotonic_state WHERE namespace=?",
                    (namespace,),
                ).fetchone()
            return None if row is None else MonotonicRecord(row[0], row[1])
        except sqlite3.Error as exc:
            raise MonotonicAnchorError("HND-SQLITE-ANCHOR-E-READ") from exc

    def compare_and_advance(self, namespace, expected_current, new_record):
        self._validate(namespace, new_record)
        if expected_current is not None:
            self._validate(namespace, expected_current)
        try:
            db = self._connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT sequence, digest FROM monotonic_state WHERE namespace=?",
                    (namespace,),
                ).fetchone()
                current = None if row is None else MonotonicRecord(row[0], row[1])
                if current != expected_current:
                    db.rollback()
                    return False
                if current is None:
                    db.execute(
                        "INSERT INTO monotonic_state(namespace, sequence, digest) VALUES(?,?,?)",
                        (namespace, new_record.sequence, new_record.digest),
                    )
                else:
                    changed = db.execute(
                        """UPDATE monotonic_state SET sequence=?, digest=?
                           WHERE namespace=? AND sequence=? AND digest=?""",
                        (new_record.sequence, new_record.digest, namespace,
                         current.sequence, current.digest),
                    ).rowcount
                    if changed != 1:
                        db.rollback()
                        return False
                db.commit()
                return True
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except sqlite3.Error as exc:
            raise MonotonicAnchorError("HND-SQLITE-ANCHOR-E-COMMIT") from exc
