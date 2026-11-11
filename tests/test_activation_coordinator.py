import unittest

from hnd_v02.activation_coordinator import (
    ActivationCoordinator, ActivationCoordinatorError,
)
from hnd_v02.monotonic_anchor import MonotonicRecord


class _Anchor:
    def __init__(self, initial=None, lose_response=False):
        self.record = initial
        self.lose_response = lose_response
        self.calls = 0

    def read_state(self, namespace):
        return self.record

    def compare_and_advance(self, namespace, expected, new):
        self.calls += 1
        if self.record != expected:
            return False
        self.record = new
        if self.lose_response:
            self.lose_response = False
            raise TimeoutError("response lost after durable write")
        return True


class ActivationCoordinatorAnchorRecoveryTests(unittest.TestCase):
    def coordinator(self, anchor):
        coordinator = object.__new__(ActivationCoordinator)
        coordinator.anchor = anchor
        return coordinator

    def test_lost_cas_response_accepts_exact_durable_successor(self):
        predecessor = MonotonicRecord(4, "a" * 64)
        successor = MonotonicRecord(5, "b" * 64)
        anchor = _Anchor(predecessor, lose_response=True)
        self.coordinator(anchor)._advance(
            "trust-manifest",
            {"sequence": 4, "digest": "a" * 64},
            {"sequence": 5, "digest": "b" * 64},
        )
        self.assertEqual(anchor.record, successor)
        self.assertEqual(anchor.calls, 1)

    def test_exact_successor_is_idempotent_without_write(self):
        successor = MonotonicRecord(1, "c" * 64)
        anchor = _Anchor(successor)
        self.coordinator(anchor)._advance(
            "vsp-profile", None,
            {"sequence": 1, "digest": "c" * 64},
        )
        self.assertEqual(anchor.calls, 0)

    def test_unexpected_same_sequence_digest_fails_closed(self):
        anchor = _Anchor(MonotonicRecord(5, "d" * 64))
        with self.assertRaises(ActivationCoordinatorError):
            self.coordinator(anchor)._advance(
                "trust-manifest",
                {"sequence": 4, "digest": "a" * 64},
                {"sequence": 5, "digest": "b" * 64},
            )
        self.assertEqual(anchor.calls, 0)

    def test_unchanged_predecessor_after_false_cas_retries_exact_successor(self):
        class FalseOnce(_Anchor):
            def compare_and_advance(self, namespace, expected, new):
                self.calls += 1
                if self.calls == 1:
                    return False
                return super().compare_and_advance(namespace, expected, new)

        predecessor = MonotonicRecord(0, "e" * 64)
        successor = MonotonicRecord(1, "f" * 64)
        anchor = FalseOnce(predecessor)
        self.coordinator(anchor)._advance(
            "trust-manifest",
            {"sequence": 0, "digest": "e" * 64},
            {"sequence": 1, "digest": "f" * 64},
        )
        self.assertEqual(anchor.record, successor)
        self.assertEqual(anchor.calls, 3)


if __name__ == "__main__":
    unittest.main()


# Full coordinator recovery tests use deterministic service doubles. They model
# durable writes whose responses are lost, not merely exceptions before writes.
from unittest.mock import patch
from hnd_v02.activation_coordinator import ActivationCoordinator
from hnd_v02.activation_transaction import ActivationState
from hnd_v02.remote_activation_intent import ActivationIntent


class _IntentService:
    def __init__(self):
        self.intent = None
        self.lose_prepare_response = True
        self.lose_finalize_response = True
        self.prepare_calls = 0
        self.finalize_calls = 0

    def prepare(self, **kwargs):
        self.prepare_calls += 1
        proposed = ActivationIntent(
            kwargs["activation_id"], "prepared",
            kwargs["predecessor_trust_manifest"],
            kwargs["predecessor_vsp_profile"],
            kwargs["successor_trust_manifest"],
            kwargs["successor_vsp_profile"],
            kwargs["profile_digest"], kwargs["operator_ack_digest"],
        )
        if self.intent is not None and self.intent != proposed:
            raise RuntimeError("immutable activation ID conflict")
        self.intent = proposed
        if self.lose_prepare_response:
            self.lose_prepare_response = False
            raise TimeoutError("prepare committed; response lost")
        return self.intent

    def read_intent(self, activation_id):
        if self.intent is None or self.intent.activation_id != activation_id:
            return None
        return self.intent

    def finalize(self, *, activation_id, profile_digest, operator_ack_digest):
        self.finalize_calls += 1
        if self.intent is None or self.intent.activation_id != activation_id:
            raise RuntimeError("intent missing")
        if (self.intent.profile_digest != profile_digest
                or self.intent.operator_ack_digest != operator_ack_digest):
            raise RuntimeError("finalize digest mismatch")
        self.intent = ActivationIntent(
            self.intent.activation_id, "finalized",
            self.intent.predecessor_trust_manifest,
            self.intent.predecessor_vsp_profile,
            self.intent.successor_trust_manifest,
            self.intent.successor_vsp_profile,
            self.intent.profile_digest, self.intent.operator_ack_digest,
        )
        if self.lose_finalize_response:
            self.lose_finalize_response = False
            raise TimeoutError("finalize committed; response lost")
        return self.intent


