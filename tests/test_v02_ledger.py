"""Tests for HND v0.2 in-memory ledger state transitions and recovery."""
import copy
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.ledger import HNDLedger, LedgerError
from hnd_v02.transaction import (
    ProtocolConfig,
    account_id_for_public_key,
    create_signed_transaction,
    public_key_b64,
)


class TestV02Ledger(unittest.TestCase):
    def setUp(self):
        self.config = ProtocolConfig("hnd-ledger-test", 2, 1_000_000)
        self.alice_key = Ed25519PrivateKey.generate()
        self.bob_key = Ed25519PrivateKey.generate()
        self.unknown_key = Ed25519PrivateKey.generate()
        self.alice_public = public_key_b64(self.alice_key)
        self.bob_public = public_key_b64(self.bob_key)
        self.alice_id = account_id_for_public_key(self.alice_public, config=self.config)
        self.bob_id = account_id_for_public_key(self.bob_public, config=self.config)
        allocations = [
            {"account_id": self.alice_id, "public_key": self.alice_public, "amount": 600_000},
            {"account_id": self.bob_id, "public_key": self.bob_public, "amount": 400_000},
        ]
        allocations.sort(key=lambda item: item["account_id"])
        self.manifest = {
            "manifest_version": 1,
            "network_id": self.config.network_id,
            "protocol_version": self.config.protocol_version,
            "total_supply": 1_000_000,
            "allocations": allocations,
        }
        self.genesis_hash = genesis_manifest_hash(self.manifest)
        self.ledger = HNDLedger(
            config=self.config, manifest=self.manifest,
            expected_genesis_hash=self.genesis_hash,
        )

    def signed(self, amount=25, nonce=0, recipient=None):
        return create_signed_transaction(
            self.alice_key,
            config=self.config,
            sender=self.alice_id,
            recipient=recipient or self.bob_id,
            amount=amount,
            nonce=nonce,
        )

    def test_genesis_initializes_balances_and_supply(self):
        self.assertEqual(self.ledger.balances[self.alice_id], 600_000)
        self.assertEqual(self.ledger.balances[self.bob_id], 400_000)
        self.assertEqual(sum(self.ledger.balances.values()), 1_000_000)
        self.assertEqual(self.ledger.nonces[self.alice_id], 0)

    def test_valid_transfer_updates_balances_nonce_and_history(self):
        tx = self.signed(amount=125)
        txid = self.ledger.apply_transaction(tx)
        self.assertEqual(self.ledger.balances[self.alice_id], 599_875)
        self.assertEqual(self.ledger.balances[self.bob_id], 400_125)
        self.assertEqual(self.ledger.nonces[self.alice_id], 1)
        self.assertEqual(self.ledger.history, [tx])
        self.assertIn(txid, self.ledger.accepted)
        self.assertEqual(sum(self.ledger.balances.values()), 1_000_000)

    def test_multiple_sequential_transfers_use_incrementing_nonce(self):
        for nonce in range(5):
            self.ledger.apply_transaction(self.signed(amount=10, nonce=nonce))
        self.assertEqual(self.ledger.nonces[self.alice_id], 5)
        self.assertEqual(self.ledger.balances[self.alice_id], 599_950)
        self.assertEqual(self.ledger.balances[self.bob_id], 400_050)

    def test_replay_of_same_transaction_is_rejected(self):
        tx = self.signed()
        self.ledger.apply_transaction(tx)
        with self.assertRaisesRegex(LedgerError, "duplicate"):
            self.ledger.apply_transaction(tx)

    def test_old_nonce_is_rejected_without_state_change(self):
        first = self.signed(amount=25, nonce=0)
        self.ledger.apply_transaction(first)
        stale_but_distinct = self.signed(amount=26, nonce=0)
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(LedgerError, "nonce"):
            self.ledger.apply_transaction(stale_but_distinct)
        self.assertEqual(self.ledger.snapshot(), before)

    def test_overspend_is_rejected_without_state_change(self):
        tx = self.signed(amount=600_001)
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(LedgerError, "balance"):
            self.ledger.apply_transaction(tx)
        self.assertEqual(self.ledger.snapshot(), before)

    def test_unknown_recipient_is_rejected(self):
        unknown_id = account_id_for_public_key(
            public_key_b64(self.unknown_key), config=self.config
        )
        tx = self.signed(recipient=unknown_id)
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(LedgerError, "unknown recipient"):
            self.ledger.apply_transaction(tx)
        self.assertEqual(self.ledger.snapshot(), before)

    def test_bad_signature_is_rejected_without_state_change(self):
        tx = self.signed()
        tx["signature"] = "AAAA"
        before = self.ledger.snapshot()
        with self.assertRaises(LedgerError):
            self.ledger.apply_transaction(tx)
        self.assertEqual(self.ledger.snapshot(), before)

    def test_snapshot_round_trip_replays_history(self):
        self.ledger.apply_transaction(self.signed(amount=100, nonce=0))
        self.ledger.apply_transaction(self.signed(amount=75, nonce=1))
        snapshot = self.ledger.snapshot()
        restored = HNDLedger.restore(
            manifest=self.manifest, config=self.config,
            expected_genesis_hash=self.genesis_hash, snapshot=snapshot,
        )
        self.assertEqual(restored.snapshot(), snapshot)

    def test_snapshot_balance_tampering_is_rejected(self):
        self.ledger.apply_transaction(self.signed(amount=100))
        snapshot = copy.deepcopy(self.ledger.snapshot())
        snapshot["balances"][self.alice_id] -= 1
        snapshot["balances"][self.bob_id] += 1
        with self.assertRaisesRegex(LedgerError, "balances mismatch"):
            HNDLedger.restore(
                manifest=self.manifest, config=self.config,
                expected_genesis_hash=self.genesis_hash, snapshot=snapshot,
            )

    def test_snapshot_history_tampering_is_rejected(self):
        self.ledger.apply_transaction(self.signed(amount=100))
        snapshot = copy.deepcopy(self.ledger.snapshot())
        snapshot["history"][0]["amount"] = 99
        with self.assertRaises(LedgerError):
            HNDLedger.restore(
                manifest=self.manifest, config=self.config,
                expected_genesis_hash=self.genesis_hash, snapshot=snapshot,
            )

    def test_snapshot_wrong_genesis_is_rejected(self):
        snapshot = self.ledger.snapshot()
        with self.assertRaisesRegex(LedgerError, "genesis hash"):
            HNDLedger.restore(
                manifest=self.manifest, config=self.config,
                expected_genesis_hash="0" * 64, snapshot=snapshot,
            )

    def test_unknown_account_view_is_rejected(self):
        with self.assertRaisesRegex(LedgerError, "unknown account"):
            self.ledger.account_view("not-an-account")




