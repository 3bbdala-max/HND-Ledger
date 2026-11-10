import base64, unittest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hnd_v02.trust_manifest import (
    governance_pop_message, trust_manifest_digest, witness_message,
    verify_vsp_with_trust_manifest,
)
from hnd_v02.vsp_verify import governance_key_id
import tests.test_vsp_payload_verifier as vsp_fixture_module

def b64(value): return base64.b64encode(value).decode("ascii")

class TrustManifestVSPIntegrationTests(unittest.TestCase):
    def test_manifest_keys_are_the_only_keys_used_for_vsp_authorization(self):
        vsp = vsp_fixture_module.VSPVerifierTests()
        vsp.setUp()
        nonce = b64(bytes(range(32)))
        keys = []
        for i, private in enumerate(vsp.gpriv):
            pub = vsp.gpub[i]
            kid = governance_key_id(pub)
            role = f"custodian-{i+1}"
            pop = private.sign(governance_pop_message(
                chain_id=vsp.ctx["chain_id"],
                hnd_genesis_sha256=vsp.ctx["hnd_genesis_sha256"],
                cometbft_genesis_sha256=vsp.ctx["cometbft_genesis_sha256"],
                nonce=nonce, key_id=kid, public_key=b64(pub), role_id=role))
            keys.append({"key_id":kid,"algorithm":"ed25519","public_key":b64(pub),
                "role_id":role,"proof_of_possession":b64(pop)})
        keys.sort(key=lambda item:item["key_id"])
        manifest = {
            "schema":"hnd.vsp-trust-manifest","schema_version":1,
            "chain_id":vsp.ctx["chain_id"],
            "hnd_genesis_sha256":vsp.ctx["hnd_genesis_sha256"],
            "cometbft_genesis_sha256":vsp.ctx["cometbft_genesis_sha256"],
            "cometbft_source_commit":vsp.ctx["cometbft_source_commit"],
            "vsp_schema_version":1,"sequence":0,"previous_manifest_sha256":None,
            "nonce":nonce,"governance_threshold":2,"governance_keys":keys,"witnesses":[],
        }
        witnesses = [Ed25519PrivateKey.generate() for _ in range(2)]
        witness_keys = {f"witness-{i+1}":key.public_key().public_bytes_raw()
                        for i,key in enumerate(witnesses)}
        digest = trust_manifest_digest(manifest)
        manifest["witnesses"] = [
            {"witness_id":f"witness-{i+1}","signature":b64(key.sign(witness_message(digest)))}
            for i,key in enumerate(witnesses)
        ]
        result = verify_vsp_with_trust_manifest(
            vsp.signed(), rfc8785.dumps(manifest), context=vsp.ctx,
            trusted_witness_keys=witness_keys)
        self.assertEqual(result["vsp"]["profile_sequence"], 1)
        self.assertEqual(result["trust_manifest"]["threshold"], 2)
        self.assertEqual(result["vsp"]["verified_signer_key_ids"], sorted(governance_key_id(vsp.gpub[i]) for i in (0, 1)))

if __name__ == "__main__":
    unittest.main()
