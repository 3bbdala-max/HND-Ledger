"""Experimental durable local HREC journal backed by SQLite.

This is local crash-recovery storage, NOT an independent checkpoint authority,
remote anti-rollback anchor, CometBFT integration, signer fence, or production
authorization. A privileged attacker able to replace this database can roll it
back; production requires an independently administered authority.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from hnd_v02.hrec_journal_model import (
    HRECError, HRECJournalModel, Operation, Phase,
)


class SQLiteHRECJournal:
    def __init__(
        self,
        path: str,
        *,
        anchor_height: int = 0,
        anchor_checkpoint: Optional[str] = None,
    ) -> None:
        if not path or path == ":memory:":
            raise HRECError("a filesystem database path is required")
        # Validate the configured trust anchor before creating or modifying files.
        HRECJournalModel(
            anchor_height=anchor_height,
            anchor_checkpoint=anchor_checkpoint,
        )
        self.path = str(Path(path))
        self._db = sqlite3.connect(
            self.path, timeout=30.0, isolation_level=None
        )
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS hrec_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS hrec_operations (
                sequence INTEGER PRIMARY KEY,
                operation_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL,
                phase INTEGER NOT NULL CHECK (phase BETWEEN 1 AND 5)
            )
        """)
        self._initialize_anchor(anchor_height, anchor_checkpoint)
        self._model = self._rebuild_model()

    def _initialize_anchor(self, height: int, checkpoint: Optional[str]) -> None:
        expected = json.dumps(
            {"height": height, "checkpoint": checkpoint},
            sort_keys=True, separators=(",", ":"),
        )
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT value FROM hrec_meta WHERE key='anchor'"
            ).fetchone()
            if row is None:
                self._db.execute(
                    "INSERT INTO hrec_meta(key, value) VALUES('anchor', ?)",
                    (expected,),
                )
            elif row[0] != expected:
                raise HRECError("configured trust anchor differs from persisted anchor")
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    @staticmethod
    def _payload(operation: Operation) -> str:
        return json.dumps({
            "operation_id": operation.operation_id,
            "chain_id": operation.chain_id,
            "height": operation.height,
            "block_hash": operation.block_hash,
            "app_state_hash": operation.app_state_hash,
            "consensus_state_hash": operation.consensus_state_hash,
            "previous_checkpoint": operation.previous_checkpoint,
            "sequence": operation.sequence,
        }, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _decode(payload: str, phase: int) -> Operation:
        try:
            data = json.loads(payload)
            data["phase"] = Phase(phase)
            return Operation(**data)
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise HRECError("corrupt HREC operation row") from exc

    def _rebuild_model(self) -> HRECJournalModel:
        row = self._db.execute(
            "SELECT value FROM hrec_meta WHERE key='anchor'"
        ).fetchone()
        anchor = json.loads(row[0])
        model = HRECJournalModel(
            anchor_height=anchor["height"],
            anchor_checkpoint=anchor["checkpoint"],
        )
        rows = self._db.execute(
            "SELECT sequence, operation_id, payload, phase "
            "FROM hrec_operations ORDER BY sequence"
        ).fetchall()
        for row_sequence, row_operation_id, payload, stored_phase in rows:
            stored = self._decode(payload, stored_phase)
            if (row_sequence != stored.sequence
                    or row_operation_id != stored.operation_id):
                raise HRECError("HREC journal row key does not match its payload")
            model.prepare(self._decode(payload, int(Phase.PREPARED)))
            for phase in range(2, int(stored.phase) + 1):
                model.advance(stored.operation_id, Phase(phase))
        return model

    def prepare(self, operation: Operation) -> Operation:
        operation.validate()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            result = self._model.prepare(operation)
            existing_row = self._db.execute(
                "SELECT payload, phase FROM hrec_operations WHERE operation_id=?",
                (operation.operation_id,),
            ).fetchone()
            if existing_row is not None:
                persisted = self._decode(existing_row[0], existing_row[1])
                if persisted.identity() != operation.identity() or persisted.phase != result.phase:
                    raise HRECError("persisted HREC operation conflicts with in-memory state")
                self._db.execute("COMMIT")
                return result
            inserted = self._db.execute("""
                INSERT INTO hrec_operations
                    (sequence, operation_id, payload, phase)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(operation_id) DO NOTHING
            """, (
                operation.sequence, operation.operation_id,
                self._payload(operation), int(Phase.PREPARED),
            )).rowcount
            if inserted != 1:
                raise HRECError("HREC operation row was not uniquely inserted")
            self._db.execute("COMMIT")
            return result
        except Exception:
            self._db.execute("ROLLBACK")
            self._model = self._rebuild_model()
            raise

    def advance(self, operation_id: str, phase: Phase) -> Operation:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            current = self._model.get(operation_id)
            if current is None:
                raise HRECError("unknown operation")
            updated = self._model.advance(operation_id, phase)
            changed = self._db.execute(
                "UPDATE hrec_operations SET phase=? WHERE operation_id=? AND phase=?",
                (int(updated.phase), operation_id, int(current.phase)),
            ).rowcount
            if changed != 1:
                raise HRECError("HREC phase update did not affect exactly one row")
            self._db.execute("COMMIT")
            return updated
        except Exception:
            self._db.execute("ROLLBACK")
            self._model = self._rebuild_model()
            raise

    def get(self, operation_id: str) -> Optional[Operation]:
        return self._model.get(operation_id)

    @property
    def anchor_height(self) -> int:
        row = self._db.execute(
            "SELECT value FROM hrec_meta WHERE key='anchor'"
        ).fetchone()
        return json.loads(row[0])["height"]

    @property
    def anchor_checkpoint(self) -> Optional[str]:
        row = self._db.execute(
            "SELECT value FROM hrec_meta WHERE key='anchor'"
        ).fetchone()
        return json.loads(row[0])["checkpoint"]

    def latest_operation(self) -> Optional[Operation]:
        row = self._db.execute(
            "SELECT payload, phase FROM hrec_operations ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        return None if row is None else self._decode(row[0], row[1])

    @property
    def latest_sequence(self) -> int:
        return self._model.latest_sequence

    @property
    def latest_checkpoint(self) -> Optional[str]:
        return self._model.latest_checkpoint

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "SQLiteHRECJournal":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
