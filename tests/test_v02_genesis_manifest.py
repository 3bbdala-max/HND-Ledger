"""Tests for the isolated HND v0.2 genesis-manifest validator."""
import copy
import json
import unittest
from pathlib import Path

from hnd_v02.genesis import genesis_manifest_hash, validate_genesis_manifest
from hnd_v02.transaction import ProtocolConfig


class TestV02GenesisManifest(unittest.TestCase):
    def setUp(self):
        vector_path = Path(__file__).resolve().parents[1] / "vectors" / "v0.2-genesis-devnet-example.json"
        self.vector = json.loads(vector_path.read_text(encoding="utf-8"))
        self.manifest = self.vector["manifest"]
        self.expected_hash = self.vector["genesis_hash_sha256"]
        self.config = ProtocolConfig("hnd-devnet-alpha", 2, 1_000_000)

    def validate(self, manifest=None, **overrides):
        args = dict(config=self.config, expected_genesis_hash=self.expected_hash)
        args.update(overrides)
        return validate_genesis_manifest(
            copy.deepcopy(self.manifest if manifest is None else manifest), **args
        )

    def test_published_genesis_fixture_validates(self):
        self.assertEqual(self.validate(), (True, "ok"))
        self.assertEqual(genesis_manifest_hash(self.manifest), self.expected_hash)

    def test_changed_allocation_fails_against_pinned_hash(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["allocations"][0]["amount"] -= 1
        manifest["allocations"][1]["amount"] += 1
        self.assertEqual(self.validate(manifest)[1], "genesis-hash-mismatch")

    def test_allocation_total_must_equal_declared_supply(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["allocations"][0]["amount"] -= 1
        self.assertEqual(self.validate(manifest)[1], "allocation-sum")

    def test_boolean_and_float_supply_rejected(self):
        for value in (True, 1.0, "1000000", 0, -1):
            with self.subTest(value=value):
                manifest = copy.deepcopy(self.manifest)
                manifest["total_supply"] = value
                self.assertEqual(self.validate(manifest)[1], "total-supply-type-or-range")

    def test_boolean_and_float_allocation_amount_rejected(self):
        for value in (True, 1.0, "1", 0, -1):
            with self.subTest(value=value):
                manifest = copy.deepcopy(self.manifest)
                manifest["allocations"][0]["amount"] = value
                self.assertEqual(self.validate(manifest)[1], "allocation-amount")

    def test_duplicate_or_unsorted_account_ids_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["allocations"][1]["account_id"] = manifest["allocations"][0]["account_id"]
        self.assertEqual(self.validate(manifest)[1], "allocation-order-or-duplicate")
        manifest = copy.deepcopy(self.manifest)
        manifest["allocations"].reverse()
        self.assertEqual(self.validate(manifest)[1], "allocation-order-or-duplicate")

    def test_account_ids_must_match_network_and_version(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["allocations"][0]["account_id"] = "hnd3:hnd-devnet-alpha:" + "a" * 64
        self.assertEqual(self.validate(manifest)[1], "allocation-account-id")

    def test_allocation_public_key_must_derive_the_declared_account_id(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["allocations"][0]["public_key"] = manifest["allocations"][1]["public_key"]
        self.assertEqual(self.validate(manifest)[1], "allocation-key-mismatch")
        manifest = copy.deepcopy(self.manifest)
        manifest["allocations"][0]["public_key"] = "not-a-key"
        self.assertEqual(self.validate(manifest)[1], "allocation-public-key")

    def test_manifest_must_match_configured_network_and_version(self):
        self.assertEqual(
            self.validate(config=ProtocolConfig("hnd-devnet-beta", 2, 1_000_000))[1],
            "network-id",
        )
        self.assertEqual(
            self.validate(config=ProtocolConfig("hnd-devnet-alpha", 3, 1_000_000))[1],
            "protocol-version",
        )

    def test_empty_and_malformed_allocations_rejected(self):
        for value in ([], None, "allocations"):
            with self.subTest(value=value):
                manifest = copy.deepcopy(self.manifest)
                manifest["allocations"] = value
                self.assertEqual(self.validate(manifest)[1], "allocations")
        manifest = copy.deepcopy(self.manifest)
        manifest["allocations"][0]["extra"] = 1
        self.assertEqual(self.validate(manifest)[1], "allocation-schema")

    def test_wrong_pinned_hash_rejected(self):
        self.assertEqual(self.validate(expected_genesis_hash="0" * 64)[1], "genesis-hash-mismatch")
        self.assertEqual(self.validate(expected_genesis_hash="bad")[1], "expected-genesis-hash")

    def test_unknown_or_missing_manifest_fields_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["mint"] = 1
        self.assertEqual(self.validate(manifest), (False, "schema"))
        manifest = copy.deepcopy(self.manifest)
        del manifest["network_id"]
        self.assertEqual(self.validate(manifest), (False, "schema"))

    def test_manifest_version_must_be_exact_integer_one(self):
        for value in (True, 1.0, "1", 2):
            with self.subTest(value=value):
                manifest = copy.deepcopy(self.manifest)
                manifest["manifest_version"] = value
                self.assertEqual(self.validate(manifest)[1], "manifest-version")


if __name__ == "__main__":
    unittest.main(verbosity=2)
