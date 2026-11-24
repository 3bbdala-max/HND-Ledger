import tempfile
import unittest
from pathlib import Path

from hnd_v02.hrec_checkpoint_anchor import initialize_hrec_anchor, publish_hrec_checkpoint
from hnd_v02.hrec_journal_model import Operation, Phase
from hnd_v02.hrec_sqlite_journal import SQLiteHRECJournal
from hnd_v02.hrec_startup_gate import (
    CometBFTCommittedState, HNDApplicationState, HRECStartupError,
    authorize_hrec_startup,
)
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


class HRECStartupGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "hrec.sqlite"
        self.anchor = FakeAnchor()
        initialize_hrec_anchor(self.anchor, genesis_digest=GENESIS)
        self.journal = SQLiteHRECJournal(
            str(self.path), anchor_height=6, anchor_checkpoint=GENESIS
        )
        self.hnd = HNDApplicationState("hnd-test", 6, GENESIS)
        self.comet = CometBFTCommittedState(
            "hnd-test", 6, GENESIS, GENESIS, GENESIS
        )

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def commit_one_operation(self):
        operation = Operation(
            operation_id="gate-op-1", chain_id="hnd-test", height=7,
            block_hash=A, app_state_hash=B, consensus_state_hash=C,
            previous_checkpoint=GENESIS, sequence=1,
        )
        self.journal.prepare(operation)
        self.journal.advance("gate-op-1", Phase.APPLICATION_COMMITTED)
        self.journal.advance("gate-op-1", Phase.CONSENSUS_COMMITTED)
        committed = self.journal.get("gate-op-1")
        publish_hrec_checkpoint(self.anchor, committed)
        self.journal.advance("gate-op-1", Phase.CHECKPOINT_PUBLISHED)
        self.journal.advance("gate-op-1", Phase.FINALIZED)
        self.hnd = HNDApplicationState("hnd-test", 7, B)
        self.comet = CometBFTCommittedState("hnd-test", 7, A, B, C)

    def gate(self):
        authorize_hrec_startup(
            anchor=self.anchor,
            journal=self.journal,
            read_hnd_state=lambda: self.hnd,
            read_cometbft_state=lambda: self.comet,
        )

    def test_genesis_state_passes_only_with_pinned_genesis_anchor(self):
        self.gate()

    def test_finalized_matching_hnd_comet_and_remote_checkpoint_pass(self):
        self.commit_one_operation()
        self.gate()

    def test_hnd_comet_height_mismatch_blocks_startup(self):
        self.comet = CometBFTCommittedState("hnd-test", 7, A, B, C)
        with self.assertRaisesRegex(HRECStartupError, "HEIGHT-MISMATCH"):
            self.gate()

    def test_application_hash_mismatch_blocks_startup(self):
        self.comet = CometBFTCommittedState("hnd-test", 6, GENESIS, A, C)
        with self.assertRaisesRegex(HRECStartupError, "APP-HASH-MISMATCH"):
            self.gate()

    def test_pending_journal_operation_blocks_startup(self):
        self.journal.prepare(Operation(
            operation_id="pending", chain_id="hnd-test", height=7,
            block_hash=A, app_state_hash=B, consensus_state_hash=C,
            previous_checkpoint=GENESIS, sequence=1,
        ))
        with self.assertRaisesRegex(HRECStartupError, "PENDING-OPERATION"):
            self.gate()

    def test_remote_anchor_mismatch_blocks_startup(self):
        self.commit_one_operation()
        self.anchor.record = MonotonicRecord(1, "e" * 64)
        with self.assertRaisesRegex(HRECStartupError, "REMOTE-CHECKPOINT-MISMATCH"):
            self.gate()


if __name__ == "__main__":
    unittest.main()
