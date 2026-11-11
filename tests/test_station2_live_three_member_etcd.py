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


if __name__ == "__main__":
    unittest.main()
