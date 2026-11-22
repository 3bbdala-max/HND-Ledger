"""Deterministic in-memory account ledger conforming to the HND v0.2 transaction profile."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .canonical import (
    UINT64_MAX,
    EncodingError,
    account_id,
    signing_message,
    transaction_id,
)
from .crypto import verify_signature

MAX_SUPPLY_UNITS = 100_000_000_000_000
ADDRESS_RE = re.compile(r"^[0-9a-f]{64}$")
HEX_RE = re.compile(r"^[0-9a-f]+$")


class LedgerError(ValueError):
    """A transaction or ledger state violates a protocol rule."""


@dataclass(frozen=True)
class Transaction:
    chain_id: bytes
    sender: str
    recipient: str
    amount: int
    nonce: int
    public_key: str
    signature: str

    def signing_bytes(self) -> bytes:
        try:
            return signing_message(
                self.chain_id,
                bytes.fromhex(self.sender),
                bytes.fromhex(self.recipient),
                self.amount,
                self.nonce,
            )
        except (ValueError, EncodingError) as exc:
            raise LedgerError(str(exc)) from exc

    @property
    def txid(self) -> str:
        try:
            raw = transaction_id(
                self.chain_id,
                bytes.fromhex(self.sender),
                bytes.fromhex(self.recipient),
                self.amount,
                self.nonce,
                bytes.fromhex(self.public_key),
                bytes.fromhex(self.signature),
            )
            return raw.hex()
        except (ValueError, EncodingError) as exc:
            raise LedgerError(str(exc)) from exc

    @classmethod
    def from_dict(cls, data: Mapping) -> "Transaction":
        expected = {
            "chain_id", "sender", "recipient", "amount",
            "nonce", "public_key", "signature",
        }
        if not isinstance(data, Mapping) or set(data.keys()) != expected:
            raise LedgerError("malformed transaction fields")
        return cls(**dict(data))


class Ledger:
    """In-memory v0.2 ledger. Networking, blocks, and consensus are not included."""

    def __init__(\n        self,\n        chain_id: bytes,\n        genesis_balances: Mapping[str, int],\n        nonces: Mapping[str, int] | None = None,\n    ):
        if not isinstance(chain_id, bytes) or len(chain_id) != 32:
            raise LedgerError("chain_id must be exactly 32 bytes")
        if not isinstance(genesis_balances, Mapping):
            raise LedgerError("genesis_balances must be a mapping")
        self.chain_id = chain_id
        self._balances: dict[str, int] = {}
        self._nonces: dict[str, int] = {}
        self._txids: set[str] = set()

        total_supply = 0
        for address, balance in genesis_balances.items():
            self._validate_address(address)
            self._validate_amount(balance, allow_zero=True)
            total_supply += balance
            if total_supply > MAX_SUPPLY_UNITS:
                raise LedgerError("genesis allocation exceeds maximum supply")
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
        if amount < lower or amount > UINT64_MAX:
            raise LedgerError("amount is outside the permitted unsigned 64-bit range")

    def balance_of(self, address: str) -> int:
        self._validate_address(address)
        return self._balances.get(address, 0)

    def nonce_of(self, address: str) -> int:
        self._validate_address(address)
        return self._nonces.get(address, 0)

    def export_state(self) -> tuple[dict[str, int], dict[str, int]]:
        """Return defensive copies of balances and account nonces."""
        return dict(self._balances), dict(self._nonces)

    def submit_transaction(self, tx: Transaction) -> str:
        """Validate completely, then apply exactly one atomic state transition."""
        if not isinstance(tx, Transaction):
            raise LedgerError("transaction must be a Transaction")
        if not isinstance(tx.chain_id, bytes) or tx.chain_id != self.chain_id:
            raise LedgerError("wrong chain_id")
        self._validate_address(tx.sender)
        self._validate_address(tx.recipient)
        if tx.sender == tx.recipient:
            raise LedgerError("self-transfer is not permitted")
        self._validate_amount(tx.amount)
        if (
            isinstance(tx.nonce, bool)
            or not isinstance(tx.nonce, int)
            or tx.nonce < 0
            or tx.nonce >= UINT64_MAX
        ):
            raise LedgerError("nonce must permit a checked unsigned 64-bit increment")
        if not isinstance(tx.public_key, str) or not HEX_RE.fullmatch(tx.public_key):
            raise LedgerError("malformed public key")
        if not isinstance(tx.signature, str) or not HEX_RE.fullmatch(tx.signature):
            raise LedgerError("malformed signature")

        try:
            public_key = bytes.fromhex(tx.public_key)
            signature = bytes.fromhex(tx.signature)
            message = tx.signing_bytes()
        except (ValueError, LedgerError) as exc:
            raise LedgerError("malformed transaction encoding") from exc
        if len(public_key) != 32 or len(signature) != 64:
            raise LedgerError("public key or signature has an invalid length")
        if account_id(public_key).hex() != tx.sender:
            raise LedgerError("public key does not control sender account")
        if not verify_signature(public_key, message, tx.signature):
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
        if recipient_balance > UINT64_MAX - tx.amount:
            raise LedgerError("recipient balance overflow")

        # Calculate every result before mutation; rejected transactions are atomic.
        new_sender_balance = sender_balance - tx.amount
        new_recipient_balance = recipient_balance + tx.amount
        new_nonce = expected_nonce + 1

        self._balances[tx.sender] = new_sender_balance
        self._balances[tx.recipient] = new_recipient_balance
        self._nonces[tx.sender] = new_nonce
        self._txids.add(txid)
        return txid
