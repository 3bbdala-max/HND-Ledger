"""Synthetic offline anti-rollback reference-model tests only."""
import threading
import unittest

from hnd_v02.anti_rollback_reference import (
    AnchorUnavailable, AmbiguousCommit, OfflineAntiRollbackModel,
    ReferenceModelError, StaleTransition, SyntheticAnchor,
)


class TestOfflineAntiRollbackReference(unittest.TestCase):
    def setUp(self):
        self.anchor = SyntheticAnchor()
        self.model = OfflineAntiRollbackModel(
            self.anchor, network_id="synthetic-net",
            genesis_hash="a" * 64, validator_id="validator-fixture-1",
            signer_id="signer-fixture-1",
        )
        self.state = {"height": 7, "app_hash": "fixture-app-hash"}

    def prepare_commit(self, op="op-1", state=None):
        record = self.model.prepare(
            operation_id=op, host_id="synthetic-host-1",
            state=state or self.state, height=(state or self.state)["height"],
        )
        return self.model.commit(op)

    def test_normal_prepare_commit_and_restore(self):
        record = self.prepare_commit()
        self.assertEqual(record.status, "COMMITTED")
        self.assertTrue(self.model.signing_allowed("synthetic-host-1"))
        self.assertEqual(self.model.restore(record.generation_id, dual_control=True), self.state)

    def test_prepared_state_never_enables_signing(self):
        self.model.prepare(operation_id="pending", host_id="synthetic-host-1",
                           state=self.state, height=7)
        self.assertFalse(self.model.signing_allowed("synthetic-host-1"))
        with self.assertRaisesRegex(ReferenceModelError, "uncommitted"):
            self.model.reconcile("pending")

    def test_ambiguous_commit_reconciles_by_operation_id(self):
        self.model.prepare(operation_id="lost-reply", host_id="synthetic-host-1",
                           state=self.state, height=7)
        with self.assertRaises(AmbiguousCommit):
            self.model.commit("lost-reply", simulate_lost_reply=True)
        self.assertEqual(self.model.reconcile("lost-reply").status, "COMMITTED")

    def test_anchor_outage_fails_closed(self):
        self.anchor.available = False
        with self.assertRaises(AnchorUnavailable):
            self.model.prepare(operation_id="offline", host_id="synthetic-host-1",
                               state=self.state, height=7)
        self.assertFalse(self.model.signing_allowed("synthetic-host-1"))

    def test_restore_requires_dual_control(self):
        record = self.prepare_commit()
        with self.assertRaisesRegex(ReferenceModelError, "dual control"):
            self.model.restore(record.generation_id)

    def test_restore_rejects_unanchored_older_generation(self):
        old = self.prepare_commit()
        newer_state = {"height": 8, "app_hash": "new"}
        new = self.prepare_commit("op-2", newer_state)
        with self.assertRaisesRegex(ReferenceModelError, "not the anchored"):
            self.model.restore(old.generation_id, dual_control=True)
        self.assertEqual(new.sequence, old.sequence + 1)

    def test_corrupt_generation_disables_signing_and_restore(self):
        record = self.prepare_commit()
        self.model.generations[record.generation_id]["app_hash"] = "tampered"
        self.assertFalse(self.model.signing_allowed("synthetic-host-1"))
        with self.assertRaisesRegex(ReferenceModelError, "digest mismatch"):
            self.model.restore(record.generation_id, dual_control=True)

    def test_chain_identity_mismatch_rejected(self):
        record = self.prepare_commit()
        self.model.identity = ("other-net", "b" * 64, "validator-fixture-1", "signer-fixture-1")
        with self.assertRaisesRegex(ReferenceModelError, "identity mismatch"):
            self.model.reconcile(record.operation_id)

    def test_old_host_is_fenced_after_takeover(self):
        self.prepare_commit()
        self.model.fence_and_takeover("synthetic-host-2")
        self.assertFalse(self.model.signing_allowed("synthetic-host-1"))
        self.assertTrue(self.model.signing_allowed("synthetic-host-2"))
        with self.assertRaisesRegex(ReferenceModelError, "fenced host"):
            self.model.prepare(operation_id="old-host", host_id="synthetic-host-1",
                               state={"height": 8}, height=8)

    def test_concurrent_prepare_only_one_compare_and_swap_wins(self):
        barrier = threading.Barrier(2)
        outcomes = []
        def attempt(op):
            barrier.wait()
            try:
                self.model.prepare(operation_id=op, host_id="synthetic-host-1",
                                   state={"height": 7, "op": op}, height=7)
                outcomes.append("ok")
            except StaleTransition:
                outcomes.append("stale")
        threads = [threading.Thread(target=attempt, args=(f"race-{i}",)) for i in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertCountEqual(outcomes, ["ok", "stale"])

    def test_duplicate_operation_is_idempotent_and_conflict_rejected(self):
        first = self.model.prepare(operation_id="same", host_id="synthetic-host-1",
                                   state=self.state, height=7)
        again = self.anchor.compare_and_swap(0, first)
        self.assertEqual(first, again)
        conflicting = self.model.prepare
        with self.assertRaises(ReferenceModelError):
            self.anchor.compare_and_swap(0, type(first)(
                **{**first.unsigned(), "state_digest": "f" * 64},
                mac=first.mac,
            ))

    def test_stale_predecessor_is_rejected(self):
        self.prepare_commit()
        with self.assertRaises(StaleTransition):
            self.anchor.compare_and_swap(0, self.anchor.read())

    def test_wrong_restore_generation_and_missing_generation_rejected(self):
        record = self.prepare_commit()
        with self.assertRaises(ReferenceModelError):
            self.model.restore("gen-not-found", dual_control=True)
        del self.model.generations[record.generation_id]
        with self.assertRaises(ReferenceModelError):
            self.model.restore(record.generation_id, dual_control=True)


if __name__ == "__main__":
    unittest.main()
