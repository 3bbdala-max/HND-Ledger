import tempfile
import unittest
from pathlib import Path

from hnd_v02.activation_transaction import (
    ActivationState, ActivationTransactionError,
)
from hnd_v02.sqlite_atomic_activation import SQLiteAtomicActivationBackend


def state(manifest_sequence=0, profile_sequence=1, height=100,
          manifest_digest="1" * 64, profile_digest="2" * 64,
          previous_manifest=None, previous_profile=None):
    return ActivationState(
        trust_manifest_sequence=manifest_sequence,
        trust_manifest_digest=manifest_digest,
        profile_sequence=profile_sequence,
        profile_digest=profile_digest,
        activation_height=height,
        operator_ack_set_sha256="3" * 64,
        previous_trust_manifest_digest=previous_manifest,
        previous_profile_digest=previous_profile,
    )


class SQLiteAtomicActivationTests(unittest.TestCase):
    def backend(self, path, validator=None):
        return SQLiteAtomicActivationBackend(
            path,
            profile_validator=validator or (lambda artifact, digest: digest in {"2" * 64, "5" * 64}),
        )

    def test_bootstrap_atomically_persists_state_and_profile_across_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activation.sqlite3"
            first = self.backend(path)
            proposed = state()
            self.assertTrue(first.compare_and_activate(None, proposed, b"profile-v1"))
            reopened = self.backend(path)
            self.assertEqual(reopened.read_active_state(), proposed)
            self.assertEqual(reopened.read_active_profile(), b"profile-v1")

    def test_successor_replaces_profile_and_advances_both_sequences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activation.sqlite3"
            backend = self.backend(path)
            first = state()
            self.assertTrue(backend.compare_and_activate(None, first, b"profile-v1"))
            second = state(
                manifest_sequence=1, profile_sequence=2, height=101,
                manifest_digest="4" * 64, profile_digest="5" * 64,
                previous_manifest="1" * 64, previous_profile="2" * 64,
            )
            backend.profile_validator = lambda artifact, digest: (
                artifact == b"profile-v2" and digest == "5" * 64
            )
            self.assertTrue(backend.compare_and_activate(first, second, b"profile-v2"))
            self.assertEqual(backend.read_active_state(), second)
            self.assertEqual(backend.read_active_profile(), b"profile-v2")

    def test_stale_compare_and_swap_cannot_overwrite_active_state(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.backend(Path(directory) / "activation.sqlite3")
            first = state()
            self.assertTrue(backend.compare_and_activate(None, first, b"profile-v1"))
            stale = state(manifest_digest="9" * 64)
            self.assertFalse(backend.compare_and_activate(None, stale, b"profile-stale"))
            self.assertEqual(backend.read_active_state(), first)
            self.assertEqual(backend.read_active_profile(), b"profile-v1")

    def test_profile_digest_mismatch_fails_before_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.backend(
                Path(directory) / "activation.sqlite3",
                validator=lambda artifact, digest: False,
            )
            with self.assertRaises(ActivationTransactionError):
                backend.compare_and_activate(None, state(), b"tampered")
            self.assertIsNone(backend.read_active_state())
            self.assertIsNone(backend.read_active_profile())

    def test_validator_exception_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            def broken_validator(artifact, digest):
                raise OSError("schema unavailable")
            backend = self.backend(
                Path(directory) / "activation.sqlite3", validator=broken_validator
            )
            with self.assertRaises(ActivationTransactionError):
                backend.compare_and_activate(None, state(), b"profile")
            self.assertIsNone(backend.read_active_state())

    def test_empty_artifact_and_memory_database_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.backend(Path(directory) / "activation.sqlite3")
            with self.assertRaises(ActivationTransactionError):
                backend.compare_and_activate(None, state(), b"")
        with self.assertRaises(ActivationTransactionError):
            self.backend(":memory:")

    def test_missing_validator_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ActivationTransactionError):
                SQLiteAtomicActivationBackend(Path(directory) / "activation.sqlite3",
                                              profile_validator=None)

    def test_backend_itself_rejects_non_successor_manifest_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.backend(Path(directory) / "activation.sqlite3")
            first = state()
            backend.compare_and_activate(None, first, b"profile-v1")
            bad = state(
                manifest_sequence=2, profile_sequence=2, height=101,
                manifest_digest="4" * 64, profile_digest="5" * 64,
                previous_manifest="1" * 64, previous_profile="2" * 64,
            )
            with self.assertRaises(ActivationTransactionError):
                backend.compare_and_activate(first, bad, b"profile-v2")
            self.assertEqual(backend.read_active_state(), first)

    def test_backend_itself_rejects_profile_sequence_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.backend(Path(directory) / "activation.sqlite3")
            first = state()
            backend.compare_and_activate(None, first, b"profile-v1")
            bad = state(
                manifest_sequence=1, profile_sequence=1, height=101,
                manifest_digest="4" * 64, profile_digest="5" * 64,
                previous_manifest="1" * 64, previous_profile="2" * 64,
            )
            with self.assertRaises(ActivationTransactionError):
                backend.compare_and_activate(first, bad, b"profile-v2")

    def test_backend_itself_rejects_predecessor_mismatch_and_nonincreasing_height(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.backend(Path(directory) / "activation.sqlite3")
            first = state()
            backend.compare_and_activate(None, first, b"profile-v1")
            cases = [
                state(manifest_sequence=1, profile_sequence=2, height=101,
                      manifest_digest="4" * 64, profile_digest="5" * 64,
                      previous_manifest="9" * 64, previous_profile="2" * 64),
                state(manifest_sequence=1, profile_sequence=2, height=100,
                      manifest_digest="4" * 64, profile_digest="5" * 64,
                      previous_manifest="1" * 64, previous_profile="2" * 64),
            ]
            for bad in cases:
                with self.subTest(state=bad):
                    with self.assertRaises(ActivationTransactionError):
                        backend.compare_and_activate(first, bad, b"profile-v2")
                    self.assertEqual(backend.read_active_state(), first)

    def test_backend_itself_rejects_invalid_bootstrap_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.backend(Path(directory) / "activation.sqlite3")
            bad = state(manifest_sequence=1, profile_sequence=2)
            with self.assertRaises(ActivationTransactionError):
                backend.compare_and_activate(None, bad, b"profile-v1")
            self.assertIsNone(backend.read_active_state())


if __name__ == "__main__":
    unittest.main()
