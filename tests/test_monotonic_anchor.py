import unittest

from hnd_v02.monotonic_anchor import (
    MonotonicAnchorConflict, MonotonicAnchorUnavailable, MonotonicRecord,
    advance_monotonic_state,
)


class MemoryAnchor:
    """Test double only; not a production trust anchor."""
    def __init__(self):
        self.records = {}

    def read_state(self, namespace):
        return self.records.get(namespace)

    def compare_and_advance(self, namespace, expected_current, new_record):
        if self.records.get(namespace) != expected_current:
            return False
        self.records[namespace] = new_record
        return True


class BrokenAnchor:
    def read_state(self, namespace):
        raise OSError("anchor offline")

    def compare_and_advance(self, *args):
        raise AssertionError("must not commit after failed read")


class MonotonicAnchorContractTests(unittest.TestCase):
    def test_bootstrap_requires_sequence_zero(self):
        anchor = MemoryAnchor()
        result = advance_monotonic_state(
            anchor, "trust-manifest", sequence=0, digest="a" * 64,
            predecessor_digest=None,
        )
        self.assertEqual(result, MonotonicRecord(0, "a" * 64))

    def test_bootstrap_rejects_nonzero_sequence(self):
        with self.assertRaises(MonotonicAnchorConflict):
            advance_monotonic_state(
                MemoryAnchor(), "trust-manifest", sequence=1,
                digest="b" * 64, predecessor_digest="a" * 64,
            )

    def test_next_state_requires_exact_predecessor(self):
        anchor = MemoryAnchor()
        advance_monotonic_state(
            anchor, "trust-manifest", sequence=0, digest="a" * 64,
            predecessor_digest=None,
        )
        result = advance_monotonic_state(
            anchor, "trust-manifest", sequence=1, digest="b" * 64,
            predecessor_digest="a" * 64,
        )
        self.assertEqual(result, MonotonicRecord(1, "b" * 64))

    def test_rejects_replay_skip_and_wrong_predecessor(self):
        anchor = MemoryAnchor()
        advance_monotonic_state(
            anchor, "vsp-profile", sequence=1, digest="a" * 64,
            predecessor_digest=None,
        )
        for sequence, predecessor in ((1, "a" * 64), (3, "a" * 64),
                                      (2, "c" * 64)):
            with self.subTest(sequence=sequence, predecessor=predecessor):
                with self.assertRaises(MonotonicAnchorConflict):
                    advance_monotonic_state(
                        anchor, "vsp-profile", sequence=sequence,
                        digest="b" * 64, predecessor_digest=predecessor,
                    )

    def test_manifest_and_vsp_sequences_are_independent(self):
        anchor = MemoryAnchor()
        advance_monotonic_state(
            anchor, "trust-manifest", sequence=0, digest="a" * 64,
            predecessor_digest=None,
        )
        advance_monotonic_state(
            anchor, "vsp-profile", sequence=0, digest="b" * 64,
            predecessor_digest=None,
        )
        self.assertNotEqual(anchor.records["trust-manifest"],
                            anchor.records["vsp-profile"])

    def test_invalid_namespace_and_digest_fail_closed(self):
        anchor = MemoryAnchor()
        for namespace, digest in (("other", "a" * 64),
                                  ("vsp-profile", "A" * 64),
                                  ("vsp-profile", "0" * 63)):
            with self.subTest(namespace=namespace, digest=digest):
                with self.assertRaises(Exception):
                    advance_monotonic_state(
                        anchor, namespace, sequence=0, digest=digest,
                        predecessor_digest=None,
                    )

    def test_unavailable_anchor_fails_closed(self):
        with self.assertRaises(MonotonicAnchorUnavailable):
            advance_monotonic_state(
                BrokenAnchor(), "trust-manifest", sequence=0,
                digest="a" * 64, predecessor_digest=None,
            )

    def test_compare_and_advance_race_fails_closed(self):
        class RacingAnchor(MemoryAnchor):
            def compare_and_advance(self, namespace, expected_current, new_record):
                self.records[namespace] = MonotonicRecord(1, "c" * 64)
                return False
        with self.assertRaises(MonotonicAnchorConflict):
            advance_monotonic_state(
                RacingAnchor(), "vsp-profile", sequence=1,
                digest="a" * 64, predecessor_digest=None,
            )


if __name__ == "__main__":
    unittest.main()
