import json
import tempfile
import unittest
from pathlib import Path

from hnd_v02.monotonic_anchor import (
    MonotonicAnchorConflict, MonotonicAnchorError, MonotonicAnchorUnavailable,
    MonotonicRecord, advance_monotonic_state,
)
from hnd_v02.remote_monotonic_anchor import RemoteMonotonicAnchor


class FakeLinearizableAnchorService:
    """In-memory service model; not evidence of a production remote service."""
    def __init__(self):
        self.state = {}
        self.requests = []

    def transport(self, url, body, headers, timeout):
        self.requests.append((url, json.loads(body), headers, timeout))
        request = json.loads(body)
        if url.endswith("/v1/state/read"):
            record = self.state.get(request["namespace"])
            result = None if record is None else {
                "sequence": record.sequence, "digest": record.digest,
            }
            response = {"record": result}
        elif url.endswith("/v1/state/compare-and-advance"):
            namespace = request["namespace"]
            expected = request["expected_current"]
            new = request["new_record"]
            current = self.state.get(namespace)
            current_json = None if current is None else {
                "sequence": current.sequence, "digest": current.digest,
            }
            advanced = current_json == expected
            if advanced:
                self.state[namespace] = MonotonicRecord(
                    new["sequence"], new["digest"]
                )
            response = {"advanced": advanced}
        else:
            return 404, {"Content-Type": "application/json"}, b'{}'
        return 200, {"Content-Type": "application/json; charset=utf-8"}, json.dumps(response).encode()


class RemoteMonotonicAnchorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        for name in ("ca.pem", "client.pem", "client.key"):
            (root / name).write_text("test fixture")
        self.service = FakeLinearizableAnchorService()
        self.anchor = RemoteMonotonicAnchor(
            "https://anchor.example/hnd",
            ca_file=str(root / "ca.pem"),
            client_cert_file=str(root / "client.pem"),
            client_key_file=str(root / "client.key"),
            transport=self.service.transport,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_bootstrap_and_successor_use_remote_compare_and_advance(self):
        first = advance_monotonic_state(
            self.anchor, "trust-manifest", sequence=0,
            digest="a" * 64, predecessor_digest=None,
        )
        second = advance_monotonic_state(
            self.anchor, "trust-manifest", sequence=1,
            digest="b" * 64, predecessor_digest="a" * 64,
        )
        self.assertEqual(first, MonotonicRecord(0, "a" * 64))
        self.assertEqual(second, MonotonicRecord(1, "b" * 64))
        self.assertEqual(self.anchor.read_state("trust-manifest"), second)
        self.assertTrue(any(url.endswith("/hnd/v1/state/compare-and-advance")
                            for url, *_ in self.service.requests))

    def test_stale_compare_and_advance_returns_false(self):
        current = MonotonicRecord(0, "a" * 64)
        self.service.state["trust-manifest"] = current
        self.assertFalse(self.anchor.compare_and_advance(
            "trust-manifest", None, MonotonicRecord(0, "b" * 64)
        ))
        self.assertEqual(self.anchor.read_state("trust-manifest"), current)

    def test_strictly_rejects_duplicate_keys_and_bad_response_shapes(self):
        self.service.transport = lambda *_: (
            200, {"Content-Type": "application/json"},
            b'{"record":null,"record":null}',
        )
        with self.assertRaises(MonotonicAnchorUnavailable):
            self.anchor.read_state("trust-manifest")
        self.service.transport = lambda *_: (
            200, {"Content-Type": "application/json"}, b'{"unexpected":null}',
        )
        with self.assertRaises(MonotonicAnchorUnavailable):
            self.anchor.read_state("trust-manifest")

    def test_rejects_non_https_and_invalid_tls_paths(self):
        with self.assertRaises(MonotonicAnchorError):
            RemoteMonotonicAnchor(
                "http://anchor.example", ca_file="x", client_cert_file="x",
                client_key_file="x", transport=self.service.transport,
            )
        with self.assertRaises(MonotonicAnchorError):
            RemoteMonotonicAnchor(
                "https://anchor.example", ca_file="missing",
                client_cert_file="missing", client_key_file="missing",
                transport=self.service.transport,
            )

    def test_rejects_invalid_records_before_network_call(self):
        count = len(self.service.requests)
        with self.assertRaises(MonotonicAnchorError):
            self.anchor.compare_and_advance(
                "trust-manifest", None, MonotonicRecord(-1, "a" * 64)
            )
        self.assertEqual(len(self.service.requests), count)

    def test_rejects_wrong_content_type_and_http_errors(self):
        self.service.transport = lambda *_: (
            200, {"Content-Type": "text/plain"}, b'{"record":null}',
        )
        with self.assertRaises(MonotonicAnchorUnavailable):
            self.anchor.read_state("trust-manifest")
        self.service.transport = lambda *_: (
            503, {"Content-Type": "application/json"}, b'{"record":null}',
        )
        with self.assertRaises(MonotonicAnchorUnavailable):
            self.anchor.read_state("trust-manifest")


if __name__ == "__main__":
    unittest.main()
