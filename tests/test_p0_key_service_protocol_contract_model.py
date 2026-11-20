"""MODEL-ONLY contract tests for the protected key-service protocol.

No cryptography, authenticated service, HSM, durable remote journal, or
multi-host fencing is implemented here. Synthetic evidence tests state
machine behavior only.
"""
import unittest


class ProtocolRejected(Exception):
    pass


class OutcomeUnknown(Exception):
    pass


class TransferBlocked(Exception):
    pass


class KeyServiceContractModel:
    def __init__(self, owner="A", epoch=1):
        self.owner = owner
        self.epoch = epoch
        self.transfer_target = None
        self.journal = {}
        self.nonces = {}
        self.key_operations = 0

    @staticmethod
    def identity(request):
        fields = (
            "request_id", "signer_id", "owner_id", "epoch", "key_id",
            "domain", "digest", "height", "round", "step", "nonce",
        )
        try:
            return tuple(request[field] for field in fields)
        except KeyError as exc:
            raise ProtocolRejected(f"missing field: {exc.args[0]}")

    def receive(self, request):
        identity = self.identity(request)
        request_id = request["request_id"]
        previous = self.journal.get(request_id)
        if previous is not None:
            if previous["identity"] != identity:
                raise ProtocolRejected("request ID identity conflict")
            return previous["state"]

        if self.transfer_target is not None:
            raise ProtocolRejected("transfer is draining")
        if (request["owner_id"], request["epoch"]) != (self.owner, self.epoch):
            raise ProtocolRejected("stale owner or epoch")
        nonce_key = (request["signer_id"], request["nonce"])
        if nonce_key in self.nonces:
            raise ProtocolRejected("replayed nonce")
        self.nonces[nonce_key] = request_id
        self.journal[request_id] = {
            "identity": identity, "request": dict(request),
            "state": "RECEIVED", "signature": None, "attestation": None,
        }
        return "RECEIVED"

    def execute_once(self, request_id):
        entry = self.journal[request_id]
        if entry["state"] == "SIGNED":
            return entry["signature"]
        if entry["state"] == "UNKNOWN":
            raise OutcomeUnknown("unknown outcome cannot be re-signed")
        if entry["state"] != "RECEIVED":
            raise ProtocolRejected("request is not executable")
        entry["state"] = "EXECUTING"
        self.key_operations += 1
        request = entry["request"]
        signature = (
            f"MODEL:{request['request_id']}:{request['epoch']}:"
            f"{request['digest']}"
        ).encode()
        # Synthetic attestation: explicitly not a cryptographic signature.
        attestation = (entry["identity"], signature, "MODEL-SERVICE")
        entry["signature"] = signature
        entry["attestation"] = attestation
        entry["state"] = "SIGNED"
        return signature

    def mark_unknown(self, request_id):
        entry = self.journal[request_id]
        if entry["state"] != "EXECUTING":
            raise ProtocolRejected("only an executing request can become unknown")
        entry["state"] = "UNKNOWN"

    def get_outcome(self, request_id):
        entry = self.journal[request_id]
        return entry["state"], entry["signature"], entry["attestation"]

    def reconcile(self, request_id, evidence, verifier):
        entry = self.journal[request_id]
        if entry["state"] != "UNKNOWN":
            raise OutcomeUnknown("request is not awaiting reconciliation")
        if evidence is None or not callable(verifier):
            raise OutcomeUnknown("authenticated evidence and verifier required")
        if verifier(entry["identity"], evidence) is not True:
            raise OutcomeUnknown("evidence rejected")
        identity, signature, service_id = evidence
        if identity != entry["identity"] or service_id != "MODEL-SERVICE":
            raise OutcomeUnknown("evidence binding mismatch")
        entry["signature"] = signature
        entry["attestation"] = evidence
        entry["state"] = "SIGNED"
        return signature

    def begin_transfer(self, target):
        if self.transfer_target is not None or target == self.owner:
            raise TransferBlocked("invalid or duplicate transfer")
        self.transfer_target = target

    def commit_transfer(self):
        if self.transfer_target is None:
            raise TransferBlocked("no transfer requested")
        for entry in self.journal.values():
            request = entry["request"]
            if request["owner_id"] == self.owner and request["epoch"] == self.epoch:
                if entry["state"] not in ("SIGNED", "REJECTED"):
                    raise TransferBlocked("old-epoch operation unresolved")
        self.owner = self.transfer_target
        self.epoch += 1
        self.transfer_target = None
        return self.owner, self.epoch


