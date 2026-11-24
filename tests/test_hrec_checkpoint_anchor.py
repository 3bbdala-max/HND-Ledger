import unittest

from hnd_v02.hrec_checkpoint_anchor import (
    NAMESPACE, initialize_hrec_anchor, publish_hrec_checkpoint,
)
from hnd_v02.hrec_journal_model import HRECError, Operation, Phase
from hnd_v02.monotonic_anchor import (
    MonotonicAnchorConflict, MonotonicRecord,
)


GENESIS = "d" * 64
A = "a" * 64
B = "b" * 64
C = "c" * 64


class FakeAnchor:
    def __init__(self):
        self.records = {}
        self.calls = 0
        self.lose_response_after_commit = False

    def read_state(self, namespace):
        return self.records.get(namespace)

    def compare_and_advance(self, namespace, expected_current, new_record):
        self.calls += 1
        if self.records.get(namespace) != expected_current:
            return False
        self.records[namespace] = new_record
        if self.lose_response_after_commit:
            self.lose_response_after_commit = False
            raise TimeoutError("committed but response lost")
        return True


def committed_operation(phase=Phase.CONSENSUS_COMMITTED):
    return Operation(
        operation_id="hrec-op-1",
        chain_id="hnd-test",
        height=7,
        block_hash=A,
        app_state_hash=B,
        consensus_state_hash=C,
        previous_checkpoint=GENESIS,
        sequence=1,
        phase=phase,
    )


class HRECCheckpointAnchorTests(unittest.TestCase):
    def setUp(self):
        self.anchor = FakeAnchor()
        initialize_hrec_anchor(self.anchor, genesis_digest=GENESIS)

    def test_genesis_initialization_is_idempotent(self):
        before = self.anchor.calls
        self.assertEqual(
            initialize_hrec_anchor(self.anchor, genesis_digest=GENESIS),
            MonotonicRecord(0, GENESIS),
        )
        self.assertEqual(self.anchor.calls, before)

    def test_committed_operation_advances_remote_anchor(self):
        op = committed_operation()
        result = publish_hrec_checkpoint(self.anchor, op)
        self.assertEqual(result, MonotonicRecord(1, op.checkpoint_digest()))
        self.assertEqual(self.anchor.read_state(NAMESPACE), result)

    def test_exact_republication_is_idempotent(self):
        op = committed_operation()
        first = publish_hrec_checkpoint(self.anchor, op)
        calls = self.anchor.calls
        second = publish_hrec_checkpoint(self.anchor, op)
        self.assertEqual(first, second)
        self.assertEqual(self.anchor.calls, calls)

    def test_lost_response_after_remote_commit_is_reconciled(self):
        op = committed_operation()
        self.anchor.lose_response_after_commit = True
        result = publish_hrec_checkpoint(self.anchor, op)
        self.assertEqual(result.digest, op.checkpoint_digest())
        self.assertEqual(self.anchor.calls, 1)

    def test_uncommitted_phase_cannot_publish(self):
        with self.assertRaises(HRECError):
            publish_hrec_checkpoint(
                self.anchor, committed_operation(Phase.APPLICATION_COMMITTED)
            )
        self.assertEqual(self.anchor.calls, 0)

    def test_wrong_predecessor_fails_closed(self):
        op = committed_operation()
        bad = Operation(
            operation_id=op.operation_id, chain_id=op.chain_id,
            height=op.height, block_hash=op.block_hash,
            app_state_hash=op.app_state_hash,
            consensus_state_hash=op.consensus_state_hash,
            previous_checkpoint="e" * 64, sequence=op.sequence,
            phase=op.phase,
        )
        with self.assertRaises(MonotonicAnchorConflict):
            publish_hrec_checkpoint(self.anchor, bad)
        self.assertEqual(self.anchor.calls, 0)

    def test_genesis_replacement_is_rejected(self):
        with self.assertRaises(MonotonicAnchorConflict):
            initialize_hrec_anchor(self.anchor, genesis_digest="e" * 64)


if __name__ == "__main__":
    unittest.main()
