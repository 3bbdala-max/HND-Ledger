"""HREC03 crash-boundary regression tests for HND durable state replacement."""

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.abci_app import HNDABCIApplication
from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.transaction import ProtocolConfig, account_id_for_public_key, public_key_b64


class TestHREC03PreRenameCrashBoundary(unittest.TestCase):
    def setUp(self):
        self.config = ProtocolConfig("hnd-hrec03-crash-test", 2, 1_000_000)
        alice_key = Ed25519PrivateKey.generate()
        bob_key = Ed25519PrivateKey.generate()
        alice_public = public_key_b64(alice_key)
        bob_public = public_key_b64(bob_key)
        self.alice_id = account_id_for_public_key(alice_public, config=self.config)
        bob_id = account_id_for_public_key(bob_public, config=self.config)
        allocations = [
            {"account_id": self.alice_id, "public_key": alice_public, "amount": 600_000},
            {"account_id": bob_id, "public_key": bob_public, "amount": 400_000},
        ]
        allocations.sort(key=lambda item: item["account_id"])
        self.manifest = {
            "manifest_version": 1,
            "network_id": self.config.network_id,
            "protocol_version": self.config.protocol_version,
            "total_supply": 1_000_000,
            "allocations": allocations,
        }
        self.genesis_hash = genesis_manifest_hash(self.manifest)
        self.temp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp.name) / "hnd-state.json"
        self.app = self.make_app()
        self.app.init_chain(
            chain_id=self.config.network_id,
            app_state_bytes=self.app.application_genesis_bytes(),
        )

    def tearDown(self):
        self.temp.cleanup()

    def make_app(self):
        return HNDABCIApplication(
            config=self.config,
            manifest=self.manifest,
            expected_genesis_hash=self.genesis_hash,
            state_path=self.state_path,
        )

    def test_file_fsync_failure_before_replace_keeps_old_generation_recoverable(self):
        old_bytes = self.state_path.read_bytes()
        old_info = self.app.info()
        self.app.finalize_block(height=1, transactions=[])

        real_fsync = os.fsync

        def fail_temporary_file_fsync(fd):
            if stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("simulated temporary state fsync failure")
            return real_fsync(fd)

        with patch("hnd_v02.abci_app.os.fsync", side_effect=fail_temporary_file_fsync):
            with self.assertRaisesRegex(OSError, "temporary state fsync failure"):
                self.app.commit()

        # The candidate was never renamed into the authoritative state path.
        self.assertEqual(self.state_path.read_bytes(), old_bytes)
        self.assertEqual(self.app.info(), old_info)
        self.assertEqual(
            list(Path(self.temp.name).glob(".hnd-state-*.tmp")),
            [],
            "failed temporary generation must be cleaned up",
        )

        # A fresh process must recover the old committed generation, not the
        # in-memory pending candidate or any partially written temporary file.
        recovered = self.make_app()
        self.assertEqual(recovered.info(), old_info)
        self.assertEqual(recovered.last_committed_height, 0)
        self.assertEqual(recovered.account_view(self.alice_id)["balance"], 600_000)


if __name__ == "__main__":
    unittest.main()
