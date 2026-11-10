import unittest
from unittest.mock import patch

from hnd_v02.activation_bundle import verify_activation_bundle_with_manifest_chain


class ActivationBundleRotationTests(unittest.TestCase):
    def test_chain_verification_precedes_unanimous_operator_acknowledgement(self):
        context = {"chain_id": "hnd-test-1"}
        manifests = [b"bootstrap", b"rotation-1", b"rotation-2"]
        vsp = {
            "profile_digest": "a" * 64,
            "profile_sequence": 7,
            "activation_height": 120,
            "validator_count": 4,
        }
        chain = {
            "sequence": 2,
            "manifest_digest": "b" * 64,
            "governance_key_ids": ["g1", "g2", "g3"],
            "governance_public_keys": {"g1": b"1" * 32},
            "rotation_count": 2,
        }
        with patch("hnd_v02.activation_bundle.verify_vsp_with_trust_manifest_chain",
                   return_value={"trust_manifest_chain": chain, "vsp": vsp}) as verify_chain, \\
             patch("hnd_v02.activation_bundle.verify_unanimous_operator_acks",
                   return_value={"ack_set_sha256": "c" * 64, "operator_count": 4,
                                 "unanimous": True}) as verify_acks:
            result = verify_activation_bundle_with_manifest_chain(
                b"vsp", manifests, b"acks", context=context,
                trusted_witness_keys={"w1": b"w" * 32},
                expected_operator_keys={"op1": b"o" * 32},
            )
        verify_chain.assert_called_once_with(
            b"vsp", manifests, context=context,
            trusted_witness_keys={"w1": b"w" * 32},
        )
        verify_acks.assert_called_once_with(
            b"acks", expected_chain_id="hnd-test-1",
            expected_profile_sha256="a" * 64,
            expected_activation_height=120,
            expected_operator_keys={"op1": b"o" * 32},
        )
        self.assertEqual(result["trust_manifest_sequence"], 2)
        self.assertEqual(result["profile_sequence"], 7)
        self.assertTrue(result["preflight_accepted"])
        self.assertFalse(result["activation_performed"])


if __name__ == "__main__":
    unittest.main()
