import base64
import json
import unittest
from unittest.mock import patch

from hnd_v02.activation_transaction import ActivationState
from hnd_v02.etcd_atomic_activation import (
    EtcdV3AtomicActivationBackend, EtcdAtomicActivationError,
)


def state(manifest_sequence=0, profile_sequence=1, height=100,
          manifest_digest="1" * 64, profile_digest="2" * 64,
          previous_manifest=None, previous_profile=None):
    return ActivationState(
        trust_manifest_sequence=manifest_sequence,
        trust_manifest_digest=manifest_digest,
        profile_sequence=profile_sequence,
        profile_digest=profile_digest,
        activation_height=height,
        operator_ack_set_sha256="3" * 64,
        previous_trust_manifest_digest=previous_manifest,
        previous_profile_digest=previous_profile,
    )


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit=-1):
        return self.payload[:limit]


class EtcdV3AtomicActivationTests(unittest.TestCase):
    def backend(self, validator=None):
        return EtcdV3AtomicActivationBackend(
            "https://etcd.example.test:2379",
            profile_validator=validator or (lambda artifact, digest: digest == "2" * 64),
        )

    def test_requires_https_and_explicit_profile_validator(self):
        with self.assertRaises(EtcdAtomicActivationError):
            EtcdV3AtomicActivationBackend(
                "http://127.0.0.1:2379",
                profile_validator=lambda artifact, digest: True,
            )
        with self.assertRaises(EtcdAtomicActivationError):
            EtcdV3AtomicActivationBackend(
                "https://etcd.example.test:2379",
                profile_validator=None,
            )

    @patch("hnd_v02.etcd_atomic_activation.urllib.request.urlopen")
    def test_bootstrap_writes_state_and_profile_in_one_etcd_transaction(self, urlopen):
        urlopen.return_value = _Response({"succeeded": True})
        backend = self.backend()
        proposed = state()
        self.assertTrue(backend.compare_and_activate(None, proposed, b"profile-v1"))
        self.assertEqual(urlopen.call_count, 1)
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/v3/kv/txn"))
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(len(payload["compare"]), 1)
        self.assertEqual(payload["compare"][0]["target"], "CREATE")
        self.assertEqual(payload["compare"][0]["create_revision"], "0")
        self.assertEqual(len(payload["success"]), 2)
        written = {
            base64.b64decode(item["request_put"]["key"]).decode("utf-8"):
            base64.b64decode(item["request_put"]["value"])
            for item in payload["success"]
        }
        self.assertEqual(
            written["/hnd/station2/active-state"],
            backend._encode_state(proposed),
        )
        self.assertEqual(written["/hnd/station2/active-profile"], b"profile-v1")

    @patch("hnd_v02.etcd_atomic_activation.urllib.request.urlopen")
    def test_successor_compares_exact_current_state_and_writes_both_records(self, urlopen):
        urlopen.return_value = _Response({"succeeded": True})
        backend = self.backend()
        current = state()
        proposed = state(
            manifest_sequence=1, profile_sequence=2, height=101,
            manifest_digest="4" * 64, profile_digest="5" * 64,
            previous_manifest="1" * 64, previous_profile="2" * 64,
        )
        backend.profile_validator = lambda artifact, digest: (
            artifact == b"profile-v2" and digest == "5" * 64
        )
        self.assertTrue(backend.compare_and_activate(current, proposed, b"profile-v2"))
        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        comparison = payload["compare"][0]
        self.assertEqual(comparison["target"], "VALUE")
        self.assertEqual(
            base64.b64decode(comparison["value"]),
            backend._encode_state(current),
        )
        self.assertEqual(len(payload["success"]), 2)

    @patch("hnd_v02.etcd_atomic_activation.urllib.request.urlopen")
    def test_etcd_compare_failure_is_reported_as_false(self, urlopen):
        urlopen.return_value = _Response({"succeeded": False})
        backend = self.backend()
        self.assertFalse(backend.compare_and_activate(None, state(), b"profile-v1"))

    @patch("hnd_v02.etcd_atomic_activation.urllib.request.urlopen")
    def test_profile_validation_failure_never_calls_etcd(self, urlopen):
        backend = self.backend(validator=lambda artifact, digest: False)
        with self.assertRaises(EtcdAtomicActivationError):
            backend.compare_and_activate(None, state(), b"tampered")
        urlopen.assert_not_called()

    @patch("hnd_v02.etcd_atomic_activation.urllib.request.urlopen")
    def test_state_and_profile_reads_decode_etcd_range_values(self, urlopen):
        proposed = state()
        state_value = base64.b64encode(
            EtcdV3AtomicActivationBackend._encode_state(proposed)
        ).decode("ascii")
        profile_value = base64.b64encode(b"profile-v1").decode("ascii")
        urlopen.side_effect = [
            _Response({"kvs": [{"value": state_value, "mod_revision": "7"}]}),
            _Response({"kvs": [{"value": profile_value, "mod_revision": "7"}]}),
        ]
        backend = self.backend()
        self.assertEqual(backend.read_active_state(), proposed)
        self.assertEqual(backend.read_active_profile(), b"profile-v1")
        self.assertEqual(urlopen.call_count, 2)

    @patch("hnd_v02.etcd_atomic_activation.urllib.request.urlopen")
    def test_corrupt_state_fails_closed(self, urlopen):
        raw = base64.b64encode(b'{"unexpected":true}').decode("ascii")
        urlopen.return_value = _Response({"kvs": [{"value": raw}]})
        with self.assertRaises(EtcdAtomicActivationError):
            self.backend().read_active_state()

    @patch("hnd_v02.etcd_atomic_activation.urllib.request.urlopen")
    def test_invalid_successor_fails_before_network_write(self, urlopen):
        invalid = state(manifest_sequence=2, profile_sequence=2)
        with self.assertRaises(EtcdAtomicActivationError):
            self.backend().compare_and_activate(None, invalid, b"profile")
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
