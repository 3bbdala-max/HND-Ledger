"""Deterministic genesis, state-root, Merkle-root, and block-header primitives.

This module defines a local protocol profile only. It does not execute
transactions, persist blocks, or implement consensus.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

from .decoder import _decode_array

from .canonical import (
    PROTOCOL_VERSION,
    UINT64_MAX,
    EncodingError,
    encode_array,
    encode_bytes,
    encode_uint,
)

MAX_SUPPLY_UNITS = 100_000_000_000_000
ADDRESS_RE = re.compile(r"^[0-9a-f]{64}$")
ZERO_HASH = bytes(32)

GENESIS_DOMAIN = b"HND-GENESIS-V2\x00"
STATE_LEAF_DOMAIN = b"HND-STATE-LEAF-V2\x00"
MERKLE_LEAF_DOMAIN = b"HND-MERKLE-LEAF-V2\x00"
MERKLE_NODE_DOMAIN = b"HND-MERKLE-NODE-V2\x00"
MERKLE_EMPTY_DOMAIN = b"HND-MERKLE-EMPTY-V2\x00"
STATE_EMPTY_DOMAIN = b"HND-STATE-EMPTY-V2\x00"
BLOCK_DOMAIN = b"HND-BLOCK-V2\x00"


def _uint(name: str, value: int, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EncodingError(f"{name} must be an integer")
    if value < minimum or value > UINT64_MAX:
        raise EncodingError(f"{name} is outside the permitted uint64 range")
    return value


def _chain_id(chain_id: bytes) -> bytes:
    if not isinstance(chain_id, bytes) or len(chain_id) != 32:
        raise EncodingError("chain_id must be exactly 32 bytes")
    return chain_id


def _address(address: str) -> bytes:
    if not isinstance(address, str) or not ADDRESS_RE.fullmatch(address):
        raise EncodingError("account address must be 64 lowercase hexadecimal characters")
    return bytes.fromhex(address)


def canonical_genesis(chain_id: bytes, allocations: Mapping[str, int]) -> bytes:
    """Encode [version, chain_id, sorted [[account_id, balance], ...]]."""
    _chain_id(chain_id)
    if not isinstance(allocations, Mapping):
        raise EncodingError("allocations must be a mapping")
    entries: list[tuple[bytes, int]] = []
    total = 0
    for address, balance in allocations.items():
        raw_address = _address(address)
        amount = _uint("genesis balance", balance)
        total += amount
        if total > MAX_SUPPLY_UNITS:
            raise EncodingError("genesis allocation exceeds maximum supply")
        entries.append((raw_address, amount))
    entries.sort(key=lambda item: item[0])
    encoded_entries = [
        encode_array([encode_bytes(address), encode_uint(balance)])
        for address, balance in entries
    ]
    return encode_array([
        encode_uint(PROTOCOL_VERSION),
        encode_bytes(chain_id),
        encode_array(encoded_entries),
    ])


def genesis_id(chain_id: bytes, allocations: Mapping[str, int]) -> bytes:
    """Return SHA-256(HND-GENESIS-V2\0 || canonical_genesis)."""
    return hashlib.sha256(
        GENESIS_DOMAIN + canonical_genesis(chain_id, allocations)
    ).digest()


def merkle_root(items: Sequence[bytes]) -> bytes:
    """Return an ordered binary Merkle root; duplicate the final odd node."""
    if not isinstance(items, (list, tuple)):
        raise EncodingError("Merkle items must be a list or tuple")
    level: list[bytes] = []
    for item in items:
        if not isinstance(item, bytes) or len(item) != 32:
            raise EncodingError("each Merkle item must be exactly 32 bytes")
        level.append(hashlib.sha256(MERKLE_LEAF_DOMAIN + item).digest())
    if not level:
        return hashlib.sha256(MERKLE_EMPTY_DOMAIN).digest()
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(MERKLE_NODE_DOMAIN + level[i] + level[i + 1]).digest()
            for i in range(0, len(level), 2)
        ]
    return level[0]


def state_root(
    balances: Mapping[str, int],
    nonces: Mapping[str, int] | None = None,
) -> bytes:
    """Hash sorted account records [account_id, balance, nonce] into a Merkle root."""
    if not isinstance(balances, Mapping):
        raise EncodingError("balances must be a mapping")
    if nonces is None:
        nonces = {}
    if not isinstance(nonces, Mapping):
        raise EncodingError("nonces must be a mapping")
    if set(nonces) - set(balances):
        raise EncodingError("nonce map contains an account absent from balances")
    entries: list[tuple[bytes, int, int]] = []
    total = 0
    for address, balance in balances.items():
        raw_address = _address(address)
        amount = _uint("balance", balance)
        nonce = _uint("nonce", nonces.get(address, 0))
        total += amount
        if total > MAX_SUPPLY_UNITS:
            raise EncodingError("state exceeds maximum supply")
        entries.append((raw_address, amount, nonce))
    entries.sort(key=lambda item: item[0])
    leaves = []
    for address, balance, nonce in entries:
        record = encode_array([
            encode_bytes(address),
            encode_uint(balance),
            encode_uint(nonce),
        ])
        leaves.append(hashlib.sha256(STATE_LEAF_DOMAIN + record).digest())
    if not leaves:
        return hashlib.sha256(STATE_EMPTY_DOMAIN).digest()
    return _merkle_prehashed(leaves)


def _merkle_prehashed(leaves: list[bytes]) -> bytes:
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(MERKLE_NODE_DOMAIN + level[i] + level[i + 1]).digest()
            for i in range(0, len(level), 2)
        ]
    return level[0]


def canonical_block_header(
    chain_id: bytes,
    height: int,
    timestamp: int,
    previous_hash: bytes,
    transactions_root: bytes,
    current_state_root: bytes,
    transaction_count: int,
) -> bytes:
    """Encode the fixed eight-field v0.2 block header."""
    _chain_id(chain_id)
    height = _uint("height", height)
    timestamp = _uint("timestamp", timestamp)
    transaction_count = _uint("transaction_count", transaction_count)
    for name, value in (
        ("previous_hash", previous_hash),
        ("transactions_root", transactions_root),
        ("state_root", current_state_root),
    ):
        if not isinstance(value, bytes) or len(value) != 32:
            raise EncodingError(f"{name} must be exactly 32 bytes")
    return encode_array([
        encode_uint(PROTOCOL_VERSION),
        encode_bytes(chain_id),
        encode_uint(height),
        encode_uint(timestamp),
        encode_bytes(previous_hash),
        encode_bytes(transactions_root),
        encode_bytes(current_state_root),
        encode_uint(transaction_count),
    ])


def create_genesis_block(
    chain_id: bytes,
    allocations: Mapping[str, int],
) -> dict[str, object]:
    """Create deterministic genesis data and its height-zero block header."""
    payload = canonical_genesis(chain_id, allocations)
    root = state_root(allocations)
    tx_root = merkle_root([])
    header = canonical_block_header(
        chain_id=chain_id,
        height=0,
        timestamp=0,
        previous_hash=ZERO_HASH,
        transactions_root=tx_root,
        current_state_root=root,
        transaction_count=0,
    )
    return {
        "genesis_payload": payload,
        "genesis_id": hashlib.sha256(GENESIS_DOMAIN + payload).digest(),
        "height": 0,
        "timestamp": 0,
        "previous_hash": ZERO_HASH,
        "transactions_root": tx_root,
        "state_root": root,
        "transaction_count": 0,
        "header": header,
        "block_hash": block_hash(header),
    }


def decode_block_header(encoded: bytes) -> dict[str, object]:
    """Decode and strictly validate the canonical eight-field v0.2 header."""
    fields = _decode_array(encoded, 8)
    version, chain_id, height, timestamp, previous_hash, tx_root, root, count = fields
    if version != PROTOCOL_VERSION:
        raise EncodingError("unsupported block protocol version")
    if not isinstance(chain_id, bytes) or len(chain_id) != 32:
        raise EncodingError("block chain_id must be exactly 32 bytes")
    for name, value in (
        ("previous_hash", previous_hash),
        ("transactions_root", tx_root),
        ("state_root", root),
    ):
        if not isinstance(value, bytes) or len(value) != 32:
            raise EncodingError(f"{name} must be exactly 32 bytes")
    height = _uint("height", height)
    timestamp = _uint("timestamp", timestamp)
    count = _uint("transaction_count", count)
    canonical = canonical_block_header(
        chain_id, height, timestamp, previous_hash, tx_root, root, count
    )
    if canonical != encoded:
        raise EncodingError("block header is not canonical")
    return {
        "version": version,
        "chain_id": chain_id,
        "height": height,
        "timestamp": timestamp,
        "previous_hash": previous_hash,
        "transactions_root": tx_root,
        "state_root": root,
        "transaction_count": count,
    }


def block_hash(header: bytes) -> bytes:
    """Hash only a strictly decoded canonical block header."""
    decode_block_header(header)
    return hashlib.sha256(BLOCK_DOMAIN + header).digest()


def verify_block_hash(header: bytes, expected_hash: bytes) -> bool:
    """Verify a supplied block hash; malformed headers return False."""
    if not isinstance(expected_hash, bytes) or len(expected_hash) != 32:
        return False
    try:
        return block_hash(header) == expected_hash
    except EncodingError:
        return False
