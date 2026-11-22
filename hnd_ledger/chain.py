"""Deterministic block construction and independent replay verification."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from .blocks import (
    block_hash,
    canonical_block_header,
    decode_block_header,
    merkle_root,
    state_root,
)
from .canonical import UINT64_MAX, EncodingError
from .ledger import Ledger, LedgerError, Transaction


class ChainError(ValueError):
    """A block cannot extend or reproduce the supplied parent state."""


def build_block(
    parent_header: bytes,
    parent_hash: bytes,
    balances: Mapping[str, int],
    nonces: Mapping[str, int],
    transactions: Sequence[Transaction],
    timestamp: int,
) -> dict[str, object]:
    """Execute ordered transactions against parent state and construct a block.

    This is a deterministic local state-transition routine. It does not decide
    which competing block wins and does not provide network consensus.
    """
    try:
        parent = decode_block_header(parent_header)
        actual_parent_hash = block_hash(parent_header)
    except EncodingError as exc:
        raise ChainError("invalid parent block header") from exc
    if not isinstance(parent_hash, bytes) or parent_hash != actual_parent_hash:
        raise ChainError("parent hash does not match parent header")
    if parent["height"] == UINT64_MAX:
        raise ChainError("parent height cannot be incremented")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int) or not 0 <= timestamp <= UINT64_MAX:
        raise ChainError("timestamp must be a uint64")
    if timestamp < parent["timestamp"]:
        raise ChainError("block timestamp cannot move backwards")
    if not isinstance(transactions, (list, tuple)):
        raise ChainError("transactions must be a list or tuple")

    chain_id = parent["chain_id"]
    try:
        ledger = Ledger(chain_id, balances, nonces)
        txids: list[bytes] = []
        for transaction in transactions:
            txid_hex = ledger.submit_transaction(transaction)
            txids.append(bytes.fromhex(txid_hex))
        new_balances, new_nonces = ledger.export_state()
        tx_root = merkle_root(txids)
        new_state_root = state_root(new_balances, new_nonces)
        header = canonical_block_header(
            chain_id=chain_id,
            height=parent["height"] + 1,
            timestamp=timestamp,
            previous_hash=parent_hash,
            transactions_root=tx_root,
            current_state_root=new_state_root,
            transaction_count=len(txids),
        )
        digest = block_hash(header)
    except (LedgerError, EncodingError, TypeError, ValueError) as exc:
        raise ChainError(f"block execution rejected: {exc}") from exc

    return {
        "header": header,
        "block_hash": digest,
        "height": parent["height"] + 1,
        "timestamp": timestamp,
        "previous_hash": parent_hash,
        "transactions_root": tx_root,
        "state_root": new_state_root,
        "transaction_count": len(txids),
        "transaction_ids": tuple(txids),
        "balances": new_balances,
        "nonces": new_nonces,
    }


def verify_block(
    parent_header: bytes,
    parent_hash: bytes,
    parent_balances: Mapping[str, int],
    parent_nonces: Mapping[str, int],
    transactions: Sequence[Transaction],
    candidate_header: bytes,
    candidate_hash: bytes,
) -> bool:
    """Independently replay transactions and compare the complete header/hash."""
    try:
        candidate = decode_block_header(candidate_header)
        rebuilt = build_block(
            parent_header,
            parent_hash,
            parent_balances,
            parent_nonces,
            transactions,
            candidate["timestamp"],
        )
        return (
            rebuilt["header"] == candidate_header
            and rebuilt["block_hash"] == candidate_hash
            and block_hash(candidate_header) == candidate_hash
        )
    except (ChainError, EncodingError, TypeError, ValueError):
        return False
