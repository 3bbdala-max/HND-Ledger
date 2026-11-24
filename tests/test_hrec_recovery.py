import tempfile
import unittest
from pathlib import Path

from hnd_v02.hrec_checkpoint_anchor import initialize_hrec_anchor, publish_hrec_checkpoint
from hnd_v02.hrec_journal_model import Operation, Phase
from hnd_v02.hrec_recovery import HRECRecoveryError, recover_pending_hrec_operation
from hnd_v02.hrec_sqlite_journal import SQLiteHRECJournal
from hnd_v02.hrec_startup_gate import CometBFTCommittedState, HNDApplicationState
from hnd_v02.monotonic_anchor import MonotonicRecord


GENESIS = "d" * 64
A = "a" * 64
B = "b" * 64
C = "c" * 64


class FakeAnchor:
    def __init__(self):
        self.record = None

    def read_state(self, namespace):
        return self.record

    def compare_and_advance(self, namespace, expected_current, new_record):
        if self.record != expected_current:
            return False
        self.record = new_record
        return True


class HRECRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.anchor = FakeAnchor()
        initialize_hrec_anchor(self.anchor, genesis_digest=GENESIS)
        self.journal = SQLiteHRECJournal(
            str(Path(self.temp.name) / "journal.sqlite"),
            anchor_height=6, anchor_checkpoint=GENESIS,
        )
        self.op = Operation(
            operation_id="recovery-op-1", chain_id="hnd-test", height=7,
            block_hash=A, app_state_hash=B, consensus_state_hash=C,
            previous_checkpoint=GENESIS, sequence=1,
        )
        self.hnd = HNDApplicationState("hnd-test", 7, B)
        self.comet = CometBFTCommittedState("hnd-test", 7, A, B, C)

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def test_prepared_operation_recovers_after_both_durable_commits(self):
        self.journal.prepare(self.op)
        result = recover_pending_hrec_operation(
            anchor=self.anchor, journal=self.journal,
            hnd=self.hnd, comet=self.comet,
        )
        self.assertEqual(result.phase, Phase.FINALIZED)
        self.assertEqual(self.journal.latest_operation(), result)
        self.assertEqual(
            self.anchor.record,
            MonotonicRecord(1, self.op.checkpoint_digest()),
        )

    def test_application_committed_operation_recovers(self):
        self.journal.prepare(self.op)
        self.journal.advance("recovery-op-1", Phase.APPLICATION_COMMITTED)
        result = recover_pending_hrec_operation(
            anchor=self.anchor, journal=self.journal,
            hnd=self.hnd, comet=self.comet,
        )
        self.assertEqual(result.phase, Phase.FINALIZED)

    def test_remote_published_but_local_phase_not_advanced_recovers_idempotently(self):
        self.journal.prepare(self.op)
        self.journal.advance("recovery-op-1", Phase.APPLICATION_COMMITTED)
        self.journal.advance("recovery-op-1", Phase.CONSENSUS_COMMITTED)
        publish_hrec_checkpoint(self.anchor, self.journal.get("recovery-op-1"))
        result = recover_pending_hrec_operation(
            anchor=self.anchor, journal=self.journal,
            hnd=self.hnd, comet=self.comet,
        )
        self.assertEqual(result.phase, Phase.FINALIZED)

    def test_durable_state_mismatch_does_not_advance_journal_or_anchor(self):
        self.journal.prepare(self.op)
        bad_comet = CometBFTCommittedState("hnd-test", 7, A, "e" * 64, C)
        with self.assertRaisesRegex(HRECRecoveryError, "DURABLE-STATE-MISMATCH"):
            recover_pending_hrec_operation(
                anchor=self.anchor, journal=self.journal,
                hnd=self.hnd, comet=bad_comet,
            )
        self.assertEqual(self.journal.get("recovery-op-1").phase, Phase.PREPARED)
        self.assertEqual(self.anchor.record, MonotonicRecord(0, GENESIS))

    def test_remote_conflict_blocks_recovery(self):
        self.journal.prepare(self.op)
        self.anchor.record = MonotonicRecord(1, "e" * 64)
        with self.assertRaisesRegex(HRECRecoveryError, "REMOTE-CONFLICT"):
            recover_pending_hrec_operation(
                anchor=self.anchor, journal=self.journal,
                hnd=self.hnd, comet=self.comet,
            )
        self.assertEqual(self.journal.get("recovery-op-1").phase, Phase.PREPARED)

    def test_recovery_does_not_rewrite_finalized_operation(self):
        self.journal.prepare(self.op)
        self.journal.advance("recovery-op-1", Phase.APPLICATION_COMMITTED)
        self.journal.advance("recovery-op-1", Phase.CONSENSUS_COMMITTED)
        publish_hrec_checkpoint(self.anchor, self.journal.get("recovery-op-1"))
        self.journal.advance("recovery-op-1", Phase.CHECKPOINT_PUBLISHED)
        self.journal.advance("recovery-op-1", Phase.FINALIZED)
        with self.assertRaisesRegex(HRECRecoveryError, "NOTHING-TO-RECOVER"):
            recover_pending_hrec_operation(
                anchor=self.anchor, journal=self.journal,
                hnd=self.hnd, comet=self.comet,
            )


if __name__ == "__main__":
    unittest.main()
