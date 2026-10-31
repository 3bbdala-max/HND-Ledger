"""Conformance tests for HND v0.2 transaction envelope and account identity."""
import base64
import json
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.transaction import (
    MAX_NONCE,
    ProtocolConfig,
    account_id_for_public_key,
    create_signed_transaction,
    is_account_id_for_config,
    public_key_b64,
    signing_bytes,
    signing_payload,
    transaction_id,
    validate_transaction,
)


class TestV02AccountIdentity(unittest.TestCase):
    def setUp(self):
        self.config = ProtocolConfig("hnd-devnet-alpha", 2, 1_000_000)
        self.alice_key = Ed25519PrivateKey.generate()
        self.bob_key = Ed25519PrivateKey.generate()
        self.alice_public = public_key_b64(self.alice_key)
        self.bob_public = public_key_b64(self.bob_key)
        self.alice_id = account_id_for_public_key(self.alice_public, config=self.config)
        self.bob_id = account_id_for_public_key(self.bob_public, config=self.config)

    def tx(self, **overrides):
        fields = dict(sender=self.alice_id, recipient=self.bob_id, amount=5, nonce=0)
        fields.update(overrides)
        return create_signed_transaction(self.alice_key, config=self.config, **fields)

    def validate(self, tx, **overrides):
        args = dict(config=self.config, expected_nonce=0,
                    sender_balance=100, sender_public_key=self.alice_public)
        args.update(overrides)
        return validate_transaction(tx, **args)

    def test_valid_signed_transaction_with_derived_addresses(self):
        self.assertTrue(is_account_id_for_config(self.alice_id, config=self.config))
        self.assertTrue(is_account_id_for_config(self.bob_id, config=self.config))
        self.assertEqual(self.validate(self.tx()), (True, "ok"))

    def test_account_id_is_deterministic_for_same_public_key(self):
        self.assertEqual(
            account_id_for_public_key(self.alice_public, config=self.config),
            self.alice_id,
        )

    def test_account_id_changes_across_networks(self):
        other = ProtocolConfig("hnd-devnet-beta", 2, 1_000_000)
        self.assertNotEqual(
            self.alice_id,
            account_id_for_public_key(self.alice_public, config=other),
        )

    def test_account_id_changes_across_protocol_versions(self):
        other = ProtocolConfig("hnd-devnet-alpha", 3, 1_000_000)
        self.assertNotEqual(
            self.alice_id,
            account_id_for_public_key(self.alice_public, config=other),
        )

    def test_different_keys_produce_different_account_ids(self):
        self.assertNotEqual(self.alice_id, self.bob_id)

    def test_malformed_public_key_rejected_for_derivation(self):
        for malformed in ("!", "AAAA", "", None):
            with self.subTest(value=malformed):
                with self.assertRaises(ValueError):
                    account_id_for_public_key(malformed, config=self.config)

    def test_wrong_network_or_version_address_rejected(self):
        other_network = ProtocolConfig("hnd-devnet-beta", 2, 1_000_000)
        other_version = ProtocolConfig("hnd-devnet-alpha", 3, 1_000_000)
        self.assertFalse(is_account_id_for_config(self.alice_id, config=other_network))
        self.assertFalse(is_account_id_for_config(self.alice_id, config=other_version))

    def test_malformed_recipient_address_rejected(self):
        with self.assertRaises(ValueError):
            self.tx(recipient="bob")
        with self.assertRaises(ValueError):
            self.tx(recipient="hnd2:hnd-devnet-alpha:not-a-digest")

    def test_signer_cannot_create_transaction_for_another_sender_id(self):
        with self.assertRaisesRegex(ValueError, "sender does not match signing key"):
            self.tx(sender=self.bob_id)

    def test_sender_address_must_match_verifying_public_key(self):
        payload = signing_payload(
            protocol_version=2,
            network_id=self.config.network_id,
            sender=self.bob_id,
            recipient=self.alice_id,
            amount=5,
            nonce=0,
        )
        tx = {**payload, "signature": base64.b64encode(
            self.alice_key.sign(signing_bytes(payload))
        ).decode("ascii")}
        self.assertEqual(self.validate(tx)[1], "sender-key-mismatch")

    def test_account_identifier_tampering_invalidates_signature(self):
        other_key = Ed25519PrivateKey.generate()
        other_id = account_id_for_public_key(public_key_b64(other_key), config=self.config)
        tx = self.tx()
        tx["sender"] = other_id
        self.assertEqual(self.validate(tx)[1], "sender-key-mismatch")

    def test_published_deterministic_identity_and_transaction_vector(self):
        vector_path = Path(__file__).resolve().parents[1] / "vectors" / "v0.2-transaction-envelope-example.json"
        vector = json.loads(vector_path.read_text(encoding="utf-8"))
        cfg = ProtocolConfig(**vector["protocol_config"])
        self.assertEqual(
            account_id_for_public_key(vector["sender_public_key_base64"], config=cfg),
            vector["transaction"]["sender"],
        )
        self.assertEqual(
            account_id_for_public_key(vector["recipient_public_key_base64"], config=cfg),
            vector["transaction"]["recipient"],
        )
        self.assertEqual(
            validate_transaction(
                vector["transaction"], config=cfg, expected_nonce=0,
                sender_balance=100,
                sender_public_key=vector["sender_public_key_base64"],
            ),
            (True, "ok"),
        )
        self.assertEqual(transaction_id(vector["transaction"]), vector["transaction_id_sha256"])


