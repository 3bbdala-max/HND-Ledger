"""Cross-layer station-two activation test using real crypto verifiers and SQLite."""
import tempfile
import unittest
from pathlib import Path

from hnd_v02.activation_transaction import activate_verified_bundle
from hnd_v02.sqlite_atomic_activation import SQLiteAtomicActivationBackend
from hnd_v02.vsp_canonical import profile_digest
from tests.test_activation_bundle import ActivationBundleTests


class StationTwoEndToEndActivationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ActivationBundleTests()
        self.fixture.setUp()
        self.profile_bytes = b"reviewed-profile-artifact-v1"
        self.expected_digest = profile_digest(self.fixture.vsp.payload).hex()

    def _activate(self, backend, artifact=None):
        return activate_verified_bundle(
            backend,
            self.fixture.vsp_raw,
            [self.fixture.manifest_raw],
            self.fixture.acks_raw,
            self.profile_bytes if artifact is None else artifact,
            context=self.fixture.vsp.ctx,
            trusted_witness_keys=self.fixture.witness_keys,
            expected_operator_keys=self.fixture.operator_public,
        )

    def test_crypto_preflight_and_atomic_sqlite_activation_are_connected(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = SQLiteAtomicActivationBackend(
                Path(directory) / "station-two.sqlite3",
                profile_validator=lambda artifact, digest: (
                    artifact == self.profile_bytes and digest == self.expected_digest
                ),
            )
            state = self._activate(backend)
            self.assertEqual(state.trust_manifest_sequence, 0)
            self.assertEqual(state.profile_sequence, 1)
            self.assertEqual(state.profile_digest, self.expected_digest)
            self.assertEqual(backend.read_active_state(), state)
            self.assertEqual(backend.read_active_profile(), self.profile_bytes)

            # Reopen to prove the committed profile and monotonic state survive
            # a process-style backend reconstruction.
            reopened = SQLiteAtomicActivationBackend(
                Path(directory) / "station-two.sqlite3",
                profile_validator=lambda artifact, digest: (
                    artifact == self.profile_bytes and digest == self.expected_digest
                ),
            )
            self.assertEqual(reopened.read_active_state(), state)
            self.assertEqual(reopened.read_active_profile(), self.profile_bytes)

    def test_profile_validation_failure_never_commits_any_activation_state(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = SQLiteAtomicActivationBackend(
                Path(directory) / "station-two.sqlite3",
                profile_validator=lambda _artifact, _digest: False,
            )
            with self.assertRaisesRegex(Exception, "HND-ACT-E-COMMIT"):
                self._activate(backend)
            self.assertIsNone(backend.read_active_state())
            self.assertIsNone(backend.read_active_profile())


if __name__ == "__main__":
    unittest.main()
