"""Deterministic in-memory account ledger for the HND 0.2 prototype."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping

from .crypto import address_from_public_key, verify_signature

MAX_AMOUNT = 2**256 - 1
ADDRESS_RE = re.compile(r"^[0-9a-f]{64}$")
HEX_RE = re.compile(r"^[0-9a-f]+$")


class LedgerError(ValueError):
    """A transaction or ledger state violates a protocol rule."""


@dataclass(frozen=True)
class Transaction:
    network_id: str
    sender: str
    recipient: str
    amount: int
    nonce: int
    public_key: str
    signature: str

    def payload_dict(self) -> dict:
        # Signature is deliberately excluded from both signing bytes and tx id.
        return {
            "amount": self.amount,
            "network_id": self.network_id,
            "nonce": self.nonce,
            "recipient": self.recipient,
            "sender": self.sender,
        }

    def signing_bytes(self) -> bytes:
        return json.dumps(
            self.payload_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @property
    def txid(self) -> str:
        return hashlib.sha256(self.signing_bytes()).hexdigest()

    @classmethod
    def from_dict(cls, data: Mapping) -> "Transaction":
        expected = {
            "network_id", "sender", "recipient", "amount",
            "nonce", "public_key", "signature",
        }
        if not isinstance(data, Mapping) or set(data.keys()) != expected:
            raise LedgerError("malformed transaction fields")
        return cls(**dict(data))


class Ledger:
    """In-memory deterministic ledger; no networking or consensus is included."""

    def __init__(self, network_id: str, genesis_balances: Mapping[str, int]):
        if not isinstance(network_id, str) or not network_id.strip():
            raise LedgerError("network_id must be a non-empty string")
        if not isinstance(genesis_balances, Mapping):
            raise LedgerError("genesis_balances must be a mapping")
        self.network_id = network_id
        self._balances: dict[str, int] = {}
        self._nonces: dict[str, int] = {}
        self._txids: set[str] = set()

        for address, balance in genesis_balances.items():
            self._validate_address(address)
            self._validate_amount(balance, allow_zero=True)
            self._balances[address] = balance
            self._nonces[address] = 0

    @staticmethod
    def _validate_address(address: str) -> None:
        if not isinstance(address, str) or not ADDRESS_RE.fullmatch(address):
            raise LedgerError("address must be 64 lowercase hexadecimal characters")

    @staticmethod
    def _validate_amount(amount: int, allow_zero: bool = False) -> None:
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise LedgerError("amount must be an integer")
        lower = 0 if allow_zero else 1
        if amount < lower or amount > MAX_AMOUNT:
            raise LedgerError("amount is outside the permitted integer range")

    def balance_of(self, address: str) -> int:
        self._validate_address(address)
        return self._balances.get(address, 0)

    def nonce_of(self, address: str) -> int:
        self._validate_address(address)
        return self._nonces.get(address, 0)

    def submit_transaction(self, tx: Transaction) -> str:
        """Validate fully, then atomically apply one transaction."""
        if not isinstance(tx, Transaction):
            raise LedgerError("transaction must be a Transaction")
        if not isinstance(tx.network_id, str) or tx.network_id != self.network_id:
            raise LedgerError("wrong network_id")
        self._validate_address(tx.sender)
        self._validate_address(tx.recipient)
        self._validate_amount(tx.amount)
        if isinstance(tx.nonce, bool) or not isinstance(tx.nonce, int) or tx.nonce < 0:
            raise LedgerError("nonce must be a non-negative integer")
        if not isinstance(tx.public_key, str) or not HEX_RE.fullmatch(tx.public_key):
            raise LedgerError("malformed public key")
        if not isinstance(tx.signature, str) or not HEX_RE.fullmatch(tx.signature):
            raise LedgerError("malformed signature")

        try:
            public_key = bytes.fromhex(tx.public_key)
        except ValueError as exc:
            raise LedgerError("malformed public key") from exc
        if len(public_key) != 32:
            raise LedgerError("public key must be 32 bytes")
        if address_from_public_key(public_key) != tx.sender:
            raise LedgerError("public key does not control sender address")
        if not verify_signature(public_key, tx.signing_bytes(), tx.signature):
            raise LedgerError("invalid signature")

        txid = tx.txid
        if txid in self._txids:
            raise LedgerError("duplicate transaction")
        expected_nonce = self.nonce_of(tx.sender)
        if tx.nonce != expected_nonce:
            raise LedgerError("nonce conflict")

        sender_balance = self.balance_of(tx.sender)
        if sender_balance < tx.amount:
            raise LedgerError("insufficient funds")

        recipient_balance = self.balance_of(tx.recipient)
        if tx.sender != tx.recipient and recipient_balance > MAX_AMOUNT - tx.amount:
            raise LedgerError("recipient balance overflow")

        # Calculate all resulting values before mutating state (atomic rejection).
        if tx.sender == tx.recipient:
            new_sender_balance = sender_balance
            new_recipient_balance = sender_balance
        else:
            new_sender_balance = sender_balance - tx.amount
            new_recipient_balance = recipient_balance + tx.amount

        self._balances[tx.sender] = new_sender_balance
        self._balances[tx.recipient] = new_recipient_balance
        self._nonces[tx.sender] = expected_nonce + 1
        self._txids.add(txid)
        return txid
