"""In-memory HND v0.2 ledger reference built on the isolated primitives.

This is a deterministic local state-transition model. It is not a peer-to-peer
network, persistent database, block producer, or distributed consensus engine.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .genesis import validate_genesis_manifest
from .transaction import (
    ProtocolConfig,
    canonical_json,
    transaction_id,
    validate_transaction,
)

_SNAPSHOT_VERSION = 1


class LedgerError(ValueError):
    """Raised when a proposed state transition cannot be applied."""


class HNDLedger:
    """In-memory account balances, nonces, replay protection, and transaction history."""

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
        self._assert_supply()
        self.state_hash = self._calculate_state_hash()

    def _state_payload(self) -> dict[str, Any]:
        return {
            "schema_version": _SNAPSHOT_VERSION,
            "network_id": self.config.network_id,
            "protocol_version": self.config.protocol_version,
            "genesis_hash": self.genesis_hash,
            "total_supply": self.total_supply,
            "balances": dict(sorted(self.balances.items())),
            "nonces": dict(sorted(self.nonces.items())),
            "accepted": sorted(self.accepted),
            "history": self.history,
        }

    def _calculate_state_hash(self) -> str:
        return hashlib.sha256(
            b"HND-LEDGER/STATE\x00" + canonical_json(self._state_payload())
        ).hexdigest()

    def _assert_supply(self) -> None:
        if any(type(value) is not int or value < 0 for value in self.balances.values()):
            raise LedgerError("invalid balance in state")
        if sum(self.balances.values()) != self.total_supply:
            raise LedgerError("total supply invariant violated")
        if set(self.balances) != set(self.public_keys) or set(self.balances) != set(self.nonces):
            raise LedgerError("account registry mismatch")

    def apply_transaction(self, tx: Any) -> str:
        """Validate and atomically apply one signed transfer; return its tx ID."""
        if type(tx) is not dict:
            raise LedgerError("transaction must be an object")

        sender = tx.get("sender")
        recipient = tx.get("recipient")
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
            tx,
            config=self.config,
            expected_nonce=self.nonces[sender],
            sender_balance=self.balances[sender],
            sender_public_key=self.public_keys[sender],
        )
        if not ok:
            raise LedgerError(f"invalid transaction: {reason}")

        amount = tx["amount"]
        # Compute all new values before mutating state.
        sender_balance = self.balances[sender] - amount
        recipient_balance = self.balances[recipient] + amount
        next_nonce = self.nonces[sender] + 1
        if next_nonce > (1 << 64) - 1:
            raise LedgerError("nonce exhausted")

        self.balances[sender] = sender_balance
        self.balances[recipient] = recipient_balance
        self.nonces[sender] = next_nonce
        self.accepted.add(txid)
        self.history.append(dict(tx))
        self._assert_supply()
        self.state_hash = self._calculate_state_hash()
        return txid

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-compatible snapshot with a hash over all ledger state."""
        return {
            **self._state_payload(),
            "state_hash": self.state_hash,
        }

    @classmethod
    def restore(cls, *, manifest: dict[str, Any], config: ProtocolConfig,
                expected_genesis_hash: str, snapshot: Mapping[str, Any]) -> "HNDLedger":
        """Rebuild from genesis by replaying history; never trust stored balances."""
        required = {
            "schema_version", "network_id", "protocol_version", "genesis_hash",
            "total_supply", "balances", "nonces", "accepted", "history", "state_hash",
        }
        if type(snapshot) is not dict or set(snapshot) != required:
            raise LedgerError("snapshot schema")
        if snapshot["schema_version"] != _SNAPSHOT_VERSION:
            raise LedgerError("snapshot version")
        if snapshot["network_id"] != config.network_id:
            raise LedgerError("snapshot network")
        if snapshot["protocol_version"] != config.protocol_version:
            raise LedgerError("snapshot protocol version")
        if snapshot["genesis_hash"] != expected_genesis_hash:
            raise LedgerError("snapshot genesis hash")
        if snapshot["total_supply"] != manifest.get("total_supply"):
            raise LedgerError("snapshot supply")

        ledger = cls(
            config=config, manifest=manifest,
            expected_genesis_hash=expected_genesis_hash,
        )
        history = snapshot["history"]
        if type(history) is not list:
            raise LedgerError("snapshot history")
        for tx in history:
            ledger.apply_transaction(tx)

        # Compare every derived field. A forged balance/nonce/accepted set is rejected.
        expected = ledger.snapshot()
        for field in ("balances", "nonces", "accepted", "history", "state_hash"):
            if snapshot[field] != expected[field]:
                raise LedgerError(f"snapshot {field} mismatch")
        return ledger

    def account_view(self, account_id: str) -> dict[str, int]:
        """Return public account state only; never expose private key material."""
        if account_id not in self.balances:
            raise LedgerError("unknown account")
        return {
            "balance": self.balances[account_id],
            "next_nonce": self.nonces[account_id],
        }
