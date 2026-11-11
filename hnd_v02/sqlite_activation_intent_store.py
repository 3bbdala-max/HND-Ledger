"""Single-host durable reference store for remote activation intents.

This is a SQLite service-side state machine, not an HTTPS server or an
independent anti-rollback trust domain. Production requires a separately
administered linearizable service and authenticated mTLS deployment.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from hnd_v02.remote_activation_intent import (
    RemoteActivationProtocolError, _record, _validate_id,
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_MAX_SEQUENCE = (1 << 53) - 1
_TOP_KEYS = {
    "activation_id", "predecessors", "successors",
    "profile_digest", "operator_ack_digest",
}


class SQLiteActivationIntentStore:
    """Durable, idempotent prepare/read/finalize state machine on one host."""

    def __init__(self, database_path: str | Path, *, timeout: float = 5.0):
        self.path = str(database_path)
        if self.path == ":memory:":
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-NOT-DURABLE")
        if type(timeout) not in (int, float) or timeout <= 0 or timeout > 60:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-TIMEOUT")
        self.timeout = float(timeout)
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
                    CREATE TABLE IF NOT EXISTS activation_intents (
                        activation_id TEXT PRIMARY KEY,
                        state TEXT NOT NULL CHECK(state IN ('prepared','finalized')),
                        request_json TEXT NOT NULL,
                        intent_json TEXT NOT NULL
                    ) WITHOUT ROWID
                """)
            finally:
                db.close()
        except sqlite3.Error as exc:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-INITIALIZE") from exc

    @staticmethod
    def _validate_request(request: Mapping[str, Any]) -> dict:
        if type(request) is not dict or set(request) != _TOP_KEYS:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-REQUEST-SHAPE")
        activation_id = _validate_id(request["activation_id"])
        predecessors, successors = request["predecessors"], request["successors"]
        if type(predecessors) is not dict or set(predecessors) != {"trust_manifest", "vsp_profile"}:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-PREDECESSORS")
        if type(successors) is not dict or set(successors) != {"trust_manifest", "vsp_profile"}:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-SUCCESSORS")
        pred = {k: _record(v, nullable=True) for k, v in predecessors.items()}
        succ = {k: _record(v) for k, v in successors.items()}
        for name, bootstrap in (("trust_manifest", 0), ("vsp_profile", 1)):
            old, new = pred[name], succ[name]
            expected = bootstrap if old is None else old["sequence"] + 1
            if expected > _MAX_SEQUENCE or new["sequence"] != expected:
                raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-SEQUENCE")
        for key in ("profile_digest", "operator_ack_digest"):
            value = request[key]
            if type(value) is not str or not _HEX64.fullmatch(value):
                raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-DIGEST")
        return {
            "activation_id": activation_id,
            "predecessors": pred,
            "successors": succ,
            "profile_digest": request["profile_digest"],
            "operator_ack_digest": request["operator_ack_digest"],
        }

    @staticmethod
    def _json(value):
        return json.dumps(value, ensure_ascii=True, allow_nan=False,
                          sort_keys=True, separators=(",", ":"))

    def prepare(self, request: Mapping[str, Any]) -> dict:
        request = self._validate_request(request)
        activation_id = request["activation_id"]
        intent = dict(request, state="prepared")
        encoded_request, encoded_intent = self._json(request), self._json(intent)
        try:
            db = self._connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT request_json, intent_json FROM activation_intents WHERE activation_id=?",
                    (activation_id,),
                ).fetchone()
                if row is not None:
                    if row[0] != encoded_request:
                        db.rollback()
                        raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-ID-CONFLICT")
                    db.commit()
                    return json.loads(row[1])
                db.execute(
                    "INSERT INTO activation_intents VALUES(?,?,?,?)",
                    (activation_id, "prepared", encoded_request, encoded_intent),
                )
                db.commit()
                return intent
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
            finally:
                db.close()
        except RemoteActivationProtocolError:
            raise
        except sqlite3.Error as exc:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-PREPARE") from exc

    def read_intent(self, activation_id: str) -> dict | None:
        activation_id = _validate_id(activation_id)
        try:
            db = self._connect()
            try:
                row = db.execute(
                    "SELECT intent_json FROM activation_intents WHERE activation_id=?",
                    (activation_id,),
                ).fetchone()
            finally:
                db.close()
            return None if row is None else json.loads(row[0])
        except sqlite3.Error as exc:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-READ") from exc

    def finalize(self, activation_id: str, profile_digest: str,
                 operator_ack_digest: str) -> dict:
        activation_id = _validate_id(activation_id)
        for value in (profile_digest, operator_ack_digest):
            if type(value) is not str or not _HEX64.fullmatch(value):
                raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-DIGEST")
        try:
            db = self._connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT intent_json FROM activation_intents WHERE activation_id=?",
                    (activation_id,),
                ).fetchone()
                if row is None:
                    db.rollback()
                    raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-NOT-FOUND")
                intent = json.loads(row[0])
                if (intent["profile_digest"] != profile_digest
                        or intent["operator_ack_digest"] != operator_ack_digest):
                    db.rollback()
                    raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-DIGEST-MISMATCH")
                if intent["state"] != "finalized":
                    intent["state"] = "finalized"
                    db.execute(
                        "UPDATE activation_intents SET state='finalized', intent_json=? WHERE activation_id=?",
                        (self._json(intent), activation_id),
                    )
                db.commit()
                return intent
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
            finally:
                db.close()
        except RemoteActivationProtocolError:
            raise
        except sqlite3.Error as exc:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-STORE-E-FINALIZE") from exc
