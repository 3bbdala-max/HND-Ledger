"""In-memory HND v0.2 ledger reference with replay-verified file persistence.

This is a deterministic local model, not a distributed blockchain, network,
validator system, or production financial service.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .genesis import validate_genesis_manifest
from .transaction import ProtocolConfig, canonical_json, transaction_id, validate_transaction

SNAPSHOT_VERSION = 1
STATE_DOMAIN = b"HND-LEDGER/STATE\x00"
SNAPSHOT_KEYS = {
    "schema_version", "network_id", "protocol_version", "genesis_hash",
    "total_supply", "balances", "nonces", "accepted", "history", "state_hash",
}


class LedgerError(ValueError):
    """Raised when a state transition or snapshot operation is invalid."""


class HNDLedger:
    """In-memory balances, nonces, replay checks, and signed transaction history."""

    def __init__(self, *, config: ProtocolConfig, manifest: dict[str, Any],
                 expected_genesis_hash: str) -> None:
        ok, reason = validate_genesis_manifest(
            manifest, config=config, expected_genesis_hash=expected_genesis_hash
        )
        if not ok:
            raise LedgerError(f"invalid genesis: {reason}")
        self.config = config
        self.genesis_hash = expected_genesis_hash
        self.total_supply = manifest["total_supply"]
        self.balances: dict[str, int] = {}
        self.public_keys: dict[str, str] = {}
        self.nonces: dict[str, int] = {}
        for allocation in manifest["allocations"]:
            account_id = allocation["account_id"]
            self.balances[account_id] = allocation["amount"]
            self.public_keys[account_id] = allocation["public_key"]
            self.nonces[account_id] = 0
        self.accepted: set[str] = set()
        self.history: list[dict[str, Any]] = []
        self._assert_invariants()
        self.state_hash = self._calculate_state_hash()

    def _state_payload(self) -> dict[str, Any]:
        history_copy = json.loads(canonical_json(self.history).decode("utf-8"))
        return {
            "schema_version": SNAPSHOT_VERSION,
            "network_id": self.config.network_id,
            "protocol_version": self.config.protocol_version,
            "genesis_hash": self.genesis_hash,
            "total_supply": self.total_supply,
            "balances": dict(sorted(self.balances.items())),
            "nonces": dict(sorted(self.nonces.items())),
            "accepted": sorted(self.accepted),
            "history": history_copy,
        }

    def _calculate_state_hash(self) -> str:
        return hashlib.sha256(
            STATE_DOMAIN + canonical_json(self._state_payload())
        ).hexdigest()

    def _assert_invariants(self) -> None:
        if set(self.balances) != set(self.public_keys) or set(self.balances) != set(self.nonces):
            raise LedgerError("account registry mismatch")
        if any(type(value) is not int or value < 0 for value in self.balances.values()):
            raise LedgerError("invalid balance in state")
        if any(type(value) is not int or value < 0 or value > (1 << 64) - 1 for value in self.nonces.values()):
            raise LedgerError("invalid nonce in state")
        if sum(self.balances.values()) != self.total_supply:
            raise LedgerError("total supply invariant violated")

    def apply_transaction(self, tx: Any) -> str:
        """Validate and atomically apply a signed transfer; return its transaction ID."""
        if type(tx) is not dict:
            raise LedgerError("transaction must be an object")
        sender, recipient = tx.get("sender"), tx.get("recipient")
        if type(sender) is not str or type(recipient) is not str:
            raise LedgerError("sender and recipient must be account IDs")
        if sender not in self.balances:
            raise LedgerError("unknown sender")
        if recipient not in self.balances:
            raise LedgerError("unknown recipient")
        try:
            txid = transaction_id(tx)
        except (TypeError, ValueError) as exc:
            raise LedgerError("malformed transaction schema or encoding") from exc
        if txid in self.accepted:
            raise LedgerError("duplicate transaction")

        ok, reason = validate_transaction(
            tx, config=self.config, expected_nonce=self.nonces[sender],
            sender_balance=self.balances[sender], sender_public_key=self.public_keys[sender],
        )
        if not ok:
            raise LedgerError(f"invalid transaction: {reason}")

        next_nonce = self.nonces[sender] + 1
        if next_nonce > (1 << 64) - 1:
            raise LedgerError("nonce exhausted")
        amount = tx["amount"]
        new_sender = self.balances[sender] - amount
        new_recipient = self.balances[recipient] + amount
        total_after = sum(self.balances.values()) - self.balances[sender] - self.balances[recipient] + new_sender + new_recipient
        if new_sender < 0 or total_after != self.total_supply:
            raise LedgerError("state invariant violated before commit")

        normalized_tx = json.loads(canonical_json(tx).decode("utf-8"))
        self.balances[sender] = new_sender
        self.balances[recipient] = new_recipient
        self.nonces[sender] = next_nonce
        self.accepted.add(txid)
        self.history.append(normalized_tx)
        self._assert_invariants()
        self.state_hash = self._calculate_state_hash()
        return txid

    def snapshot(self) -> dict[str, Any]:
        payload = self._state_payload()
        return {**payload, "state_hash": self._calculate_state_hash()}

    def save(self, path: str | os.PathLike[str]) -> None:
        """Atomically save JSON through a temporary sibling file and replace."""
        destination = Path(path)
        if not destination.parent.exists() or not destination.parent.is_dir():
            raise FileNotFoundError("snapshot parent directory does not exist")
        encoded = json.dumps(
            self.snapshot(), sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False
        ) + "\n"
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=destination.parent,
                prefix=f".{destination.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temp_name = handle.name
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, destination)
            temp_name = None
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass

    @classmethod
    def restore(cls, *, manifest: dict[str, Any], config: ProtocolConfig,
                expected_genesis_hash: str, snapshot: Mapping[str, Any]) -> "HNDLedger":
        """Rebuild from Genesis by replaying history; never trust stored balances."""
        if type(snapshot) is not dict or set(snapshot) != SNAPSHOT_KEYS:
            raise LedgerError("snapshot schema")
        if type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != SNAPSHOT_VERSION:
            raise LedgerError("snapshot version")
        if type(snapshot["network_id"]) is not str or snapshot["network_id"] != config.network_id:
            raise LedgerError("snapshot network")
        if type(snapshot["protocol_version"]) is not int or snapshot["protocol_version"] != config.protocol_version:
            raise LedgerError("snapshot protocol version")
        if type(snapshot["genesis_hash"]) is not str or snapshot["genesis_hash"] != expected_genesis_hash:
            raise LedgerError("snapshot genesis hash")
        if type(snapshot["total_supply"]) is not int or snapshot["total_supply"] != manifest.get("total_supply"):
            raise LedgerError("snapshot supply")
        if type(snapshot["balances"]) is not dict or type(snapshot["nonces"]) is not dict:
            raise LedgerError("snapshot account state")
        if type(snapshot["accepted"]) is not list or type(snapshot["history"]) is not list:
            raise LedgerError("snapshot history")
        if type(snapshot["state_hash"]) is not str or len(snapshot["state_hash"]) != 64:
            raise LedgerError("snapshot state hash")

        ledger = cls(config=config, manifest=manifest, expected_genesis_hash=expected_genesis_hash)
        for index, tx in enumerate(snapshot["history"]):
            try:
                ledger.apply_transaction(tx)
            except LedgerError as exc:
                raise LedgerError(f"snapshot transaction {index} rejected: {exc}") from exc

        expected = ledger.snapshot()
        for field in ("balances", "nonces", "accepted", "history", "state_hash"):
            try:
                stored = canonical_json(snapshot[field])
                rebuilt = canonical_json(expected[field])
            except (TypeError, ValueError) as exc:
                raise LedgerError(f"snapshot {field} malformed") from exc
            if stored != rebuilt:
                raise LedgerError(f"snapshot {field} mismatch")
        return ledger

    @classmethod
    def load(cls, path: str | os.PathLike[str], *, manifest: dict[str, Any],
             config: ProtocolConfig, expected_genesis_hash: str) -> "HNDLedger":
        """Load JSON from disk and restore by replaying signed history from Genesis."""
        try:
            with open(path, "r", encoding="utf-8") as handle:
                snapshot = json.load(
                    handle,
                    parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
                )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise LedgerError("snapshot cannot be decoded") from exc
        return cls.restore(
            manifest=manifest, config=config,
            expected_genesis_hash=expected_genesis_hash, snapshot=snapshot,
        )

    def account_view(self, account_id: str) -> dict[str, int]:
        if account_id not in self.balances:
            raise LedgerError("unknown account")
        return {"balance": self.balances[account_id], "next_nonce": self.nonces[account_id]}
