"""SQLite-backed MODEL-ONLY Option A signer-transfer prototype.

This is a local single-process persistence model using synthetic signature
markers. It is not a cryptographic signer, HSM, distributed authority,
multi-host fencing mechanism, or CometBFT integration.
"""
from contextlib import contextmanager
import sqlite3
import unittest


class Fenced(Exception):
    pass


class TransferBlocked(Exception):
    pass


class UnknownBlocked(Exception):
    pass


class SQLiteOptionAModel:
    def __init__(self, path, initial_owner="A"):
        self.path = str(path)
        self.db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self._initialize(initial_owner)

    def close(self):
        self.db.close()

    @contextmanager
    def _write_tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def _initialize(self, initial_owner):
        with self._write_tx():
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS ownership (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    owner TEXT NOT NULL,
                    epoch INTEGER NOT NULL CHECK(epoch > 0)
                )
            """)
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS control (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    transfer_target TEXT
                )
            """)
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS operations (
                    request_id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    epoch INTEGER NOT NULL,
                    digest TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                        ('ADMITTED','KEY_OPERATION_PENDING','UNKNOWN_BLOCKED',
                         'COMMITTED','SAFELY_ABORTED')),
                    signature BLOB
                )
            """)
            self.db.execute(
                "INSERT OR IGNORE INTO ownership(singleton, owner, epoch) VALUES(1, ?, 1)",
                (initial_owner,),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO control(singleton, transfer_target) VALUES(1, NULL)"
            )

    def ownership(self):
        row = self.db.execute(
            "SELECT owner, epoch FROM ownership WHERE singleton=1"
        ).fetchone()
        return row[0], row[1]

    def admit(self, *, owner, epoch, request_id, digest):
        with self._write_tx():
            existing = self.db.execute(
                "SELECT owner, epoch, digest, status FROM operations WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if existing:
                if existing[:3] != (owner, epoch, digest):
                    raise Fenced("request ID reused with different identity or payload")
                return existing[3]

            current = self.db.execute(
                "SELECT owner, epoch FROM ownership WHERE singleton=1"
            ).fetchone()
            target = self.db.execute(
                "SELECT transfer_target FROM control WHERE singleton=1"
            ).fetchone()[0]
            if target is not None:
                raise Fenced("transfer is draining; new admissions are closed")
            if current != (owner, epoch):
                raise Fenced("stale owner or epoch")
            self.db.execute(
                """INSERT INTO operations
                   (request_id, owner, epoch, digest, status)
                   VALUES(?, ?, ?, ?, 'ADMITTED')""",
                (request_id, owner, epoch, digest),
            )
            return "ADMITTED"

    def begin_key_operation(self, request_id):
        with self._write_tx():
            row = self.db.execute(
                "SELECT status FROM operations WHERE request_id=?", (request_id,)
            ).fetchone()
            if row is None:
                raise KeyError(request_id)
            if row[0] == "COMMITTED":
                return "COMMITTED"
            if row[0] not in ("ADMITTED", "KEY_OPERATION_PENDING"):
                raise UnknownBlocked(row[0])
            self.db.execute(
                "UPDATE operations SET status='KEY_OPERATION_PENDING' WHERE request_id=?",
                (request_id,),
            )
            return "KEY_OPERATION_PENDING"

    def commit_synthetic_signature(self, request_id):
        # Synthetic deterministic marker only; no cryptographic key is used.
        with self._write_tx():
            row = self.db.execute(
                "SELECT owner, epoch, digest, status, signature FROM operations WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise KeyError(request_id)
            owner, epoch, digest, status, signature = row
            if status == "COMMITTED":
                return bytes(signature)
            if status != "KEY_OPERATION_PENDING":
                raise UnknownBlocked(status)
            result = f"SQLITE-MODEL-ONLY:{owner}:{epoch}:{request_id}:{digest}".encode()
            self.db.execute(
                """UPDATE operations SET status='COMMITTED', signature=?
                   WHERE request_id=?""",
                (sqlite3.Binary(result), request_id),
            )
        # The method returns only after SQLite COMMIT has completed.
        return result

    def mark_unknown(self, request_id):
        with self._write_tx():
            cur = self.db.execute(
                """UPDATE operations SET status='UNKNOWN_BLOCKED'
                   WHERE request_id=? AND status='KEY_OPERATION_PENDING'""",
                (request_id,),
            )
            if cur.rowcount != 1:
                raise UnknownBlocked("operation is not pending")

    def reconcile_committed(self, request_id, exact_signature):
        if not exact_signature:
            raise UnknownBlocked("no exact result evidence")
        with self._write_tx():
            row = self.db.execute(
                "SELECT status, signature FROM operations WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise KeyError(request_id)
            if row[0] == "COMMITTED":
                if bytes(row[1]) != bytes(exact_signature):
                    raise Fenced("reconciliation conflicts with committed result")
                return bytes(row[1])
            if row[0] != "UNKNOWN_BLOCKED":
                raise UnknownBlocked("operation is not awaiting reconciliation")
            self.db.execute(
                """UPDATE operations SET status='COMMITTED', signature=?
                   WHERE request_id=?""",
                (sqlite3.Binary(bytes(exact_signature)), request_id),
            )
        return bytes(exact_signature)

    def begin_transfer(self, new_owner):
        with self._write_tx():
            current = self.db.execute(
                "SELECT owner FROM ownership WHERE singleton=1"
            ).fetchone()[0]
            target = self.db.execute(
                "SELECT transfer_target FROM control WHERE singleton=1"
            ).fetchone()[0]
            if target is not None:
                raise TransferBlocked("another transfer is already pending")
            if new_owner == current:
                raise ValueError("new owner must differ")
            self.db.execute(
                "UPDATE control SET transfer_target=? WHERE singleton=1",
                (new_owner,),
            )

    def commit_transfer(self):
        with self._write_tx():
            target = self.db.execute(
                "SELECT transfer_target FROM control WHERE singleton=1"
            ).fetchone()[0]
            if target is None:
                raise ValueError("no transfer requested")
            owner, epoch = self.db.execute(
                "SELECT owner, epoch FROM ownership WHERE singleton=1"
            ).fetchone()
            unresolved = self.db.execute(
                """SELECT request_id FROM operations
                   WHERE epoch=? AND status NOT IN ('COMMITTED','SAFELY_ABORTED')
                   LIMIT 1""",
                (epoch,),
            ).fetchone()
            if unresolved:
                raise TransferBlocked("unresolved old-epoch operation: " + unresolved[0])
            self.db.execute(
                "UPDATE ownership SET owner=?, epoch=? WHERE singleton=1",
                (target, epoch + 1),
            )
            self.db.execute(
                "UPDATE control SET transfer_target=NULL WHERE singleton=1"
            )
            return target, epoch + 1

    def operation(self, request_id):
        row = self.db.execute(
            """SELECT request_id, owner, epoch, digest, status, signature
               FROM operations WHERE request_id=?""",
            (request_id,),
        ).fetchone()
        if row is None:
            return None
        return row[:5] + (bytes(row[5]) if row[5] is not None else None,)


class SQLiteOptionATests(unittest.TestCase):
    def setUp(self):
        self.tmp = __import__("tempfile").TemporaryDirectory()
        self.path = self.tmp.name + "/signer-model.sqlite3"
        self.model = SQLiteOptionAModel(self.path)

    def tearDown(self):
        self.model.close()
        self.tmp.cleanup()

    def reopen(self):
        self.model.close()
        self.model = SQLiteOptionAModel(self.path)

    def test_transfer_drains_admitted_operation_and_persists_epoch(self):
        self.model.admit(owner="A", epoch=1, request_id="r1", digest="d1")
        self.model.begin_key_operation("r1")
        self.model.begin_transfer("B")
        with self.assertRaises(TransferBlocked):
            self.model.commit_transfer()
        result = self.model.commit_synthetic_signature("r1")
        self.reopen()
        self.assertEqual(self.model.operation("r1")[4:], ("COMMITTED", result))
        self.assertEqual(self.model.commit_transfer(), ("B", 2))
        self.reopen()
        self.assertEqual(self.model.ownership(), ("B", 2))
        with self.assertRaises(Fenced):
            self.model.admit(owner="A", epoch=1, request_id="late", digest="d2")

    def test_unknown_survives_restart_and_blocks_transfer_until_reconciled(self):
        self.model.admit(owner="A", epoch=1, request_id="uncertain", digest="d")
        self.model.begin_key_operation("uncertain")
        self.model.mark_unknown("uncertain")
        self.model.begin_transfer("B")
        self.reopen()
        self.assertEqual(self.model.operation("uncertain")[4], "UNKNOWN_BLOCKED")
        with self.assertRaises(TransferBlocked):
            self.model.commit_transfer()
        exact = b"TEST-FIXTURE:independently-recovered-result"
        self.model.reconcile_committed("uncertain", exact)
        self.assertEqual(self.model.commit_transfer(), ("B", 2))

    def test_same_request_retry_survives_drain_but_new_admission_is_rejected(self):
        self.model.admit(owner="A", epoch=1, request_id="same", digest="d")
        self.model.begin_transfer("B")
        self.reopen()
        self.assertEqual(
            self.model.admit(owner="A", epoch=1, request_id="same", digest="d"),
            "ADMITTED",
        )
        with self.assertRaises(Fenced):
            self.model.admit(owner="A", epoch=1, request_id="new", digest="d2")

    def test_committed_retry_returns_exact_persisted_result_after_restart(self):
        self.model.admit(owner="A", epoch=1, request_id="r", digest="d")
        self.model.begin_key_operation("r")
        first = self.model.commit_synthetic_signature("r")
        self.reopen()
        self.assertEqual(self.model.commit_synthetic_signature("r"), first)

    def test_request_id_payload_reuse_is_rejected(self):
        self.model.admit(owner="A", epoch=1, request_id="r", digest="d")
        with self.assertRaises(Fenced):
            self.model.admit(owner="A", epoch=1, request_id="r", digest="changed")


    def test_independent_connections_admission_wins_then_transfer_drains(self):
        # Two SQLite connections share one file; no in-memory state is shared.
        second = SQLiteOptionAModel(self.path)
        try:
            self.model.admit(owner="A", epoch=1, request_id="cross-1", digest="d1")
            second.begin_transfer("B")
            with self.assertRaises(TransferBlocked):
                second.commit_transfer()
            self.model.begin_key_operation("cross-1")
            self.model.commit_synthetic_signature("cross-1")
            self.assertEqual(second.commit_transfer(), ("B", 2))
            self.assertEqual(self.model.ownership(), ("B", 2))
        finally:
            second.close()

    def test_independent_connections_transfer_wins_before_new_admission(self):
        second = SQLiteOptionAModel(self.path)
        try:
            self.model.begin_transfer("B")
            with self.assertRaises(Fenced):
                second.admit(owner="A", epoch=1, request_id="cross-late", digest="d")
            self.assertEqual(second.commit_transfer(), ("B", 2))
            with self.assertRaises(Fenced):
                self.model.admit(owner="A", epoch=1, request_id="cross-stale", digest="d")
        finally:
            second.close()

    def test_sqlite_immediate_write_lock_serializes_independent_connections(self):
        # Exercise the database lock itself, not a Python mutex. The second
        # connection must fail to acquire a writer lock while the first holds it.
        second = sqlite3.connect(self.path, timeout=0.05, isolation_level=None)
        try:
            self.model.db.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError):
                second.execute("BEGIN IMMEDIATE")
            self.model.db.execute("ROLLBACK")
            second.execute("BEGIN IMMEDIATE")
            second.execute("ROLLBACK")
        finally:
            second.close()


if __name__ == "__main__":
    unittest.main()
