import json
import ssl
import unittest
from unittest.mock import patch

from hnd_v02.activation_witness_client import (
    ActivationWitnessClientError,
    HTTPSActivationWitnessClient,
)


class _Response:
    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit=-1):
        return self.raw[:limit]


class _Opener:
    def __init__(self, response):
        self.response = response
        self.request = None
        self.timeout = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        return self.response


class HTTPSActivationWitnessClientTests(unittest.TestCase):
    def context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        return context

    def test_requires_verified_server_tls_and_https_endpoint(self):
        with self.assertRaises(ActivationWitnessClientError):
            HTTPSActivationWitnessClient(
                "http://witness.example.test",
                ssl_context=self.context(),
            )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        with self.assertRaises(ActivationWitnessClientError):
            HTTPSActivationWitnessClient(
                "https://witness.example.test",
                ssl_context=context,
            )

    @patch("hnd_v02.activation_witness_client.urllib.request.build_opener")
    def test_acknowledge_posts_exact_payload_and_returns_receipt(self, build_opener):
        receipt = {
            "schema": "hnd.station2.witness-ack.v1",
            "activation_id": "activation-001",
            "activation_digest": "a" * 64,
            "witness_id": "witness-a",
            "config_epoch": 3,
            "counter": 1,
            "signature": "c2ln",
        }
        opener = _Opener(_Response(json.dumps({"receipt": receipt}).encode("utf-8")))
        build_opener.return_value = opener
        client = HTTPSActivationWitnessClient(
            "https://witness.example.test",
            ssl_context=self.context(),
            timeout=4,
        )
        result = client.acknowledge("activation-001", "a" * 64)
        self.assertEqual(result, receipt)
        self.assertEqual(opener.timeout, 4)
        self.assertTrue(opener.request.full_url.endswith("/v1/witness/acknowledge"))
        self.assertEqual(
            json.loads(opener.request.data.decode("ascii")),
            {"activation_id": "activation-001", "activation_digest": "a" * 64},
        )
        self.assertEqual(opener.request.get_method(), "POST")

    @patch("hnd_v02.activation_witness_client.urllib.request.build_opener")
    def test_duplicate_json_keys_and_wrong_response_shape_are_rejected(self, build_opener):
        client = HTTPSActivationWitnessClient(
            "https://witness.example.test",
            ssl_context=self.context(),
        )
        build_opener.return_value = _Opener(
            _Response(b'{"receipt":{},"receipt":{}}')
        )
        with self.assertRaises(ActivationWitnessClientError):
            client.acknowledge("activation-001", "a" * 64)
        build_opener.return_value = _Opener(_Response(b'{"receipt":[]}'))
        with self.assertRaises(ActivationWitnessClientError):
            client.acknowledge("activation-001", "a" * 64)

    @patch("hnd_v02.activation_witness_client.urllib.request.build_opener")
    def test_invalid_request_is_rejected_before_network(self, build_opener):
        client = HTTPSActivationWitnessClient(
            "https://witness.example.test",
            ssl_context=self.context(),
        )
        with self.assertRaises(ActivationWitnessClientError):
            client.acknowledge("../bad", "a" * 64)
        build_opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
