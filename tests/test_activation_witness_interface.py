import unittest

from hnd_v02.witness_production_attestation import require_production_witness_backend
from hnd_v02.activation_witness_store import SQLiteActivationWitnessStore
from hnd_v02.activation_witness_service import create_activation_witness_server
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class _ProductionContractFake:
    capabilities = {
        "backend": "test-contract-only",
        "production_capable": True,
        "quorum_ready": True,
        "anti_rollback_verified": True,
        "protected_key_custody": True,
    }

    def acknowledge(self, activation_id, activation_digest):
        return {}


class WitnessBackendInterfaceTests(unittest.TestCase):
    def test_reference_sqlite_capabilities_are_never_production_ready(self):
        store = SQLiteActivationWitnessStore(
            ":memory:", witness_id="witness-test", config_epoch=1,
            signing_key=Ed25519PrivateKey.generate(),
        )
        self.assertEqual(store.capabilities["backend"], "sqlite-reference")
        for key in (
            "production_capable",
            "quorum_ready",
            "anti_rollback_verified",
            "protected_key_custody",
        ):
            self.assertIs(store.capabilities[key], False)
        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-PRODUCTION-GATE"):
            require_production_witness_backend(store)

    def test_service_rejects_sqlite_by_default(self):
        store = SQLiteActivationWitnessStore(
            ":memory:", witness_id="witness-test", config_epoch=1,
            signing_key=Ed25519PrivateKey.generate(),
        )
        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-PRODUCTION-GATE"):
            create_activation_witness_server(
                store,
                ssl_context=None,
                authorized_client_cert_sha256={"a" * 64},
            )

    def test_missing_capabilities_fail_closed(self):
        class IncompleteBackend:
            def acknowledge(self, activation_id, activation_digest):
                return {}

        with self.assertRaisesRegex(ValueError, "HND-WITNESS-SERVICE-E-CAPABILITIES"):
            require_production_witness_backend(IncompleteBackend())

    def test_complete_capability_contract_passes_admission_check_only(self):
        # This fake verifies interface validation only; it is not a production backend.
        require_production_witness_backend(_ProductionContractFake())


if __name__ == "__main__":
    unittest.main()