class TestV02TransactionRules(unittest.TestCase):
    def setUp(self):
        self.config = ProtocolConfig("hnd-devnet-alpha", 2, 1_000_000)
        self.alice_key = Ed25519PrivateKey.generate()
        self.bob_key = Ed25519PrivateKey.generate()
        self.alice_public = public_key_b64(self.alice_key)
        self.bob_public = public_key_b64(self.bob_key)
        self.alice_id = account_id_for_public_key(self.alice_public, config=self.config)
        self.bob_id = account_id_for_public_key(self.bob_public, config=self.config)

    def tx(self, **overrides):
        fields = dict(sender=self.alice_id, recipient=self.bob_id, amount=5, nonce=0)
        fields.update(overrides)
        return create_signed_transaction(self.alice_key, config=self.config, **fields)

    def validate(self, tx, **overrides):
        args = dict(config=self.config, expected_nonce=0,
                    sender_balance=100, sender_public_key=self.alice_public)
        args.update(overrides)
        return validate_transaction(tx, **args)

    def test_bool_amount_rejected(self):
        self.assertEqual(self.validate(self.tx(amount=True)), (False, "amount"))

    def test_float_string_zero_negative_and_over_limit_amount_rejected(self):
        for value in (5.0, "5", None, 0, -1, 1_000_001):
            with self.subTest(value=value):
                self.assertEqual(self.validate(self.tx(amount=value))[1], "amount")

    def test_bool_float_string_negative_and_overflow_nonce_rejected(self):
        for value in (False, 0.0, "0", -1, MAX_NONCE + 1):
            with self.subTest(value=value):
                self.assertEqual(self.validate(self.tx(nonce=value))[1], "nonce-type-or-range")

    def test_nonce_must_match_expected_value(self):
        self.assertEqual(self.validate(self.tx(nonce=1), expected_nonce=0)[1], "nonce")

    def test_network_and_protocol_version_are_bound_to_transaction(self):
        tx = self.tx()
        self.assertEqual(
            self.validate(tx, config=ProtocolConfig("hnd-devnet-beta", 2, 1_000_000))[1],
            "network_id",
        )
        self.assertEqual(
            self.validate(tx, config=ProtocolConfig("hnd-devnet-alpha", 3, 1_000_000))[1],
            "protocol_version",
        )

    def test_signature_covers_every_identity_and_transaction_field(self):
        tx = self.tx()
        tx["recipient"] = self.alice_id
        self.assertEqual(self.validate(tx)[1], "self-transfer")
        tx = self.tx()
        tx["amount"] = 6
        self.assertEqual(self.validate(tx)[1], "signature")
        tx = self.tx()
        tx["nonce"] = 1
        self.assertEqual(self.validate(tx)[1], "nonce")

    def test_malformed_signature_and_sender_public_key_rejected(self):
        tx = self.tx()
        tx["signature"] = "not-base64"
        self.assertEqual(self.validate(tx)[1], "signature")
        self.assertEqual(self.validate(self.tx(), sender_public_key="bad")[1], "signature")

    def test_missing_and_unknown_fields_rejected(self):
        tx = self.tx()
        tx["fee"] = 0
        self.assertEqual(self.validate(tx), (False, "schema"))
        tx = self.tx()
        del tx["network_id"]
        self.assertEqual(self.validate(tx), (False, "schema"))

    def test_balance_and_expected_nonce_types_are_strict(self):
        self.assertEqual(self.validate(self.tx(amount=101), sender_balance=100)[1], "balance")
        self.assertEqual(self.validate(self.tx(), expected_nonce=True)[1], "expected-nonce")
        self.assertEqual(self.validate(self.tx(), sender_balance=True)[1], "sender-balance")

    def test_protocol_config_rejects_boolean_values(self):
        with self.assertRaises(ValueError):
            ProtocolConfig("hnd-devnet-alpha", True, 100)
        with self.assertRaises(ValueError):
            ProtocolConfig("hnd-devnet-alpha", 2, True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
