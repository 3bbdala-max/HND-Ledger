"""Canonical rollback checkpoints, signatures, and authority contract.

This module provides deterministic record and signature primitives only. It
does not implement a production authority, durable monotonic storage, caller
authentication, or automatic enforcement by the ledger.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .protocol import canonical_cbor

CHECKPOINT_DOMAIN = "HND-ROLLBACK-CHECKPOINT-V1"
CHECKPOINT_SIGNATURE_DOMAIN = b"HND-ROLLBACK-CHECKPOINT-SIGN-V1\\x00"
CHECKPOINT_VERSION = 1
_ENVELOPE_DOMAIN = "HND-SIGNED-ROLLBACK-CHECKPOINT-V1"
_HASH_BYTES = 32
_SIGNATURE_BYTES = 64


class CheckpointError(ValueError):
    """Raised for malformed, unauthenticated, or inconsistent checkpoints."""


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
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version != CHECKPOINT_VERSION:
            raise CheckpointError("unsupported checkpoint version")

    def encode(self) -> bytes:
        return canonical_cbor([
            CHECKPOINT_DOMAIN, self.version, self.chain_id, self.genesis_hash,
            self.height, self.block_hash, self.app_hash, self.sequence,
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
            if isinstance(version, bool) or not isinstance(version, int) or version != CHECKPOINT_VERSION:
                raise CheckpointError("unsupported checkpoint version")
            return cls(chain_id, genesis_hash, height, block_hash, app_hash, sequence, version)
        except CheckpointError:
            raise
        except Exception as exc:
            raise CheckpointError("invalid checkpoint encoding") from exc

    @property
    def digest(self) -> bytes:
        """Stable identifier for CAS; it is not an authenticity proof."""
        return hashlib.sha256(self.encode()).digest()


@dataclass(frozen=True, slots=True)
class SignedRollbackCheckpoint:
    """Checkpoint payload plus its Ed25519 signer identity and signature."""

    checkpoint: RollbackCheckpoint
    public_key: bytes
    signature: bytes

    def __post_init__(self) -> None:
        _hash(self.public_key, "signer public key")
        if not isinstance(self.signature, bytes) or len(self.signature) != _SIGNATURE_BYTES:
            raise CheckpointError("checkpoint signature must be exactly 64 bytes")

    def encode(self) -> bytes:
        return canonical_cbor([
            _ENVELOPE_DOMAIN, CHECKPOINT_VERSION, self.checkpoint.encode(),
            self.public_key, self.signature,
        ])

    @classmethod
    def decode(cls, raw: bytes) -> "SignedRollbackCheckpoint":
        if not isinstance(raw, bytes):
            raise CheckpointError("signed checkpoint must be bytes")
        try:
            value = cbor2.loads(raw)
            if canonical_cbor(value) != raw:
                raise CheckpointError("signed checkpoint is not canonical")
            if not isinstance(value, list) or len(value) != 5:
                raise CheckpointError("signed checkpoint has an invalid shape")
            domain, version, payload, public_key, signature = value
            if domain != _ENVELOPE_DOMAIN:
                raise CheckpointError("signed checkpoint envelope domain mismatch")
            if isinstance(version, bool) or not isinstance(version, int) or version != CHECKPOINT_VERSION:
                raise CheckpointError("unsupported signed checkpoint version")
            return cls(RollbackCheckpoint.decode(payload), public_key, signature)
        except CheckpointError:
            raise
        except Exception as exc:
            raise CheckpointError("invalid signed checkpoint encoding") from exc


def sign_checkpoint(
    checkpoint: RollbackCheckpoint, private_key: Ed25519PrivateKey
) -> SignedRollbackCheckpoint:
    if not isinstance(checkpoint, RollbackCheckpoint):
        raise CheckpointError("checkpoint has an invalid type")
    if not isinstance(private_key, Ed25519PrivateKey):
        raise CheckpointError("signing key must be an Ed25519 private key")
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signature = private_key.sign(CHECKPOINT_SIGNATURE_DOMAIN + checkpoint.encode())
    return SignedRollbackCheckpoint(checkpoint, public_key, signature)


def verify_signed_checkpoint(
    signed: SignedRollbackCheckpoint | bytes, trusted_public_key: bytes
) -> RollbackCheckpoint:
    """Verify both the pinned authority identity and Ed25519 signature."""
    if isinstance(signed, bytes):
        signed = SignedRollbackCheckpoint.decode(signed)
    if not isinstance(signed, SignedRollbackCheckpoint):
        raise CheckpointError("signed checkpoint has an invalid type")
    _hash(trusted_public_key, "trusted public key")
    if signed.public_key != trusted_public_key:
        raise CheckpointError("checkpoint signer is not trusted")
    try:
        Ed25519PublicKey.from_public_bytes(trusted_public_key).verify(
            signed.signature,
            CHECKPOINT_SIGNATURE_DOMAIN + signed.checkpoint.encode(),
        )
    except (InvalidSignature, ValueError) as exc:
        raise CheckpointError("checkpoint signature verification failed") from exc
    return signed.checkpoint


@runtime_checkable
class CheckpointAuthority(Protocol):
    """Contract for an independently operated monotonic checkpoint authority.

    Implementations must authenticate callers, durably serialize updates, and
    enforce atomic compare-and-swap. A local file/database in the ledger's
    rollback domain does not satisfy this contract.
    """

    def read(self, chain_id: bytes, genesis_hash: bytes) -> bytes | None:
        """Return the latest signed checkpoint for this chain, if any."""
        ...

    def compare_and_swap(
        self,
        *,
        expected_sequence: int | None,
        expected_digest: bytes | None,
        new_checkpoint: bytes,
    ) -> bool:
        """Atomically accept exactly one verified successor of the expected tip."""
        ...


def validate_successor(
    current: RollbackCheckpoint | None, candidate: RollbackCheckpoint
) -> None:
    """Validate chain identity and strict sequence/height monotonicity."""
    if not isinstance(candidate, RollbackCheckpoint):
        raise CheckpointError("candidate checkpoint has an invalid type")
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
