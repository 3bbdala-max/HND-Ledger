import unittest

from hnd_v02.hrec_journal_model import (
    HRECError, HRECJournalModel, Operation, Phase,
)


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
DIGEST_D = "d" * 64


def operation(operation_id="op-1", sequence=1, previous=DIGEST_D, height=7):
    return Operation(
        operation_id=operation_id,
        chain_id="hnd-test",
        height=height,
        block_hash=DIGEST_A,
        app_state_hash=DIGEST_B,
        consensus_state_hash=DIGEST_C,
        previous_checkpoint=previous,
        sequence=sequence,
    )


class HRECJournalModelTests(unittest.TestCase):
    def test_exact_prepare_retry_is_idempotent_after_advancement(self):
        journal = HRECJournalModel(anchor_height=6, anchor_checkpoint=DIGEST_D)
        first = operation()
        journal.prepare(first)
        journal.advance("op-1", Phase.APPLICATION_COMMITTED)
        self.assertEqual(
            journal.prepare(first).phase, Phase.APPLICATION_COMMITTED
        )

    def test_operation_id_cannot_be_reused_with_different_contents(self):
        journal = HRECJournalModel(anchor_height=6, anchor_checkpoint=DIGEST_D)
        journal.prepare(operation())
        with self.assertRaises(HRECError):
            journal.prepare(operation(operation_id="op-1", sequence=1,
                                      previous=DIGEST_C))

    def test_only_one_operation_may_be_pending(self):
        journal = HRECJournalModel(anchor_height=6, anchor_checkpoint=DIGEST_D)
        journal.prepare(operation())
        with self.assertRaises(HRECError):
            journal.prepare(operation("op-2"))

    def test_phase_cannot_be_skipped(self):
        journal = HRECJournalModel(anchor_height=6, anchor_checkpoint=DIGEST_D)
        journal.prepare(operation())
        with self.assertRaises(HRECError):
            journal.advance("op-1", Phase.CONSENSUS_COMMITTED)

    def test_sequence_advances_only_after_finalization(self):
        journal = HRECJournalModel(anchor_height=6, anchor_checkpoint=DIGEST_D)
        journal.prepare(operation())
        for phase in (
            Phase.APPLICATION_COMMITTED,
            Phase.CONSENSUS_COMMITTED,
            Phase.CHECKPOINT_PUBLISHED,
            Phase.FINALIZED,
        ):
            journal.advance("op-1", phase)
        self.assertEqual(journal.latest_sequence, 1)
        self.assertIsNotNone(journal.latest_checkpoint)
        next_op = operation("op-2", sequence=2,
                            previous=journal.latest_checkpoint, height=8)
        journal.prepare(next_op)

    def test_stale_sequence_is_rejected(self):
        journal = HRECJournalModel(anchor_height=6, anchor_checkpoint=DIGEST_D)
        with self.assertRaises(HRECError):
            journal.prepare(operation(sequence=2))

    def test_invalid_digest_is_rejected(self):
        journal = HRECJournalModel(anchor_height=6, anchor_checkpoint=DIGEST_D)
        bad = Operation(
            operation_id="bad", chain_id="hnd-test", height=1,
            block_hash="not-a-hash", app_state_hash=DIGEST_B,
            consensus_state_hash=DIGEST_C, previous_checkpoint=DIGEST_D,
            sequence=1,
        )
        with self.assertRaises(HRECError):
            journal.prepare(bad)


if __name__ == "__main__":
    unittest.main()
