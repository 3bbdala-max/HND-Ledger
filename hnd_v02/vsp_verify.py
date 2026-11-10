"""Pure VSP v1 payload, signature and CometBFT Genesis verifier."""
from __future__ import annotations
import base64, hashlib, re
from typing import Any, Mapping
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from hnd_v02.vsp_canonical import VSPInputError, governance_signature_message, parse_vsp_envelope, profile_digest

HEX64=re.compile(r"^[0-9a-f]{64}$",re.ASCII)
HEX40=re.compile(r"^[0-9a-f]{40}$",re.ASCII)
CHAIN=re.compile(r"^[A-Za-z0-9._-]{1,50}$",re.ASCII)
IDENT=re.compile(r"^[A-Za-z0-9._:-]{1,128}$",re.ASCII)
REF=re.compile(r"^[A-Za-z0-9._:/-]{1,128}$",re.ASCII)
MAX_SAFE=(2**53)-1
PAYLOAD={"schema","schema_version","chain_id","hnd_genesis_sha256","cometbft","profile_sequence","previous_profile_sha256","activation","validators","total_voting_power","governance_policy","change"}
COMET={"version","source_commit","binary_sha256","genesis_sha256","profile_sha256"}
VALIDATOR={"consensus_key_type","consensus_pubkey","consensus_address","voting_power","operator_id","operator_attestation_ref"}

def fail(code): raise VSPInputError(code)
def exact(obj, fields, code):
    if type(obj) is not dict or set(obj)!=fields: fail(code)
    return obj
def uint(value, minimum=0, code="VSP-E-INTEGER"):
    if type(value) is not int or not minimum<=value<=MAX_SAFE: fail(code)
    return value
def hexstr(value, pattern, code):
    if type(value) is not str or not pattern.fullmatch(value): fail(code)
    return value
def decode64(value, length, code):
    if type(value) is not str: fail(code)
    try: raw=base64.b64decode(value,validate=True)
    except (ValueError,base64.binascii.Error) as exc: raise VSPInputError(code) from exc
    if len(raw)!=length or base64.b64encode(raw).decode("ascii")!=value: fail(code)
    return raw
def governance_key_id(public_key: bytes)->str:
    if type(public_key) is not bytes or len(public_key)!=32: fail("VSP-E-GOVERNANCE-PUBLIC-KEY")
    return "gk1-"+hashlib.sha256(b"HND-GOV-KEY-v1\x00"+public_key).hexdigest()
def cometbft_ed25519_address(public_key: bytes)->bytes:
    if type(public_key) is not bytes or len(public_key)!=32: fail("VSP-E-CONSENSUS-PUBLIC-KEY")
    return hashlib.sha256(public_key).digest()[:20]

