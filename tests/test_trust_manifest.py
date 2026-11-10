import base64, copy, unittest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hnd_v02.trust_manifest import (
    TrustManifestError, governance_pop_message, parse_trust_manifest,
    trust_manifest_digest, witness_message,
)
from hnd_v02.vsp_verify import governance_key_id

def b64(value):
    return base64.b64encode(value).decode("ascii")

class TrustManifestTests(unittest.TestCase):
    def setUp(self):
        self.gov = [Ed25519PrivateKey.generate() for _ in range(3)]
        self.witness = [Ed25519PrivateKey.generate() for _ in range(2)]
        self.witness_keys = {f"witness-{i+1}": key.public_key().public_bytes_raw()
                             for i, key in enumerate(self.witness)}
        self.context = {
            "chain_id": "hnd-testnet-1",
            "hnd_genesis_sha256": "1" * 64,
            "cometbft_genesis_sha256": "2" * 64,
            "cometbft_source_commit": "3" * 40,
        }
        nonce = b64(bytes(range(32)))
        keys = []
        for i, private in enumerate(self.gov):
            pub = private.public_key().public_bytes_raw()
            kid = governance_key_id(pub)
            role = f"custodian-{i+1}"
            proof = private.sign(governance_pop_message(
                chain_id=self.context["chain_id"],
                hnd_genesis_sha256=self.context["hnd_genesis_sha256"],
                cometbft_genesis_sha256=self.context["cometbft_genesis_sha256"],
                nonce=nonce, key_id=kid, public_key=b64(pub), role_id=role))
            keys.append({"key_id": kid, "algorithm": "ed25519",
                         "public_key": b64(pub), "role_id": role,
                         "proof_of_possession": b64(proof)})
        keys.sort(key=lambda item: item["key_id"])
        self.manifest = {
            "schema": "hnd.vsp-trust-manifest", "schema_version": 1,
            **self.context, "vsp_schema_version": 1, "sequence": 0,
            "previous_manifest_sha256": None, "nonce": nonce,
            "governance_threshold": 2, "governance_keys": keys, "witnesses": [],
        }
        digest = trust_manifest_digest(self.manifest)
        self.manifest["witnesses"] = [
            {"witness_id": f"witness-{i+1}",
             "signature": b64(key.sign(witness_message(digest)))}
            for i, key in enumerate(self.witness)
        ]
        self.raw = rfc8785.dumps(self.manifest)

    def parse(self, raw=None, context=None, witness_keys=None):
        return parse_trust_manifest(raw if raw is not None else self.raw,
            expected_context=context if context is not None else self.context,
            trusted_witness_keys=witness_keys if witness_keys is not None else self.witness_keys)

    def test_valid_witnessed_bootstrap_manifest(self):
        result = self.parse()
        self.assertEqual(result["sequence"], 0)
        self.assertEqual(result["threshold"], 2)
        self.assertEqual(len(result["governance_key_ids"]), 3)
        self.assertEqual(len(result["witness_ids"]), 2)

    def test_rejects_wrong_external_network_context(self):
        context = dict(self.context, chain_id="other-chain")
        with self.assertRaisesRegex(TrustManifestError, "TM-E-EXPECTED-CONTEXT"):
            self.parse(context=context)

    def test_rejects_untrusted_witness(self):
        with self.assertRaisesRegex(TrustManifestError, "TM-E-UNTRUSTED-WITNESS"):
            self.parse(witness_keys={"witness-1": self.witness_keys["witness-1"]})

    def test_rejects_tampered_witness_signature(self):
        changed = copy.deepcopy(self.manifest)
        changed["witnesses"][0]["signature"] = b64(bytes(64))
        with self.assertRaisesRegex(TrustManifestError, "TM-E-WITNESS-SIGNATURE"):
            self.parse(rfc8785.dumps(changed))

    def test_rejects_tampered_governance_proof_of_possession(self):
        changed = copy.deepcopy(self.manifest)
        changed["governance_keys"][0]["proof_of_possession"] = b64(bytes(64))
        digest = trust_manifest_digest(changed)
        changed["witnesses"] = [
            {"witness_id": f"witness-{i+1}", "signature": b64(key.sign(witness_message(digest)))}
            for i, key in enumerate(self.witness)
        ]
        with self.assertRaisesRegex(TrustManifestError, "TM-E-GOVERNANCE-POP"):
            self.parse(rfc8785.dumps(changed))

    def test_rejects_duplicate_governance_identity(self):
        changed = copy.deepcopy(self.manifest)
        changed["governance_keys"][1] = copy.deepcopy(changed["governance_keys"][0])
        digest = trust_manifest_digest(changed)
        changed["witnesses"] = [
            {"witness_id": f"witness-{i+1}", "signature": b64(key.sign(witness_message(digest)))}
            for i, key in enumerate(self.witness)
        ]
        with self.assertRaisesRegex(TrustManifestError, "TM-E-GOVERNANCE-DUPLICATE"):
            self.parse(rfc8785.dumps(changed))

    def test_rejects_wrong_sequence_and_threshold(self):
        for field, value, error in (
            ("sequence", 1, "TM-E-INITIAL-SEQUENCE"),
            ("governance_threshold", 1, "TM-E-THRESHOLD"),
        ):
            changed = copy.deepcopy(self.manifest)
            changed[field] = value
            digest = trust_manifest_digest(changed)
            changed["witnesses"] = [
                {"witness_id": f"witness-{i+1}", "signature": b64(key.sign(witness_message(digest)))}
                for i, key in enumerate(self.witness)
            ]
            with self.subTest(field=field), self.assertRaisesRegex(TrustManifestError, error):
                self.parse(rfc8785.dumps(changed))

    def test_rejects_noncanonical_duplicate_and_bom(self):
        with self.assertRaisesRegex(TrustManifestError, "TM-E-NONCANONICAL"):
            self.parse(self.raw + b" ")
        with self.assertRaises(TrustManifestError):
            self.parse(b"\xef\xbb\xbf" + self.raw)
        with self.assertRaises(TrustManifestError):
            self.parse(b'{"schema":"a","schema":"b"}')

if __name__ == "__main__":
    unittest.main()
