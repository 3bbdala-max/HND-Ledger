import json
import tempfile
import unittest
from pathlib import Path

from hnd_v02.remote_monotonic_anchor import RemoteMonotonicAnchor
from hnd_v02.monotonic_anchor import MonotonicAnchorUnavailable
from hnd_v02.remote_activation_intent import (
    RemoteActivationIntentClient, RemoteActivationProtocolError,
)


class IntentService:
    def __init__(self):
        self.intents = {}
        self.calls = []
        self.fail_after_commit = False

    def transport(self, url, body, headers, timeout):
        request = json.loads(body)
        self.calls.append((url, request))
        route = url.rsplit("/", 3)[-3:]
        path = "/" + "/".join(route)
        if url.endswith("/v2/activation/prepare"):
            intent = {
                "activation_id": request["activation_id"], "state": "prepared",
                "predecessors": request["predecessors"], "successors": request["successors"],
                "profile_digest": request["profile_digest"],
                "operator_ack_digest": request["operator_ack_digest"],
            }
            existing = self.intents.get(intent["activation_id"])
            if existing is not None and existing != intent:
                return 409, {"Content-Type": "application/json"}, b'{"error":"conflict"}'
            self.intents[intent["activation_id"]] = intent
            response = intent
        elif url.endswith("/v2/activation/read"):
            response = {"intent": self.intents.get(request["activation_id"])}
        elif url.endswith("/v2/activation/finalize"):
            intent = self.intents.get(request["activation_id"])
            if intent is None:
                return 404, {"Content-Type": "application/json"}, b'{}'
            if (intent["profile_digest"] != request["profile_digest"]
                    or intent["operator_ack_digest"] != request["operator_ack_digest"]):
                return 409, {"Content-Type": "application/json"}, b'{}'
            intent = dict(intent)
            intent["state"] = "finalized"
            self.intents[request["activation_id"]] = intent
            response = intent
            if self.fail_after_commit:
                self.fail_after_commit = False
                raise OSError("response lost after durable commit")
        else:
            return 404, {"Content-Type": "application/json"}, b'{}'
        return 200, {"Content-Type": "application/json; charset=utf-8"}, json.dumps(response).encode()


class RemoteActivationIntentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        for name in ("ca.pem", "client.pem", "client.key"):
            (root / name).write_text("fixture")
        self.service = IntentService()
        anchor = RemoteMonotonicAnchor(
            "https://anchor.example/hnd", ca_file=str(root / "ca.pem"),
            client_cert_file=str(root / "client.pem"),
            client_key_file=str(root / "client.key"),
            transport=self.service.transport,
        )
        self.client = RemoteActivationIntentClient(anchor)
        self.old_tm = None
        self.old_vsp = None
        self.new_tm = {"sequence": 0, "digest": "1" * 64}
        self.new_vsp = {"sequence": 1, "digest": "2" * 64}

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, activation_id="activation-001"):
        return self.client.prepare(
            activation_id=activation_id,
            predecessor_trust_manifest=self.old_tm,
            predecessor_vsp_profile=self.old_vsp,
            successor_trust_manifest=self.new_tm,
            successor_vsp_profile=self.new_vsp,
            profile_digest="3" * 64, operator_ack_digest="4" * 64,
        )

    def test_prepare_read_and_finalize(self):
        prepared = self.prepare()
        self.assertEqual(prepared.state, "prepared")
        self.assertEqual(self.client.read_intent("activation-001"), prepared)
        finalized = self.client.finalize(
            activation_id="activation-001", profile_digest="3" * 64,
            operator_ack_digest="4" * 64,
        )
        self.assertEqual(finalized.state, "finalized")
        self.assertEqual(self.client.read_intent("activation-001"), finalized)

    def test_lost_finalize_response_is_reconciled_by_same_activation_id(self):
        self.prepare()
        self.service.fail_after_commit = True
        with self.assertRaises(Exception):
            self.client.finalize(
                activation_id="activation-001", profile_digest="3" * 64,
                operator_ack_digest="4" * 64,
            )
        observed = self.client.read_intent("activation-001")
        self.assertEqual(observed.state, "finalized")

    def test_prepare_rejects_sequence_skip_before_network(self):
        before = len(self.service.calls)
        with self.assertRaises(RemoteActivationProtocolError):
            self.client.prepare(
                activation_id="bad-sequence", predecessor_trust_manifest=None,
                predecessor_vsp_profile=None,
                successor_trust_manifest={"sequence": 1, "digest": "1" * 64},
                successor_vsp_profile=self.new_vsp, profile_digest="3" * 64,
                operator_ack_digest="4" * 64,
            )
        self.assertEqual(len(self.service.calls), before)

    def test_finalize_rejects_wrong_digests(self):
        self.prepare()
        with self.assertRaises(MonotonicAnchorUnavailable):
            self.client.finalize(
                activation_id="activation-001", profile_digest="9" * 64,
                operator_ack_digest="4" * 64,
            )

    def test_read_unknown_intent_returns_none(self):
        self.assertIsNone(self.client.read_intent("not-created"))

    def test_prepare_rejects_malformed_remote_intent(self):
        self.client._request = lambda *_: {"activation_id": "other", "state": "prepared"}
        with self.assertRaises(RemoteActivationProtocolError):
            self.prepare()


if __name__ == "__main__":
    unittest.main()