class _TwoNamespaceAnchor:
    def __init__(self):
        self.records = {"trust-manifest": None, "vsp-profile": None}
        self.lose_response = {"trust-manifest": True, "vsp-profile": True}
        self.calls = {"trust-manifest": 0, "vsp-profile": 0}

    def read_state(self, namespace):
        return self.records[namespace]

    def compare_and_advance(self, namespace, expected, new):
        self.calls[namespace] += 1
        if self.records[namespace] != expected:
            return False
        self.records[namespace] = new
        if self.lose_response[namespace]:
            self.lose_response[namespace] = False
            raise TimeoutError("anchor committed; response lost")
        return True


class _AtomicBackend:
    def __init__(self):
        self.state = None
        self.calls = 0
        self.lose_response = True

    def read_active_state(self):
        return self.state

    def compare_and_activate(self, expected_current, new_state, profile_artifact):
        if self.state != expected_current:
            return False
        self.calls += 1
        self.state = new_state
        if self.lose_response:
            self.lose_response = False
            raise TimeoutError("local activation committed; response lost")
        return True


class ActivationCoordinatorEndToEndRecoveryTests(unittest.TestCase):
    def test_same_activation_id_recovers_lost_responses_at_every_commit_boundary(self):
        evidence = {
            "trust_manifest_sequence": 0,
            "trust_manifest_digest": "1" * 64,
            "profile_sequence": 1,
            "profile_digest": "2" * 64,
            "activation_height": 100,
            "operator_ack_set_sha256": "3" * 64,
            "previous_trust_manifest_digest": None,
            "previous_profile_digest": None,
        }
        intent = _IntentService()
        anchor = _TwoNamespaceAnchor()
        backend = _AtomicBackend()
        coordinator = ActivationCoordinator(
            intent_client=intent, anchor=anchor, backend=backend,
        )
        args = dict(
            activation_id="station2-bootstrap-001",
            vsp_raw=b"vsp", trust_manifests=[b"manifest"],
            operator_acks_raw=b"acks", profile_artifact=b"profile",
            context={"chain_id": "hnd-test"},
            trusted_witness_keys={"witness-1": b"w" * 32},
            expected_operator_keys={"operator-1": b"o" * 32},
        )
        with patch(
            "hnd_v02.activation_coordinator.verify_activation_bundle_with_manifest_chain",
            return_value=evidence,
        ):
            # First attempt durably prepares, advances both anchors and commits
            # locally, but loses the local response. It must not finalize yet.
            with self.assertRaises(ActivationCoordinatorError):
                coordinator.activate(**args)
            self.assertEqual(intent.intent.state, "prepared")
            self.assertIsNotNone(backend.state)
            self.assertEqual(backend.calls, 1)

            # Repeating the exact same immutable activation ID reconciles the
            # already committed anchors/local state and finalizes the intent.
            result = coordinator.activate(**args)

        self.assertEqual(result, backend.state)
        self.assertEqual(intent.intent.state, "finalized")
        self.assertEqual(intent.prepare_calls, 2)
        self.assertEqual(intent.finalize_calls, 1)
        self.assertEqual(backend.calls, 1)
        self.assertEqual(anchor.calls, {"trust-manifest": 1, "vsp-profile": 1})
        self.assertEqual(anchor.records["trust-manifest"], MonotonicRecord(0, "1" * 64))
        self.assertEqual(anchor.records["vsp-profile"], MonotonicRecord(1, "2" * 64))

    def test_conflicting_remote_anchor_blocks_local_activation(self):
        evidence = {
            "trust_manifest_sequence": 0,
            "trust_manifest_digest": "1" * 64,
            "profile_sequence": 1,
            "profile_digest": "2" * 64,
            "activation_height": 100,
            "operator_ack_set_sha256": "3" * 64,
            "previous_trust_manifest_digest": None,
            "previous_profile_digest": None,
        }
        intent = _IntentService()
        anchor = _TwoNamespaceAnchor()
        anchor.records["trust-manifest"] = MonotonicRecord(0, "9" * 64)
        backend = _AtomicBackend()
        coordinator = ActivationCoordinator(
            intent_client=intent, anchor=anchor, backend=backend,
        )
        with patch(
            "hnd_v02.activation_coordinator.verify_activation_bundle_with_manifest_chain",
            return_value=evidence,
        ):
            with self.assertRaises(ActivationCoordinatorError):
                coordinator.activate(
                    activation_id="station2-conflict-001",
                    vsp_raw=b"vsp", trust_manifests=[b"manifest"],
                    operator_acks_raw=b"acks", profile_artifact=b"profile",
                    context={"chain_id": "hnd-test"},
                    trusted_witness_keys={"witness-1": b"w" * 32},
                    expected_operator_keys={"operator-1": b"o" * 32},
                )
        self.assertIsNone(backend.state)
        self.assertEqual(backend.calls, 0)
