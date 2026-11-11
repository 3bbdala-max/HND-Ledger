"""Negative and positive tests for the Station 2 startup authorization seam."""
import tempfile
import unittest
from pathlib import Path

from hnd_v02.startup_authorization import (
    StartupAuthorizationError,
    authorize_then_start,
)
from hnd_v02.sqlite_atomic_activation import SQLiteAtomicActivationBackend
from hnd_v02.vsp_canonical import profile_digest
from tests.test_activation_bundle import ActivationBundleTests


class StartupAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ActivationBundleTests()
        self.fixture.setUp()
        self.profile = b"reviewed-profile-artifact-v1"
        self.digest = profile_digest(self.fixture.vsp.payload).hex()
        self.started = []

    def _backend(self, path, valid=True):
        return SQLiteAtomicActivationBackend(
            path,
            profile_validator=lambda artifact, digest: (
                valid and artifact == self.profile and digest == self.digest
            ),
        )

    def _run(self, backend, **overrides):
        args = dict(
            backend=backend,
            vsp_raw=self.fixture.vsp_raw,
            trust_manifests=[self.fixture.manifest_raw],
            operator_acks_raw=self.fixture.acks_raw,
            profile_artifact=self.profile,
            context=self.fixture.vsp.ctx,
            trusted_witness_keys=self.fixture.witness_keys,
            expected_operator_keys=self.fixture.operator_public,
            launch=lambda state: self.started.append(state) or "launched",
        )
        args.update(overrides)
        return authorize_then_start(**args)

    def test_launcher_runs_only_after_committed_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self._backend(Path(directory) / "activation.sqlite3")
            state, result = self._run(backend)
            self.assertEqual(result, "launched")
            self.assertEqual(self.started, [state])
            self.assertEqual(backend.read_active_state(), state)
            self.assertEqual(backend.read_active_profile(), self.profile)

    def test_invalid_operator_acknowledgements_never_launch_or_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self._backend(Path(directory) / "activation.sqlite3")
            with self.assertRaises(Exception):
                self._run(backend, operator_acks_raw=b"[]")
            self.assertEqual(self.started, [])
            self.assertIsNone(backend.read_active_state())

    def test_profile_install_failure_never_launches_or_commits(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self._backend(Path(directory) / "activation.sqlite3", valid=False)
            with self.assertRaises(Exception):
                self._run(backend)
            self.assertEqual(self.started, [])
            self.assertIsNone(backend.read_active_state())

    def test_missing_launcher_is_rejected_before_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self._backend(Path(directory) / "activation.sqlite3")
            with self.assertRaisesRegex(StartupAuthorizationError, "LAUNCHER"):
                self._run(backend, launch=None)
            self.assertIsNone(backend.read_active_state())

    def test_missing_trust_chain_never_launches(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self._backend(Path(directory) / "activation.sqlite3")
            with self.assertRaisesRegex(StartupAuthorizationError, "TRUST-CHAIN"):
                self._run(backend, trust_manifests=[])
            self.assertEqual(self.started, [])
            self.assertIsNone(backend.read_active_state())


if __name__ == "__main__":
    unittest.main()
