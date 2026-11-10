"""Fail-closed contract for externally anchored monotonic HND state.

This module intentionally provides no filesystem or software-only production
anchor. A deployment must inject an independently protected monotonic anchor
(e.g. hardware-backed or remote quorum service) implementing this interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol
import re

_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_MAX_SEQUENCE = (1 << 53) - 1
_ALLOWED_NAMESPACES = frozenset({"trust-manifest", "vsp-profile"})


class MonotonicAnchorError(RuntimeError):
    """The monotonic state could not be safely read or advanced."""


class MonotonicAnchorUnavailable(MonotonicAnchorError):
    """No trustworthy external anchor is available."""


class MonotonicAnchorConflict(MonotonicAnchorError):
    """The expected predecessor changed or a concurrent advance won."""


@dataclass(frozen=True)
class MonotonicRecord:
    sequence: int
    digest: str


class MonotonicStateAnchor(Protocol):
    """Atomic compare-and-advance API supplied by an independent trust domain.

    read_state returns None for an uninitialized namespace, otherwise a record.
    compare_and_advance MUST be linearizable and durable before returning True;
    it must return False if current state differs from expected_current.
    """

    def read_state(self, namespace: str) -> MonotonicRecord | None: ...

    def compare_and_advance(
        self, namespace: str, expected_current: MonotonicRecord | None,
        new_record: MonotonicRecord,
    ) -> bool: ...


def advance_monotonic_state(
    anchor: MonotonicStateAnchor, namespace: str, *,
    sequence: int, digest: str, predecessor_digest: str | None,
) -> MonotonicRecord:
    """Atomically accept exactly the next state, or bootstrap sequence zero.

    The caller must first cryptographically verify the manifest/VSP payload.
    This function enforces ordering only; it does not verify signatures.
    """
    if namespace not in _ALLOWED_NAMESPACES:
        raise MonotonicAnchorError("HND-ANCHOR-E-NAMESPACE")
    if type(sequence) is not int or not 0 <= sequence <= _MAX_SEQUENCE:
        raise MonotonicAnchorError("HND-ANCHOR-E-SEQUENCE")
    if type(digest) is not str or not _HEX64.fullmatch(digest):
        raise MonotonicAnchorError("HND-ANCHOR-E-DIGEST")
    if predecessor_digest is not None and (
        type(predecessor_digest) is not str
        or not _HEX64.fullmatch(predecessor_digest)
    ):
        raise MonotonicAnchorError("HND-ANCHOR-E-PREDECESSOR")

    try:
        current = anchor.read_state(namespace)
    except Exception as exc:
        raise MonotonicAnchorUnavailable("HND-ANCHOR-E-READ") from exc

    if current is None:
        if sequence != 0 or predecessor_digest is not None:
            raise MonotonicAnchorConflict("HND-ANCHOR-E-BOOTSTRAP")
    else:
        if type(current) is not MonotonicRecord:
            raise MonotonicAnchorUnavailable("HND-ANCHOR-E-RECORD")
        if (type(current.sequence) is not int
                or not 0 <= current.sequence <= _MAX_SEQUENCE
                or type(current.digest) is not str
                or not _HEX64.fullmatch(current.digest)):
            raise MonotonicAnchorUnavailable("HND-ANCHOR-E-CORRUPT")
        if sequence != current.sequence + 1:
            raise MonotonicAnchorConflict("HND-ANCHOR-E-SEQUENCE-ROLLBACK")
        if predecessor_digest != current.digest:
            raise MonotonicAnchorConflict("HND-ANCHOR-E-PREDECESSOR")

    new_record = MonotonicRecord(sequence, digest)
    try:
        advanced = anchor.compare_and_advance(namespace, current, new_record)
    except Exception as exc:
        raise MonotonicAnchorUnavailable("HND-ANCHOR-E-COMMIT") from exc
    if advanced is not True:
        raise MonotonicAnchorConflict("HND-ANCHOR-E-CONCURRENT-ADVANCE")
    return new_record