def validate_roster(payload, genesis_validators):
    vals=payload["validators"]
    if type(vals) is not list or not vals or len(vals)>10000: fail("VSP-E-VALIDATOR-COUNT")
    if type(genesis_validators) is not list or not genesis_validators: fail("VSP-E-GENESIS-VALIDATOR-CONTEXT")
    seen_keys=set(); seen_addresses=set(); seen_ops=set(); ordered=[]; roster=set(); total=0
    for v in vals:
        exact(v,VALIDATOR,"VSP-E-VALIDATOR-SCHEMA")
        if v["consensus_key_type"]!="ed25519": fail("VSP-E-CONSENSUS-KEY-TYPE")
        pub=decode64(v["consensus_pubkey"],32,"VSP-E-CONSENSUS-PUBLIC-KEY")
        address=bytes.fromhex(hexstr(v["consensus_address"],HEX40,"VSP-E-CONSENSUS-ADDRESS"))
        if cometbft_ed25519_address(pub)!=address: fail("VSP-E-CONSENSUS-ADDRESS-DERIVATION")
        power=uint(v["voting_power"],1,"VSP-E-VOTING-POWER")
        op=v["operator_id"]
        if type(op) is not str or not IDENT.fullmatch(op): fail("VSP-E-OPERATOR-ID")
        ref=v["operator_attestation_ref"]
        if type(ref) is not str or not ref or len(ref)>256: fail("VSP-E-OPERATOR-ATTESTATION-REF")
        if pub in seen_keys or address in seen_addresses or op in seen_ops: fail("VSP-E-DUPLICATE-VALIDATOR-IDENTITY")
        seen_keys.add(pub); seen_addresses.add(address); seen_ops.add(op); ordered.append(address)
        total+=power
        if total>MAX_SAFE: fail("VSP-E-TOTAL-VOTING-POWER")
        roster.add((pub,address,power))
    if ordered!=sorted(ordered): fail("VSP-E-VALIDATOR-ORDER")
    if uint(payload["total_voting_power"],1,"VSP-E-TOTAL-VOTING-POWER")!=total: fail("VSP-E-TOTAL-VOTING-POWER-MISMATCH")
    upstream=set()
    for item in genesis_validators:
        if type(item) is not dict: fail("VSP-E-GENESIS-VALIDATOR-SCHEMA")
        key=item.get("pub_key")
        if type(key) is not dict or key.get("type")!="tendermint/PubKeyEd25519": fail("VSP-E-GENESIS-VALIDATOR-KEY-TYPE")
        pub=decode64(key.get("value"),32,"VSP-E-GENESIS-VALIDATOR-KEY")
        try:
            address=bytes.fromhex(item.get("address",""))
            power_text=item.get("power")
            if type(power_text) is not str or not re.fullmatch(r"[1-9][0-9]*",power_text): fail("VSP-E-GENESIS-VALIDATOR-POWER")
            power=int(power_text)
        except (TypeError,ValueError) as exc: raise VSPInputError("VSP-E-GENESIS-VALIDATOR-SCHEMA") from exc
        if len(address)!=20 or cometbft_ed25519_address(pub)!=address: fail("VSP-E-GENESIS-VALIDATOR-ADDRESS")
        if power>MAX_SAFE: fail("VSP-E-GENESIS-VALIDATOR-POWER")
        upstream.add((pub,address,power))
    if len(upstream)!=len(genesis_validators) or upstream!=roster: fail("VSP-E-GENESIS-ROSTER-MISMATCH")

def validate_payload(payload, context):
    exact(payload,PAYLOAD,"VSP-E-PAYLOAD-SCHEMA")
    if payload["schema"]!="hnd.validator-set-profile" or type(payload["schema_version"]) is not int or payload["schema_version"]!=1: fail("VSP-E-SCHEMA-VERSION")
    chain=payload["chain_id"]
    if type(chain) is not str or not CHAIN.fullmatch(chain) or chain!=context["chain_id"]: fail("VSP-E-CHAIN-ID")
    if hexstr(payload["hnd_genesis_sha256"],HEX64,"VSP-E-HND-GENESIS-DIGEST")!=context["hnd_genesis_sha256"]: fail("VSP-E-HND-GENESIS-MISMATCH")
    c=exact(payload["cometbft"],COMET,"VSP-E-COMETBFT-SCHEMA")
    if c["version"]!=context["cometbft_version"]: fail("VSP-E-COMETBFT-VERSION")
    if context["cometbft_genesis_chain_id"]!=chain: fail("VSP-E-COMETBFT-GENESIS-CHAIN-ID")
    if hexstr(c["source_commit"],re.compile(r"^[0-9a-f]{40}$"),"VSP-E-COMETBFT-SOURCE")!=context["cometbft_source_commit"]: fail("VSP-E-COMETBFT-SOURCE-MISMATCH")
    for field,ctx,code in [("binary_sha256","cometbft_binary_sha256","VSP-E-COMETBFT-BINARY-MISMATCH"),("genesis_sha256","cometbft_genesis_sha256","VSP-E-COMETBFT-GENESIS-MISMATCH"),("profile_sha256","cometbft_profile_sha256","VSP-E-COMETBFT-PROFILE-MISMATCH")]:
        if hexstr(c[field],HEX64,code)!=context[ctx]: fail(code)
    seq=uint(payload["profile_sequence"],1,"VSP-E-PROFILE-SEQUENCE")
    activation=exact(payload["activation"],{"kind","height"},"VSP-E-ACTIVATION-SCHEMA")
    height=uint(activation["height"],0,"VSP-E-ACTIVATION-HEIGHT")
    change=exact(payload["change"],{"type","reason","change_reference"},"VSP-E-CHANGE-SCHEMA")
    active=context.get("active_profile")
    if active is None:
        if seq!=1 or payload["previous_profile_sha256"] is not None or activation!={"kind":"genesis","height":0}: fail("VSP-E-INITIAL-PROFILE-TRANSITION")
        if change["type"]!="initial": fail("VSP-E-INITIAL-CHANGE-TYPE")
    else:
        if type(active) is not dict or set(active)!={"sequence","digest","current_height"}: fail("VSP-E-ACTIVE-PROFILE-CONTEXT")
        if type(active["sequence"]) is not int or type(active["current_height"]) is not int or active["sequence"]<1 or active["current_height"]<0: fail("VSP-E-ACTIVE-PROFILE-CONTEXT")
        if seq!=active["sequence"]+1: fail("VSP-E-PROFILE-SEQUENCE-ROLLBACK")
        if payload["previous_profile_sha256"]!=active["digest"]: fail("VSP-E-PROFILE-PREDECESSOR")
        hexstr(payload["previous_profile_sha256"],HEX64,"VSP-E-PROFILE-PREDECESSOR")
        if activation["kind"]!="height" or height<=active["current_height"] or change["type"]=="initial": fail("VSP-E-ACTIVATION-HEIGHT")
    if activation["kind"] not in ("genesis","height"): fail("VSP-E-ACTIVATION-KIND")
    gov=exact(payload["governance_policy"],{"policy_id","authorized_key_ids","threshold"},"VSP-E-GOVERNANCE-POLICY")
    ids=gov["authorized_key_ids"]
    if gov["policy_id"]!="hnd-vsp-2-of-3-v1" or type(gov["threshold"]) is not int or gov["threshold"]!=2: fail("VSP-E-GOVERNANCE-POLICY")
    if type(ids) is not list or len(ids)!=3 or any(type(x) is not str for x in ids) or ids!=sorted(set(ids)): fail("VSP-E-GOVERNANCE-KEY-IDS")
    if any(not re.fullmatch(r"gk1-[0-9a-f]{64}",x,re.ASCII) for x in ids): fail("VSP-E-GOVERNANCE-KEY-ID-FORMAT")
    if type(change["type"]) is not str or change["type"] not in {"initial","add","remove","power_change","key_rotation","recovery"}: fail("VSP-E-CHANGE-TYPE")
    if type(change["reason"]) is not str or not change["reason"] or len(change["reason"])>512: fail("VSP-E-CHANGE-REASON")
    if type(change["change_reference"]) is not str or not REF.fullmatch(change["change_reference"]): fail("VSP-E-CHANGE-REFERENCE")
    validate_roster(payload,context["cometbft_genesis_validators"])

