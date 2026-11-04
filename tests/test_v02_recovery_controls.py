"""Negative controls for bounded recovery and fail-closed convergence."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hnd_v02.recovery_controls import (
    RecoveryReadinessTimeout,
    ReplicaConvergenceError,
    assert_replica_convergence,
    wait_for_recovery_readiness,
)


class TestRecoveryControls(unittest.TestCase):
    def test_readiness_timeout_terminates_process_without_touching_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "durable-state.json"
            original = b'{"height":7,"app_hash":"pinned"}\n'
            state.write_bytes(original)
            process = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with self.assertRaisesRegex(
                RecoveryReadinessTimeout, "process_terminated=true"
            ):
                wait_for_recovery_readiness(
                    process,
                    lambda: False,
                    timeout_seconds=0.08,
                    poll_interval=0.01,
                    terminate_grace_seconds=0.5,
                )
            self.assertIsNotNone(process.poll())
            self.assertEqual(state.read_bytes(), original)
            self.assertFalse(process.returncode == 0)

    def test_ready_process_is_not_terminated(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_for_recovery_readiness(
                process, lambda: True, timeout_seconds=0.5
            )
            self.assertIsNone(process.poll())
        finally:
            process.terminate()
            process.wait(timeout=2)

    def test_recovery_gate_rejects_post_recovery_divergence_by_validator(self):
        fingerprints = [
            {"validator": "val1", "height": 10, "block_hash": "block-a", "app_hash": b"a" * 32},
            {"validator": "val2", "height": 10, "block_hash": "block-a", "app_hash": b"a" * 32},
            {"validator": "val3", "height": 10, "block_hash": "block-a", "app_hash": b"a" * 32},
            {"validator": "val4", "height": 10, "block_hash": "block-a", "app_hash": b"b" * 32},
        ]
        with self.assertRaisesRegex(
            ReplicaConvergenceError, "divergent=val4"
        ):
            assert_replica_convergence(fingerprints)

    def test_recovery_gate_rejects_height_and_block_hash_mismatch(self):
        fingerprints = [
            {"validator": "val1", "height": 10, "block_hash": "block-a", "app_hash": b"a" * 32},
            {"validator": "val2", "height": 11, "block_hash": "block-b", "app_hash": b"a" * 32},
        ]
        with self.assertRaisesRegex(ReplicaConvergenceError, "divergent=val2"):
            assert_replica_convergence(fingerprints)


if __name__ == "__main__":
    unittest.main(verbosity=2)
