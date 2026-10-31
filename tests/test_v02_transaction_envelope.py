"""Conformance tests for the isolated HND v0.2 transaction-envelope draft."""
import json
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.transaction import (
    MAX_NONCE,
    ProtocolConfig,
    create_signed_transaction,
    public_key_b64,
    transaction_id,
    validate_transaction,
)


class TestV02TransactionEnvelope(unittest.TestCase):
    def setUp(self):
        self.config = ProtocolConfig(
            network_id="hnd-devnet-alpha",
            protocol_version=2,
            max_amount=1_000_000,
        )
        self.key = Ed25519PrivateKey.generate()
        self.pub = public_key_b64(self.key)

    def tx(self, **overrides):
        fields = dict(sender="alice", recipient="bob", amount=5, nonce=0)
        fields.update(overrides)
        return create_signed_transaction(self.key, config=self.config, **fields)

    def validate(self, tx, **overrides):
        args = dict(config=self.config, expected_nonce=0,
                    sender_balance=100, sender_public_key=self.pub)
        args.update(overrides)
        return validate_transaction(tx, **args)

    def test_valid_signed_transaction(self):
        self.assertEqual(self.validate(self.tx()), (True, "ok"))

    def test_bool_amount_rejected(self):
        self.assertEqual(self.validate(self.tx(amount=True)), (False, "amount"))

    def test_float_and_string_amount_rejected(self):
        for value in (5.0, "5", None):
            with self.subTest(value=value):
                self.assertEqual(self.validate(self.tx(amount=value))[1], "amount")

    def test_zero_negative_and_over_limit_amount_rejected(self):
        for value in (0, -1, 1_000_001):
            with self.subTest(value=value):
                self.assertEqual(self.validate(self.tx(amount=value))[1], "amount")

    def test_bool_float_string_and_negative_nonce_rejected(self):
        for value in (False, 0.0, "0", -1):
            with self.subTest(value=value):
                self.assertEqual(self.validate(self.tx(nonce=value))[1], "nonce-type-or-range")

    def test_nonce_overflow_rejected(self):
        self.assertEqual(self.validate(self.tx(nonce=MAX_NONCE + 1))[1], "nonce-type-or-range")

    def test_nonce_must_match_expected_value(self):
        tx = self.tx(nonce=1)
        self.assertEqual(self.validate(tx, expected_nonce=0)[1], "nonce")

    def test_network_replay_rejected(self):
        tx = self.tx()
        other_network = ProtocolConfig("hnd-devnet-beta", 2, 1_000_000)
        self.assertEqual(self.validate(tx, config=other_network), (False, "network_id"))

    def test_protocol_version_replay_rejected(self):
        tx = self.tx()
        other_version = ProtocolConfig("hnd-devnet-alpha", 3, 1_000_000)
        self.assertEqual(self.validate(tx, config=other_version), (False, "protocol_version"))

    def test_signature_covers_network_and_version(self):
        tx = self.tx()
        tx["network_id"] = "hnd-devnet-beta"
        cfg = ProtocolConfig("hnd-devnet-beta", 2, 1_000_000)
        self.assertEqual(self.validate(tx, config=cfg)[1], "signature")
        tx = self.tx()
        tx["protocol_version"] = 3
        cfg = ProtocolConfig("hnd-devnet-alpha", 3, 1_000_000)
        self.assertEqual(self.validate(tx, config=cfg)[1], "signature")

    def test_tampered_amount_or_recipient_invalidates_signature(self):
        tx = self.tx()
        tx["amount"] = 6
        self.assertEqual(self.validate(tx)[1], "signature")
        tx = self.tx()
        tx["recipient"] = "mallory"
        self.assertEqual(self.validate(tx)[1], "signature")

    def test_malformed_signature_and_public_key_rejected(self):
        tx = self.tx()
        tx["signature"] = "not-base64"
        self.assertEqual(self.validate(tx)[1], "signature")
        tx = self.tx()
        self.assertEqual(self.validate(tx, sender_public_key="bad")[1], "signature")

    def test_unknown_or_missing_fields_rejected(self):
        tx = self.tx()
        tx["fee"] = 0
        self.assertEqual(self.validate(tx), (False, "schema"))
        tx = self.tx()
        del tx["network_id"]
        self.assertEqual(self.validate(tx), (False, "schema"))

    def test_balance_and_self_transfer_checks(self):
        self.assertEqual(self.validate(self.tx(amount=101), sender_balance=100)[1], "balance")
        self.assertEqual(self.validate(self.tx(recipient="alice"))[1], "self-transfer")

    def test_config_rejects_boolean_numeric_parameters(self):
        with self.assertRaises(ValueError):
            ProtocolConfig("hnd-devnet-alpha", True, 100)
        with self.assertRaises(ValueError):
            ProtocolConfig("hnd-devnet-alpha", 2, True)
        with self.assertRaises(ValueError):
            ProtocolConfig("bad network id", 2, 100)

    def test_published_deterministic_vector(self):
        from pathlib import Path
        vector_path = Path(__file__).resolve().parents[1] / "vectors" / "v0.2-transaction-envelope-example.json"
        vector = json.loads(vector_path.read_text(encoding="utf-8"))
        cfg = ProtocolConfig(**vector["protocol_config"])
        tx = vector["transaction"]
        self.assertEqual(
            validate_transaction(
                tx, config=cfg, expected_nonce=0, sender_balance=100,
                sender_public_key=vector["sender_public_key_base64"],
            ),
            (True, "ok"),
        )
        self.assertEqual(transaction_id(tx), vector["transaction_id_sha256"])

    def test_transaction_id_is_deterministic_and_domain_specific(self):
        tx_a = self.tx()
        tx_b = self.tx()
        self.assertEqual(transaction_id(tx_a), transaction_id(tx_b))
        tx_other = create_signed_transaction(
            self.key, config=ProtocolConfig("hnd-devnet-beta", 2, 1_000_000),
            sender="alice", recipient="bob", amount=5, nonce=0)
        self.assertNotEqual(transaction_id(tx_a), transaction_id(tx_other))


if __name__ == "__main__":
    unittest.main(verbosity=2)
