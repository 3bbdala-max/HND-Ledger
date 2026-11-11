"""Tests for the pinned CometBFT process supervisor boundary."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from hnd_v02.cometbft_supervisor import (
    CometBFTSupervisorError,
    start_authorized_cometbft,
)
from hnd_v02.sqlite_atomic_activation import SQLiteAtomicActivationBackend
from hnd_v02.vsp_canonical import profile_digest
from tests.test_activation_bundle import ActivationBundleTests


class CometBFTSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ActivationBundleTests()
        self.fixture.setUp()
        self.profile = b"reviewed-profile-artifact-v1"
        self.digest = profile_digest(self.fixture.vsp.payload).hex()
        self.calls = []
        self.child = object()

    def _backend(self, path):
        return SQLiteAtomicActivationBackend(
            path,
            profile_validator=lambda artifact, digest: (
                artifact == self.profile and digest == self.digest
            ),
        )

    def _launch(self, directory, *, valid_acks=True, expected_digest=None):
        root = Path(directory)
        binary = root / "cometbft"
        binary.write_bytes(b"pinned-cometbft-test-binary")
        binary.chmod(0o755)
        actual_digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        self.backend = self._backend(root / "activation.sqlite3")

        def fake_popen(args, **kwargs):
            self.calls.append((args, kwargs, self.backend.read_active_state()))
            return self.child

        result = start_authorized_cometbft(
            backend=self.backend,
            vsp_raw=self.fixture.vsp_raw,
            trust_manifests=[self.fixture.manifest_raw],
            operator_acks_raw=self.fixture.acks_raw if valid_acks else b"[]",
            profile_artifact=self.profile,
            context=self.fixture.vsp.ctx,
            trusted_witness_keys=self.fixture.witness_keys,
            expected_operator_keys=self.fixture.operator_public,
            binary_path=str(binary),
            expected_binary_sha256=expected_digest or actual_digest,
            arguments=["start", "--home", str(root / "node-home")],
            cwd=str(root),
            environment={"PATH": "/usr/bin"},
            popen=fake_popen,
        )
        return result, binary, actual_digest

    def test_pinned_binary_starts_only_after_activation_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "node-home").mkdir()
            (state, child), binary, _ = self._launch(directory)
            self.assertIs(child, self.child)
            self.assertEqual(self.backend.read_active_state(), state)
            self.assertEqual(len(self.calls), 1)
            args, kwargs, state_at_spawn = self.calls[0]
            self.assertEqual(args, [str(binary), "start", "--home", str(Path(directory) / "node-home")])
            self.assertEqual(state_at_spawn, state)
            self.assertIs(kwargs["shell"], False)
            self.assertIs(kwargs["start_new_session"], True)
            self.assertEqual(kwargs["env"], {"PATH": "/usr/bin"})

    def test_wrong_binary_digest_never_activates_or_spawns(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "node-home").mkdir()
            with self.assertRaisesRegex(CometBFTSupervisorError, "DIGEST-MISMATCH"):
                self._launch(directory, expected_digest="0" * 64)
            self.assertEqual(self.calls, [])
            self.assertIsNone(self.backend.read_active_state())

    def test_invalid_authorization_never_spawns_process(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "node-home").mkdir()
            with self.assertRaises(Exception):
                self._launch(directory, valid_acks=False)
            self.assertEqual(self.calls, [])
            self.assertIsNone(self.backend.read_active_state())

    def test_symlinked_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "real-cometbft"
            target.write_bytes(b"binary")
            target.chmod(0o755)
            link = root / "cometbft"
            link.symlink_to(target)
            with self.assertRaisesRegex(CometBFTSupervisorError, "FILE-TYPE"):
                from hnd_v02.cometbft_supervisor import _pinned_executable
                _pinned_executable(str(link), hashlib.sha256(b"binary").hexdigest())
            self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
