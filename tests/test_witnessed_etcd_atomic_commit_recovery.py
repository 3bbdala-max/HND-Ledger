"""Regression test for a committed etcd transaction whose HTTP response is lost."""
import unittest
from unittest.mock import patch

from hnd_v02.activation_transaction import ActivationState
from hnd_v02.activation_witness import compute_activation_digest
from hnd_v02.witnessed_etcd_activation_coordinator import (
    WitnessedEtcdActivationCoordinator,
)


class LostCommitResponseBackend:
    def __init__(self, digest):
        self.digest = digest
        self.state = None
        self.profile = None
        self.intent = None
        self.commit_calls = 0
        self.finalized = None

    def read_active_state(self):
        return self.state

    def read_active_profile(self):
        return self.profile

    def compare_and_activate_with_intent(self, current, proposed, profile, *, activation_id):
        self.commit_calls += 1
        self.state = proposed
        self.profile = profile
        self.intent = {
            "activation_id": activation_id,
            "state": "pending_witness",
            "activation_digest": self.digest,
            "trust_manifest_sequence": proposed.trust_manifest_sequence,
            "trust_manifest_digest": proposed.trust_manifest_digest,
            "profile_sequence": proposed.profile_sequence,
            "profile_digest": proposed.profile_digest,
            "operator_ack_digest": proposed.operator_ack_set_sha256,
        }
        if self.commit_calls == 1:
            raise TimeoutError("etcd committed transaction; HTTP response was lost")
        return True

    def read_activation_intent(self, activation_id):
        if self.intent and self.intent["activation_id"] == activation_id:
            return self.intent
        return None

    def finalize_activation_intent(self, activation_id, receipt, **kwargs):
        self.finalized = dict(
            self.intent, state="finalized",
            witness_receipt=receipt, witness_counter=1,
        )
        self.intent = self.finalized
        return self.finalized


class Witness:
    def __init__(self):
        self.calls = []

    def acknowledge(self, activation_id, digest):
        self.calls.append((activation_id, digest))
        return {"schema": "hnd.station2.witness-ack.v1", "signature": "test-receipt"}


class LostEtcdCommitResponseRecoveryTests(unittest.TestCase):
    @patch(
        "hnd_v02.witnessed_etcd_activation_coordinator.verify_activation_bundle_with_manifest_chain"
    )
    def test_reconciles_same_activation_intent_after_lost_etcd_commit_response(self, verify):
        evidence = {
            "trust_manifest_sequence": 0,
            "trust_manifest_digest": "1" * 64,
            "profile_sequence": 1,
            "profile_digest": "2" * 64,
            "activation_height": 100,
            "operator_ack_set_sha256": "3" * 64,
            "previous_trust_manifest_digest": None,
            "previous_profile_digest": None,
        }
        verify.return_value = evidence
        activation_id = "activation-lost-etcd-response-001"
        proposed = ActivationState(**evidence)
        profile = b"immutable-profile-artifact"
        digest = compute_activation_digest(activation_id, proposed, profile)
        backend = LostCommitResponseBackend(digest)
        witness = Witness()
        coordinator = WitnessedEtcdActivationCoordinator(
            backend=backend,
            witness_client=witness,
            trusted_witness_keys={"witness-a": b"k" * 32},
            expected_witness_id="witness-a",
            expected_config_epoch=3,
        )

        result = coordinator.activate(
            activation_id=activation_id,
            vsp_raw=b"vsp",
            trust_manifests=[b"manifest"],
            operator_acks_raw=b"acks",
            profile_artifact=profile,
            context={},
            trusted_operator_keys={},
        )

        self.assertEqual(result, proposed)
        self.assertEqual(backend.commit_calls, 1)
        self.assertEqual(witness.calls, [(activation_id, digest)])
        self.assertEqual(backend.finalized["state"], "finalized")
        self.assertEqual(backend.finalized["activation_digest"], digest)
        self.assertEqual(backend.finalized["witness_receipt"], witness.acknowledge(activation_id, digest))


if __name__ == "__main__":
    unittest.main()
