"""SQLite-backed MODEL-ONLY Option A signer-transfer prototype.

This is a local single-process persistence model using synthetic signature
markers. It is not a cryptographic signer, HSM, distributed authority,
multi-host fencing mechanism, or CometBFT integration.
"""
from contextlib import contextmanager
import sqlite3
import subprocess
import sys
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

    def reconcile_committed(self, request_id, evidence, verifier):
        """Reconcile only when an injected verifier accepts bound evidence.

        The verifier is a trust-boundary dependency, not implemented here.
        Tests use a fixture verifier; production must use independently
        authenticated evidence from a protected key service or equivalent.
        """
        if not evidence or not callable(verifier):
            raise UnknownBlocked("verified evidence and verifier are required")
        observed = self.db.execute(
            """SELECT owner, epoch, digest, status, signature
               FROM operations WHERE request_id=?""",
            (request_id,),
        ).fetchone()
        if observed is None:
            raise KeyError(request_id)
        owner, epoch, digest, status, stored = observed
        if status not in ("UNKNOWN_BLOCKED", "COMMITTED"):
            raise UnknownBlocked("operation is not awaiting reconciliation")
        accepted = verifier(
            request_id, owner, epoch, digest, bytes(evidence)
        )
        if accepted is not True:
            raise UnknownBlocked("evidence verifier rejected result")
        with self._write_tx():
            current = self.db.execute(
                """SELECT owner, epoch, digest, status, signature
                   FROM operations WHERE request_id=?""",
                (request_id,),
            ).fetchone()
            if current is None:
                raise KeyError(request_id)
            if current[:3] != observed[:3]:
                raise Fenced("operation identity changed during verification")
            if current[3] == "COMMITTED":
                if bytes(current[4]) != bytes(evidence):
                    raise Fenced("reconciliation conflicts with committed result")
                return bytes(current[4])
            if current[3] != "UNKNOWN_BLOCKED":
                raise UnknownBlocked("operation state changed during verification")
            self.db.execute(
                """UPDATE operations SET status='COMMITTED', signature=?
                   WHERE request_id=?""",
                (sqlite3.Binary(bytes(evidence)), request_id),
            )
        return bytes(evidence)

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


class IndependentKeyJournalModel:
    """Separate SQLite journal standing in for an external key service.

    Results are synthetic markers. This class models durable idempotency and
    recovery only; it is not a cryptographic signer or trusted key custody.
    """
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), timeout=5, isolation_level=None)
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS key_operations (
                request_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                digest TEXT NOT NULL,
                result BLOB NOT NULL
            )
        """)

    def close(self):
        self.db.close()

    def execute_once(self, request_id, owner, epoch, digest):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                """SELECT owner, epoch, digest, result
                   FROM key_operations WHERE request_id=?""",
                (request_id,),
            ).fetchone()
            if row is not None:
                if row[:3] != (owner, epoch, digest):
                    raise Fenced("key journal request identity conflict")
                self.db.execute("COMMIT")
                return bytes(row[3])
            result = (
                f"KEY-JOURNAL-MODEL-ONLY:{owner}:{epoch}:{request_id}:{digest}"
                .encode()
            )
            self.db.execute(
                """INSERT INTO key_operations
                   (request_id, owner, epoch, digest, result)
                   VALUES(?, ?, ?, ?, ?)""",
                (request_id, owner, epoch, digest, sqlite3.Binary(result)),
            )
            self.db.execute("COMMIT")
            return result
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def get(self, request_id):
        return self.db.execute(
            """SELECT owner, epoch, digest, result
               FROM key_operations WHERE request_id=?""",
            (request_id,),
        ).fetchone()

    def count(self, request_id):
        return self.db.execute(
            "SELECT COUNT(*) FROM key_operations WHERE request_id=?",
            (request_id,),
        ).fetchone()[0]


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
        self.model.reconcile_committed("uncertain", exact, lambda rid, owner, epoch, digest, result: (rid, owner, epoch, digest, result) == ("uncertain", "A", 1, "d", exact))
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


    def test_child_process_exit_after_pending_intent_keeps_transfer_blocked(self):
        # A real child process exits without cleanup after the durable pending
        # marker is written. This does not simulate a real key operation.
        child_code = r"""
import os
import runpy
import sys
ns = runpy.run_path(sys.argv[1])
Model = ns["SQLiteOptionAModel"]
model = Model(sys.argv[2])
model.admit(owner="A", epoch=1, request_id="crash-pending", digest="d")
model.begin_key_operation("crash-pending")
os._exit(23)
"""
        script = __import__("pathlib").Path(__file__).resolve()
        result = subprocess.run(
            [sys.executable, "-c", child_code, str(script), self.path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 23, result.stderr)
        self.model.close()
        self.model = SQLiteOptionAModel(self.path)
        self.assertEqual(
            self.model.operation("crash-pending")[4], "KEY_OPERATION_PENDING"
        )
        self.model.begin_transfer("B")
        with self.assertRaises(TransferBlocked):
            self.model.commit_transfer()


    def test_external_journal_recovers_after_crash_before_main_commit(self):
        journal_path = self.path + ".external-key-journal.sqlite3"
        child_code = r"""
