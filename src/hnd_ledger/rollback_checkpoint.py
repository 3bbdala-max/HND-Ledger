"""Canonical rollback-checkpoint records and provider-neutral authority contract.

This module defines data interchange only. It does not provide a production
trust anchor, signature policy, persistence, or automatic chain enforcement.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import cbor2

from .protocol import canonical_cbor

CHECKPOINT_DOMAIN = "HND-ROLLBACK-CHECKPOINT-V1"
CHECKPOINT_VERSION = 1
_HASH_BYTES = 32


class CheckpointError(ValueError):
    """Raised for malformed or inconsistent checkpoint records."""


def _uint(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CheckpointError(f"{field} must be an integer")
    if value < minimum or value > (1 << 64) - 1:
        raise CheckpointError(f"{field} is outside the uint64 range")
    return value


def _hash(value: object, field: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != _HASH_BYTES:
        raise CheckpointError(f"{field} must be exactly 32 bytes")
    return value


@dataclass(frozen=True, slots=True)
class RollbackCheckpoint:
    """One finalized ledger tip, identified independently of local storage."""

    chain_id: bytes
    genesis_hash: bytes
    height: int
    block_hash: bytes
    app_hash: bytes
    sequence: int
    version: int = CHECKPOINT_VERSION

    def __post_init__(self) -> None:
        _hash(self.chain_id, "chain_id")
        _hash(self.genesis_hash, "genesis_hash")
        _uint(self.height, "height")
        _hash(self.block_hash, "block_hash")
        _hash(self.app_hash, "app_hash")
        _uint(self.sequence, "sequence", minimum=1)
        if isinstance(self.version, bool) or self.version != CHECKPOINT_VERSION:
            raise CheckpointError("unsupported checkpoint version")

    def encode(self) -> bytes:
        """Return the unique canonical CBOR representation."""
        return canonical_cbor([
            CHECKPOINT_DOMAIN,
            self.version,
            self.chain_id,
            self.genesis_hash,
            self.height,
            self.block_hash,
            self.app_hash,
            self.sequence,
        ])

    @classmethod
    def decode(cls, raw: bytes) -> "RollbackCheckpoint":
        if not isinstance(raw, bytes):
            raise CheckpointError("checkpoint payload must be bytes")
        try:
            value = cbor2.loads(raw)
            if canonical_cbor(value) != raw:
                raise CheckpointError("checkpoint payload is not canonical")
            if not isinstance(value, list) or len(value) != 8:
                raise CheckpointError("checkpoint payload has an invalid shape")
            domain, version, chain_id, genesis_hash, height, block_hash, app_hash, sequence = value
            if domain != CHECKPOINT_DOMAIN:
                raise CheckpointError("checkpoint domain mismatch")
            if isinstance(version, bool) or version != CHECKPOINT_VERSION:
                raise CheckpointError("unsupported checkpoint version")
            return cls(
                chain_id=chain_id,
                genesis_hash=genesis_hash,
                height=height,
                block_hash=block_hash,
                app_hash=app_hash,
                sequence=sequence,
                version=version,
            )
        except CheckpointError:
            raise
        except Exception as exc:
            raise CheckpointError("invalid checkpoint encoding") from exc

    @property
    def digest(self) -> bytes:
        """Stable identifier for compare-and-swap; not an authenticity proof."""
        return hashlib.sha256(self.encode()).digest()


@runtime_checkable
class CheckpointAuthority(Protocol):
    """Contract for an independently operated monotonic checkpoint authority.

    Implementations must authenticate the caller, durably serialize updates,
    enforce compare-and-swap, and return only the currently accepted record.
    Local files or databases in the ledger's rollback domain do not satisfy
    this contract merely by implementing these method names.
    """

    def read(self, chain_id: bytes, genesis_hash: bytes) -> bytes | None:
        """Return the latest canonical checkpoint for this chain, if any."""
        ...

    def compare_and_swap(
        self,
        *,
        expected_sequence: int | None,
        expected_digest: bytes | None,
        new_checkpoint: bytes,
    ) -> bool:
        """Atomically accept exactly one valid successor of the expected tip."""
        ...


def validate_successor(
    current: RollbackCheckpoint | None,
    candidate: RollbackCheckpoint,
) -> None:
    """Validate chain identity and strict sequence/height monotonicity."""
    if current is None:
        if candidate.sequence != 1:
            raise CheckpointError("first checkpoint sequence must be 1")
        return
    if candidate.chain_id != current.chain_id:
        raise CheckpointError("checkpoint chain id changed")
    if candidate.genesis_hash != current.genesis_hash:
        raise CheckpointError("checkpoint genesis hash changed")
    if candidate.sequence != current.sequence + 1:
        raise CheckpointError("checkpoint sequence is not the next value")
    if candidate.height <= current.height:
        raise CheckpointError("checkpoint height must advance")
