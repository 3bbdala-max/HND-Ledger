"""Offline synthetic anti-rollback protocol model.

This module is deliberately NOT a production trust anchor. It uses an in-memory
anchor and a fixed synthetic MAC key solely to exercise protocol state machines.
It must never be connected to CometBFT, a signer, a filesystem, HSM, TPM, KMS,
network service, or real validator identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import threading
from typing import Any


class ReferenceModelError(RuntimeError):
    """A fail-closed reference-model rejection."""


class AnchorUnavailable(ReferenceModelError):
    pass


class StaleTransition(ReferenceModelError):
    pass


class HistoricalOperation(ReferenceModelError):
    """The operation committed, but is no longer the current anchor state."""


class AmbiguousCommit(ReferenceModelError):
    """The caller did not receive the result; reconcile by operation ID."""


_FAKE_MAC_KEY = b"HND-OFFLINE-TEST-ONLY-NOT-A-SECRET"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _mac(value: Any) -> str:
    return hmac.new(_FAKE_MAC_KEY, _canonical(value), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class AnchorRecord:
    network_id: str
    genesis_hash: str
    validator_id: str
    signer_id: str
    schema_version: int
    height: int
    round: int
    step: int
    sequence: int
    state_digest: str
    generation_id: str
    predecessor_digest: str
    operation_id: str
    status: str
    mac: str

    def unsigned(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "mac"}


@dataclass(frozen=True)
class OperationOutcome:
    """Historical operation result plus an explicit latest-anchor comparison."""

    record: AnchorRecord
    is_current: bool
    current_sequence: int | None
    current_operation_id: str | None


def _transaction_digest(record: AnchorRecord) -> str:
    return _digest({
        key: value for key, value in record.unsigned().items()
        if key != "status"
    })


class SyntheticAnchor:
    """Thread-safe in-memory compare-and-swap anchor; no durability guarantee."""

    def __init__(self):
        self._lock = threading.Lock()
        self._record: AnchorRecord | None = None
        # Keep the last committed generation separately while a newer
        # operation is PREPARED. This is an in-memory model, not durable storage.
        self._last_committed: AnchorRecord | None = None
        self._operations: dict[str, tuple[str, AnchorRecord]] = {}
        # Shared by every model instance using this anchor; deliberately in-memory.
        self._host_epoch = 1
        self._active_host = "synthetic-host-1"
        self.available = True

    def read(self) -> AnchorRecord | None:
        with self._lock:
            if not self.available:
                raise AnchorUnavailable("synthetic anchor unavailable")
            return self._record

    def compare_and_swap(self, expected_sequence: int, record: AnchorRecord, *,
                          host_id: str, host_epoch: int) -> AnchorRecord:
        """Atomically fence the caller and transition the anchor record."""
        with self._lock:
            if not self.available:
                raise AnchorUnavailable("synthetic anchor unavailable")
            if host_id != self._active_host or host_epoch != self._host_epoch:
                raise StaleTransition("fenced host cannot change anchor state")
            prior = self._operations.get(record.operation_id)
            transaction_digest = _transaction_digest(record)
            if prior:
                if prior[0] != transaction_digest:
                    raise ReferenceModelError("operation ID reused with conflicting payload")
                if prior[1].status == "COMMITTED":
                    return prior[1]
                if prior[1].status == "PREPARED" and record.status == "COMMITTED":
                    if self._record != prior[1] or record.sequence != prior[1].sequence:
                        raise StaleTransition("prepared operation is no longer the current anchor record")
                    self._record = record
                    self._last_committed = record
                    self._operations[record.operation_id] = (transaction_digest, record)
                    return record
                if prior[1] == record:
                    return prior[1]
                raise ReferenceModelError("invalid repeated operation transition")
            current_sequence = self._record.sequence if self._record else 0
            if current_sequence != expected_sequence:
                raise StaleTransition("anchor compare-and-swap predecessor is stale")
            # A PREPARED record is the single in-flight transition. A later
            # operation must not supersede it: doing so would strand the first
            # operation outside the current anchor record and make recovery
            # ambiguous. Exact retries and its PREPARED->COMMITTED transition
            # were handled above by the operation-ID branch.
            if self._record is not None and self._record.status == "PREPARED":
                raise ReferenceModelError(
                    "another operation is already PREPARED; only that operation may be retried or committed"
                )
            if record.sequence != expected_sequence + 1:
                raise StaleTransition("anchor sequence must increase by exactly one")
            expected_predecessor = _digest(self._record.unsigned()) if self._record else "0" * 64
            if not hmac.compare_digest(record.predecessor_digest, expected_predecessor):
                raise StaleTransition("anchor predecessor digest does not match current record")
            if self._record is not None:
                previous_hrs = (self._record.height, self._record.round, self._record.step)
                proposed_hrs = (record.height, record.round, record.step)
                if proposed_hrs <= previous_hrs:
                    raise StaleTransition("HRS must strictly advance beyond the anchored state")
            if record.status != "PREPARED":
                raise ReferenceModelError("new anchor operation must begin PREPARED")
            self._record = record
            self._operations[record.operation_id] = (transaction_digest, record)
            return record

    def read_last_committed(self) -> AnchorRecord | None:
        """Return the last committed record, even while a newer prepare is pending."""
        with self._lock:
            if not self.available:
                raise AnchorUnavailable("synthetic anchor unavailable")
            return self._last_committed

    def host_epoch(self) -> int:
        with self._lock:
            if not self.available:
                raise AnchorUnavailable("synthetic anchor unavailable")
            return self._host_epoch

    def active_host(self) -> str:
        with self._lock:
            if not self.available:
                raise AnchorUnavailable("synthetic anchor unavailable")
            return self._active_host

    def host_is_current(self, host_id: str, epoch: int) -> bool:
        with self._lock:
            if not self.available:
                raise AnchorUnavailable("synthetic anchor unavailable")
            return host_id == self._active_host and epoch == self._host_epoch

    def fence_host(self, new_host_id: str) -> int:
        with self._lock:
            if not self.available:
                raise AnchorUnavailable("synthetic anchor unavailable")
            if not new_host_id or new_host_id == self._active_host:
                raise ValueError("new distinct host ID required")
            self._host_epoch += 1
            self._active_host = new_host_id
            return self._host_epoch

    def operation(self, operation_id: str) -> AnchorRecord | None:
        with self._lock:
            if not self.available:
                raise AnchorUnavailable("synthetic anchor unavailable")
            item = self._operations.get(operation_id)
            return item[1] if item else None


class OfflineAntiRollbackModel:
    """Protocol simulator with immutable synthetic generations and host fencing."""

    def __init__(self, anchor: SyntheticAnchor, *, network_id: str,
                 genesis_hash: str, validator_id: str, signer_id: str):
        self.anchor = anchor
        self.identity = (network_id, genesis_hash, validator_id, signer_id)
        self.generations: dict[str, dict] = {}
        self._prepared: dict[str, AnchorRecord] = {}
        self._host_epoch = anchor.host_epoch()
        self._active_host = anchor.active_host()

    def _validate_identity(self, record: AnchorRecord) -> None:
        if (record.network_id, record.genesis_hash, record.validator_id, record.signer_id) != self.identity:
            raise ReferenceModelError("chain/genesis/validator/signer identity mismatch")
        if record.schema_version != 1:
            raise ReferenceModelError("unsupported anchor schema version")
        if not hmac.compare_digest(record.mac, _mac(record.unsigned())):
            raise ReferenceModelError("synthetic anchor record authentication failed")

    def prepare(self, *, operation_id: str, host_id: str, state: dict,
                height: int, round: int = 0, step: int = 1) -> AnchorRecord:
        """Prepare/retry an operation; a COMMITTED return is historical outcome only."""
        if not operation_id or not host_id:
            raise ValueError("operation_id and host_id are required")
        if not self.anchor.host_is_current(host_id, self._host_epoch):
            raise ReferenceModelError("fenced host cannot prepare state")
        # Match the pinned CometBFT v0.40.0 FilePV HRS storage widths:
        # height=int64, round=int32, step=int8. FilePV uses stepNone=0
        # only as the initial sentinel, then propose=1, prevote=2,
        # precommit=3 for actual signing operations.
        if not isinstance(height, int) or isinstance(height, bool) or not 0 <= height <= (2**63 - 1):
            raise ValueError("height must be an integer in the CometBFT int64 range")
        if not isinstance(round, int) or isinstance(round, bool) or not 0 <= round <= (2**31 - 1):
            raise ValueError("round must be an integer in the CometBFT int32 range")
        if not isinstance(step, int) or isinstance(step, bool) or step not in (0, 1, 2, 3):
            raise ValueError("step must be 0 (initial sentinel), 1 (propose), 2 (prevote), or 3 (precommit)")
        if step == 0 and (height, round) != (0, 0):
            raise ValueError("step 0 is reserved for the initial (height=0, round=0) sentinel")
        current = self.anchor.read()
        existing = self.anchor.operation(operation_id)
        if existing is not None:
            self._validate_identity(existing)
            if existing.status == "PREPARED" and current != existing:
                raise ReferenceModelError(
                    "prepared operation is no longer the current anchor record"
                )
            if (
                existing.state_digest != _digest(state)
                or existing.height != height
                or existing.round != round
                or existing.step != step
            ):
                raise ReferenceModelError("operation ID reused with conflicting prepare payload")
            existing_state = self.generations.get(existing.generation_id)
            if existing_state is None or _digest(existing_state) != existing.state_digest:
                raise ReferenceModelError("existing operation generation missing or corrupted")
            if existing.status not in ("PREPARED", "COMMITTED"):
                raise ReferenceModelError("existing operation has invalid status")
            self._prepared[operation_id] = existing
            return existing
        expected = current.sequence if current else 0
        predecessor = _digest(current.unsigned()) if current else "0" * 64
        generation_id = "gen-" + _digest({"operation": operation_id, "state": state})[:24]
        if generation_id in self.generations and self.generations[generation_id] != state:
            raise ReferenceModelError("immutable generation collision")
        self.generations.setdefault(generation_id, json.loads(_canonical(state)))
        fields = dict(
            network_id=self.identity[0], genesis_hash=self.identity[1],
            validator_id=self.identity[2], signer_id=self.identity[3],
            schema_version=1, height=height, round=round, step=step,
            sequence=expected + 1, state_digest=_digest(state),
            generation_id=generation_id, predecessor_digest=predecessor,
            operation_id=operation_id, status="PREPARED",
        )
        record = AnchorRecord(**fields, mac=_mac(fields))
        stored = self.anchor.compare_and_swap(
            expected, record, host_id=host_id, host_epoch=self._host_epoch
        )
        self._prepared[operation_id] = stored
        return stored

    def commit(self, operation_id: str, *, simulate_lost_reply: bool = False) -> AnchorRecord:
        """Commit/retry one operation; use confirm_current for signing readiness."""
        if not self.anchor.host_is_current(self._active_host, self._host_epoch):
            raise ReferenceModelError("fenced host cannot commit state")
        prepared = self._prepared.get(operation_id) or self.anchor.operation(operation_id)
        if prepared is None:
            raise ReferenceModelError("unknown prepared operation")
        self._validate_identity(prepared)
        if prepared.status == "COMMITTED":
            return prepared
        if prepared.status != "PREPARED":
            raise ReferenceModelError("operation is not prepared")
        state = self.generations.get(prepared.generation_id)
        if state is None or _digest(state) != prepared.state_digest:
            raise ReferenceModelError("prepared generation missing or corrupted")
        committed_fields = prepared.unsigned()
        committed_fields["status"] = "COMMITTED"
        committed = AnchorRecord(**committed_fields, mac=_mac(committed_fields))
        result = self.anchor.compare_and_swap(
            prepared.sequence - 1, committed,
            host_id=self._active_host, host_epoch=self._host_epoch,
        )
        if simulate_lost_reply:
            raise AmbiguousCommit("commit may have completed; reconcile by operation ID")
        return result

    def reconcile(self, operation_id: str) -> AnchorRecord:
        """Resolve the operation's historical outcome, not current-state authorization."""
        record = self.anchor.operation(operation_id)
        if record is None:
            raise ReferenceModelError("operation not present at anchor")
        self._validate_identity(record)
        if record.status != "COMMITTED":
            raise ReferenceModelError("operation remains uncommitted; signing disabled")
        state = self.generations.get(record.generation_id)
        if state is None or _digest(state) != record.state_digest:
            raise ReferenceModelError("committed generation unavailable or corrupted")
        return record

    def operation_outcome(self, operation_id: str) -> OperationOutcome:
        """Report an operation's outcome and whether it is still the latest anchor state.

        A historical COMMITTED record is not current-state or signing authorization.
        Anchor unavailability propagates as AnchorUnavailable (unknown/blocked).
        """
        historical = self.anchor.operation(operation_id)
        if historical is None:
            raise ReferenceModelError("operation not present at anchor")
        self._validate_identity(historical)
        current = self.anchor.read()
        if current is not None:
            self._validate_identity(current)
        same_identity = current is not None and (
            current.network_id == historical.network_id
            and current.genesis_hash == historical.genesis_hash
            and current.validator_id == historical.validator_id
            and current.signer_id == historical.signer_id
            and current.schema_version == historical.schema_version
        )
        is_current = bool(
            current is not None
            and current.operation_id == historical.operation_id
            and current.sequence == historical.sequence
            and hmac.compare_digest(
                _transaction_digest(current), _transaction_digest(historical)
            )
            and hmac.compare_digest(current.state_digest, historical.state_digest)
            and same_identity
            and current.status == historical.status
        )
        return OperationOutcome(
            record=historical,
            is_current=is_current,
            current_sequence=current.sequence if current is not None else None,
            current_operation_id=current.operation_id if current is not None else None,
        )

    def confirm_current(self, operation_id: str) -> AnchorRecord:
        """Require a matching latest COMMITTED anchor record and intact generation."""
        outcome = self.operation_outcome(operation_id)
        record = outcome.record
        if not outcome.is_current:
            raise HistoricalOperation(
                "operation committed historically but is not the current anchor record"
            )
        if record.status != "COMMITTED":
            raise ReferenceModelError("current anchor operation is not COMMITTED")
        state = self.generations.get(record.generation_id)
        if state is None or _digest(state) != record.state_digest:
            raise ReferenceModelError("current committed generation missing or corrupted")
        return record

    def restore(self, generation_id: str, *, dual_control: bool = False) -> dict:
        if not dual_control:
            raise ReferenceModelError("restore requires dual control")
        record = self.anchor.read()
        if record is None:
            raise ReferenceModelError("no trusted committed anchor record")
        self._validate_identity(record)
        if record.status != "COMMITTED" or record.generation_id != generation_id:
            raise ReferenceModelError("restore target is not the anchored committed generation")
        state = self.generations.get(generation_id)
        if state is None or _digest(state) != record.state_digest:
            raise ReferenceModelError("restore generation digest mismatch")
        return json.loads(_canonical(state))

    def fence_and_takeover(self, new_host_id: str) -> int:
        epoch = self.anchor.fence_host(new_host_id)
        self._host_epoch = epoch
        self._active_host = new_host_id
        return epoch

    def signing_allowed(self, host_id: str) -> bool:
        try:
            record = self.anchor.read()
            if record is None or record.status != "COMMITTED":
                return False
            current = self.confirm_current(record.operation_id)
            return (
                current == record
                and self.anchor.host_is_current(host_id, self._host_epoch)
            )
        except ReferenceModelError:
            return False
