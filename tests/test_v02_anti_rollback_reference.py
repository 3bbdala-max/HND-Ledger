"""Synthetic offline anti-rollback reference-model tests only."""
import threading
import unittest

from hnd_v02.anti_rollback_reference import (
    AnchorUnavailable, AmbiguousCommit, OfflineAntiRollbackModel,
    AnchorRecord, ReferenceModelError, StaleTransition, SyntheticAnchor, _mac,
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
        read_barrier = threading.Barrier(2)

        class SimultaneousReadAnchor(SyntheticAnchor):
            def read(inner_self):
                snapshot = super(SimultaneousReadAnchor, inner_self).read()
                read_barrier.wait(timeout=2)
                return snapshot

        anchor = SimultaneousReadAnchor()
        model = OfflineAntiRollbackModel(
            anchor, network_id="synthetic-net", genesis_hash="a" * 64,
            validator_id="validator-fixture-1", signer_id="signer-fixture-1",
        )
        outcomes = []
        def attempt(op):
            try:
                model.prepare(operation_id=op, host_id="synthetic-host-1",
                              state={"height": 7, "op": op}, height=7)
                outcomes.append("ok")
            except StaleTransition:
                outcomes.append("stale")
        threads = [threading.Thread(target=attempt, args=(f"race-{i}",)) for i in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=3)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertCountEqual(outcomes, ["ok", "stale"])

    def test_prepare_retry_is_idempotent_before_and_after_commit(self):
        first = self.model.prepare(operation_id="same", host_id="synthetic-host-1",
                                   state=self.state, height=7)
        retried = self.model.prepare(operation_id="same", host_id="synthetic-host-1",
                                     state=self.state, height=7)
        self.assertEqual(first, retried)
        committed = self.model.commit("same")
        retried_after_commit = self.model.prepare(
            operation_id="same", host_id="synthetic-host-1",
            state=self.state, height=7,
        )
        self.assertEqual(committed, retried_after_commit)
        self.assertEqual(retried_after_commit.status, "COMMITTED")

    def test_prepare_rejects_operation_id_reuse_with_conflicting_payload(self):
        self.model.prepare(operation_id="same", host_id="synthetic-host-1",
                           state=self.state, height=7)
        with self.assertRaisesRegex(ReferenceModelError, "conflicting prepare payload"):
            self.model.prepare(
                operation_id="same", host_id="synthetic-host-1",
                state={"height": 7, "app_hash": "different"}, height=7,
            )

    def test_stale_predecessor_is_rejected(self):
        committed = self.prepare_commit()
        fields = committed.unsigned()
        fields.update(
            operation_id="stale-distinct-operation",
            sequence=committed.sequence + 1,
            predecessor_digest="0" * 64,
            status="PREPARED",
        )
        stale = AnchorRecord(**fields, mac=_mac(fields))
        with self.assertRaises(StaleTransition):
            self.anchor.compare_and_swap(
                0, stale, host_id="synthetic-host-1", host_epoch=1
            )

    def test_wrong_restore_generation_and_missing_generation_rejected(self):
        record = self.prepare_commit()
        with self.assertRaises(ReferenceModelError):
            self.model.restore("gen-not-found", dual_control=True)
        del self.model.generations[record.generation_id]
        with self.assertRaises(ReferenceModelError):
            self.model.restore(record.generation_id, dual_control=True)

    def test_shared_anchor_fencing_rejects_stale_model_instance(self):
        first = self.model
        second = OfflineAntiRollbackModel(
            self.anchor, network_id="synthetic-net", genesis_hash="a" * 64,
            validator_id="validator-fixture-1", signer_id="signer-fixture-1",
        )
        self.prepare_commit()
        first.fence_and_takeover("synthetic-host-2")
        self.assertFalse(second.signing_allowed("synthetic-host-1"))
        with self.assertRaisesRegex(ReferenceModelError, "fenced host"):
            second.prepare(operation_id="stale-instance", host_id="synthetic-host-1",
                           state={"height": 8}, height=8)
        self.assertTrue(first.signing_allowed("synthetic-host-2"))

    def test_anchor_rejects_wrong_predecessor_digest_at_correct_sequence(self):
        committed = self.prepare_commit()
        fields = committed.unsigned()
        fields.update(
            operation_id="wrong-predecessor",
            sequence=committed.sequence + 1,
            predecessor_digest="f" * 64,
            status="PREPARED",
        )
        bad = AnchorRecord(**fields, mac=_mac(fields))
        with self.assertRaisesRegex(StaleTransition, "predecessor digest"):
            self.anchor.compare_and_swap(
                committed.sequence, bad, host_id="synthetic-host-1", host_epoch=1
            )

    def test_first_anchor_record_uses_zero_predecessor_sentinel(self):
        empty_anchor = SyntheticAnchor()
        empty_model = OfflineAntiRollbackModel(
            empty_anchor, network_id="synthetic-net",
            genesis_hash="a" * 64, validator_id="validator-fixture-1",
            signer_id="signer-fixture-1",
        )
        first = empty_model.prepare(
            operation_id="first-record", host_id="synthetic-host-1",
            state=self.state, height=7,
        )
        self.assertEqual(first.sequence, 1)
        self.assertEqual(first.predecessor_digest, "0" * 64)
        fields = first.unsigned()
        fields.update(
            operation_id="wrong-first-sentinel",
            sequence=first.sequence + 1,
            predecessor_digest="1" * 64,
        )
        bad = AnchorRecord(**fields, mac=_mac(fields))
        with self.assertRaisesRegex(StaleTransition, "predecessor digest"):
            empty_anchor.compare_and_swap(
                first.sequence, bad, host_id="synthetic-host-1", host_epoch=1
            )

    def test_round_and_step_reject_negative_values_and_booleans(self):
        for field in ("round", "step"):
            for invalid in (-1, True, False):
                kwargs = {field: invalid}
                with self.subTest(field=field, value=invalid):
                    with self.assertRaisesRegex(ValueError, field):
                        self.model.prepare(
                            operation_id=f"invalid-{field}-{invalid}",
                            host_id="synthetic-host-1", state=self.state,
                            height=7, **kwargs,
                        )

    def test_round_and_step_accept_nonnegative_integers(self):
        record = self.model.prepare(
            operation_id="valid-round-step", host_id="synthetic-host-1",
            state=self.state, height=7, round=2, step=3,
        )
        self.assertEqual((record.round, record.step), (2, 3))

    def test_hrs_matches_cometbft_v040_storage_widths_and_step_mapping(self):
        maximums = self.model.prepare(
            operation_id="hrs-maximums", host_id="synthetic-host-1",
            state=self.state, height=(2**63 - 1), round=(2**31 - 1), step=3,
        )
        self.assertEqual(
            (maximums.height, maximums.round, maximums.step),
            (2**63 - 1, 2**31 - 1, 3),
        )

        invalid_cases = (
            {"height": 2**63, "round": 0, "step": 1, "message": "height"},
            {"height": 0, "round": 2**31, "step": 1, "message": "round"},
            {"height": 0, "round": 0, "step": 4, "message": "step"},
            {"height": 0, "round": 0, "step": -1, "message": "step"},
            {"height": 7, "round": 0, "step": 0, "message": "step 0 is reserved"},
        )
        for index, case in enumerate(invalid_cases):
            with self.subTest(case=case):
                with self.assertRaisesRegex(ValueError, case["message"]):
                    self.model.prepare(
                        operation_id=f"hrs-invalid-{index}",
                        host_id="synthetic-host-1", state=self.state,
                        height=case["height"], round=case["round"],
                        step=case["step"],
                    )

    def test_hrs_zero_step_is_only_valid_as_initial_sentinel(self):
        anchor = SyntheticAnchor()
        model = OfflineAntiRollbackModel(
            anchor, network_id="synthetic-net", genesis_hash="a" * 64,
            validator_id="validator-fixture-1", signer_id="signer-fixture-1",
        )
        initial = model.prepare(
            operation_id="initial-sentinel", host_id="synthetic-host-1",
            state={"initial": True}, height=0, round=0, step=0,
        )
        self.assertEqual((initial.height, initial.round, initial.step), (0, 0, 0))

        with self.assertRaisesRegex(ValueError, "step 0 is reserved"):
            OfflineAntiRollbackModel(
                SyntheticAnchor(), network_id="synthetic-net",
                genesis_hash="a" * 64, validator_id="validator-fixture-1",
                signer_id="signer-fixture-1",
            ).prepare(
                operation_id="noninitial-sentinel", host_id="synthetic-host-1",
                state={"height": 0}, height=0, round=1, step=0,
            )

    def test_hrs_allows_forward_step_round_and_height_transitions(self):
        transitions = (
            (7, 0, 1),
            (7, 0, 2),
            (7, 0, 3),
            (7, 1, 1),
            (8, 0, 1),
        )
        for index, (height, round_number, step) in enumerate(transitions):
            record = self.model.prepare(
                operation_id=f"hrs-forward-{index}",
                host_id="synthetic-host-1",
                state={"height": height, "transition": index},
                height=height, round=round_number, step=step,
            )
            self.model.commit(record.operation_id)
        final = self.anchor.read()
        self.assertEqual((final.height, final.round, final.step), (8, 0, 1))

    def test_hrs_rejects_height_round_step_regressions_and_duplicates(self):
        invalid_transitions = (
            (7, 99, 3),  # height regression
            (8, 0, 3),   # round regression
            (8, 1, 2),   # step regression
            (8, 1, 3),   # duplicate HRS
        )
        for index, candidate in enumerate(invalid_transitions):
            with self.subTest(candidate=candidate):
                anchor = SyntheticAnchor()
                model = OfflineAntiRollbackModel(
                    anchor, network_id="synthetic-net",
                    genesis_hash="a" * 64, validator_id="validator-fixture-1",
                    signer_id="signer-fixture-1",
                )
                first = model.prepare(
                    operation_id="hrs-base", host_id="synthetic-host-1",
                    state={"height": 8}, height=8, round=1, step=3,
                )
                model.commit(first.operation_id)
                height, round_number, step = candidate
                with self.assertRaisesRegex(StaleTransition, "HRS must strictly advance"):
                    model.prepare(
                        operation_id=f"hrs-regression-{index}",
                        host_id="synthetic-host-1",
                        state={"height": height, "candidate": candidate},
                        height=height, round=round_number, step=step,
                    )

    def test_stale_model_cannot_commit_after_shared_fencing(self):
        second = OfflineAntiRollbackModel(
            self.anchor, network_id="synthetic-net", genesis_hash="a" * 64,
            validator_id="validator-fixture-1", signer_id="signer-fixture-1",
        )
        second.prepare(operation_id="pending-before-takeover", host_id="synthetic-host-1",
                       state=self.state, height=7)
        self.model.fence_and_takeover("synthetic-host-2")
        with self.assertRaisesRegex(ReferenceModelError, "fenced host cannot commit"):
            second.commit("pending-before-takeover")

    def test_anchor_atomically_rejects_stale_epoch_at_transition_boundary(self):
        prepared = self.model.prepare(
            operation_id="fence-at-cas", host_id="synthetic-host-1",
            state=self.state, height=7,
        )
        self.model.fence_and_takeover("synthetic-host-2")
        with self.assertRaisesRegex(StaleTransition, "fenced host cannot change"):
            self.anchor.compare_and_swap(
                prepared.sequence - 1, prepared,
                host_id="synthetic-host-1", host_epoch=1,
            )
        self.assertEqual(self.anchor.operation("fence-at-cas").status, "PREPARED")


if __name__ == "__main__":
    unittest.main()
