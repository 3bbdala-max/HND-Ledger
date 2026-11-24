"""HREC bridge to the existing external monotonic-anchor contract.

The caller must supply an independently administered, linearizable,
durable MonotonicStateAnchor. The repository's SQLite adapter is test/reference
only and is NOT a production trust domain.
"""
from __future__ import annotations

from hnd_v02.hrec_journal_model import HRECError, Operation, Phase
from hnd_v02.monotonic_anchor import (
    MonotonicAnchorConflict,
    MonotonicAnchorError,
    MonotonicAnchorUnavailable,
    MonotonicRecord,
    MonotonicStateAnchor,
    advance_monotonic_state,
)

NAMESPACE = "hrec-checkpoint"


def initialize_hrec_anchor(
    anchor: MonotonicStateAnchor, *, genesis_digest: str
) -> MonotonicRecord:
    """Pin the trusted genesis checkpoint once; repeated exact initialization is safe."""
    current = anchor.read_state(NAMESPACE)
    expected = MonotonicRecord(0, genesis_digest)
    if current == expected:
        return expected
    if current is not None:
        raise MonotonicAnchorConflict("HND-HREC-ANCHOR-E-GENESIS-CONFLICT")
    return advance_monotonic_state(
        anchor, NAMESPACE, sequence=0, digest=genesis_digest,
        predecessor_digest=None,
    )


def publish_hrec_checkpoint(
    anchor: MonotonicStateAnchor, operation: Operation
) -> MonotonicRecord:
    """Publish a committed operation with exact-predecessor CAS and lost-reply recovery.

    This function must be called only after durable HND and CometBFT commits have
    both been independently confirmed. It does not itself prove those commits.
    """
    operation.validate()
    if operation.phase != Phase.CONSENSUS_COMMITTED:
        raise HRECError("HREC checkpoint publication requires CONSENSUS_COMMITTED")
    proposed = MonotonicRecord(operation.sequence, operation.checkpoint_digest())
    expected = MonotonicRecord(
        operation.sequence - 1, operation.previous_checkpoint
    )
    if operation.sequence < 1:
        raise HRECError("HREC checkpoint sequence must be positive")

    try:
        current = anchor.read_state(NAMESPACE)
    except Exception as exc:
        raise MonotonicAnchorUnavailable("HND-HREC-ANCHOR-E-READ") from exc

    if current == proposed:
        return proposed
    if current != expected:
        raise MonotonicAnchorConflict("HND-HREC-ANCHOR-E-PREDECESSOR")

    try:
        advanced = anchor.compare_and_advance(NAMESPACE, expected, proposed)
    except Exception as exc:
        # A lost response is an unknown outcome. Read back the exact operation.
        try:
            observed = anchor.read_state(NAMESPACE)
        except Exception as read_exc:
            raise MonotonicAnchorUnavailable(
                "HND-HREC-ANCHOR-E-OUTCOME-UNKNOWN"
            ) from read_exc
        if observed == proposed:
            return proposed
        if observed != expected:
            raise MonotonicAnchorConflict(
                "HND-HREC-ANCHOR-E-POST-TIMEOUT-CONFLICT"
            ) from exc
        # The predecessor is still present: one exact retry is safe.
        try:
            advanced = anchor.compare_and_advance(NAMESPACE, expected, proposed)
        except Exception as retry_exc:
            raise MonotonicAnchorUnavailable(
                "HND-HREC-ANCHOR-E-RETRY-UNKNOWN"
            ) from retry_exc

    if advanced is True:
        return proposed
    try:
        observed = anchor.read_state(NAMESPACE)
    except Exception as exc:
        raise MonotonicAnchorUnavailable(
            "HND-HREC-ANCHOR-E-CAS-OUTCOME-UNKNOWN"
        ) from exc
    if observed == proposed:
        return proposed
    raise MonotonicAnchorConflict("HND-HREC-ANCHOR-E-CAS-CONFLICT")
