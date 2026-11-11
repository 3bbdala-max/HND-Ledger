import unittest
from unittest.mock import patch

from hnd_v02.activation_transaction import (
    ActivationState, ActivationTransactionConflict,
    ActivationTransactionError, ActivationTransactionUnavailable,
    activate_verified_bundle,
)


def evidence(manifest_seq=0, profile_seq=1, height=100, previous_manifest=None, previous_profile=None):
    return {
        "trust_manifest_sequence": manifest_seq,
        "trust_manifest_digest": "1" * 64,
        "profile_sequence": profile_seq,
        "profile_digest": "2" * 64,
        "activation_height": height,
        "operator_ack_set_sha256": "3" * 64,
        "previous_trust_manifest_digest": previous_manifest,
        "previous_profile_digest": previous_profile,
        "preflight_accepted": True,
        "activation_performed": False,
    }


class FakeAtomicBackend:
    def __init__(self, current=None, result=True):
        self.current = current
        self.result = result
        self.calls = []

    def read_active_state(self):
        return self.current

    def compare_and_activate(self, expected_current, new_state, profile_artifact):
        self.calls.append((expected_current, new_state, profile_artifact))
        if self.result:
            self.current = new_state
        return self.result


class AtomicActivationTransactionTests(unittest.TestCase):
    def call_activate(self, backend, result=None):
        with patch(
            "hnd_v02.activation_transaction.verify_activation_bundle_with_manifest_chain",
            return_value=result or evidence(),
        ):
            return activate_verified_bundle(
                backend, b"vsp", [b"manifest"], b"acks", b"profile",
                context={"chain_id": "hnd-test"},
                trusted_witness_keys={"w1": b"a" * 32},
                expected_operator_keys={"op1": b"b" * 32},
            )

    def test_bootstrap_commits_both_namespaces_in_one_backend_call(self):
        backend = FakeAtomicBackend()
        state = self.call_activate(backend)
        self.assertEqual(state.trust_manifest_sequence, 0)
        self.assertEqual(state.profile_sequence, 1)
        self.assertEqual(len(backend.calls), 1)
        self.assertIsNone(backend.calls[0][0])
        self.assertEqual(backend.calls[0][2], b"profile")

    def test_exact_already_committed_state_is_idempotent_after_lost_response(self):
        committed = ActivationState(0, "1" * 64, 1, "2" * 64, 100, "3" * 64)
        backend = FakeAtomicBackend(committed)
        state = self.call_activate(backend)
        self.assertEqual(state, committed)
        self.assertEqual(backend.calls, [])

    def test_same_sequences_with_different_digest_are_not_idempotent(self):
        current = ActivationState(0, "4" * 64, 1, "5" * 64, 100, "6" * 64)
        backend = FakeAtomicBackend(current)
        with self.assertRaises(ActivationTransactionConflict):
            self.call_activate(backend)
        self.assertEqual(backend.calls, [])

    def test_successor_requires_both_monotonic_sequences_and_height(self):
        current = ActivationState(0, "4" * 64, 1, "5" * 64, 100, "6" * 64)
        backend = FakeAtomicBackend(current)
        proposed = evidence(manifest_seq=1, profile_seq=2, height=101, previous_manifest="4" * 64, previous_profile="5" * 64)
        state = self.call_activate(backend, proposed)
        self.assertEqual(state.trust_manifest_sequence, 1)
        self.assertEqual(state.profile_sequence, 2)
        self.assertEqual(backend.calls[0][0], current)

    def test_skipped_or_rolled_back_manifest_sequence_is_rejected(self):
        current = ActivationState(0, "4" * 64, 1, "5" * 64, 100, "6" * 64)
        backend = FakeAtomicBackend(current)
        with self.assertRaises(ActivationTransactionConflict):
            self.call_activate(backend, evidence(manifest_seq=2, profile_seq=2, height=101, previous_manifest="4" * 64, previous_profile="5" * 64))
        self.assertEqual(backend.calls, [])

    def test_skipped_profile_sequence_is_rejected(self):
        current = ActivationState(0, "4" * 64, 1, "5" * 64, 100, "6" * 64)
        backend = FakeAtomicBackend(current)
        with self.assertRaises(ActivationTransactionConflict):
            self.call_activate(backend, evidence(manifest_seq=1, profile_seq=3, height=101, previous_manifest="4" * 64, previous_profile="5" * 64))
        self.assertEqual(backend.calls, [])

    def test_non_increasing_activation_height_is_rejected(self):
        current = ActivationState(0, "4" * 64, 1, "5" * 64, 100, "6" * 64)
        backend = FakeAtomicBackend(current)
        with self.assertRaises(ActivationTransactionConflict):
            self.call_activate(backend, evidence(manifest_seq=1, profile_seq=2, height=100, previous_manifest="4" * 64, previous_profile="5" * 64))
        self.assertEqual(backend.calls, [])


    def test_manifest_predecessor_digest_must_match_active_anchor(self):
        current = ActivationState(0, "4" * 64, 1, "5" * 64, 100, "6" * 64)
        backend = FakeAtomicBackend(current)
        with self.assertRaises(ActivationTransactionConflict):
            self.call_activate(backend, evidence(
                manifest_seq=1, profile_seq=2, height=101,
                previous_manifest="9" * 64, previous_profile="5" * 64))
        self.assertEqual(backend.calls, [])

    def test_profile_predecessor_digest_must_match_active_anchor(self):
        current = ActivationState(0, "4" * 64, 1, "5" * 64, 100, "6" * 64)
        backend = FakeAtomicBackend(current)
        with self.assertRaises(ActivationTransactionConflict):
            self.call_activate(backend, evidence(
                manifest_seq=1, profile_seq=2, height=101,
                previous_manifest="4" * 64, previous_profile="9" * 64))
        self.assertEqual(backend.calls, [])

    def test_backend_compare_and_activate_conflict_fails_closed(self):
        backend = FakeAtomicBackend(result=False)
        with self.assertRaises(ActivationTransactionConflict):
            self.call_activate(backend)
        self.assertEqual(len(backend.calls), 1)

    def test_backend_unavailable_fails_closed(self):
        class Unavailable(FakeAtomicBackend):
            def read_active_state(self):
                raise OSError("anchor offline")
        with self.assertRaises(ActivationTransactionUnavailable):
            self.call_activate(Unavailable())

    def test_failed_cryptographic_preflight_never_calls_backend(self):
        backend = FakeAtomicBackend()
        with patch(
            "hnd_v02.activation_transaction.verify_activation_bundle_with_manifest_chain",
            side_effect=ValueError("bad signature"),
        ):
            with self.assertRaises(ActivationTransactionError):
                activate_verified_bundle(
                    backend, b"vsp", [b"manifest"], b"acks", b"profile",
                    context={"chain_id": "hnd-test"},
                    trusted_witness_keys={"w1": b"a" * 32},
                    expected_operator_keys={"op1": b"b" * 32},
                )
        self.assertEqual(backend.calls, [])


if __name__ == "__main__":
    unittest.main()
