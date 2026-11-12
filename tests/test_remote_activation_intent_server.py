import ssl
import tempfile
import unittest
from pathlib import Path

from hnd_v02.remote_activation_intent_server import (
    ActivationIntentHTTPError,
    _strict_loads,
    create_activation_intent_server,
    dispatch_activation_request,
)
from hnd_v02.sqlite_activation_intent_store import SQLiteActivationIntentStore


class RemoteActivationIntentServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteActivationIntentStore(Path(self.temp.name) / "server.sqlite")
        self.request = {
            "activation_id": "server-activation-001",
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

    def test_unwitnessed_finalize_is_rejected_and_intent_remains_prepared(self):
        prepared = dispatch_activation_request(
            self.store, "/v2/activation/prepare", self.request
        )
        self.assertEqual(prepared["state"], "prepared")
        read = dispatch_activation_request(
            self.store, "/v2/activation/read",
            {"activation_id": self.request["activation_id"]},
        )
        self.assertEqual(read["intent"], prepared)
        with self.assertRaises(ActivationIntentHTTPError) as caught:
            dispatch_activation_request(
                self.store, "/v2/activation/finalize", {
                    "activation_id": self.request["activation_id"],
                    "profile_digest": "3" * 64,
                    "operator_ack_digest": "4" * 64,
                },
            )
        self.assertEqual(caught.exception.status, 409)
        self.assertIn("WITNESS-RECEIPT-REQUIRED", str(caught.exception))
        still_prepared = self.store.read_intent(self.request["activation_id"])
        self.assertEqual(still_prepared["state"], "prepared")

    def test_duplicate_prepare_conflict_is_fail_closed(self):
        dispatch_activation_request(self.store, "/v2/activation/prepare", self.request)
        changed = dict(self.request, profile_digest="5" * 64)
        with self.assertRaises(ActivationIntentHTTPError) as caught:
            dispatch_activation_request(self.store, "/v2/activation/prepare", changed)
        self.assertEqual(caught.exception.status, 409)

    def test_read_requires_exact_shape(self):
        with self.assertRaises(ActivationIntentHTTPError) as caught:
            dispatch_activation_request(
                self.store, "/v2/activation/read",
                {"activation_id": "x", "extra": True},
            )
        self.assertEqual(caught.exception.status, 400)

    def test_unknown_route_rejected(self):
        with self.assertRaises(ActivationIntentHTTPError) as caught:
            dispatch_activation_request(self.store, "/wrong", {})
        self.assertEqual(caught.exception.status, 404)

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_values(self):
        with self.assertRaises(ValueError):
            _strict_loads(b'{"activation_id":"a","activation_id":"b"}')
        with self.assertRaises(ValueError):
            _strict_loads(b'{"x":NaN}')

    def test_server_requires_client_certificate_authentication_and_pin(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.verify_mode = ssl.CERT_NONE
        with self.assertRaises(ValueError):
            create_activation_intent_server(
                self.store, ssl_context=context,
                authorized_client_cert_sha256={"a" * 64},
            )
        context.verify_mode = ssl.CERT_REQUIRED
        with self.assertRaises(ValueError):
            create_activation_intent_server(
                self.store, ssl_context=context,
                authorized_client_cert_sha256=set(),
            )


if __name__ == "__main__":
    unittest.main()
