"""ABCI++-style deterministic application boundary for the HND ledger.

This module is an application-layer lifecycle model, not an ABCI socket server.
Only commit() writes a decided block to LocalChain; proposal candidates are
always isolated copies of the last committed state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .chain import (
    MAX_BLOCK_BYTES,
    MAX_BLOCK_TRANSACTIONS,
    Block,
    ChainError,
    LocalChain,
    state_commitment,
)
from .protocol import Transaction, decode_transaction, encode_transaction
from .state import LedgerState


def _copy_state(state: LedgerState) -> LedgerState:
    return LedgerState(
        balances=dict(state.balances),
        next_nonces=dict(state.next_nonces),
        chain_id=state.chain_id,
        supply_cap=state.supply_cap,
    )


def _decode_batch(raw_transactions: Iterable[bytes], chain_id: bytes) -> tuple[Transaction, ...]:
    try:
        raw_items = tuple(raw_transactions)
    except TypeError as exc:
        raise ChainError("transactions must be iterable") from exc
    if len(raw_items) > MAX_BLOCK_TRANSACTIONS:
        raise ChainError("block transaction count exceeds limit")
    if any(not isinstance(raw, bytes) for raw in raw_items):
        raise ChainError("encoded transaction must be bytes")
    if sum(map(len, raw_items)) > MAX_BLOCK_BYTES:
        raise ChainError("encoded block exceeds byte limit")
    return tuple(decode_transaction(raw, chain_id) for raw in raw_items)


def _execute(base: LedgerState, transactions: tuple[Transaction, ...]) -> LedgerState:
    candidate = _copy_state(base)
    try:
        for tx in transactions:
            candidate.apply(tx)
    except ValueError as exc:
        raise ChainError(f"invalid transaction sequence: {exc}") from exc
    return candidate


@dataclass(frozen=True, slots=True)
class FinalizedCandidate:
    """In-memory result awaiting the durable Commit phase."""

    transactions: tuple[Transaction, ...]
    app_hash: bytes
    base_height: int
    base_app_hash: bytes


class LedgerApplication:
    """Small lifecycle facade; it does not implement CometBFT transport."""

    def __init__(self, chain: LocalChain):
        self.chain = chain
        self._finalized: FinalizedCandidate | None = None

    @property
    def height(self) -> int:
        return self.chain.height

    @property
    def app_hash(self) -> bytes:
        return state_commitment(self.chain.state)

    def info(self) -> dict[str, int | bytes]:
        return {"last_block_height": self.height, "last_block_app_hash": self.app_hash}

    def check_tx(self, raw_transaction: bytes) -> None:
        """Admission check against committed state; does not reserve a nonce."""
        tx = decode_transaction(raw_transaction, self.chain.state.chain_id)
        candidate = _copy_state(self.chain.state)
        try:
            candidate.apply(tx)
        except ValueError as exc:
            raise ChainError(f"transaction rejected: {exc}") from exc

    def prepare_proposal(self, raw_transactions: Iterable[bytes]) -> tuple[bytes, ...]:
        """Select a valid ordered prefix without changing committed state."""
        if self._finalized is not None:
            raise ChainError("cannot prepare while a finalized block awaits commit")
        selected: list[bytes] = []
        candidate = _copy_state(self.chain.state)
        total_bytes = 0
        for raw in raw_transactions:
            if len(selected) >= MAX_BLOCK_TRANSACTIONS:
                break
            if not isinstance(raw, bytes):
                continue
            if total_bytes + len(raw) > MAX_BLOCK_BYTES:
                continue
            try:
                tx = decode_transaction(raw, self.chain.state.chain_id)
                next_candidate = _copy_state(candidate)
                next_candidate.apply(tx)
            except (ValueError, TypeError):
                continue
            selected.append(raw)
            total_bytes += len(raw)
            candidate = next_candidate
        return tuple(selected)

    def process_proposal(self, raw_transactions: Iterable[bytes]) -> bool:
        """Validate a complete proposal deterministically against committed state."""
        if self._finalized is not None:
            raise ChainError("cannot process proposal while a finalized block awaits commit")
        try:
            txs = _decode_batch(raw_transactions, self.chain.state.chain_id)
            _execute(self.chain.state, txs)
        except (ChainError, ValueError, TypeError):
            return False
        return True

    def finalize_block(self, raw_transactions: Iterable[bytes]) -> bytes:
        """Compute the decided block result in memory; no durable write occurs."""
        if self._finalized is not None:
            raise ChainError("a finalized block already awaits commit")
        txs = _decode_batch(raw_transactions, self.chain.state.chain_id)
        candidate = _execute(self.chain.state, txs)
        app_hash = state_commitment(candidate)
        self._finalized = FinalizedCandidate(
            transactions=txs,
            app_hash=app_hash,
            base_height=self.height,
            base_app_hash=self.app_hash,
        )
        return app_hash

    def commit(self) -> Block:
        """Persist the finalized block atomically and advance committed state."""
        if self._finalized is None:
            raise ChainError("no finalized block is awaiting commit")
        pending = self._finalized
        if self.height != pending.base_height or self.app_hash != pending.base_app_hash:
            raise ChainError("committed state changed after finalization; candidate must be discarded")
        block = self.chain.append(pending.transactions)
        actual_app_hash = state_commitment(self.chain.state)
        if actual_app_hash != pending.app_hash:
            # This indicates an internal determinism violation. Do not hide it.
            raise ChainError("committed application hash differs from finalized hash")
        self._finalized = None
        return block
