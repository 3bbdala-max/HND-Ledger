import base64
import json
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.activation_witness_service import create_activation_witness_server
from hnd_v02.activation_witness_store import SQLiteActivationWitnessStore
from hnd_v02.witness_production_attestation import (
    require_production_witness_backend,
)

_DOMAIN = b"HND-STATION2-WITNESS-PRODUCTION-ATTESTATION-V1" + bytes([0])


class _ProductionContractFake:
    capabilities = {
        "backend": "etcd-witness-v1",
        "production_capable": True,
        "quorum_ready": True,
        "anti_rollback_verified": True,
        "protected_key_custody": True,
    }
    backend_identity = {
        "backend": "etcd-witness-v1",
        "witness_id": "witness-prod-a",
        "config_epoch": 4,
        "quorum_id": "witness-quorum-a",
        "anchor_id": "anchor-prod-a",
        "signing_key_ref": "hsm://witness-prod-a/key-7",
    }

    def acknowledge(self, activation_id, activation_digest):
        return {}


class WitnessBackendInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.attestor = Ed25519PrivateKey.generate()
        self.public_key = self.attestor.public_key().public_bytes_raw()
        self.now = 1_800_000_000
        self.attestation = {
            "schema": "hnd.station2.witness-production-attestation.v1",
            "backend": "etcd-witness-v1",
            "witness_id": "witness-prod-a",
            "config_epoch": 4,
            "quorum_id": "witness-quorum-a",
            "anchor_id": "anchor-prod-a",
            "signing_key_ref": "hsm://witness-prod-a/key-7",
            "review_reference": "SEC-REVIEW-2026-001",
            "issued_at": self.now - 60,
            "expires_at": self.now + 3600,
        }
        self.attestation = self._signed(self.attestation)

    def _signed(self, payload):
        signature = self.attestor.sign(
            _DOMAIN + json.dumps(
                payload, ensure_ascii=True, allow_nan=False,
                sort_keys=True, separators=(",", ":"),
            ).encode("ascii")
        )
        return {
            **payload,
            "signature": base64.b64encode(signature).decode("ascii"),
        }

    def test_reference_sqlite_capabilities_are_never_production_ready(self):
        store = SQLiteActivationWitnessStore(
            ":memory:", witness_id="witness-test", config_epoch=1,
            signing_key=Ed25519PrivateKey.generate(),
        )
        self.assertEqual(store.capabilities["backend"], "sqlite-reference")
        for key in (
            "production_capable", "quorum_ready",
            "anti_rollback_verified", "protected_key_custody",
        ):
            self.assertIs(store.capabilities[key], False)
        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-PRODUCTION-GATE"):
            require_production_witness_backend(store)

    def test_development_reference_service_cannot_bind_non_loopback(self):
        store = SQLiteActivationWitnessStore(
            ":memory:", witness_id="witness-test", config_epoch=1,
            signing_key=Ed25519PrivateKey.generate(),
        )
        with self.assertRaisesRegex(
            ValueError, "HND-WITNESS-SERVICE-E-DEVELOPMENT-BIND"
        ):
            create_activation_witness_server(
                store, ssl_context=None,
                authorized_client_cert_sha256={"a" * 64},
                address=("0.0.0.0", 9445),
                require_production_backend=False,
            )

    def test_service_rejects_sqlite_by_default(self):
        store = SQLiteActivationWitnessStore(
            ":memory:", witness_id="witness-test", config_epoch=1,
            signing_key=Ed25519PrivateKey.generate(),
        )
        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-PRODUCTION-GATE"):
            create_activation_witness_server(
                store, ssl_context=None,
                authorized_client_cert_sha256={"a" * 64},
            )

    def test_missing_capabilities_fail_closed(self):
        class IncompleteBackend:
            def acknowledge(self, activation_id, activation_digest):
                return {}

        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-CAPABILITIES"):
            require_production_witness_backend(
                IncompleteBackend(), attestation=self.attestation,
                trusted_attestor_public_key=self.public_key, now=self.now,
            )

    def test_self_asserted_capabilities_are_not_enough(self):
        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-ATTESTATION-REQUIRED"):
            require_production_witness_backend(_ProductionContractFake())

    def test_pinned_attestation_is_required_and_binds_backend_identity(self):
        require_production_witness_backend(
            _ProductionContractFake(), attestation=self.attestation,
            trusted_attestor_public_key=self.public_key, now=self.now,
        )

    def test_tampered_or_wrong_attestor_signature_is_rejected(self):
        tampered = dict(self.attestation)
        tampered["quorum_id"] = "attacker-controlled-quorum"
        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-ATTESTATION-INVALID"):
            require_production_witness_backend(
                _ProductionContractFake(), attestation=tampered,
                trusted_attestor_public_key=self.public_key, now=self.now,
            )
        other_key = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-ATTESTATION-INVALID"):
            require_production_witness_backend(
                _ProductionContractFake(), attestation=self.attestation,
                trusted_attestor_public_key=other_key, now=self.now,
            )

    def test_expired_attestation_is_rejected(self):
        expired = dict(self.attestation)
        expired["issued_at"] = self.now - 7200
        expired["expires_at"] = self.now - 1
        expired = self._signed({k: v for k, v in expired.items() if k != "signature"})
        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-ATTESTATION-EXPIRED"):
            require_production_witness_backend(
                _ProductionContractFake(), attestation=expired,
                trusted_attestor_public_key=self.public_key, now=self.now,
            )

    def test_capability_backend_name_must_match_signed_backend(self):
        class MismatchedBackend(_ProductionContractFake):
            capabilities = {
                **_ProductionContractFake.capabilities,
                "backend": "different-backend",
            }

        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-ATTESTATION-BINDING"):
            require_production_witness_backend(
                MismatchedBackend(), attestation=self.attestation,
                trusted_attestor_public_key=self.public_key, now=self.now,
            )

    def test_future_issued_attestation_is_rejected(self):
        future = dict(self.attestation)
        future["issued_at"] = self.now + 61
        future["expires_at"] = self.now + 3600
        future = self._signed({k: v for k, v in future.items() if k != "signature"})
        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-ATTESTATION-EXPIRED"):
            require_production_witness_backend(
                _ProductionContractFake(), attestation=future,
                trusted_attestor_public_key=self.public_key, now=self.now,
            )

    def test_attestation_validity_window_cannot_exceed_90_days(self):
        long_lived = dict(self.attestation)
        long_lived["issued_at"] = self.now
        long_lived["expires_at"] = self.now + 90 * 24 * 60 * 60 + 1
        long_lived = self._signed({k: v for k, v in long_lived.items() if k != "signature"})
        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-ATTESTATION-EXPIRED"):
            require_production_witness_backend(
                _ProductionContractFake(), attestation=long_lived,
                trusted_attestor_public_key=self.public_key, now=self.now,
            )

    def test_attestation_rejects_unknown_payload_fields(self):
        extra = dict(self.attestation)
        extra["operator_note"] = "not covered by the signed schema"
        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-ATTESTATION-SHAPE"):
            require_production_witness_backend(
                _ProductionContractFake(), attestation=extra,
                trusted_attestor_public_key=self.public_key, now=self.now,
            )

    def test_identity_mismatch_is_rejected_after_signature_verification(self):
        mismatched = dict(self.attestation)
        mismatched["anchor_id"] = "different-anchor"
        mismatched = self._signed({k: v for k, v in mismatched.items() if k != "signature"})
        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-ATTESTATION-BINDING"):
            require_production_witness_backend(
                _ProductionContractFake(), attestation=mismatched,
                trusted_attestor_public_key=self.public_key, now=self.now,
            )


if __name__ == "__main__":
    unittest.main()
