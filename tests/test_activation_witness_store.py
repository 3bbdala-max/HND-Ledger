import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

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

    def test_second_activation_is_rejected_while_first_is_unresolved(self):
        store = self.store()
        first = store.acknowledge("activation-1", "a" * 64)
        with self.assertRaisesRegex(
            ActivationWitnessStoreError, "HND-WITNESS-STORE-E-PENDING-CONFLICT"
        ):
            store.acknowledge("activation-2", "b" * 64)
        with sqlite3.connect(self.path) as db:
            counter = db.execute(
                "SELECT counter FROM witness_counter WHERE singleton = 1"
            ).fetchone()[0]
            pending = db.execute(
                "SELECT activation_id, activation_digest FROM witness_pending WHERE singleton = 1"
            ).fetchone()
        self.assertEqual(counter, 1)
        self.assertEqual(pending, ("activation-1", "a" * 64))
        self.assertEqual(first["counter"], 1)

    def test_concurrent_distinct_activations_have_one_pending_winner(self):
        store = self.store()
        barrier = threading.Barrier(3)
        outcomes = []
        outcome_lock = threading.Lock()

        def acknowledge(activation_id, digest):
            barrier.wait()
            try:
                result = store.acknowledge(activation_id, digest)
                outcome = ("ok", result["activation_id"])
            except ActivationWitnessStoreError as exc:
                outcome = ("error", str(exc))
            with outcome_lock:
                outcomes.append(outcome)

        threads = [
            threading.Thread(target=acknowledge, args=("activation-1", "a" * 64)),
            threading.Thread(target=acknowledge, args=("activation-2", "b" * 64)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=15)
            self.assertFalse(thread.is_alive())

        successes = [item for item in outcomes if item[0] == "ok"]
        conflicts = [
            item for item in outcomes
            if item == ("error", "HND-WITNESS-STORE-E-PENDING-CONFLICT")
        ]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(conflicts), 1)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT counter FROM witness_counter WHERE singleton = 1"
                ).fetchone()[0],
                1,
            )

    def test_pending_lock_survives_restart_and_same_activation_retry(self):
        first = self.store().acknowledge("activation-1", "a" * 64)
        restarted = self.store()
        self.assertEqual(
            restarted.acknowledge("activation-1", "a" * 64), first
        )
        with self.assertRaisesRegex(
            ActivationWitnessStoreError, "HND-WITNESS-STORE-E-PENDING-CONFLICT"
        ):
            restarted.acknowledge("activation-2", "b" * 64)

    def test_same_id_with_different_digest_is_rejected(self):
        store = self.store()
        store.acknowledge("activation-1", "a" * 64)
        with self.assertRaisesRegex(
            ActivationWitnessStoreError, "HND-WITNESS-STORE-E-ID-CONFLICT"
        ):
            store.acknowledge("activation-1", "b" * 64)

    def test_legacy_receipts_without_pending_state_fail_closed(self):
        with sqlite3.connect(self.path) as db:
            db.execute("""
                CREATE TABLE witness_counter (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    counter INTEGER NOT NULL CHECK(counter >= 0)
                )
            """)
            db.execute("INSERT INTO witness_counter VALUES (1, 1)")
            db.execute("""
                CREATE TABLE witness_receipts (
                    activation_id TEXT PRIMARY KEY,
                    activation_digest TEXT NOT NULL,
                    config_epoch INTEGER NOT NULL,
                    counter INTEGER NOT NULL UNIQUE,
                    receipt_json BLOB NOT NULL
                )
            """)
            db.execute(
                "INSERT INTO witness_receipts VALUES (?, ?, ?, ?, ?)",
                ("old-activation", "a" * 64, 7, 1, b"{}"),
            )
        with self.assertRaisesRegex(
            ActivationWitnessStoreError,
            "HND-WITNESS-STORE-E-LEGACY-STATE-UNRESOLVED",
        ):
            self.store()

    def test_pending_replay_verifies_signature_and_all_bound_receipt_fields(self):
        corruptions = {
            "schema": "hnd.station2.witness-ack.v999",
            "activation_id": "activation-other",
            "activation_digest": "b" * 64,
            "witness_id": "witness-other",
            "config_epoch": 8,
            "counter": 2,
            "signature": "A" * 88,
        }
        for field, replacement in corruptions.items():
            with self.subTest(field=field):
                path = self.temp.name + "/" + field + ".sqlite"
                store = SQLiteActivationWitnessStore(
                    path, witness_id="witness-a", config_epoch=7,
                    signing_key=self.key,
                )
                store.acknowledge("activation-1", "a" * 64)
                with sqlite3.connect(path) as db:
                    raw = db.execute(
                        "SELECT receipt_json FROM witness_pending WHERE singleton = 1"
                    ).fetchone()[0]
                    receipt = __import__("json").loads(bytes(raw).decode("ascii"))
                    receipt[field] = replacement
                    encoded = __import__("json").dumps(
                        receipt, ensure_ascii=True, allow_nan=False,
                        sort_keys=True, separators=(",", ":"),
                    ).encode("ascii")
                    # Mutate both copies identically: the signature and trusted
                    # expected tuple must still reject a self-consistent forgery.
                    db.execute(
                        "UPDATE witness_pending SET receipt_json = ? WHERE singleton = 1",
                        (encoded,),
                    )
                    db.execute(
                        "UPDATE witness_receipts SET receipt_json = ? WHERE activation_id = ?",
                        (encoded, "activation-1"),
                    )
                    before = (
                        db.execute(
                            "SELECT counter FROM witness_counter WHERE singleton = 1"
                        ).fetchone(),
                        db.execute(
                            "SELECT activation_id, activation_digest, receipt_json "
                            "FROM witness_pending WHERE singleton = 1"
                        ).fetchone(),
                        db.execute(
                            "SELECT activation_digest, config_epoch, counter, receipt_json "
                            "FROM witness_receipts WHERE activation_id = ?",
                            ("activation-1",),
                        ).fetchone(),
                    )
                with self.assertRaisesRegex(
                    ActivationWitnessStoreError,
                    "HND-WITNESS-STORE-E-PENDING-CORRUPT",
                ):
                    store.acknowledge("activation-1", "a" * 64)
                with sqlite3.connect(path) as db:
                    after = (
                        db.execute(
                            "SELECT counter FROM witness_counter WHERE singleton = 1"
                        ).fetchone(),
                        db.execute(
                            "SELECT activation_id, activation_digest, receipt_json "
                            "FROM witness_pending WHERE singleton = 1"
                        ).fetchone(),
                        db.execute(
                            "SELECT activation_digest, config_epoch, counter, receipt_json "
                            "FROM witness_receipts WHERE activation_id = ?",
                            ("activation-1",),
                        ).fetchone(),
                    )
                self.assertEqual(after, before)

    def test_pending_replay_requires_matching_immutable_receipt_row(self):
        corruptions = {
            "activation_digest": ("activation_digest", "b" * 64),
            "config_epoch": ("config_epoch", 8),
            "counter": ("counter", 2),
            "receipt_json": ("receipt_json", b"{}"),
        }
        for label, (column, replacement) in corruptions.items():
            with self.subTest(field=label):
                path = self.temp.name + "/row-" + label + ".sqlite"
                store = SQLiteActivationWitnessStore(
                    path, witness_id="witness-a", config_epoch=7,
                    signing_key=self.key,
                )
                store.acknowledge("activation-1", "a" * 64)
                with sqlite3.connect(path) as db:
                    db.execute(
                        f"UPDATE witness_receipts SET {column} = ? WHERE activation_id = ?",
                        (replacement, "activation-1"),
                    )
                    before = (
                        db.execute(
                            "SELECT counter FROM witness_counter WHERE singleton = 1"
                        ).fetchone(),
                        db.execute(
                            "SELECT activation_id, activation_digest, receipt_json "
                            "FROM witness_pending WHERE singleton = 1"
                        ).fetchone(),
                        db.execute(
                            "SELECT activation_digest, config_epoch, counter, receipt_json "
                            "FROM witness_receipts WHERE activation_id = ?",
                            ("activation-1",),
                        ).fetchone(),
                    )
                with self.assertRaisesRegex(
                    ActivationWitnessStoreError,
                    "HND-WITNESS-STORE-E-PENDING-CORRUPT",
                ):
                    store.acknowledge("activation-1", "a" * 64)
                with sqlite3.connect(path) as db:
                    after = (
                        db.execute(
                            "SELECT counter FROM witness_counter WHERE singleton = 1"
                        ).fetchone(),
                        db.execute(
                            "SELECT activation_id, activation_digest, receipt_json "
                            "FROM witness_pending WHERE singleton = 1"
                        ).fetchone(),
                        db.execute(
                            "SELECT activation_digest, config_epoch, counter, receipt_json "
                            "FROM witness_receipts WHERE activation_id = ?",
                            ("activation-1",),
                        ).fetchone(),
                    )
                self.assertEqual(after, before)

    def test_pending_replay_rejects_missing_immutable_receipt_row(self):
        store = self.store()
        store.acknowledge("activation-1", "a" * 64)
        with sqlite3.connect(self.path) as db:
            db.execute(
                "DELETE FROM witness_receipts WHERE activation_id = ?",
                ("activation-1",),
            )
        with self.assertRaisesRegex(
            ActivationWitnessStoreError,
            "HND-WITNESS-STORE-E-PENDING-CORRUPT",
        ):
            store.acknowledge("activation-1", "a" * 64)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT counter FROM witness_counter WHERE singleton = 1"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                db.execute(
                    "SELECT activation_id FROM witness_pending WHERE singleton = 1"
                ).fetchone()[0],
                "activation-1",
            )

    def test_connection_failure_is_reported_as_store_error(self):
        store = self.store()
        with patch(
            "hnd_v02.activation_witness_store.sqlite3.connect",
            side_effect=sqlite3.OperationalError("database unavailable"),
        ):
            with self.assertRaisesRegex(
                ActivationWitnessStoreError, "HND-WITNESS-STORE-E-WRITE"
            ):
                store.acknowledge("activation-1", "a" * 64)

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
