"""Tests for the pinned CometBFT process supervisor boundary."""
import hashlib
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pathlib import Path

from hnd_v02.cometbft_supervisor import (
    CometBFTSupervisorError,
    start_authorized_cometbft,
)
from hnd_v02.activation_witness import compute_activation_digest, verify_witness_receipt
from hnd_v02.activation_witness_store import SQLiteActivationWitnessStore
from hnd_v02.vsp_canonical import profile_digest
from tests.test_activation_bundle import ActivationBundleTests


_DEFAULT_ENVIRONMENT = object()
_WITNESS_ID = "activation-witness-ci"
_CONFIG_EPOCH = 3


class _WitnessedMemoryBackend:
    """Test-only CAS backend with the same witness-finalization contract."""

    def __init__(self, profile_validator):
        self.profile_validator = profile_validator
        self.state = None
        self.profile = None
        self.intent = None

    def read_active_state(self):
        return self.state

    def read_active_profile(self):
        return self.profile

    def compare_and_activate_with_intent(
        self, expected_current, new_state, profile_artifact, *, activation_id
    ):
        if self.intent is not None:
            digest = compute_activation_digest(activation_id, new_state, profile_artifact)
            if (
                self.intent.get("activation_id") == activation_id
                and self.intent.get("activation_digest") == digest
            ):
                return False
        if self.state != expected_current:
            return False
        if self.profile_validator(profile_artifact, new_state.profile_digest) is not True:
            raise ValueError("profile validation failed")
        digest = compute_activation_digest(activation_id, new_state, profile_artifact)
        self.state = new_state
        self.profile = profile_artifact
        self.intent = {
            "activation_id": activation_id,
            "state": "pending_witness",
            "activation_digest": digest,
            "trust_manifest_sequence": new_state.trust_manifest_sequence,
            "trust_manifest_digest": new_state.trust_manifest_digest,
            "profile_sequence": new_state.profile_sequence,
            "profile_digest": new_state.profile_digest,
            "operator_ack_digest": new_state.operator_ack_set_sha256,
        }
        return True

    def read_activation_intent(self, activation_id):
        if self.intent is None or self.intent.get("activation_id") != activation_id:
            return None
        return dict(self.intent)

    def finalize_activation_intent(
        self, activation_id, witness_receipt, *,
        trusted_witness_keys, expected_witness_id, expected_config_epoch,
    ):
        if self.intent is None or self.intent.get("activation_id") != activation_id:
            raise ValueError("activation intent missing")
        verified = verify_witness_receipt(
            witness_receipt,
            trusted_witness_keys=trusted_witness_keys,
            expected_activation_id=activation_id,
            expected_activation_digest=self.intent["activation_digest"],
            expected_witness_id=expected_witness_id,
            expected_config_epoch=expected_config_epoch,
        )
        self.intent = {
            **self.intent,
            "state": "finalized",
            "witness_receipt": witness_receipt,
            "witness_counter": verified.counter,
        }
        return dict(self.intent)


class _UnavailableWitness:
    def acknowledge(self, _activation_id, _activation_digest):
        raise TimeoutError("reference witness unavailable")


class CometBFTSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ActivationBundleTests()
        self.fixture.setUp()
        self.profile = b"reviewed-profile-artifact-v1"
        self.digest = profile_digest(self.fixture.vsp.payload).hex()
        self.calls = []
        self.child = object()

    def _backend(self, _path):
        return _WitnessedMemoryBackend(
            profile_validator=lambda artifact, digest: (
                artifact == self.profile and digest == self.digest
            )
        )

    def _launch(self, directory, *, valid_acks=True, expected_digest=None,
                environment=_DEFAULT_ENVIRONMENT, witness_unavailable=False,
                application_binding_valid=True, popen_failure=False):
        root = Path(directory)
        binary = root / "cometbft"
        binary.write_bytes(b"pinned-cometbft-test-binary")
        binary.chmod(0o755)
        actual_digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        self.backend = self._backend(root / "activation.sqlite3")
        witness_private_key = Ed25519PrivateKey.generate()
        witness_public_key = witness_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.trusted_witness_keys = dict(self.fixture.witness_keys)
        self.trusted_witness_keys[_WITNESS_ID] = witness_public_key
        self.witness_client = (
            _UnavailableWitness()
            if witness_unavailable
            else SQLiteActivationWitnessStore(
                str(root / "witness.sqlite3"),
                witness_id=_WITNESS_ID,
                config_epoch=_CONFIG_EPOCH,
                signing_key=witness_private_key,
            )
        )
        self.application = object()
        self.events = []
        self.abci_server = MagicMock()
        self.abci_server.stop.return_value.wait.return_value = None

        def fake_start_grpc_server(application, *, bind_address, max_workers):
            self.assertIs(application, self.application)
            self.assertEqual(bind_address, "127.0.0.1:26658")
            self.assertEqual(max_workers, 16)
            self.assertEqual(self.backend.intent["state"], "finalized")
            self.events.append("abci-listener")
            return self.abci_server, 26658

        def fake_popen(args, **kwargs):
            inherited = kwargs["pass_fds"]
            self.assertEqual(len(inherited), 1)
            fd = inherited[0]
            os.lseek(fd, 0, os.SEEK_SET)
            pinned_bytes = os.read(fd, 1024)
            os.lseek(fd, 0, os.SEEK_SET)
            self.assertEqual(self.backend.intent["state"], "finalized")
            self.events.append("cometbft-spawn")
            self.calls.append((args, kwargs, self.backend.read_active_state(), pinned_bytes))
            if popen_failure:
                raise OSError("simulated CometBFT spawn failure")
            return self.child

        with patch(
            "hnd_v02.cometbft_supervisor.start_grpc_server",
            side_effect=fake_start_grpc_server,
        ):
            result = start_authorized_cometbft(
            backend=self.backend,
            application=self.application,
            application_binding_verifier=(
                lambda app, state, artifact: application_binding_valid
                and app is self.application
                and state == self.backend.read_active_state()
                and artifact == self.profile
            ),
            witness_client=self.witness_client,
            activation_id="supervisor-activation-test-001",
            expected_witness_id=_WITNESS_ID,
            expected_config_epoch=_CONFIG_EPOCH,
            vsp_raw=self.fixture.vsp_raw,
            trust_manifests=[self.fixture.manifest_raw],
            operator_acks_raw=self.fixture.acks_raw if valid_acks else b"[]",
            profile_artifact=self.profile,
            context=self.fixture.vsp.ctx,
            trusted_witness_keys=self.trusted_witness_keys,
            expected_operator_keys=self.fixture.operator_public,
            binary_path=str(binary),
            expected_binary_sha256=expected_digest or actual_digest,
            arguments=["start", "--home", str(root / "node-home")],
            cwd=str(root),
            environment=(
                {"PATH": "/usr/bin"}
                if environment is _DEFAULT_ENVIRONMENT else environment
            ),
            popen=fake_popen,
            )
        return result, binary, actual_digest

    def test_pinned_binary_starts_only_after_activation_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "node-home").mkdir()
            (state, launch_result), binary, _ = self._launch(directory)
            self.assertIs(launch_result["cometbft_process"], self.child)
            self.assertIs(launch_result["abci_server"], self.abci_server)
            self.assertEqual(launch_result["abci_port"], 26658)
            self.assertEqual(self.events, ["abci-listener", "cometbft-spawn"])
            self.assertEqual(self.backend.read_active_state(), state)
            self.assertEqual(self.backend.intent["state"], "finalized")
            self.assertEqual(self.backend.intent["witness_receipt"]["witness_id"], _WITNESS_ID)
            self.assertEqual(len(self.calls), 1)
            args, kwargs, state_at_spawn, pinned_bytes = self.calls[0]
            fd = kwargs["pass_fds"][0]
            self.assertEqual(args, [f"/proc/self/fd/{fd}", "start", "--home", str(Path(directory) / "node-home")])
            self.assertEqual(kwargs["executable"], f"/proc/self/fd/{fd}")
            self.assertEqual(pinned_bytes, b"pinned-cometbft-test-binary")
            self.assertEqual(state_at_spawn, state)
            self.assertIs(kwargs["shell"], False)
            self.assertIs(kwargs["start_new_session"], True)
            self.assertIs(kwargs["close_fds"], True)
            self.assertEqual(kwargs["pass_fds"], (fd,))
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


    def test_application_binding_mismatch_opens_no_listener_or_process(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "node-home").mkdir()
            with self.assertRaisesRegex(CometBFTSupervisorError, "APPLICATION-BINDING"):
                self._launch(directory, application_binding_valid=False)
            self.assertEqual(self.events, [])
            self.assertEqual(self.calls, [])
            self.assertEqual(self.backend.intent["state"], "finalized")

    def test_cometbft_spawn_failure_closes_the_previously_opened_abci_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "node-home").mkdir()
            with self.assertRaisesRegex(OSError, "simulated CometBFT spawn failure"):
                self._launch(directory, popen_failure=True)
            self.assertEqual(self.events, ["abci-listener", "cometbft-spawn"])
            self.abci_server.stop.assert_called_once_with(grace=0)
            self.abci_server.stop.return_value.wait.assert_called_once_with()

    def test_unavailable_witness_keeps_node_stopped_with_pending_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "node-home").mkdir()
            with self.assertRaises(Exception):
                self._launch(directory, witness_unavailable=True)
            self.assertEqual(self.calls, [])
            self.assertIsNotNone(self.backend.read_active_state())
            self.assertEqual(self.backend.intent["state"], "pending_witness")

    def test_ambient_environment_is_rejected_before_activation_or_spawn(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "node-home").mkdir()
            with self.assertRaisesRegex(CometBFTSupervisorError, "ENVIRONMENT"):
                self._launch(directory, environment=None)
            self.assertEqual(self.calls, [])
            self.assertIsNone(self.backend.read_active_state())

    def test_dynamic_loader_environment_overrides_are_rejected(self):
        for key in ("LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "GLIBC_TUNABLES"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                (Path(directory) / "node-home").mkdir()
                with self.assertRaisesRegex(CometBFTSupervisorError, "ENVIRONMENT"):
                    self._launch(
                        directory,
                        environment={"PATH": "/usr/bin", key: "/tmp/untrusted"},
                    )
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
                from hnd_v02.cometbft_supervisor import _open_pinned_executable
                _open_pinned_executable(str(link), hashlib.sha256(b"binary").hexdigest())
            self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
