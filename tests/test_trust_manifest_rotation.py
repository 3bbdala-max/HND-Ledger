import base64
import unittest

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.trust_manifest import (
    governance_pop_message, parse_trust_manifest, trust_manifest_digest, witness_message,
)
from hnd_v02.trust_manifest_rotation import (
    ROTATION_AUTH_DOMAIN, ROTATION_DOMAIN, verify_trust_manifest_chain,
)
from hnd_v02.vsp_verify import governance_key_id


def b64(value):
    return base64.b64encode(value).decode("ascii")


def public(private):
    return private.public_key().public_bytes_raw()


class TrustManifestRotationTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "chain_id": "hnd-rotation-test-1",
            "hnd_genesis_sha256": "1" * 64,
            "cometbft_genesis_sha256": "2" * 64,
            "cometbft_source_commit": "3" * 40,
        }
        self.witness_private = [Ed25519PrivateKey.generate() for _ in range(2)]
        self.witness_keys = {
            f"witness-{i+1}": public(key)
            for i, key in enumerate(self.witness_private)
        }
        self.old_private = [Ed25519PrivateKey.generate() for _ in range(3)]
        self.bootstrap = self._make_bootstrap(self.old_private)
        self.bootstrap_result = parse_trust_manifest(
            self.bootstrap, expected_context=self.context,
            trusted_witness_keys=self.witness_keys,
        )

    def _governance_entries(self, private_keys, nonce):
        entries = []
        for i, private in enumerate(private_keys):
            pub = public(private)
            key_id = governance_key_id(pub)
            role = f"custodian-{i+1}"
            proof = private.sign(governance_pop_message(
                chain_id=self.context["chain_id"],
                hnd_genesis_sha256=self.context["hnd_genesis_sha256"],
                cometbft_genesis_sha256=self.context["cometbft_genesis_sha256"],
                nonce=nonce, key_id=key_id, public_key=b64(pub), role_id=role,
            ))
            entries.append({
                "key_id": key_id, "algorithm": "ed25519",
                "public_key": b64(pub), "role_id": role,
                "proof_of_possession": b64(proof),
            })
        return sorted(entries, key=lambda item: item["key_id"])

    def _make_bootstrap(self, private_keys):
        nonce = b64(bytes(range(32)))
        manifest = {
            "schema": "hnd.vsp-trust-manifest", "schema_version": 1,
            **self.context, "vsp_schema_version": 1, "sequence": 0,
            "previous_manifest_sha256": None, "nonce": nonce,
            "governance_threshold": 2,
            "governance_keys": self._governance_entries(private_keys, nonce),
            "witnesses": [],
        }
        digest = trust_manifest_digest(manifest)
        manifest["witnesses"] = [
            {"witness_id": f"witness-{i+1}",
             "signature": b64(key.sign(witness_message(digest)))}
            for i, key in enumerate(self.witness_private)
        ]
        return rfc8785.dumps(manifest)

    def _make_rotation(self, previous_digest, old_private, new_private, sequence=1):
        nonce = b64(bytes([sequence]) * 32)
        manifest = {
            "schema": "hnd.vsp-trust-manifest-rotation", "schema_version": 1,
            **self.context, "vsp_schema_version": 1, "sequence": sequence,
            "previous_manifest_sha256": previous_digest, "nonce": nonce,
            "governance_threshold": 2,
            "governance_keys": self._governance_entries(new_private, nonce),
            "authorizations": [], "witnesses": [],
        }
        core = {k: v for k, v in manifest.items()
                if k not in {"authorizations", "witnesses"}}
        digest = __import__("hashlib").sha256(
            ROTATION_DOMAIN + rfc8785.dumps(core)
        ).digest()
        message = ROTATION_AUTH_DOMAIN + digest
        old_entries = []
        old_by_id = sorted(
            ((governance_key_id(public(key)), key) for key in old_private),
            key=lambda pair: pair[0],
        )
        for key_id, private in old_by_id[:2]:
            old_entries.append({
                "key_id": key_id, "algorithm": "ed25519",
                "signature": b64(private.sign(message)),
            })
        manifest["authorizations"] = old_entries
        manifest["witnesses"] = [
            {"witness_id": f"witness-{i+1}",
             "signature": b64(key.sign(witness_message(digest)))}
            for i, key in enumerate(self.witness_private)
        ]
        return rfc8785.dumps(manifest)

    def test_bootstrap_then_rotation_chain(self):
        new_private = [Ed25519PrivateKey.generate() for _ in range(3)]
        rotation = self._make_rotation(
            self.bootstrap_result["manifest_digest"], self.old_private, new_private
        )
        result = verify_trust_manifest_chain(
            [self.bootstrap, rotation], expected_context=self.context,
            trusted_witness_keys=self.witness_keys,
        )
        self.assertEqual(result["sequence"], 1)
        self.assertEqual(result["rotation_count"], 1)
        self.assertEqual(len(result["governance_key_ids"]), 3)

    def test_rejects_skipped_sequence(self):
        new_private = [Ed25519PrivateKey.generate() for _ in range(3)]
        rotation = self._make_rotation(
            self.bootstrap_result["manifest_digest"], self.old_private,
            new_private, sequence=2,
        )
        with self.assertRaisesRegex(ValueError, "TMR-E-SEQUENCE"):
            verify_trust_manifest_chain(
                [self.bootstrap, rotation], expected_context=self.context,
                trusted_witness_keys=self.witness_keys,
            )

    def test_rejects_wrong_predecessor_digest(self):
        new_private = [Ed25519PrivateKey.generate() for _ in range(3)]
        rotation = self._make_rotation("f" * 64, self.old_private, new_private)
        with self.assertRaisesRegex(ValueError, "TMR-E-PREVIOUS-DIGEST"):
            verify_trust_manifest_chain(
                [self.bootstrap, rotation], expected_context=self.context,
                trusted_witness_keys=self.witness_keys,
            )


if __name__ == "__main__":
    unittest.main()