class TestV02LedgerFilePersistence(unittest.TestCase):
    """Additional tests for atomic file save and replay-verified restoration."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from hnd_v02.genesis import genesis_manifest_hash
        from hnd_v02.ledger import HNDLedger
        from hnd_v02.transaction import ProtocolConfig, account_id_for_public_key, public_key_b64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        self.tempfile = tempfile
        self.Path = Path
        self.HNDLedger = HNDLedger
        self.config = ProtocolConfig("hnd-ledger-persist", 2, 1_000_000)
        self.key_a, self.key_b = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        self.pub_a, self.pub_b = public_key_b64(self.key_a), public_key_b64(self.key_b)
        self.id_a = account_id_for_public_key(self.pub_a, config=self.config)
        self.id_b = account_id_for_public_key(self.pub_b, config=self.config)
        allocations = sorted([
            {"account_id": self.id_a, "public_key": self.pub_a, "amount": 500_000},
            {"account_id": self.id_b, "public_key": self.pub_b, "amount": 500_000},
        ], key=lambda item: item["account_id"])
        self.manifest = {
            "manifest_version": 1,
            "network_id": self.config.network_id,
            "protocol_version": 2,
            "total_supply": 1_000_000,
            "allocations": allocations,
        }
        self.genesis_hash = genesis_manifest_hash(self.manifest)
        self.ledger = HNDLedger(
            config=self.config, manifest=self.manifest,
            expected_genesis_hash=self.genesis_hash,
        )

    def signed(self, sender="a", amount=1):
        from hnd_v02.transaction import create_signed_transaction
        key, source, target = (
            (self.key_a, self.id_a, self.id_b)
            if sender == "a" else (self.key_b, self.id_b, self.id_a)
        )
        return create_signed_transaction(
            key, config=self.config, sender=source, recipient=target,
            amount=amount, nonce=self.ledger.nonces[source],
        )

    def load(self, path, expected_hash=None):
        return self.HNDLedger.load(
            path, manifest=self.manifest, config=self.config,
            expected_genesis_hash=expected_hash or self.genesis_hash,
        )

    def test_atomic_file_save_and_load_replays_signed_history(self):
        for amount in (10, 20, 30):
            self.ledger.apply_transaction(self.signed(amount=amount))
        with self.tempfile.TemporaryDirectory() as directory:
            path = self.Path(directory) / "ledger.json"
            self.ledger.save(path)
            restored = self.load(path)
        self.assertEqual(restored.snapshot(), self.ledger.snapshot())

    def test_file_snapshot_wrong_genesis_hash_rejected(self):
        from hnd_v02.ledger import LedgerError
        with self.tempfile.TemporaryDirectory() as directory:
            path = self.Path(directory) / "ledger.json"
            self.ledger.save(path)
            with self.assertRaisesRegex(LedgerError, "snapshot genesis hash"):
                self.load(path, "0" * 64)

    def test_corrupt_json_file_rejected(self):
        from hnd_v02.ledger import LedgerError
        with self.tempfile.TemporaryDirectory() as directory:
            path = self.Path(directory) / "ledger.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(LedgerError, "cannot be decoded"):
                self.load(path)

    def test_missing_snapshot_parent_directory_rejected(self):
        with self.tempfile.TemporaryDirectory() as directory:
            path = self.Path(directory) / "missing" / "ledger.json"
            with self.assertRaises(FileNotFoundError):
                self.ledger.save(path)

    def test_rehashed_balance_tampering_rejected_by_history_replay(self):
        import hashlib
        import json
        from hnd_v02.ledger import LedgerError, STATE_DOMAIN
        from hnd_v02.transaction import canonical_json
        self.ledger.apply_transaction(self.signed(amount=20))
        snapshot = self.ledger.snapshot()
        snapshot["balances"][self.id_a] -= 1
        snapshot["balances"][self.id_b] += 1
        payload = {key: value for key, value in snapshot.items() if key != "state_hash"}
        snapshot["state_hash"] = hashlib.sha256(
            STATE_DOMAIN + canonical_json(payload)
        ).hexdigest()
        with self.tempfile.TemporaryDirectory() as directory:
            path = self.Path(directory) / "ledger.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaisesRegex(LedgerError, "snapshot balances mismatch"):
                self.load(path)

    def test_boolean_snapshot_version_rejected(self):
        from hnd_v02.ledger import LedgerError
        snapshot = self.ledger.snapshot()
        snapshot["schema_version"] = True
        with self.assertRaisesRegex(LedgerError, "snapshot version"):
            self.HNDLedger.restore(
                manifest=self.manifest, config=self.config,
                expected_genesis_hash=self.genesis_hash, snapshot=snapshot,
            )

    def test_snapshot_history_is_detached_from_live_ledger(self):
        self.ledger.apply_transaction(self.signed(amount=20))
        snapshot = self.ledger.snapshot()
        snapshot["history"][0]["amount"] = 999
        self.assertEqual(self.ledger.history[0]["amount"], 20)

    def test_supply_and_balances_stable_over_2000_signed_transfers(self):
        for _ in range(1000):
            self.ledger.apply_transaction(self.signed(sender="a"))
            self.ledger.apply_transaction(self.signed(sender="b"))
        self.assertEqual(sum(self.ledger.balances.values()), 1_000_000)
        self.assertEqual(self.ledger.balances[self.id_a], 500_000)
        self.assertEqual(self.ledger.balances[self.id_b], 500_000)
        self.assertEqual(len(self.ledger.history), 2000)
        self.assertEqual(self.ledger.nonces[self.id_a], 1000)
        self.assertEqual(self.ledger.nonces[self.id_b], 1000)


if __name__ == "__main__":
    unittest.main(verbosity=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# Keep the offline anti-rollback protocol model in the existing CI test invocation.
from tests.test_v02_anti_rollback_reference import TestOfflineAntiRollbackReference  # noqa: F401
