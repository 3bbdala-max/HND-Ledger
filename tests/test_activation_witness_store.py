import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from hnd_v02.activation_witness import verify_witness_receipt
from hnd_v02.activation_witness_store import (
    ActivationWitnessStoreError, SQLiteActivationWitnessStore,
)


class SQLiteActivationWitnessStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = self.temp.name + "/witness.sqlite"
        self.key = Ed25519PrivateKey.generate()
        self.public = self.key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def store(self):
        return SQLiteActivationWitnessStore(
            self.path, witness_id="witness-a", config_epoch=7,
            signing_key=self.key,
        )

    def test_ack_is_signed_and_idempotent_across_store_restart(self):
        first = self.store().acknowledge("activation-1", "a" * 64)
        second = self.store().acknowledge("activation-1", "a" * 64)
        restarted = self.store().acknowledge("activation-1", "a" * 64)
        self.assertEqual(first, second)
        self.assertEqual(first, restarted)
        verified = verify_witness_receipt(
            first, trusted_witness_keys={"witness-a": self.public},
            expected_activation_id="activation-1",
            expected_activation_digest="a" * 64,
            expected_witness_id="witness-a", expected_config_epoch=7,
        )
        self.assertEqual(verified.counter, 1)

    def test_new_activation_gets_strictly_increasing_counter(self):
        store = self.store()
        one = store.acknowledge("activation-1", "a" * 64)
        two = store.acknowledge("activation-2", "b" * 64)
        self.assertEqual((one["counter"], two["counter"]), (1, 2))

    def test_same_id_with_different_digest_is_rejected(self):
        store = self.store()
        store.acknowledge("activation-1", "a" * 64)
        with self.assertRaises(ActivationWitnessStoreError):
            store.acknowledge("activation-1", "b" * 64)

    def test_config_epoch_change_cannot_rewrite_existing_ack(self):
        self.store().acknowledge("activation-1", "a" * 64)
        changed = SQLiteActivationWitnessStore(
            self.path, witness_id="witness-a", config_epoch=8,
            signing_key=self.key,
        )
        with self.assertRaises(ActivationWitnessStoreError):
            changed.acknowledge("activation-1", "a" * 64)


if __name__ == "__main__":
    unittest.main()
