"""Canonical rollback checkpoints, signatures, and authority contract.

This module provides deterministic record and signature primitives only. It
does not implement a production authority, durable monotonic storage, caller
authentication, or automatic enforcement by the ledger.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
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
CHECKPOINT_SIGNATURE_DOMAIN = b"HND-ROLLBACK-CHECKPOINT-SIGN-V1\x00"
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
        if not isinstance(self.checkpoint, RollbackCheckpoint):
            raise CheckpointError("signed checkpoint payload has an invalid type")
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
        """Atomically accept one successor; exact retries of an accepted candidate succeed."""
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


class CheckpointRelation(str, Enum):
    """Relationship between a local replayed tip and the accepted remote tip."""

    UNANCHORED = "unanchored"
    MATCH = "match"
    LOCAL_BEHIND = "local_behind"
    LOCAL_AHEAD_UNVERIFIED = "local_ahead_unverified"
    DIVERGED = "diverged"


@dataclass(frozen=True, slots=True)
class CheckpointAssessment:
    """Fail-closed startup assessment; only an exact match permits writes."""

    relation: CheckpointRelation
    reason: str

    @property
    def writes_allowed(self) -> bool:
        return self.relation is CheckpointRelation.MATCH


def assess_local_tip(
    checkpoint: RollbackCheckpoint | None,
    *,
    chain_id: bytes,
    genesis_hash: bytes,
    height: int,
    block_hash: bytes,
    app_hash: bytes,
    checkpoint_ancestor_block_hash: bytes | None = None,
    checkpoint_ancestor_app_hash: bytes | None = None,
) -> CheckpointAssessment:
    """Compare local replay result with the latest independently trusted anchor.

    When the local database is ahead, callers may provide the locally replayed
    block and application commitments at the checkpoint height. A mismatch
    proves divergence. A match proves that the trusted checkpoint is an
    ancestor of the replayed local chain, but the suffix still requires an
    explicit recovery decision before writes are enabled.
    """
    _hash(chain_id, "local chain_id")
    _hash(genesis_hash, "local genesis_hash")
    _uint(height, "local height")
    _hash(block_hash, "local block_hash")
    _hash(app_hash, "local app_hash")

    if (checkpoint_ancestor_block_hash is None) != (checkpoint_ancestor_app_hash is None):
        raise CheckpointError("both checkpoint ancestor commitments must be supplied together")
    if checkpoint_ancestor_block_hash is not None:
        _hash(checkpoint_ancestor_block_hash, "checkpoint ancestor block hash")
        _hash(checkpoint_ancestor_app_hash, "checkpoint ancestor app hash")

    if checkpoint is None:
        return CheckpointAssessment(
            CheckpointRelation.UNANCHORED,
            "no independently trusted checkpoint is configured",
        )
    if not isinstance(checkpoint, RollbackCheckpoint):
        raise CheckpointError("trusted checkpoint has an invalid type")
    if chain_id != checkpoint.chain_id:
        raise CheckpointError("local chain id does not match trusted checkpoint")
    if genesis_hash != checkpoint.genesis_hash:
        raise CheckpointError("local genesis hash does not match trusted checkpoint")

    if height < checkpoint.height:
        return CheckpointAssessment(
            CheckpointRelation.LOCAL_BEHIND,
            "local database is behind the independently trusted checkpoint",
        )
    if height > checkpoint.height:
        if checkpoint_ancestor_block_hash is not None and (
            checkpoint_ancestor_block_hash != checkpoint.block_hash
            or checkpoint_ancestor_app_hash != checkpoint.app_hash
        ):
            return CheckpointAssessment(
                CheckpointRelation.DIVERGED,
                "local chain does not contain the trusted checkpoint at its height",
            )
        if checkpoint_ancestor_block_hash is None:
            reason = (
                "local suffix and checkpoint ancestry have not been verified; "
                "explicit recovery is required"
            )
        else:
            reason = (
                "trusted checkpoint ancestry matches, but the local suffix "
                "still requires explicit verification and recovery"
            )
        return CheckpointAssessment(
            CheckpointRelation.LOCAL_AHEAD_UNVERIFIED,
            reason,
        )
    if block_hash != checkpoint.block_hash or app_hash != checkpoint.app_hash:
        return CheckpointAssessment(
            CheckpointRelation.DIVERGED,
            "local block or application commitment conflicts at the trusted height",
        )
    return CheckpointAssessment(
        CheckpointRelation.MATCH,
        "local chain tip exactly matches the independently trusted checkpoint",
    )



def read_and_assess_checkpoint(
    authority: CheckpointAuthority,
    trusted_public_key: bytes,
    *,
    chain_id: bytes,
    genesis_hash: bytes,
    height: int,
    block_hash: bytes,
    app_hash: bytes,
    checkpoint_ancestor_block_hash: bytes | None = None,
    checkpoint_ancestor_app_hash: bytes | None = None,
) -> CheckpointAssessment:
    """Read, authenticate, and compare an independent checkpoint.

    Authority read failures are surfaced as CheckpointError. They must never
    be converted into an unanchored/allow-writes fallback. A missing record is
    explicitly classified as UNANCHORED, which is not write-eligible.
    """
    try:
        raw_checkpoint = authority.read(chain_id, genesis_hash)
    except Exception as exc:
        raise CheckpointError(
            "checkpoint authority read failed; refusing unanchored fallback"
        ) from exc

    if raw_checkpoint is None:
        checkpoint = None
    elif isinstance(raw_checkpoint, bytes):
        checkpoint = verify_signed_checkpoint(raw_checkpoint, trusted_public_key)
    else:
        raise CheckpointError("checkpoint authority returned an invalid record type")

    return assess_local_tip(
        checkpoint,
        chain_id=chain_id,
        genesis_hash=genesis_hash,
        height=height,
        block_hash=block_hash,
        app_hash=app_hash,
        checkpoint_ancestor_block_hash=checkpoint_ancestor_block_hash,
        checkpoint_ancestor_app_hash=checkpoint_ancestor_app_hash,
    )



def publish_checkpoint(
    authority: CheckpointAuthority,
    trusted_public_key: bytes,
    signed_candidate: bytes,
) -> RollbackCheckpoint:
    """Publish one signed successor using CAS and safe idempotent retry.

    The caller must invoke this only after the corresponding consensus block
    has been durably committed locally. A false CAS result is reconciled by
    rereading the authority: an exact already-accepted candidate is success;
    any different latest checkpoint is a conflict. This helper does not make
    the local SQLite commit and remote authority update atomic.
    """
    candidate = verify_signed_checkpoint(signed_candidate, trusted_public_key)

    try:
        current_raw = authority.read(candidate.chain_id, candidate.genesis_hash)
    except Exception as exc:
        raise CheckpointError("checkpoint authority read failed before publish") from exc

    if current_raw is None:
        current = None
    elif isinstance(current_raw, bytes):
        current = verify_signed_checkpoint(current_raw, trusted_public_key)
        if (current.chain_id != candidate.chain_id
                or current.genesis_hash != candidate.genesis_hash):
            raise CheckpointError("authority returned a checkpoint for another chain")
    else:
        raise CheckpointError("checkpoint authority returned an invalid record type")

    if current is not None and candidate.digest == current.digest:
        return candidate
    validate_successor(current, candidate)

    cas_error = None
    try:
        accepted = authority.compare_and_swap(
            expected_sequence=None if current is None else current.sequence,
            expected_digest=None if current is None else current.digest,
            new_checkpoint=signed_candidate,
        )
    except Exception as exc:
        # A timeout can happen after the authority committed but before the
        # acknowledgement reached us. Resolve the outcome by reading again.
        cas_error = exc
        accepted = False
    if not isinstance(accepted, bool):
        raise CheckpointError("checkpoint authority returned an invalid CAS result")
    if accepted:
        return candidate

    # The request may have succeeded remotely while its acknowledgement was
    # lost, or a competing writer may have advanced the authority.
    try:
        latest_raw = authority.read(candidate.chain_id, candidate.genesis_hash)
    except Exception as exc:
        raise CheckpointError(
            "checkpoint CAS outcome is unknown; authority reread failed"
        ) from (cas_error or exc)
    if not isinstance(latest_raw, bytes):
        if cas_error is not None:
            raise CheckpointError(
                "checkpoint CAS outcome is unknown; no accepted record was returned"
            ) from cas_error
        raise CheckpointError("checkpoint CAS conflict; no matching accepted record")
    latest = verify_signed_checkpoint(latest_raw, trusted_public_key)
    if (latest.chain_id == candidate.chain_id
            and latest.genesis_hash == candidate.genesis_hash
            and latest.digest == candidate.digest):
        return candidate
    if cas_error is not None:
        raise CheckpointError(
            "checkpoint CAS outcome is unknown; authority contains a different record"
        ) from cas_error
    raise CheckpointError("checkpoint compare-and-swap conflict")



def assess_local_chain(
    authority: CheckpointAuthority,
    trusted_public_key: bytes,
    chain: object,
) -> CheckpointAssessment:
    """Authenticate the external anchor and assess a replay-verified LocalChain.

    This is an explicit integration helper, not an automatic startup hook.
    The supplied LocalChain must already have completed its normal replay and
    integrity checks. It never enables writes for an unanchored, behind,
    ahead, or divergent database.
    """
    from .chain import LocalChain, state_commitment

    if not isinstance(chain, LocalChain):
        raise CheckpointError("local chain object has an invalid type")
    try:
        chain_id = chain.state.chain_id
        genesis_hash, _ = chain.checkpoint_ancestor_commitments(0)
        height = chain.height
        block_hash = chain.tip_hash
        app_hash = state_commitment(chain.state)
    except Exception as exc:
        raise CheckpointError("unable to obtain verified local chain commitments") from exc

    try:
        raw_checkpoint = authority.read(chain_id, genesis_hash)
    except Exception as exc:
        raise CheckpointError(
            "checkpoint authority read failed; refusing local chain startup"
        ) from exc

    if raw_checkpoint is None:
        checkpoint = None
    elif isinstance(raw_checkpoint, bytes):
        checkpoint = verify_signed_checkpoint(raw_checkpoint, trusted_public_key)
    else:
        raise CheckpointError("checkpoint authority returned an invalid record type")

    ancestor_block_hash = None
    ancestor_app_hash = None
    if checkpoint is not None and checkpoint.height <= height:
        try:
            ancestor_block_hash, ancestor_app_hash = (
                chain.checkpoint_ancestor_commitments(checkpoint.height)
            )
        except Exception as exc:
            raise CheckpointError(
                "unable to verify trusted checkpoint ancestry in local chain"
            ) from exc

    return assess_local_tip(
        checkpoint,
        chain_id=chain_id,
        genesis_hash=genesis_hash,
        height=height,
        block_hash=block_hash,
        app_hash=app_hash,
        checkpoint_ancestor_block_hash=ancestor_block_hash,
        checkpoint_ancestor_app_hash=ancestor_app_hash,
    )
