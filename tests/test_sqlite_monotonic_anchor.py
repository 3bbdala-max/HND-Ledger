import tempfile
import unittest
from pathlib import Path

from hnd_v02.monotonic_anchor import (
    MonotonicRecord, MonotonicAnchorError, MonotonicAnchorConflict,
    advance_monotonic_state,
)
from hnd_v02.sqlite_monotonic_anchor import SQLiteMonotonicAnchor


class SQLiteMonotonicAnchorTests(unittest.TestCase):
    def test_reopens_with_persisted_state_and_rejects_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "anchor.sqlite3"
            first = SQLiteMonotonicAnchor(path)
            advance_monotonic_state(
                first, "trust-manifest", sequence=0, digest="a" * 64,
                predecessor_digest=None,
            )
            reopened = SQLiteMonotonicAnchor(path)
            self.assertEqual(reopened.read_state("trust-manifest"),
                             MonotonicRecord(0, "a" * 64))
            with self.assertRaises(MonotonicAnchorConflict):
                advance_monotonic_state(
                    reopened, "trust-manifest", sequence=0,
                    digest="b" * 64, predecessor_digest=None,
                )

    def test_namespaces_remain_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            anchor = SQLiteMonotonicAnchor(Path(directory) / "anchor.db")
            advance_monotonic_state(
                anchor, "trust-manifest", sequence=0, digest="a" * 64,
                predecessor_digest=None,
            )
            advance_monotonic_state(
                anchor, "vsp-profile", sequence=1, digest="b" * 64,
                predecessor_digest=None,
            )
            self.assertEqual(anchor.read_state("trust-manifest").sequence, 0)
            self.assertEqual(anchor.read_state("vsp-profile").sequence, 1)

    def test_compare_and_advance_is_compare_and_swap(self):
        with tempfile.TemporaryDirectory() as directory:
            anchor = SQLiteMonotonicAnchor(Path(directory) / "anchor.db")
            current = MonotonicRecord(0, "a" * 64)
            self.assertTrue(anchor.compare_and_advance(
                "trust-manifest", None, current
            ))
            self.assertFalse(anchor.compare_and_advance(
                "trust-manifest", None, MonotonicRecord(0, "b" * 64)
            ))
            self.assertEqual(anchor.read_state("trust-manifest"), current)

    def test_backend_direct_calls_enforce_bootstrap_and_exact_successors(self):
        with tempfile.TemporaryDirectory() as directory:
            anchor = SQLiteMonotonicAnchor(Path(directory) / "anchor.db")
            with self.assertRaises(MonotonicAnchorConflict):
                anchor.compare_and_advance(
                    "trust-manifest", None, MonotonicRecord(1, "a" * 64)
                )
            self.assertTrue(anchor.compare_and_advance(
                "trust-manifest", None, MonotonicRecord(0, "a" * 64)
            ))
            current = MonotonicRecord(0, "a" * 64)
            for replay_or_skip in (
                MonotonicRecord(0, "b" * 64),
                MonotonicRecord(2, "b" * 64),
            ):
                with self.subTest(proposed=replay_or_skip):
                    with self.assertRaises(MonotonicAnchorConflict):
                        anchor.compare_and_advance(
                            "trust-manifest", current, replay_or_skip
                        )
            self.assertEqual(anchor.read_state("trust-manifest"), current)

            with self.assertRaises(MonotonicAnchorConflict):
                anchor.compare_and_advance(
                    "vsp-profile", None, MonotonicRecord(0, "c" * 64)
                )
            self.assertTrue(anchor.compare_and_advance(
                "vsp-profile", None, MonotonicRecord(1, "c" * 64)
            ))
            self.assertTrue(anchor.compare_and_advance(
                "vsp-profile", MonotonicRecord(1, "c" * 64),
                MonotonicRecord(2, "d" * 64),
            ))

    def test_rejects_memory_database_and_bad_records(self):
        with self.assertRaises(MonotonicAnchorError):
            SQLiteMonotonicAnchor(":memory:")
        with tempfile.TemporaryDirectory() as directory:
            anchor = SQLiteMonotonicAnchor(Path(directory) / "anchor.db")
            with self.assertRaises(MonotonicAnchorError):
                anchor.compare_and_advance(
                    "trust-manifest", None, MonotonicRecord(0, "A" * 64)
                )


    def test_activation_witness_namespace_is_monotonic_and_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "anchor.db"
            anchor = SQLiteMonotonicAnchor(path)
            first = MonotonicRecord(0, "a" * 64)
            self.assertTrue(anchor.compare_and_advance(
                "activation-witness", None, first
            ))
            reopened = SQLiteMonotonicAnchor(path)
            self.assertEqual(reopened.read_state("activation-witness"), first)
            self.assertTrue(reopened.compare_and_advance(
                "activation-witness", first, MonotonicRecord(1, "b" * 64)
            ))
            with self.assertRaises(MonotonicAnchorConflict):
                reopened.compare_and_advance(
                    "activation-witness", None, MonotonicRecord(0, "c" * 64)
                )

if __name__ == "__main__":
    unittest.main()
