import ssl
import tempfile
import unittest
from pathlib import Path

from hnd_v02.monotonic_anchor import MonotonicRecord, MonotonicAnchorConflict
from hnd_v02.remote_monotonic_anchor_server import (
    MonotonicAnchorHTTPError, _strict_loads,
    create_monotonic_anchor_server, dispatch_monotonic_anchor_request,
)
from hnd_v02.sqlite_monotonic_anchor import SQLiteMonotonicAnchor


class RemoteMonotonicAnchorServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.anchor = SQLiteMonotonicAnchor(Path(self.temp.name) / "anchor.sqlite")
        self.bootstrap = {
            "namespace": "trust-manifest",
            "expected_current": None,
            "new_record": {"sequence": 0, "digest": "a" * 64},
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_read_and_compare_and_advance_round_trip(self):
        self.assertEqual(dispatch_monotonic_anchor_request(
            self.anchor, "/v1/state/read", {"namespace": "trust-manifest"}
        ), {"record": None})
        self.assertEqual(dispatch_monotonic_anchor_request(
            self.anchor, "/v1/state/compare-and-advance", self.bootstrap
        ), {"advanced": True})
        self.assertEqual(dispatch_monotonic_anchor_request(
            self.anchor, "/v1/state/read", {"namespace": "trust-manifest"}
        ), {"record": {"sequence": 0, "digest": "a" * 64}})

    def test_stale_compare_and_advance_is_false_and_does_not_mutate(self):
        dispatch_monotonic_anchor_request(
            self.anchor, "/v1/state/compare-and-advance", self.bootstrap
        )
        stale = dict(self.bootstrap, new_record={"sequence": 0, "digest": "b" * 64})
        self.assertEqual(dispatch_monotonic_anchor_request(
            self.anchor, "/v1/state/compare-and-advance", stale
        ), {"advanced": False})
        self.assertEqual(self.anchor.read_state("trust-manifest"),
                         MonotonicRecord(0, "a" * 64))

    def test_invalid_transition_and_shapes_fail_closed(self):
        bad = dict(self.bootstrap, new_record={"sequence": 1, "digest": "b" * 64})
        with self.assertRaises(MonotonicAnchorHTTPError) as caught:
            dispatch_monotonic_anchor_request(
                self.anchor, "/v1/state/compare-and-advance", bad
            )
        self.assertEqual(caught.exception.status, 409)
        for route, payload in (
            ("/v1/state/read", {"namespace": "trust-manifest", "extra": 1}),
            ("/v1/state/compare-and-advance", {"namespace": "trust-manifest"}),
            ("/v1/state/read", {"namespace": "unknown"}),
        ):
            with self.subTest(route=route, payload=payload):
                with self.assertRaises(MonotonicAnchorHTTPError):
                    dispatch_monotonic_anchor_request(self.anchor, route, payload)

    def test_unknown_route_and_strict_json_rejected(self):
        with self.assertRaises(MonotonicAnchorHTTPError) as caught:
            dispatch_monotonic_anchor_request(self.anchor, "/wrong", {})
        self.assertEqual(caught.exception.status, 404)
        with self.assertRaises(ValueError):
            _strict_loads(b'{"namespace":"a","namespace":"b"}')
        with self.assertRaises(ValueError):
            _strict_loads(b'{"value":NaN}')


    def test_dispatch_accepts_injected_non_sqlite_anchor_implementation(self):
        class InjectedAnchor:
            def __init__(self):
                self.state = {}
            def read_state(self, namespace):
                return self.state.get(namespace)
            def compare_and_advance(self, namespace, expected_current, new_record):
                if self.state.get(namespace) != expected_current:
                    return False
                if expected_current is None:
                    if new_record.sequence != (0 if namespace == "trust-manifest" else 1):
                        raise MonotonicAnchorConflict("bad bootstrap")
                elif new_record.sequence != expected_current.sequence + 1:
                    raise MonotonicAnchorConflict("bad successor")
                self.state[namespace] = new_record
                return True

        injected = InjectedAnchor()
        self.assertEqual(dispatch_monotonic_anchor_request(
            injected, "/v1/state/compare-and-advance", self.bootstrap
        ), {"advanced": True})
        self.assertEqual(dispatch_monotonic_anchor_request(
            injected, "/v1/state/read", {"namespace": "trust-manifest"}
        ), {"record": {"sequence": 0, "digest": "a" * 64}})

    def test_server_requires_mtls_and_nonempty_pins(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.verify_mode = ssl.CERT_NONE
        with self.assertRaises(ValueError):
            create_monotonic_anchor_server(
                self.anchor, ssl_context=context,
                authorized_client_cert_sha256={"a" * 64},
            )
        context.verify_mode = ssl.CERT_REQUIRED
        with self.assertRaises(ValueError):
            create_monotonic_anchor_server(
                self.anchor, ssl_context=context,
                authorized_client_cert_sha256=set(),
            )


if __name__ == "__main__":
    unittest.main()
