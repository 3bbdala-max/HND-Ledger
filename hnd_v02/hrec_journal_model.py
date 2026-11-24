"""Experimental HREC journal state machine.

This module is a deterministic protocol model only. It is NOT a durable journal,
checkpoint authority, CometBFT integration, signer fence, or production control.
Persistence and independent authority must be supplied by separately reviewed
components before this state machine can authorize any service.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum
import hashlib
import json
import re
from typing import Dict, Optional


_HEX_256 = re.compile(r"^[0-9a-f]{64}$")


class HRECError(ValueError):
    """Invalid or conflicting HREC journal operation."""


class Phase(IntEnum):
    PREPARED = 1
    APPLICATION_COMMITTED = 2
    CONSENSUS_COMMITTED = 3
    CHECKPOINT_PUBLISHED = 4
    FINALIZED = 5


@dataclass(frozen=True)
class Operation:
    operation_id: str
    chain_id: str
    height: int
    block_hash: str
    app_state_hash: str
    consensus_state_hash: str
    previous_checkpoint: str
    sequence: int
    phase: Phase = Phase.PREPARED

    def validate(self) -> None:
        if not self.operation_id or not self.chain_id:
            raise HRECError("operation_id and chain_id are required")
        if self.height < 1 or self.sequence < 1:
            raise HRECError("height and sequence must be positive")
        for name in ("block_hash", "app_state_hash",
                     "consensus_state_hash", "previous_checkpoint"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _HEX_256.fullmatch(value):
                raise HRECError(f"{name} must be a lowercase SHA-256 hex digest")
        if not isinstance(self.phase, Phase):
            raise HRECError("phase must be a Phase value")

    def fingerprint(self) -> str:
        payload = asdict(self)
        payload["phase"] = int(self.phase)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class HRECJournalModel:
    """In-memory transition validator; never use as an independent authority."""

    def __init__(self) -> None:
        self._operations: Dict[str, Operation] = {}
        self._latest_sequence = 0
        self._latest_checkpoint: Optional[str] = None

    def prepare(self, operation: Operation) -> Operation:
        operation.validate()
        existing = self._operations.get(operation.operation_id)
        if existing is not None:
            if existing == operation:
                return existing  # exact retry is idempotent
            raise HRECError("operation_id reused with different contents")
        if operation.sequence != self._latest_sequence + 1:
            raise HRECError("sequence must be exactly the next sequence")
        if self._latest_checkpoint is not None:
            if operation.previous_checkpoint != self._latest_checkpoint:
                raise HRECError("previous checkpoint does not match latest checkpoint")
        self._operations[operation.operation_id] = operation
        return operation

    def advance(self, operation_id: str, phase: Phase) -> Operation:
        current = self._operations.get(operation_id)
        if current is None:
            raise HRECError("unknown operation")
        if phase == current.phase:
            return current
        if int(phase) != int(current.phase) + 1:
            raise HRECError("phase transition must advance exactly one step")
        updated = Operation(
            operation_id=current.operation_id,
            chain_id=current.chain_id,
            height=current.height,
            block_hash=current.block_hash,
            app_state_hash=current.app_state_hash,
            consensus_state_hash=current.consensus_state_hash,
            previous_checkpoint=current.previous_checkpoint,
            sequence=current.sequence,
            phase=phase,
        )
        self._operations[operation_id] = updated
        if phase == Phase.FINALIZED:
            self._latest_sequence = updated.sequence
            self._latest_checkpoint = updated.fingerprint()
        return updated

    def get(self, operation_id: str) -> Optional[Operation]:
        return self._operations.get(operation_id)

    @property
    def latest_sequence(self) -> int:
        return self._latest_sequence

    @property
    def latest_checkpoint(self) -> Optional[str]:
        return self._latest_checkpoint
