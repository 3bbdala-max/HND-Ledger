import base64, unittest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import tests.test_vsp_payload_verifier as vsp_fixture_module
from hnd_v02.activation_bundle import verify_activation_bundle
from hnd_v02.operator_ack import acknowledgement_message
from hnd_v02.trust_manifest import governance_pop_message, trust_manifest_digest, witness_message
from hnd_v02.vsp_canonical import profile_digest
from hnd_v02.vsp_verify import governance_key_id

def b64(value): return base64.b64encode(value).decode("ascii")

class ActivationBundleTests(unittest.TestCase):
    def setUp(self):
        self.vsp = vsp_fixture_module.VSPVerifierTests()
        self.vsp.setUp()
        nonce = b64(bytes(range(32)))
        keys = []
        for i, private in enumerate(self.vsp.gpriv):
            pub = self.vsp.gpub[i]
            kid = governance_key_id(pub)
            role = f"custodian-{i+1}"
            pop = private.sign(governance_pop_message(
                chain_id=self.vsp.ctx["chain_id"],
                hnd_genesis_sha256=self.vsp.ctx["hnd_genesis_sha256"],
                cometbft_genesis_sha256=self.vsp.ctx["cometbft_genesis_sha256"],
                nonce=nonce, key_id=kid, public_key=b64(pub), role_id=role))
            keys.append({"key_id":kid,"algorithm":"ed25519","public_key":b64(pub),
                "role_id":role,"proof_of_possession":b64(pop)})
        keys.sort(key=lambda item:item["key_id"])
        self.manifest = {
            "schema":"hnd.vsp-trust-manifest","schema_version":1,
            "chain_id":self.vsp.ctx["chain_id"],
            "hnd_genesis_sha256":self.vsp.ctx["hnd_genesis_sha256"],
            "cometbft_genesis_sha256":self.vsp.ctx["cometbft_genesis_sha256"],
            "cometbft_source_commit":self.vsp.ctx["cometbft_source_commit"],
            "vsp_schema_version":1,"sequence":0,"previous_manifest_sha256":None,
            "nonce":nonce,"governance_threshold":2,"governance_keys":keys,"witnesses":[],
        }
        self.witnesses = [Ed25519PrivateKey.generate() for _ in range(2)]
        self.witness_keys = {f"witness-{i+1}":key.public_key().public_bytes_raw()
                             for i,key in enumerate(self.witnesses)}
        digest = trust_manifest_digest(self.manifest)
        self.manifest["witnesses"] = [
            {"witness_id":f"witness-{i+1}","signature":b64(key.sign(witness_message(digest)))}
            for i,key in enumerate(self.witnesses)]
        self.manifest_raw = rfc8785.dumps(self.manifest)
        self.vsp_raw = self.vsp.signed()
        self.operators = {f"operator-{i+1}":Ed25519PrivateKey.generate() for i in range(2)}
        self.operator_public = {name:key.public_key().public_bytes_raw()
                                for name,key in self.operators.items()}
        digest = profile_digest(self.vsp.payload).hex()
        self.acks = []
        for name,key in self.operators.items():
            nonce = (name + "_activation_nonce_0001")
            msg = acknowledgement_message(chain_id=self.vsp.ctx["chain_id"],
                profile_sha256=digest,activation_height=0,operator_id=name,nonce=nonce)
            self.acks.append({"schema":"hnd.operator-ack","schema_version":1,
                "chain_id":self.vsp.ctx["chain_id"],"profile_sha256":digest,
                "activation_height":0,"operator_id":name,"nonce":nonce,
                "signature":b64(key.sign(msg))})
        self.acks.sort(key=lambda item:item["operator_id"])
        self.acks_raw = rfc8785.dumps(self.acks)

    def verify(self, acks=None):
        return verify_activation_bundle(self.vsp_raw,self.manifest_raw,
            acks if acks is not None else self.acks_raw,context=self.vsp.ctx,
            trusted_witness_keys=self.witness_keys,
            expected_operator_keys=self.operator_public)

    def test_complete_offline_activation_bundle(self):
        result = self.verify()
        self.assertTrue(result["preflight_accepted"])
        self.assertTrue(result["unanimous_operator_approval"])
        self.assertEqual(result["operator_count"],2)

    def test_missing_operator_ack_blocks_preflight(self):
        with self.assertRaisesRegex(Exception,"ACK-E-UNANIMOUS-SET"):
            self.verify(rfc8785.dumps(self.acks[:1]))

if __name__ == "__main__":
    unittest.main()