def verify_vsp_envelope(raw: bytes, *, context: Mapping[str,Any], governance_public_keys: Mapping[str,bytes])->dict:
    required={"chain_id","hnd_genesis_sha256","cometbft_version","cometbft_source_commit","cometbft_binary_sha256","cometbft_genesis_sha256","cometbft_genesis_chain_id","cometbft_profile_sha256","cometbft_genesis_validators"}
    if type(context) is not dict or not required.issubset(context): fail("VSP-E-EXPECTED-CONTEXT")
    envelope=parse_vsp_envelope(raw)
    payload=envelope["payload"]
    validate_payload(payload,context)
    if type(governance_public_keys) is not dict or len(governance_public_keys)!=3: fail("VSP-E-TRUST-MANIFEST-KEY-SET")
    keys={}
    for kid,pub in governance_public_keys.items():
        if governance_key_id(pub)!=kid: fail("VSP-E-TRUST-MANIFEST-KEY-ID")
        keys[kid]=pub
    if sorted(keys)!=payload["governance_policy"]["authorized_key_ids"]: fail("VSP-E-TRUST-MANIFEST-MISMATCH")
    msg=governance_signature_message(profile_digest(payload))
    valid=[]
    for record in envelope["signatures"]:
        pub=keys.get(record["key_id"])
        if pub is None: fail("VSP-E-UNKNOWN-GOVERNANCE-KEY")
        sig=base64.b64decode(record["signature"],validate=True)
        try: Ed25519PublicKey.from_public_bytes(pub).verify(sig,msg)
        except (InvalidSignature,ValueError) as exc: raise VSPInputError("VSP-E-GOVERNANCE-SIGNATURE") from exc
        valid.append(record["key_id"])
    if len(set(valid))<2: fail("VSP-E-GOVERNANCE-THRESHOLD")
    return {"profile_digest":profile_digest(payload).hex(),"profile_sequence":payload["profile_sequence"],"activation_height":payload["activation"]["height"],"validator_count":len(payload["validators"]),"total_voting_power":payload["total_voting_power"],"verified_signer_key_ids":sorted(valid)}
