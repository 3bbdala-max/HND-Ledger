"""SQLite atomic activation reference backend for HND Station 2.

This backend atomically stores the active profile bytes and both monotonic
sequence/digest pairs in one SQLite transaction. It is a single-host reference
only: database/host rollback remains possible, so it is NOT an independent
production trust anchor.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from hnd_v02.activation_transaction import (
    ActivationState, ActivationTransactionError, _validate_state,
)


class SQLiteAtomicActivationBackend:
    """Single-host atomic reference; requires an injected pinned-schema validator.

    The validator must parse the artifact with the reviewed CometBFT v0.40.0
    schema and verify its shared-profile digest. No permissive default exists.
    """

    def __init__(
        self,
        database_path: str | Path,
        *,
        profile_validator: Callable[[bytes, str], bool],
        timeout: float = 5.0,
    ):
        self.path = str(database_path)
        if self.path == ":memory:":
            raise ActivationTransactionError("HND-SQLITE-ACT-E-MEMORY-NOT-DURABLE")
        if not callable(profile_validator):
            raise ActivationTransactionError("HND-SQLITE-ACT-E-VALIDATOR-REQUIRED")
        if type(timeout) not in (int, float) or timeout <= 0:
            raise ActivationTransactionError("HND-SQLITE-ACT-E-TIMEOUT")
        self.timeout = float(timeout)
        self.profile_validator = profile_validator
        self._initialize()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _initialize(self):
        try:
            db = self._connect()
            try:
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("""
                    CREATE TABLE IF NOT EXISTS active_activation (
                        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                        trust_sequence INTEGER NOT NULL,
                        trust_digest TEXT NOT NULL,
                        profile_sequence INTEGER NOT NULL,
                        profile_digest TEXT NOT NULL,
                        activation_height INTEGER NOT NULL,
                        operator_ack_digest TEXT NOT NULL,
                        previous_trust_digest TEXT,
                        previous_profile_digest TEXT,
                        profile_artifact BLOB NOT NULL
                    )
                """)
            finally:
                db.close()
        except sqlite3.Error as exc:
            raise ActivationTransactionError("HND-SQLITE-ACT-E-INITIALIZE") from exc

    @staticmethod
    def _state_from_row(row):
        if row is None:
            return None
        return ActivationState(
            trust_manifest_sequence=row[0],
            trust_manifest_digest=row[1],
            profile_sequence=row[2],
            profile_digest=row[3],
            activation_height=row[4],
            operator_ack_set_sha256=row[5],
            previous_trust_manifest_digest=row[6],
            previous_profile_digest=row[7],
        )

    @staticmethod
    def _state_values(state):
        _validate_state(state)
        return (
            state.trust_manifest_sequence, state.trust_manifest_digest,
            state.profile_sequence, state.profile_digest,
            state.activation_height, state.operator_ack_set_sha256,
            state.previous_trust_manifest_digest, state.previous_profile_digest,
        )

    def read_active_state(self):
        try:
            db = self._connect()
            try:
                row = db.execute("""
                    SELECT trust_sequence, trust_digest, profile_sequence,
                           profile_digest, activation_height, operator_ack_digest,
                           previous_trust_digest, previous_profile_digest
                    FROM active_activation WHERE singleton=1
                """).fetchone()
            finally:
                db.close()
            state = self._state_from_row(row)
            if state is not None:
                _validate_state(state)
            return state
        except (sqlite3.Error, ValueError, TypeError) as exc:
            raise ActivationTransactionError("HND-SQLITE-ACT-E-READ") from exc

    def read_active_profile(self):
        try:
            db = self._connect()
            try:
                row = db.execute(
                    "SELECT profile_artifact FROM active_activation WHERE singleton=1"
                ).fetchone()
            finally:
                db.close()
            return None if row is None else bytes(row[0])
        except sqlite3.Error as exc:
            raise ActivationTransactionError("HND-SQLITE-ACT-E-PROFILE-READ") from exc

    def compare_and_activate(self, expected_current, new_state, profile_artifact):
        values = self._state_values(new_state)
        if expected_current is not None:
            self._state_values(expected_current)
        if type(profile_artifact) is not bytes or not profile_artifact:
            raise ActivationTransactionError("HND-SQLITE-ACT-E-PROFILE")
        try:
            valid = self.profile_validator(profile_artifact, new_state.profile_digest)
        except Exception as exc:
            raise ActivationTransactionError("HND-SQLITE-ACT-E-PROFILE-VALIDATION") from exc
        if valid is not True:
            raise ActivationTransactionError("HND-SQLITE-ACT-E-PROFILE-DIGEST")

        try:
            db = self._connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("""
                    SELECT trust_sequence, trust_digest, profile_sequence,
                           profile_digest, activation_height, operator_ack_digest,
                           previous_trust_digest, previous_profile_digest
                    FROM active_activation WHERE singleton=1
                """).fetchone()
                current = self._state_from_row(row)
                if current != expected_current:
                    db.rollback()
                    return False
                if row is None:
                    db.execute("""
                        INSERT INTO active_activation VALUES(1,?,?,?,?,?,?,?,?,?)
                    """, (*values, sqlite3.Binary(profile_artifact)))
                else:
                    db.execute("""
                        UPDATE active_activation SET
                            trust_sequence=?, trust_digest=?, profile_sequence=?,
                            profile_digest=?, activation_height=?, operator_ack_digest=?,
                            previous_trust_digest=?, previous_profile_digest=?,
                            profile_artifact=? WHERE singleton=1
                    """, (*values, sqlite3.Binary(profile_artifact)))
                db.commit()
                return True
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except sqlite3.Error as exc:
            raise ActivationTransactionError("HND-SQLITE-ACT-E-COMMIT") from exc
