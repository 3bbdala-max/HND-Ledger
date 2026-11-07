"""Atomic account-state transitions for the HND local prototype."""

from __future__ import annotations

from dataclasses import dataclass, field

from .protocol import (
    CHAIN_ID, MAX_SUPPLY, MAX_U64, Transaction, verify_transaction,
)


class LedgerError(ValueError):
    """Raised when a transaction cannot be applied to ledger state."""


@dataclass
class LedgerState:
    balances: dict[bytes, int] = field(default_factory=dict)
    next_nonces: dict[bytes, int] = field(default_factory=dict)
    chain_id: bytes = CHAIN_ID
    supply_cap: int = MAX_SUPPLY

    def __post_init__(self) -> None:
        if not isinstance(self.chain_id, bytes) or len(self.chain_id) != 32:
            raise LedgerError("chain_id must be 32 bytes")
        if isinstance(self.supply_cap, bool) or not isinstance(self.supply_cap, int):
            raise LedgerError("supply cap must be an integer")
        if self.supply_cap < 0 or self.supply_cap > MAX_SUPPLY:
            raise LedgerError("supply cap is outside the protocol limit")
        for account, balance in self.balances.items():
            self._check_account(account)
            self._check_u64(balance, "balance")
        for account, nonce in self.next_nonces.items():
            self._check_account(account)
            self._check_u64(nonce, "next nonce")
        if sum(self.balances.values()) > self.supply_cap:
            raise LedgerError("initial balances exceed supply cap")

    @staticmethod
    def _check_account(account: bytes) -> None:
        if not isinstance(account, bytes) or len(account) != 32:
            raise LedgerError("account id must be 32 bytes")

    @staticmethod
    def _check_u64(value: int, field_name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise LedgerError(f"{field_name} must be an integer")
        if value < 0 or value > MAX_U64:
            raise LedgerError(f"{field_name} is outside uint64 range")

    @property
    def total_supply(self) -> int:
        return sum(self.balances.values())

    def apply(self, tx: Transaction) -> None:
        try:
            verify_transaction(tx, self.chain_id)
        except ValueError as exc:
            raise LedgerError(str(exc)) from exc

        expected = self.next_nonces.get(tx.sender, 0)
        if tx.nonce != expected:
            raise LedgerError("incorrect nonce")
        sender_balance = self.balances.get(tx.sender, 0)
        if sender_balance < tx.amount:
            raise LedgerError("insufficient funds")
        recipient_balance = self.balances.get(tx.recipient, 0)
        if recipient_balance + tx.amount > MAX_U64:
            raise LedgerError("recipient balance overflow")
        next_nonce = expected + 1
        if next_nonce > MAX_U64:
            raise LedgerError("sender nonce overflow")
        if self.total_supply > self.supply_cap:
            raise LedgerError("current state exceeds supply cap")

        # All validation precedes mutation: rejected transactions are atomic.
        # A transfer preserves total supply, so the cap check above remains
        # valid for the candidate state without a post-mutation failure path.
        new_sender_balance = sender_balance - tx.amount
        new_recipient_balance = recipient_balance + tx.amount
        self.balances[tx.sender] = new_sender_balance
        self.balances[tx.recipient] = new_recipient_balance
        self.next_nonces[tx.sender] = next_nonce
