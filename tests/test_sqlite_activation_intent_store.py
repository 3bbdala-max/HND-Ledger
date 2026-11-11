import tempfile
import unittest
from pathlib import Path

from hnd_v02.remote_activation_intent import RemoteActivationProtocolError
from hnd_v02.sqlite_activation_intent_store import SQLiteActivationIntentStore


class SQLiteActivationIntentStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "intents.sqlite"
        self.store = SQLiteActivationIntentStore(self.path)
        self.request = {
            "activation_id": "activation-001",
            "predecessors": {"trust_manifest": None, "vsp_profile": None},
            "successors": {
                "trust_manifest": {"sequence": 0, "digest": "1" * 64},
                "vsp_profile": {"sequence": 1, "digest": "2" * 64},
            },
            "profile_digest": "3" * 64,
            "operator_ack_digest": "4" * 64,
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_prepare_is_idempotent_and_survives_reopen(self):
        first = self.store.prepare(self.request)
        second = self.store.prepare(dict(self.request))
        self.assertEqual(first, second)
        reopened = SQLiteActivationIntentStore(self.path)
        self.assertEqual(reopened.read_intent("activation-001"), first)

    def test_same_id_with_different_request_is_rejected(self):
        self.store.prepare(self.request)
        changed = dict(self.request, profile_digest="5" * 64)
        with self.assertRaises(RemoteActivationProtocolError):
            self.store.prepare(changed)

    def test_finalize_is_idempotent_and_survives_reopen(self):
        self.store.prepare(self.request)
        first = self.store.finalize("activation-001", "3" * 64, "4" * 64)
        second = self.store.finalize("activation-001", "3" * 64, "4" * 64)
        self.assertEqual(first["state"], "finalized")
        self.assertEqual(second, first)
        reopened = SQLiteActivationIntentStore(self.path)
        self.assertEqual(reopened.read_intent("activation-001"), first)

    def test_finalize_rejects_wrong_digest_without_mutating_intent(self):
        self.store.prepare(self.request)
        with self.assertRaises(RemoteActivationProtocolError):
            self.store.finalize("activation-001", "9" * 64, "4" * 64)
        self.assertEqual(self.store.read_intent("activation-001")["state"], "prepared")

    def test_finalize_unknown_id_is_rejected(self):
        with self.assertRaises(RemoteActivationProtocolError):
            self.store.finalize("missing", "3" * 64, "4" * 64)

    def test_invalid_sequence_is_rejected_before_storage(self):
        bad = dict(self.request)
        bad["successors"] = {
            "trust_manifest": {"sequence": 1, "digest": "1" * 64},
            "vsp_profile": {"sequence": 1, "digest": "2" * 64},
        }
        with self.assertRaises(RemoteActivationProtocolError):
            self.store.prepare(bad)
        self.assertIsNone(self.store.read_intent("activation-001"))

    def test_memory_database_is_rejected_as_non_durable(self):
        with self.assertRaises(RemoteActivationProtocolError):
            SQLiteActivationIntentStore(":memory:")


if __name__ == "__main__":
    unittest.main()
