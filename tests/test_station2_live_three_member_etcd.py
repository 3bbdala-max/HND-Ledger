"""Live integration checks against a real three-member etcd v3 cluster.

The CI harness supplies an HTTPS JSON-gateway endpoint and a client TLS
certificate. These tests establish real Raft-backed transaction/CAS behavior;
they do not claim independent administrative or disaster-recovery domains.
"""
from __future__ import annotations

import hashlib
import os
import ssl
import unittest
from concurrent.futures import ThreadPoolExecutor

from hnd_v02.activation_transaction import ActivationState
from hnd_v02.activation_witness import compute_activation_digest
from hnd_v02.etcd_atomic_activation import EtcdV3AtomicActivationBackend


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class LiveThreeMemberEtcdActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        endpoint = os.environ.get("HND_ETCD_ENDPOINT")
        ca_file = os.environ.get("HND_ETCD_CA_FILE")
        cert_file = os.environ.get("HND_ETCD_CLIENT_CERT")
        key_file = os.environ.get("HND_ETCD_CLIENT_KEY")
        if not all((endpoint, ca_file, cert_file, key_file)):
            raise RuntimeError("live etcd integration environment is incomplete")
        context = ssl.create_default_context(cafile=ca_file)
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        cls.endpoint = endpoint
        cls.context = context

    def setUp(self):
        self.backend = EtcdV3AtomicActivationBackend(
            self.endpoint,
            profile_validator=lambda raw, expected: _digest(raw) == expected,
            key_prefix="/hnd/station2/live-integration/" + self._testMethodName,
            timeout=10,
            ssl_context=self.context,
        )

    def _state(self, *, trust_seq, profile_seq, height, profile, previous=None):
        return ActivationState(
            trust_manifest_sequence=trust_seq,
            trust_manifest_digest=_digest(f"trust-{trust_seq}".encode()),
            profile_sequence=profile_seq,
            profile_digest=_digest(profile),
            activation_height=height,
            operator_ack_set_sha256=_digest(f"acks-{height}".encode()),
            previous_trust_manifest_digest=(
                previous.trust_manifest_digest if previous else None
            ),
            previous_profile_digest=previous.profile_digest if previous else None,
        )

    def test_real_cluster_atomic_bootstrap_and_readback(self):
        profile = b"station2-live-etcd-bootstrap-profile"
        state = self._state(
            trust_seq=0, profile_seq=1, height=1, profile=profile
        )
        activation_id = "ci-live-bootstrap-001"
        self.assertTrue(
            self.backend.compare_and_activate_with_intent(
                None, state, profile, activation_id=activation_id
            )
        )
        self.assertEqual(self.backend.read_active_state(), state)
        self.assertEqual(self.backend.read_active_profile(), profile)
        intent = self.backend.read_activation_intent(activation_id)
        self.assertEqual(intent["state"], "pending_witness")
        self.assertEqual(intent["activation_id"], activation_id)

    def test_real_cluster_allows_only_one_concurrent_cas_successor(self):
        current_profile = b"station2-live-etcd-race-base"
        current = self._state(
            trust_seq=0, profile_seq=1, height=10, profile=current_profile
        )
        bootstrap_id = "ci-live-race-bootstrap-001"
        self.assertTrue(
            self.backend.compare_and_activate_with_intent(
                None, current, current_profile, activation_id=bootstrap_id
            )
        )

        candidates = []
        for suffix in ("a", "b"):
            profile = f"station2-live-race-{suffix}".encode()
            state = self._state(
                trust_seq=1, profile_seq=2, height=11,
                profile=profile, previous=current,
            )
            candidates.append((f"ci-live-race-{suffix}", state, profile))

        def attempt(candidate):
            activation_id, state, profile = candidate
            return self.backend.compare_and_activate_with_intent(
                current, state, profile, activation_id=activation_id
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, candidates))
        self.assertEqual(sorted(results), [False, True])

        observed = self.backend.read_active_state()
        self.assertIn(observed, [candidate[1] for candidate in candidates])
        self.assertIn(self.backend.read_active_profile(),
                      [candidate[2] for candidate in candidates])


    def test_two_member_loss_blocks_activation_then_recovers(self):
        """Stopping two Raft members must block writes until quorum returns."""
        pid_file = os.environ.get("HND_ETCD_PID_FILE")
        self.assertTrue(pid_file, "live etcd member PID file is required")
        with open(pid_file, encoding="ascii") as stream:
            pids = [int(line.strip()) for line in stream if line.strip()]
        self.assertEqual(len(pids), 3, "expected exactly three etcd members")

        stopped = pids[1:]
        try:
            for pid in stopped:
                os.kill(pid, 19)  # SIGSTOP: preserve data dir for deterministic recovery
            profile = b"station2-no-quorum-must-not-activate"
            state = self._state(
                trust_seq=0, profile_seq=1, height=20, profile=profile
            )
            with self.assertRaises(Exception) as caught:
                self.backend.compare_and_activate_with_intent(
                    None, state, profile, activation_id="ci-live-no-quorum-001"
                )
            self.assertIn(
                "HND-ETCD-ACT-E-REQUEST",
                str(caught.exception),
                "quorum loss must fail closed as an unavailable transaction",
            )
        finally:
            for pid in stopped:
                try:
                    os.kill(pid, 18)  # SIGCONT
                except ProcessLookupError:
                    pass

        # Raft election and linearizable reads can remain unavailable briefly
        # after SIGCONT. Retry the same immutable activation ID until quorum
        # returns; reconcile an ambiguous response by reading the committed state.
        import time

        profile = b"station2-quorum-recovered"
        state = self._state(
            trust_seq=0, profile_seq=1, height=21, profile=profile
        )
        activation_id = "ci-live-quorum-recovery-001"
        expected_digest = compute_activation_digest(activation_id, state, profile)
        deadline = time.monotonic() + 20.0
        recovered = False
        last_error = None
        while time.monotonic() < deadline:
            try:
                # Retry only this immutable activation ID. If the prior
                # transaction committed but its response was lost, the CAS
                # retry must reconcile the exact state and intent below.
                self.backend.compare_and_activate_with_intent(
                    None, state, profile, activation_id=activation_id
                )
            except Exception as exc:
                last_error = exc

            try:
                observed_state = self.backend.read_active_state()
                if observed_state == state:
                    observed_profile = self.backend.read_active_profile()
                    intent = self.backend.read_activation_intent(activation_id)
                    if (
                        observed_profile == profile
                        and type(intent) is dict
                        and intent.get("state") == "pending_witness"
                        and intent.get("activation_id") == activation_id
                        and intent.get("activation_digest") == expected_digest
                    ):
                        recovered = True
                        break
                    last_error = AssertionError(
                        "recovered etcd data did not match the exact activation "
                        "profile and immutable witness intent"
                    )
            except Exception as exc:
                last_error = exc
            time.sleep(0.25)

        self.assertTrue(
            recovered,
            "etcd did not regain quorum and reconcile the exact activation "
            f"within 20s: {last_error!r}",
        )


if __name__ == "__main__":
    unittest.main()
