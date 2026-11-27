import base64
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.activation_transaction import ActivationState
from hnd_v02.activation_witness import (
    ActivationWitnessError,
    compute_activation_digest,
    verify_witness_receipt,
    _canonical,
    _DOMAIN,
)


class ActivationWitnessReceiptTests(unittest.TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        self.public = self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.state = ActivationState(
            trust_manifest_sequence=0,
            trust_manifest_digest="1" * 64,
            profile_sequence=1,
            profile_digest="2" * 64,
            activation_height=100,
            operator_ack_set_sha256="3" * 64,
        )
        self.activation_id = "station2-bootstrap-001"
        self.digest = compute_activation_digest(
            self.activation_id, self.state, b"exact-profile-artifact"
        )
        self.trusted = {"witness-east-01": self.public}

    def receipt(self):
        payload = {
            "schema": "hnd.station2.witness-ack.v1",
            "activation_id": self.activation_id,
            "activation_digest": self.digest,
            "witness_id": "witness-east-01",
            "config_epoch": 7,
            "counter": 41,
        }
        signature = self.private.sign(_DOMAIN + _canonical(payload))
        return {
            **payload,
            "signature": base64.b64encode(signature).decode("ascii"),
        }

    def verify(self, receipt):
        return verify_witness_receipt(
            receipt,
            trusted_witness_keys=self.trusted,
            expected_activation_id=self.activation_id,
            expected_activation_digest=self.digest,
            expected_witness_id="witness-east-01",
            expected_config_epoch=7,
        )

    def test_accepts_exact_trusted_signed_receipt(self):
        verified = self.verify(self.receipt())
        self.assertEqual(verified.activation_id, self.activation_id)
        self.assertEqual(verified.activation_digest, self.digest)
        self.assertEqual(verified.counter, 41)

    def test_rejects_signature_tampering(self):
        receipt = self.receipt()
        receipt["counter"] = 42
        with self.assertRaises(ActivationWitnessError):
            self.verify(receipt)

    def test_rejects_different_activation_digest(self):
        receipt = self.receipt()
        receipt["activation_digest"] = "f" * 64
        with self.assertRaises(ActivationWitnessError):
            self.verify(receipt)

    def test_rejects_untrusted_witness_identity(self):
        receipt = self.receipt()
        receipt["witness_id"] = "witness-unknown"
        with self.assertRaises(ActivationWitnessError):
            self.verify(receipt)

    def test_rejects_wrong_configuration_epoch(self):
        receipt = self.receipt()
        receipt["config_epoch"] = 8
        with self.assertRaises(ActivationWitnessError):
            self.verify(receipt)

    def test_rejects_duplicate_or_extra_fields_by_exact_shape(self):
        receipt = self.receipt()
        receipt["extra"] = "not-signed"
        with self.assertRaises(ActivationWitnessError):
            self.verify(receipt)

    def test_activation_digest_binds_exact_profile_bytes(self):
        other = compute_activation_digest(
            self.activation_id, self.state, b"different-profile-artifact"
        )
        self.assertNotEqual(self.digest, other)


if __name__ == "__main__":
    unittest.main()
