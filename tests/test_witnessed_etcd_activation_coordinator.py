import unittest
from unittest.mock import patch

from hnd_v02.activation_transaction import ActivationState
from hnd_v02.witnessed_etcd_activation_coordinator import (
    WitnessedActivationCoordinatorError,
    WitnessedEtcdActivationCoordinator,
)


class _Backend:
    def __init__(self):
        self.state = None
        self.profile = None
        self.intent = None
        self.finalized_receipt = None

    def read_active_state(self):
        return self.state

    def read_active_profile(self):
        return self.profile

    def compare_and_activate_with_intent(self, current, proposed, profile, *, activation_id):
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
        return True

    def read_activation_intent(self, activation_id):
        return self.intent

    def finalize_activation_intent(self, activation_id, receipt, **kwargs):
        self.finalized_receipt = receipt
        self.intent = dict(
            self.intent, state="finalized", witness_receipt=receipt, witness_counter=1
        )
        return self.intent


class _Witness:
    def __init__(self, receipt):
        self.receipt = receipt
        self.calls = []

    def acknowledge(self, activation_id, digest):
        self.calls.append((activation_id, digest))
        return self.receipt


class WitnessedEtcdActivationCoordinatorTests(unittest.TestCase):
    def evidence(self):
        return {
            "trust_manifest_sequence": 0,
            "trust_manifest_digest": "1" * 64,
            "profile_sequence": 1,
            "profile_digest": "2" * 64,
            "activation_height": 100,
            "operator_ack_set_sha256": "3" * 64,
            "previous_trust_manifest_digest": None,
            "previous_profile_digest": None,
        }

    @patch(
        "hnd_v02.witnessed_etcd_activation_coordinator.verify_activation_bundle_with_manifest_chain"
    )
    def test_activation_returns_only_after_witness_finalization_and_readback(self, verify):
        verify.return_value = self.evidence()
        backend = _Backend()
        receipt = {"schema": "hnd.station2.witness-ack.v1", "signature": "opaque"}
        witness = _Witness(receipt)
        coordinator = WitnessedEtcdActivationCoordinator(
            backend=backend,
            witness_client=witness,
            trusted_witness_keys={"witness-a": b"k" * 32},
            expected_witness_id="witness-a",
            expected_config_epoch=3,
        )
        backend.digest = "0" * 64
        # The backend's atomic commit must write the digest calculated from the
        # same complete state and exact profile artifact.
        from hnd_v02.activation_witness import compute_activation_digest
        proposed = ActivationState(**self.evidence())
        backend.digest = compute_activation_digest("activation-001", proposed, b"profile")
        result = coordinator.activate(
            activation_id="activation-001",
            vsp_raw=b"vsp",
            trust_manifests=[b"manifest"],
            operator_acks_raw=b"acks",
            profile_artifact=b"profile",
            context={},
            trusted_operator_keys={},
        )
        self.assertEqual(result, proposed)
        self.assertEqual(witness.calls, [("activation-001", backend.digest)])
        self.assertEqual(backend.finalized_receipt, receipt)
        self.assertEqual(backend.intent["state"], "finalized")

    @patch(
        "hnd_v02.witnessed_etcd_activation_coordinator.verify_activation_bundle_with_manifest_chain"
    )
    def test_invalid_evidence_stops_before_any_activation_or_witness_call(self, verify):
        verify.side_effect = ValueError("bad evidence")
        backend = _Backend()
        witness = _Witness({})
        coordinator = WitnessedEtcdActivationCoordinator(
            backend=backend,
            witness_client=witness,
            trusted_witness_keys={"witness-a": b"k" * 32},
            expected_witness_id="witness-a",
            expected_config_epoch=3,
        )
        with self.assertRaises(WitnessedActivationCoordinatorError):
            coordinator.activate(
                activation_id="activation-002",
                vsp_raw=b"vsp",
                trust_manifests=[b"manifest"],
                operator_acks_raw=b"acks",
                profile_artifact=b"profile",
                context={},
                trusted_operator_keys={},
            )
        self.assertIsNone(backend.intent)
        self.assertEqual(witness.calls, [])


if __name__ == "__main__":
    unittest.main()
