"""Synthetic tests for VSP payload schema, signatures and Genesis binding."""
import base64, copy, json, unittest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hnd_v02.vsp_canonical import VSPInputError, governance_signature_message, profile_digest
from hnd_v02.vsp_verify import cometbft_ed25519_address, governance_key_id, verify_vsp_envelope

def b64(x): return base64.b64encode(x).decode("ascii")

class VSPVerifierTests(unittest.TestCase):
    def setUp(self):
        self.gpriv=[Ed25519PrivateKey.generate() for _ in range(3)]
        self.gpub=[k.public_key().public_bytes_raw() for k in self.gpriv]
        self.trust={governance_key_id(k):k for k in self.gpub}
        self.ids=sorted(self.trust)
        self.vpriv=[Ed25519PrivateKey.generate() for _ in range(2)]
        self.vpub=[k.public_key().public_bytes_raw() for k in self.vpriv]
        self.validators=[{"consensus_key_type":"ed25519","consensus_pubkey":b64(p),"consensus_address":cometbft_ed25519_address(p).hex(),"voting_power":10,"operator_id":f"operator-{i+1}","operator_attestation_ref":f"evidence:operator-{i+1}"} for i,p in enumerate(self.vpub)]
        self.validators.sort(key=lambda x:bytes.fromhex(x["consensus_address"]))
        self.genesis=[{"address":v["consensus_address"].upper(),"pub_key":{"type":"tendermint/PubKeyEd25519","value":v["consensus_pubkey"]},"power":str(v["voting_power"])} for v in self.validators]
        self.ctx={"chain_id":"hnd-testnet-1","hnd_genesis_sha256":"1"*64,"cometbft_version":"v0.40.0","cometbft_source_commit":"2"*40,"cometbft_binary_sha256":"3"*64,"cometbft_genesis_sha256":"4"*64,"cometbft_profile_sha256":"5"*64,"cometbft_genesis_validators":self.genesis}
        self.payload={"schema":"hnd.validator-set-profile","schema_version":1,"chain_id":self.ctx["chain_id"],"hnd_genesis_sha256":self.ctx["hnd_genesis_sha256"],"cometbft":{"version":self.ctx["cometbft_version"],"source_commit":self.ctx["cometbft_source_commit"],"binary_sha256":self.ctx["cometbft_binary_sha256"],"genesis_sha256":self.ctx["cometbft_genesis_sha256"],"profile_sha256":self.ctx["cometbft_profile_sha256"]},"profile_sequence":1,"previous_profile_sha256":None,"activation":{"kind":"genesis","height":0},"validators":copy.deepcopy(self.validators),"total_voting_power":20,"governance_policy":{"policy_id":"hnd-vsp-2-of-3-v1","authorized_key_ids":self.ids,"threshold":2},"change":{"type":"initial","reason":"test fixture","change_reference":"test:initial"}}
    def signed(self,payload=None,signers=(0,1)):
        p=copy.deepcopy(payload if payload is not None else self.payload)
        msg=governance_signature_message(profile_digest(p))
        sigs=[]
        for i in signers:
            pub=self.gpub[i]; sigs.append({"key_id":governance_key_id(pub),"algorithm":"ed25519","signature":b64(self.gpriv[i].sign(msg))})
        sigs.sort(key=lambda x:x["key_id"])
        return rfc8785.dumps({"payload":p,"signatures":sigs})
    def verify(self,raw=None,context=None,trust=None):
        return verify_vsp_envelope(raw or self.signed(),context=context or self.ctx,governance_public_keys=trust or self.trust)
    def test_valid_two_of_three_signatures_and_exact_genesis_roster(self):
        out=self.verify()
        self.assertEqual((out["profile_sequence"],out["validator_count"],out["total_voting_power"]),(1,2,20))
    def test_rejects_tampered_payload(self):
        envelope=json.loads(self.signed())
        envelope["payload"]["change"]["reason"]="tampered"
        with self.assertRaisesRegex(VSPInputError,"VSP-E-GOVERNANCE-SIGNATURE"): self.verify(rfc8785.dumps(envelope))
    def test_rejects_wrong_trust_key_id(self):
        wrong=dict(self.trust); wrong[next(iter(wrong))]=bytes(32)
        with self.assertRaisesRegex(VSPInputError,"VSP-E-TRUST-MANIFEST-KEY-ID"): self.verify(trust=wrong)
    def test_rejects_genesis_roster_mismatch(self):
        c=dict(self.ctx); c["cometbft_genesis_validators"]=self.genesis[:1]
        with self.assertRaisesRegex(VSPInputError,"VSP-E-GENESIS-ROSTER-MISMATCH"): self.verify(context=c)
    def test_rejects_address_mismatch_and_unknown_fields(self):
        p=copy.deepcopy(self.payload); p["validators"][0]["consensus_address"]="0"*40
        with self.assertRaisesRegex(VSPInputError,"VSP-E-CONSENSUS-ADDRESS-DERIVATION"): self.verify(self.signed(p))
        p=copy.deepcopy(self.payload); p["extra"]=True
        with self.assertRaisesRegex(VSPInputError,"VSP-E-PAYLOAD-SCHEMA"): self.verify(self.signed(p))
    def test_rejects_stale_sequence_and_predecessor(self):
        c=dict(self.ctx); c["active_profile"]={"sequence":4,"digest":"6"*64,"current_height":100}
        p=copy.deepcopy(self.payload); p.update(profile_sequence=6,previous_profile_sha256="6"*64,activation={"kind":"height","height":110}); p["change"]["type"]="add"
        with self.assertRaisesRegex(VSPInputError,"VSP-E-PROFILE-SEQUENCE-ROLLBACK"): self.verify(self.signed(p),context=c)
        p["profile_sequence"]=5; p["previous_profile_sha256"]="7"*64
        with self.assertRaisesRegex(VSPInputError,"VSP-E-PROFILE-PREDECESSOR"): self.verify(self.signed(p),context=c)

if __name__=="__main__": unittest.main()
