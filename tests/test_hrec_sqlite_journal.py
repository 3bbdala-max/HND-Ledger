import os
import tempfile
import unittest

from hnd_v02.hrec_journal_model import HRECError, Operation, Phase
from hnd_v02.hrec_sqlite_journal import SQLiteHRECJournal


A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64


def op(operation_id="durable-1", sequence=1, height=7, previous=D):
    return Operation(
        operation_id=operation_id,
        chain_id="hnd-test",
        height=height,
        block_hash=A,
        app_state_hash=B,
        consensus_state_hash=C,
        previous_checkpoint=previous,
        sequence=sequence,
    )


class SQLiteHRECJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "hrec.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def open_journal(self):
        return SQLiteHRECJournal(
            self.path, anchor_height=6, anchor_checkpoint=D
        )

    def test_prepared_operation_survives_reopen(self):
        with self.open_journal() as journal:
            journal.prepare(op())
        with self.open_journal() as journal:
            restored = journal.get("durable-1")
            self.assertIsNotNone(restored)
            self.assertEqual(restored.phase, Phase.PREPARED)

    def test_intermediate_phase_survives_reopen(self):
        with self.open_journal() as journal:
            journal.prepare(op())
            journal.advance("durable-1", Phase.APPLICATION_COMMITTED)
            journal.advance("durable-1", Phase.CONSENSUS_COMMITTED)
        with self.open_journal() as journal:
            restored = journal.get("durable-1")
            self.assertEqual(restored.phase, Phase.CONSENSUS_COMMITTED)

    def test_finalized_checkpoint_survives_reopen(self):
        with self.open_journal() as journal:
            journal.prepare(op())
            for phase in (
                Phase.APPLICATION_COMMITTED,
                Phase.CONSENSUS_COMMITTED,
                Phase.CHECKPOINT_PUBLISHED,
                Phase.FINALIZED,
            ):
                journal.advance("durable-1", phase)
            expected = journal.latest_checkpoint
        with self.open_journal() as journal:
            self.assertEqual(journal.latest_sequence, 1)
            self.assertEqual(journal.latest_checkpoint, expected)

    def test_exact_prepare_retry_is_idempotent(self):
        with self.open_journal() as journal:
            journal.prepare(op())
            journal.advance("durable-1", Phase.APPLICATION_COMMITTED)
            result = journal.prepare(op())
            self.assertEqual(result.phase, Phase.APPLICATION_COMMITTED)

    def test_changed_anchor_is_rejected(self):
        with self.open_journal():
            pass
        with self.assertRaises(HRECError):
            SQLiteHRECJournal(
                self.path, anchor_height=5, anchor_checkpoint=D
            )

    def test_next_operation_requires_previous_finalization(self):
        with self.open_journal() as journal:
            journal.prepare(op())
            with self.assertRaises(HRECError):
                journal.prepare(op("durable-2", sequence=2, height=8))

    def test_database_rejects_stale_sequence_after_finalization(self):
        with self.open_journal() as journal:
            journal.prepare(op())
            for phase in (
                Phase.APPLICATION_COMMITTED,
                Phase.CONSENSUS_COMMITTED,
                Phase.CHECKPOINT_PUBLISHED,
                Phase.FINALIZED,
            ):
                journal.advance("durable-1", phase)
            with self.assertRaises(HRECError):
                journal.prepare(op("stale", sequence=1, height=8))


if __name__ == "__main__":
    unittest.main()
