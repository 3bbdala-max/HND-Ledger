"""MODEL-ONLY Option A signer-transfer state machine.

This is a deterministic reference model, not a production signer, durable
database, cryptographic key boundary, distributed authority, or CometBFT
adapter. It uses synthetic signatures and in-memory state only.
"""
from dataclasses import dataclass
import unittest


class Fenced(Exception):
    pass


class TransferBlocked(Exception):
    pass


class UnknownBlocked(Exception):
    pass


@dataclass(frozen=True)
class Ownership:
    owner: str
    epoch: int


@dataclass
class Operation:
    request_id: str
    owner: str
    epoch: int
    digest: str
    status: str = "ADMITTED"
    signature: bytes | None = None


class OptionAModel:
    """Single-process model of drain-before-transfer ordering."""

    def __init__(self, owner="A"):
        self.ownership = Ownership(owner, 1)
        self.operations = {}
        self.transfer_target = None
        self.released = []

    def admit(self, *, owner, epoch, request_id, digest):
        # Exact retries of already-admitted work remain addressable while a
        # transfer drains; they do not create a new admission.
        existing = self.operations.get(request_id)
        if existing is not None:
            if (existing.owner, existing.epoch, existing.digest) != (owner, epoch, digest):
                raise Fenced("request ID reused with different payload")
            return existing
        if self.transfer_target is not None:
            raise Fenced("transfer is draining; new admissions are closed")
        if (owner, epoch) != (self.ownership.owner, self.ownership.epoch):
            raise Fenced("stale owner or epoch")
        op = Operation(request_id, owner, epoch, digest)
        self.operations[request_id] = op
        return op

    def begin_key_operation(self, request_id):
        op = self.operations[request_id]
        if op.status == "COMMITTED":
            return op.signature
        if op.status not in ("ADMITTED", "KEY_OPERATION_PENDING"):
            raise UnknownBlocked(op.status)
        op.status = "KEY_OPERATION_PENDING"
        return None

    def commit_signature(self, request_id):
        op = self.operations[request_id]
        if op.status == "COMMITTED":
            return op.signature
        if op.status != "KEY_OPERATION_PENDING":
            raise UnknownBlocked(op.status)
        # Synthetic marker only. No cryptographic operation occurs here.
        signature = f"MODEL-ONLY:{op.owner}:{op.epoch}:{op.request_id}:{op.digest}".encode()
        op.signature = signature
        op.status = "COMMITTED"
        self.released.append((request_id, op.owner, op.epoch, signature))
        return signature

    def mark_unknown(self, request_id):
        op = self.operations[request_id]
        if op.status == "KEY_OPERATION_PENDING":
            op.status = "UNKNOWN_BLOCKED"

    def reconcile_committed(self, request_id, exact_signature):
        op = self.operations[request_id]
        if op.status != "UNKNOWN_BLOCKED":
            raise ValueError("only UNKNOWN_BLOCKED operations require reconciliation")
        # In this model the test harness supplies independently verified evidence.
        if not exact_signature:
            raise UnknownBlocked("no proof of exact committed signature")
        op.signature = exact_signature
        op.status = "COMMITTED"
        if not any(item[0] == request_id for item in self.released):
            self.released.append((request_id, op.owner, op.epoch, exact_signature))
        return exact_signature

    def begin_transfer(self, new_owner):
        if self.transfer_target is not None:
            raise TransferBlocked("another transfer is already draining")
        if new_owner == self.ownership.owner:
            raise ValueError("new owner must differ in this model")
        self.transfer_target = new_owner

    def commit_transfer(self):
        if self.transfer_target is None:
            raise ValueError("no transfer requested")
        unresolved = [
            op.request_id for op in self.operations.values()
            if op.epoch == self.ownership.epoch
            and op.status not in ("COMMITTED", "SAFELY_ABORTED")
        ]
        if unresolved:
            raise TransferBlocked("unresolved old-epoch operations: " + ",".join(unresolved))
        self.ownership = Ownership(self.transfer_target, self.ownership.epoch + 1)
        self.transfer_target = None
        return self.ownership


class OptionATransferModelTests(unittest.TestCase):
    def setUp(self):
        self.model = OptionAModel()

    def test_sign_wins_transfer_waits_for_durable_commit(self):
        self.model.admit(owner="A", epoch=1, request_id="r1", digest="d1")
        self.model.begin_key_operation("r1")
        self.model.begin_transfer("B")
        with self.assertRaises(Fenced):
            self.model.admit(owner="A", epoch=1, request_id="r2", digest="d2")
        with self.assertRaises(TransferBlocked):
            self.model.commit_transfer()
        signature = self.model.commit_signature("r1")
        self.assertTrue(signature.startswith(b"MODEL-ONLY:"))
        self.assertEqual(self.model.commit_transfer(), Ownership("B", 2))
        self.assertEqual(len(self.model.released), 1)

    def test_exact_retry_remains_addressable_during_transfer_drain(self):
        admitted = self.model.admit(owner="A", epoch=1, request_id="retry", digest="d")
        self.model.begin_transfer("B")
        retried = self.model.admit(owner="A", epoch=1, request_id="retry", digest="d")
        self.assertIs(admitted, retried)
        with self.assertRaises(Fenced):
            self.model.admit(owner="A", epoch=1, request_id="new", digest="new-d")

    def test_transfer_wins_before_old_owner_admission(self):
        self.model.begin_transfer("B")
        self.assertEqual(self.model.commit_transfer(), Ownership("B", 2))
        with self.assertRaises(Fenced):
            self.model.admit(owner="A", epoch=1, request_id="late", digest="d")
        self.model.admit(owner="B", epoch=2, request_id="new", digest="d2")
        self.assertEqual(self.model.ownership, Ownership("B", 2))

    def test_unknown_after_key_operation_blocks_transfer_until_reconciled(self):
        self.model.admit(owner="A", epoch=1, request_id="uncertain", digest="d")
        self.model.begin_key_operation("uncertain")
        self.model.mark_unknown("uncertain")
        self.model.begin_transfer("B")
        with self.assertRaises(TransferBlocked):
            self.model.commit_transfer()
        with self.assertRaises(UnknownBlocked):
            self.model.begin_key_operation("uncertain")
        recovered = b"MODEL-ONLY:reconciled-exact-result"
        self.model.reconcile_committed("uncertain", recovered)
        self.assertEqual(self.model.commit_transfer(), Ownership("B", 2))
        self.assertEqual(self.model.released[0][3], recovered)

    def test_unknown_cannot_be_cleared_without_exact_evidence(self):
        self.model.admit(owner="A", epoch=1, request_id="uncertain", digest="d")
        self.model.begin_key_operation("uncertain")
        self.model.mark_unknown("uncertain")
        with self.assertRaises(UnknownBlocked):
            self.model.reconcile_committed("uncertain", None)
        self.model.begin_transfer("B")
        with self.assertRaises(TransferBlocked):
            self.model.commit_transfer()

    def test_same_request_retry_is_idempotent_but_payload_change_is_rejected(self):
        first = self.model.admit(owner="A", epoch=1, request_id="same", digest="digest")
        retry = self.model.admit(owner="A", epoch=1, request_id="same", digest="digest")
        self.assertIs(first, retry)
        with self.assertRaises(Fenced):
            self.model.admit(owner="A", epoch=1, request_id="same", digest="altered")


if __name__ == "__main__":
    unittest.main()
