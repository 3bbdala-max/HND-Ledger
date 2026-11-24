"""Explicit crash recovery for a single pending HREC operation.

Recovery is never inferred from the local journal alone. The caller must read
authoritative durable HND and CometBFT state. Recovery advances only the exact
operation already prepared in the journal and never invents a replacement.
"""
from __future__ import annotations

from hnd_v02.hrec_journal_model import HRECError, Phase
from hnd_v02.hrec_checkpoint_anchor import (
    NAMESPACE, publish_hrec_checkpoint,
)
from hnd_v02.hrec_startup_gate import (
    CometBFTCommittedState, HNDApplicationState,
)
from hnd_v02.monotonic_anchor import (
    MonotonicAnchorConflict, MonotonicRecord, MonotonicStateAnchor,
)


class HRECRecoveryError(RuntimeError):
    """Pending HREC operation cannot be recovered without ambiguity."""


def recover_pending_hrec_operation(
    *,
    anchor: MonotonicStateAnchor,
    journal,
    hnd: HNDApplicationState,
    comet: CometBFTCommittedState,
):
    """Reconcile one pending operation against both durable stores and remote CAS.

    This is an explicit operator/service recovery operation, not a normal
    startup side effect. Any mismatch or unknown remote outcome fails closed.
    """
    operation = journal.latest_operation()
    if operation is None:
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-NO-PENDING-OPERATION")
    if operation.phase == Phase.FINALIZED:
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-NOTHING-TO-RECOVER")
    if hnd.chain_id != comet.chain_id or operation.chain_id != hnd.chain_id:
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-CHAIN-ID")
    if (type(hnd.height) is not int or type(comet.height) is not int
            or hnd.height != operation.height or comet.height != operation.height):
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-HEIGHT")
    if (hnd.app_state_hash != operation.app_state_hash
            or comet.app_state_hash != operation.app_state_hash
            or comet.block_hash != operation.block_hash
            or comet.consensus_state_hash != operation.consensus_state_hash):
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-DURABLE-STATE-MISMATCH")
    if operation.height != journal.anchor_height + operation.sequence:
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-HEIGHT-SEQUENCE")
    if operation.sequence != journal.latest_sequence + 1:
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-SEQUENCE")

    predecessor = MonotonicRecord(
        operation.sequence - 1, operation.previous_checkpoint
    )
    proposed = MonotonicRecord(
        operation.sequence, operation.checkpoint_digest()
    )
    try:
        remote = anchor.read_state(NAMESPACE)
    except Exception as exc:
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-REMOTE-READ") from exc
    if remote not in (predecessor, proposed):
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-REMOTE-CONFLICT")

    try:
        if operation.phase == Phase.PREPARED:
            operation = journal.advance(
                operation.operation_id, Phase.APPLICATION_COMMITTED
            )
        if operation.phase == Phase.APPLICATION_COMMITTED:
            operation = journal.advance(
                operation.operation_id, Phase.CONSENSUS_COMMITTED
            )
        if operation.phase == Phase.CONSENSUS_COMMITTED:
            published = publish_hrec_checkpoint(anchor, operation)
            if published != proposed:
                raise HRECRecoveryError("HND-HREC-RECOVERY-E-PUBLISH-MISMATCH")
            operation = journal.advance(
                operation.operation_id, Phase.CHECKPOINT_PUBLISHED
            )
        if operation.phase == Phase.CHECKPOINT_PUBLISHED:
            operation = journal.advance(
                operation.operation_id, Phase.FINALIZED
            )
    except HRECRecoveryError:
        raise
    except Exception as exc:
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-TRANSITION") from exc

    if operation.phase != Phase.FINALIZED:
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-NOT-FINALIZED")
    try:
        observed = anchor.read_state(NAMESPACE)
    except Exception as exc:
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-VERIFY-READ") from exc
    if observed != proposed:
        raise HRECRecoveryError("HND-HREC-RECOVERY-E-VERIFY-MISMATCH")
    return operation
