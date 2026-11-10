import base64, copy, unittest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hnd_v02.operator_ack import (
    OperatorAckError, acknowledgement_message, verify_unanimous_operator_acks,
)

def b64(value): return base64.b64encode(value).decode("ascii")

class OperatorAckTests(unittest.TestCase):
    def setUp(self):
        self.keys = {f"operator-{i+1}": Ed25519PrivateKey.generate() for i in range(4)}
        self.public = {name:key.public_key().public_bytes_raw() for name,key in self.keys.items()}
        self.chain = "hnd-testnet-1"
        self.profile = "a" * 64
        self.height = 250
        self.items = []
        for name,key in self.keys.items():
            nonce = (name + "-unique-nonce-0001").replace("-", "_")
            message = acknowledgement_message(chain_id=self.chain,
                profile_sha256=self.profile, activation_height=self.height,
                operator_id=name, nonce=nonce)
            self.items.append({"schema":"hnd.operator-ack","schema_version":1,
                "chain_id":self.chain,"profile_sha256":self.profile,
                "activation_height":self.height,"operator_id":name,
                "nonce":nonce,"signature":b64(key.sign(message))})
        self.items.sort(key=lambda item:item["operator_id"])
        self.raw = rfc8785.dumps(self.items)

    def verify(self, raw=None):
        return verify_unanimous_operator_acks(raw if raw is not None else self.raw,
            expected_chain_id=self.chain, expected_profile_sha256=self.profile,
            expected_activation_height=self.height, expected_operator_keys=self.public)

    def test_all_operators_must_ack_same_profile(self):
        result = self.verify()
        self.assertTrue(result["unanimous"])
        self.assertEqual(result["operator_count"], 4)

    def test_missing_or_extra_ack_is_rejected(self):
        with self.assertRaisesRegex(OperatorAckError, "ACK-E-UNANIMOUS-SET"):
            self.verify(rfc8785.dumps(self.items[:-1]))
        changed = copy.deepcopy(self.items)
        changed.append(copy.deepcopy(changed[-1]))
        changed.sort(key=lambda item:item["operator_id"])
        with self.assertRaises(OperatorAckError):
            self.verify(rfc8785.dumps(changed))

    def test_wrong_profile_or_height_is_rejected(self):
        changed = copy.deepcopy(self.items)
        changed[0]["profile_sha256"] = "b" * 64
        with self.assertRaisesRegex(OperatorAckError, "ACK-E-PROFILE-CONTEXT"):
            self.verify(rfc8785.dumps(changed))
        changed = copy.deepcopy(self.items)
        changed[0]["activation_height"] += 1
        with self.assertRaisesRegex(OperatorAckError, "ACK-E-PROFILE-CONTEXT|ACK-E-ACTIVATION"):
            self.verify(rfc8785.dumps(changed))

    def test_bad_signature_and_duplicate_identity_are_rejected(self):
        changed = copy.deepcopy(self.items)
        changed[0]["signature"] = b64(bytes(64))
        with self.assertRaisesRegex(OperatorAckError, "ACK-E-SIGNATURE-VERIFY"):
            self.verify(rfc8785.dumps(changed))
        changed = copy.deepcopy(self.items)
        changed[1]["operator_id"] = changed[0]["operator_id"]
        changed.sort(key=lambda item:item["operator_id"])
        with self.assertRaises(OperatorAckError):
            self.verify(rfc8785.dumps(changed))

    def test_rejects_shared_public_key_for_distinct_operator_ids(self):
        keys = dict(self.public)
        keys["operator-2"] = keys["operator-1"]
        with self.assertRaisesRegex(OperatorAckError, "ACK-E-EXPECTED-KEY-DUPLICATE"):
            verify_unanimous_operator_acks(self.raw, expected_chain_id=self.chain,
                expected_profile_sha256=self.profile, expected_activation_height=self.height,
                expected_operator_keys=keys)

    def test_noncanonical_and_invalid_inputs_fail_closed(self):
        with self.assertRaisesRegex(OperatorAckError, "ACK-E-NONCANONICAL"):
            self.verify(self.raw + b" ")
        with self.assertRaises(OperatorAckError):
            self.verify(b"\xef\xbb\xbf" + self.raw)

if __name__ == "__main__":
    unittest.main()
