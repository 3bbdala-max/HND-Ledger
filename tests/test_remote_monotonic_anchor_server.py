import ssl
import tempfile
import unittest
from pathlib import Path

from hnd_v02.monotonic_anchor import MonotonicRecord, MonotonicAnchorConflict
from hnd_v02.remote_monotonic_anchor_server import (
    AnchorClientPolicy, AnchorClientRegistry, MonotonicAnchorHTTPError,
    _strict_loads, create_monotonic_anchor_server,
    dispatch_monotonic_anchor_request,
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

    def policy_for(self, namespace):
        roles = {
            "trust-manifest": "trust-manifest-authority",
            "vsp-profile": "vsp-profile-authority",
        }
        return AnchorClientPolicy(
            "test-" + namespace, roles[namespace],
            frozenset({namespace}),
            frozenset({"read", "compare-and-advance"}),
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_read_and_compare_and_advance_round_trip(self):
        self.assertEqual(dispatch_monotonic_anchor_request(
            self.anchor, "/v1/state/read", {"namespace": "trust-manifest"},
            client_policy=self.policy_for("trust-manifest"),
        ), {"record": None})
        self.assertEqual(dispatch_monotonic_anchor_request(
            self.anchor, "/v1/state/compare-and-advance", self.bootstrap,
            client_policy=self.policy_for("trust-manifest"),
        ), {"advanced": True})
        self.assertEqual(dispatch_monotonic_anchor_request(
            self.anchor, "/v1/state/read", {"namespace": "trust-manifest"},
            client_policy=self.policy_for("trust-manifest"),
        ), {"record": {"sequence": 0, "digest": "a" * 64}})

    def test_stale_compare_and_advance_is_false_and_does_not_mutate(self):
        dispatch_monotonic_anchor_request(
            self.anchor, "/v1/state/compare-and-advance", self.bootstrap,
            client_policy=self.policy_for("trust-manifest"),
        )
        stale = dict(self.bootstrap, new_record={"sequence": 0, "digest": "b" * 64})
        self.assertEqual(dispatch_monotonic_anchor_request(
            self.anchor, "/v1/state/compare-and-advance", stale,
            client_policy=self.policy_for("trust-manifest"),
        ), {"advanced": False})
        self.assertEqual(self.anchor.read_state("trust-manifest"),
                         MonotonicRecord(0, "a" * 64))

    def test_invalid_transition_and_shapes_fail_closed(self):
        bad = dict(self.bootstrap, new_record={"sequence": 1, "digest": "b" * 64})
        with self.assertRaises(MonotonicAnchorHTTPError) as caught:
            dispatch_monotonic_anchor_request(
                self.anchor, "/v1/state/compare-and-advance", bad,
                client_policy=self.policy_for("trust-manifest"),
            )
        self.assertEqual(caught.exception.status, 409)
        for route, payload in (
            ("/v1/state/read", {"namespace": "trust-manifest", "extra": 1}),
            ("/v1/state/compare-and-advance", {"namespace": "trust-manifest"}),
            ("/v1/state/read", {"namespace": "unknown"}),
        ):
            with self.subTest(route=route, payload=payload):
                with self.assertRaises(MonotonicAnchorHTTPError):
                    dispatch_monotonic_anchor_request(
                self.anchor, route, payload,
                client_policy=self.policy_for("trust-manifest"),
            )

    def test_unknown_route_and_strict_json_rejected(self):
        with self.assertRaises(MonotonicAnchorHTTPError) as caught:
            dispatch_monotonic_anchor_request(
                self.anchor, "/wrong", {},
                client_policy=self.policy_for("trust-manifest"),
            )
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
            injected, "/v1/state/compare-and-advance", self.bootstrap,
            client_policy=self.policy_for("trust-manifest"),
        ), {"advanced": True})
        self.assertEqual(dispatch_monotonic_anchor_request(
            injected, "/v1/state/read", {"namespace": "trust-manifest"},
            client_policy=self.policy_for("trust-manifest"),
        ), {"record": {"sequence": 0, "digest": "a" * 64}})

    def test_server_requires_mtls_and_role_registry(self):
        registry = AnchorClientRegistry({
            "a" * 64: AnchorClientPolicy(
                "trust-1", "trust-manifest-authority",
                frozenset({"trust-manifest"}),
                frozenset({"read", "compare-and-advance"}),
            )
        })
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.verify_mode = ssl.CERT_NONE
        with self.assertRaises(ValueError):
            create_monotonic_anchor_server(
                self.anchor, ssl_context=context, client_registry=registry,
            )
        context.verify_mode = ssl.CERT_REQUIRED
        with self.assertRaises(ValueError):
            create_monotonic_anchor_server(
                self.anchor, ssl_context=context, client_registry={},
            )

    def test_role_authorization_blocks_cross_namespace_and_read_only_writes(self):
        trust = AnchorClientPolicy(
            "trust-1", "trust-manifest-authority",
            frozenset({"trust-manifest"}),
            frozenset({"read", "compare-and-advance"}),
        )
        finalizer = AnchorClientPolicy(
            "finalizer-1", "finalizer",
            frozenset({"trust-manifest", "vsp-profile"}),
            frozenset({"read"}),
        )
        self.assertEqual(dispatch_monotonic_anchor_request(
            self.anchor, "/v1/state/read", {"namespace": "trust-manifest"},
            client_policy=trust,
        ), {"record": None})
        with self.assertRaisesRegex(MonotonicAnchorHTTPError, "AUTHZ"):
            dispatch_monotonic_anchor_request(
                self.anchor, "/v1/state/read", {"namespace": "vsp-profile"},
                client_policy=trust,
            )
        with self.assertRaisesRegex(MonotonicAnchorHTTPError, "AUTHZ"):
            dispatch_monotonic_anchor_request(
                self.anchor, "/v1/state/compare-and-advance", self.bootstrap,
                client_policy=finalizer,
            )
        self.assertIsNone(self.anchor.read_state("trust-manifest"))

    def test_recovery_and_operator_roles_have_no_v1_mutation_authority(self):
        for role in ("recovery", "operator"):
            policy = AnchorClientPolicy(role + "-1", role, frozenset(), frozenset())
            with self.assertRaisesRegex(MonotonicAnchorHTTPError, "AUTHZ"):
                dispatch_monotonic_anchor_request(
                    self.anchor, "/v1/state/read",
                    {"namespace": "trust-manifest"}, client_policy=policy,
                )

    def test_certificate_revocation_and_rotation_take_effect_immediately(self):
        old_pin, new_pin = "a" * 64, "b" * 64
        policy = AnchorClientPolicy(
            "trust-1", "trust-manifest-authority",
            frozenset({"trust-manifest"}),
            frozenset({"read", "compare-and-advance"}),
        )
        registry = AnchorClientRegistry({old_pin: policy})
        self.assertEqual(
            registry.authorize(old_pin, "read", "trust-manifest"), policy
        )
        registry.rotate(old_pin, new_pin, policy)
        with self.assertRaisesRegex(MonotonicAnchorHTTPError, "AUTHZ"):
            registry.authorize(old_pin, "read", "trust-manifest")
        self.assertEqual(
            registry.authorize(new_pin, "read", "trust-manifest"), policy
        )
        registry.revoke(new_pin)
        with self.assertRaisesRegex(MonotonicAnchorHTTPError, "AUTHZ"):
            registry.authorize(new_pin, "read", "trust-manifest")

    def test_certificate_rotation_cannot_expand_namespace_authority(self):
        old = AnchorClientPolicy(
            "finalizer-1", "finalizer",
            frozenset({"trust-manifest"}), frozenset({"read"}),
        )
        broader = AnchorClientPolicy(
            "finalizer-1", "finalizer",
            frozenset({"trust-manifest", "vsp-profile"}), frozenset({"read"}),
        )
        registry = AnchorClientRegistry({"a" * 64: old})
        with self.assertRaisesRegex(ValueError, "cannot broaden"):
            registry.rotate("a" * 64, "b" * 64, broader)
        self.assertEqual(
            registry.authorize("a" * 64, "read", "trust-manifest"), old
        )

    def test_policy_rejects_privilege_escalation(self):
        with self.assertRaises(ValueError):
            AnchorClientPolicy(
                "trust-1", "trust-manifest-authority",
                frozenset({"trust-manifest", "vsp-profile"}),
                frozenset({"read", "compare-and-advance"}),
            )
        with self.assertRaises(ValueError):
            AnchorClientPolicy(
                "finalizer-1", "finalizer",
                frozenset({"trust-manifest"}), frozenset({"read", "compare-and-advance"}),
            )

if __name__ == "__main__":
    unittest.main()