import os
import runpy
import sys
ns = runpy.run_path(sys.argv[1])
Model = ns["SQLiteOptionAModel"]
Journal = ns["IndependentKeyJournalModel"]
model = Model(sys.argv[2])
journal = Journal(sys.argv[3])
model.admit(owner="A", epoch=1, request_id="external-crash", digest="payload")
model.begin_key_operation("external-crash")
journal.execute_once("external-crash", "A", 1, "payload")
os._exit(24)
"""
        script = __import__("pathlib").Path(__file__).resolve()
        child = subprocess.run(
            [sys.executable, "-c", child_code, str(script), self.path, journal_path],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(child.returncode, 24, child.stderr)
        self.model.close()
        self.model = SQLiteOptionAModel(self.path)
        journal = IndependentKeyJournalModel(journal_path)
        try:
            self.assertEqual(
                self.model.operation("external-crash")[4],
                "KEY_OPERATION_PENDING",
            )
            recorded = journal.get("external-crash")
            self.assertEqual(recorded[:3], ("A", 1, "payload"))
            evidence = bytes(recorded[3])

            def verify(rid, owner, epoch, digest, result):
                entry = journal.get(rid)
                return (
                    entry is not None
                    and entry[:3] == (owner, epoch, digest)
                    and bytes(entry[3]) == result
                )

            recovered = journal.execute_once(
                "external-crash", "A", 1, "payload"
            )
            self.assertEqual(recovered, evidence)
            self.assertEqual(journal.count("external-crash"), 1)
            self.model.mark_unknown("external-crash")
            self.model.begin_transfer("B")
            self.model.reconcile_committed("external-crash", evidence, verify)
            self.assertEqual(self.model.commit_transfer(), ("B", 2))
        finally:
            journal.close()

    def test_unknown_blocked_cannot_be_restarted_as_a_fresh_key_operation(self):
        self.model.admit(owner="A", epoch=1, request_id="unknown-retry", digest="d")
        self.model.begin_key_operation("unknown-retry")
        self.model.mark_unknown("unknown-retry")
        with self.assertRaises(UnknownBlocked):
            self.model.begin_key_operation("unknown-retry")
        with self.assertRaises(UnknownBlocked):
            self.model.commit_synthetic_signature("unknown-retry")
        self.assertEqual(
            self.model.operation("unknown-retry")[4], "UNKNOWN_BLOCKED"
        )


    def test_reconciliation_requires_verifier_acceptance(self):
        self.model.admit(owner="A", epoch=1, request_id="verify-reject", digest="d")
        self.model.begin_key_operation("verify-reject")
        self.model.mark_unknown("verify-reject")
        evidence = b"FIXTURE-RESULT"
        with self.assertRaises(UnknownBlocked):
            self.model.reconcile_committed(
                "verify-reject", evidence,
                lambda rid, owner, epoch, digest, result: False
            )
        self.assertEqual(self.model.operation("verify-reject")[4], "UNKNOWN_BLOCKED")

    def test_reconciliation_verifier_receives_bound_operation_identity(self):
        self.model.admit(owner="A", epoch=1, request_id="verify-bound", digest="d")
        self.model.begin_key_operation("verify-bound")
        self.model.mark_unknown("verify-bound")
        seen = []
        evidence = b"FIXTURE-RESULT"
        def verifier(rid, owner, epoch, digest, result):
            seen.append((rid, owner, epoch, digest, result))
            return (rid, owner, epoch, digest, result) == (
                "verify-bound", "A", 1, "d", evidence
            )
        self.assertEqual(
            self.model.reconcile_committed("verify-bound", evidence, verifier),
            evidence
        )
        self.assertEqual(seen, [("verify-bound", "A", 1, "d", evidence)])

    def test_reconciliation_rejects_conflicting_result_after_commit(self):
        self.model.admit(owner="A", epoch=1, request_id="reconcile-conflict", digest="d")
        self.model.begin_key_operation("reconcile-conflict")
        exact = self.model.commit_synthetic_signature("reconcile-conflict")
        self.assertEqual(
            self.model.reconcile_committed("reconcile-conflict", exact, lambda rid, owner, epoch, digest, result: True), exact
        )
        with self.assertRaises(Fenced):
            self.model.reconcile_committed(
                "reconcile-conflict", b"DIFFERENT-FIXTURE-RESULT",
                lambda rid, owner, epoch, digest, result: True
            )


if __name__ == "__main__":
    unittest.main()
