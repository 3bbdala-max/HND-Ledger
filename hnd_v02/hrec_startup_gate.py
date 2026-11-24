"""Fail-closed HREC startup reconciliation gate.

The injected readers must read authoritative durable HND and CometBFT state.
This module does not implement those database readers or prove OS-level
exclusive launch control; deployment must wire reviewed readers and remove
alternate process launch paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from hnd_v02.hrec_journal_model import Phase
from hnd_v02.monotonic_anchor import (
    MonotonicAnchorUnavailable, MonotonicRecord, MonotonicStateAnchor,
)
from hnd_v02.hrec_checkpoint_anchor import NAMESPACE


class HRECStartupError(RuntimeError):
    """HREC startup reconciliation failed; CometBFT must not be launched."""


@dataclass(frozen=True)
class HNDApplicationState:
    chain_id: str
    height: int
    app_state_hash: str


@dataclass(frozen=True)
class CometBFTCommittedState:
    chain_id: str
    height: int
    block_hash: str
    app_state_hash: str
    consensus_state_hash: str


def authorize_hrec_startup(
    *,
    anchor: MonotonicStateAnchor,
    journal,
    read_hnd_state: Callable[[], HNDApplicationState],
    read_cometbft_state: Callable[[], CometBFTCommittedState],
) -> None:
    """Require HND, CometBFT, local journal and remote anchor to agree exactly."""
    if not callable(read_hnd_state) or not callable(read_cometbft_state):
        raise HRECStartupError("HND-HREC-STARTUP-E-STATE-READER")
    try:
        hnd = read_hnd_state()
        comet = read_cometbft_state()
        remote = anchor.read_state(NAMESPACE)
        anchor_height = journal.anchor_height
        anchor_digest = journal.anchor_checkpoint
        latest = journal.latest_operation()
    except Exception as exc:
        raise HRECStartupError("HND-HREC-STARTUP-E-READ-UNAVAILABLE") from exc

    if type(hnd) is not HNDApplicationState or type(comet) is not CometBFTCommittedState:
        raise HRECStartupError("HND-HREC-STARTUP-E-STATE-SHAPE")
    if (type(hnd.height) is not int or type(comet.height) is not int
            or hnd.height < 0 or comet.height < 0):
        raise HRECStartupError("HND-HREC-STARTUP-E-HEIGHT")
    if hnd.chain_id != comet.chain_id:
        raise HRECStartupError("HND-HREC-STARTUP-E-CHAIN-ID")
    if hnd.height != comet.height:
        raise HRECStartupError("HND-HREC-STARTUP-E-HEIGHT-MISMATCH")
    if hnd.app_state_hash != comet.app_state_hash:
        raise HRECStartupError("HND-HREC-STARTUP-E-APP-HASH-MISMATCH")

    if latest is None:
        if hnd.height != anchor_height or comet.height != anchor_height:
            raise HRECStartupError("HND-HREC-STARTUP-E-MISSING-JOURNAL")
        expected = MonotonicRecord(0, anchor_digest)
    else:
        if latest.phase is not Phase.FINALIZED:
            raise HRECStartupError("HND-HREC-STARTUP-E-PENDING-OPERATION")
        if latest.chain_id != hnd.chain_id:
            raise HRECStartupError("HND-HREC-STARTUP-E-CHAIN-ID")
        if latest.height != hnd.height or latest.height != comet.height:
            raise HRECStartupError("HND-HREC-STARTUP-E-HEIGHT-MISMATCH")
        if latest.height != anchor_height + latest.sequence:
            raise HRECStartupError("HND-HREC-STARTUP-E-HEIGHT-SEQUENCE")
        if latest.block_hash != comet.block_hash:
            raise HRECStartupError("HND-HREC-STARTUP-E-BLOCK-HASH")
        if latest.app_state_hash != hnd.app_state_hash:
            raise HRECStartupError("HND-HREC-STARTUP-E-HND-APP-HASH")
        if latest.consensus_state_hash != comet.consensus_state_hash:
            raise HRECStartupError("HND-HREC-STARTUP-E-CONSENSUS-HASH")
        expected = MonotonicRecord(latest.sequence, latest.checkpoint_digest())

    if remote != expected:
        raise HRECStartupError("HND-HREC-STARTUP-E-REMOTE-CHECKPOINT-MISMATCH")