def request(request_id="r1", **overrides):
    value = {
        "request_id": request_id, "signer_id": "validator-1",
        "owner_id": "A", "epoch": 1, "key_id": "key-1",
        "domain": "HND-test-chain", "digest": "sha256:abc",
        "height": 10, "round": 0, "step": 2, "nonce": "nonce-1",
    }
    value.update(overrides)
    return value


class ProtectedKeyServiceContractTests(unittest.TestCase):
    def setUp(self):
        self.service = KeyServiceContractModel()

    def test_identical_retry_returns_exact_stored_signature(self):
        req = request()
        self.service.receive(req)
        first = self.service.execute_once("r1")
        self.assertEqual(self.service.receive(req), "SIGNED")
        self.assertEqual(self.service.execute_once("r1"), first)
        self.assertEqual(self.service.key_operations, 1)

    def test_same_request_id_with_changed_identity_is_rejected(self):
        self.service.receive(request())
        with self.assertRaises(ProtocolRejected):
            self.service.receive(request(digest="sha256:changed"))

    def test_stale_epoch_is_rejected_before_key_operation(self):
        with self.assertRaises(ProtocolRejected):
            self.service.receive(request(epoch=0))
        self.assertEqual(self.service.key_operations, 0)

    def test_replayed_nonce_on_different_request_is_rejected(self):
        self.service.receive(request())
        with self.assertRaises(ProtocolRejected):
            self.service.receive(request("r2"))
        self.assertEqual(self.service.key_operations, 0)

    def test_unknown_request_cannot_trigger_second_key_operation(self):
        self.service.receive(request())
        self.service.journal["r1"]["state"] = "EXECUTING"
        self.service.key_operations = 1
        self.service.mark_unknown("r1")
        with self.assertRaises(OutcomeUnknown):
            self.service.execute_once("r1")
        self.assertEqual(self.service.key_operations, 1)

    def test_missing_or_rejected_attestation_cannot_reconcile(self):
        self.service.receive(request())
        self.service.journal["r1"]["state"] = "EXECUTING"
        self.service.mark_unknown("r1")
        with self.assertRaises(OutcomeUnknown):
            self.service.reconcile("r1", None, lambda *_: True)
        with self.assertRaises(OutcomeUnknown):
            self.service.reconcile("r1", ("bad",), lambda *_: False)

    def test_reconciliation_recovers_original_result_without_resigning(self):
        self.service.receive(request())
        self.service.journal["r1"]["state"] = "EXECUTING"
        self.service.key_operations = 1
        entry = self.service.journal["r1"]
        sig = b"same-original-result"
        evidence = (entry["identity"], sig, "MODEL-SERVICE")
        self.service.mark_unknown("r1")
        result = self.service.reconcile("r1", evidence, lambda identity, ev: identity == ev[0])
        self.assertEqual(result, sig)
        self.assertEqual(self.service.key_operations, 1)
        self.assertEqual(self.service.get_outcome("r1")[0], "SIGNED")

    def test_transfer_blocks_while_old_epoch_is_unknown(self):
        self.service.receive(request())
        self.service.journal["r1"]["state"] = "EXECUTING"
        self.service.mark_unknown("r1")
        self.service.begin_transfer("B")
        with self.assertRaises(TransferBlocked):
            self.service.commit_transfer()
        self.assertEqual((self.service.owner, self.service.epoch), ("A", 1))

    def test_old_owner_rejected_after_transfer(self):
        self.service.begin_transfer("B")
        self.assertEqual(self.service.commit_transfer(), ("B", 2))
        with self.assertRaises(ProtocolRejected):
            self.service.receive(request("stale", owner_id="A", epoch=1))
        self.assertEqual(self.service.key_operations, 0)

    def test_conflicting_or_unbound_evidence_cannot_reconcile(self):
        self.service.receive(request())
        self.service.journal["r1"]["state"] = "EXECUTING"
        self.service.mark_unknown("r1")
        wrong = (("different-identity",), b"sig", "MODEL-SERVICE")
        with self.assertRaises(OutcomeUnknown):
            self.service.reconcile("r1", wrong, lambda *_: True)


if __name__ == "__main__":
    unittest.main()
