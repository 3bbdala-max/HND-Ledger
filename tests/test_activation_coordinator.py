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
