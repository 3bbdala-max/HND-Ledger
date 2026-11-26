"""Regression tests for the explicitly disposable ABCI integration adapter."""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.abci_app import ABCIApplicationError, HNDABCIApplication
from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.transaction import (
    ProtocolConfig,
    account_id_for_public_key,
    canonical_json,
    public_key_b64,
)
from scripts.hnd_v02_test_abci_server import build_application, main

TEST_ENV = "HND_DISPOSABLE_ABCI_TEST_SERVER"


class DisposableABCIServerTests(unittest.TestCase):
    def _args(self, root: Path, *, recovery: bool = False) -> Namespace:
        config = ProtocolConfig("disposable-abci-test", 2, 1000)
        key = Ed25519PrivateKey.generate()
        public_key = public_key_b64(key)
        account_id = account_id_for_public_key(public_key, config=config)
        manifest = {
            "manifest_version": 1,
            "network_id": config.network_id,
            "protocol_version": config.protocol_version,
            "total_supply": 1000,
            "allocations": [
                {
                    "account_id": account_id,
                    "public_key": public_key,
                    "amount": 1000,
                }
            ],
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_bytes(canonical_json(manifest))
        return Namespace(
            manifest=str(manifest_path),
            genesis_hash=genesis_manifest_hash(manifest),
            network_id=config.network_id,
            protocol_version=config.protocol_version,
            max_amount=config.max_amount,
            state_path=str(root / "state.json"),
            initialize_genesis=not recovery,
            recovery=recovery,
        )

    def test_entrypoint_refuses_without_explicit_test_environment(self):
        with patch.dict(os.environ, {TEST_ENV: "0"}):
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main([])
        self.assertEqual(raised.exception.code, 2)

    def test_entrypoint_requires_explicit_startup_mode(self):
        argv = [
            "--manifest", "unused.json",
            "--genesis-hash", "0" * 64,
            "--network-id", "disposable-abci-test",
            "--max-amount", "1000",
            "--state-path", "unused-state.json",
        ]
        with patch.dict(os.environ, {TEST_ENV: "1"}):
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main(argv)
        self.assertEqual(raised.exception.code, 2)

    def test_first_boot_builds_uninitialized_app_for_cometbft_initchain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self._args(root)
            app = build_application(args)
            self.assertIsInstance(app, HNDABCIApplication)
            self.assertFalse(app._initialized)
            self.assertFalse(Path(args.state_path).exists())

    def test_first_boot_refuses_to_reuse_existing_state_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self._args(root)
            Path(args.state_path).write_bytes(b"do-not-overwrite")
            with self.assertRaisesRegex(ValueError, "Genesis initialization requires an absent state path"):
                build_application(args)
            self.assertEqual(Path(args.state_path).read_bytes(), b"do-not-overwrite")

    def test_recovery_mode_refuses_missing_state(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self._args(Path(directory), recovery=True)
            with self.assertRaisesRegex(ABCIApplicationError, "recovery mode requires an existing"):
                build_application(args)

    def test_manifest_genesis_mismatch_fails_before_server_start(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self._args(Path(directory))
            args.genesis_hash = "0" * 64
            with self.assertRaisesRegex(ValueError, "independently supplied --genesis-hash"):
                build_application(args)


if __name__ == "__main__":
    unittest.main()
