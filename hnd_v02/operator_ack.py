"""Offline unanimous validator-operator acknowledgement verifier."""
from __future__ import annotations
import base64, hashlib, json, re
from typing import Mapping
import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from hnd_v02.vsp_canonical import _validate_tree, _reject_duplicate_pairs

ACK_DOMAIN = b"HND-VSP-OPERATOR-ACK-v1\x00"
ACK_SET_DOMAIN = b"HND-VSP-OPERATOR-ACK-SET-v1\x00"
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
IDENT = re.compile(r"^[A-Za-z0-9._:-]{1,128}$", re.ASCII)
MAX_BYTES = 262144

class OperatorAckError(ValueError):
    """Fail-closed operator acknowledgement rejection."""

def _fail(code):
    raise OperatorAckError(code)

def _b64(value):
    if type(value) is not str: _fail("ACK-E-SIGNATURE")
    try: raw = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc: raise OperatorAckError("ACK-E-SIGNATURE") from exc
    if len(raw) != 64 or base64.b64encode(raw).decode("ascii") != value: _fail("ACK-E-SIGNATURE")
    return raw

def acknowledgement_message(*, chain_id, profile_sha256, activation_height, operator_id, nonce):
    body = {"schema":"hnd.operator-ack","schema_version":1,"chain_id":chain_id,
        "profile_sha256":profile_sha256,"activation_height":activation_height,
        "operator_id":operator_id,"nonce":nonce}
    return ACK_DOMAIN + rfc8785.dumps(body)

def verify_unanimous_operator_acks(raw: bytes, *, expected_chain_id: str,
        expected_profile_sha256: str, expected_activation_height: int,
        expected_operator_keys: Mapping[str, bytes]) -> dict:
    """Require exactly one valid Ed25519 acknowledgement from every operator."""
    if type(raw) is not bytes or not raw or len(raw) > MAX_BYTES: _fail("ACK-E-BYTE-LIMIT")
    if raw.startswith(b"\xef\xbb\xbf"): _fail("ACK-E-BOM")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_int=lambda token: int(token, 10),
            parse_float=lambda _token: (_ for _ in ()).throw(ValueError("float")),
            parse_constant=lambda _token: (_ for _ in ()).throw(ValueError("constant")))
    except Exception as exc:
        if isinstance(exc, OperatorAckError): raise
        raise OperatorAckError("ACK-E-JSON") from exc
    _validate_tree(value)
    if rfc8785.dumps(value) != raw: _fail("ACK-E-NONCANONICAL")
    if type(value) is not list or not value or len(value) > 10000: _fail("ACK-E-ARRAY")
    if type(expected_operator_keys) is not dict or not expected_operator_keys: _fail("ACK-E-EXPECTED-OPERATORS")
    if type(expected_activation_height) is not int or expected_activation_height < 0: _fail("ACK-E-ACTIVATION")
    if type(expected_chain_id) is not str or type(expected_profile_sha256) is not str or not HEX64.fullmatch(expected_profile_sha256): _fail("ACK-E-CONTEXT")
    expected_ids = set(expected_operator_keys)
    if any(type(k) is not str or not IDENT.fullmatch(k) or type(v) is not bytes or len(v) != 32 for k,v in expected_operator_keys.items()): _fail("ACK-E-EXPECTED-OPERATORS")
    if len(set(expected_operator_keys.values())) != len(expected_operator_keys): _fail("ACK-E-EXPECTED-KEY-DUPLICATE")
    ids = [item.get("operator_id") for item in value if type(item) is dict]
    if len(ids) != len(value) or ids != sorted(ids): _fail("ACK-E-ORDER")
    if set(ids) != expected_ids or len(ids) != len(expected_ids): _fail("ACK-E-UNANIMOUS-SET")
    for item in value:
        if type(item) is not dict or set(item) != {"schema","schema_version","chain_id","profile_sha256","activation_height","operator_id","nonce","signature"}: _fail("ACK-E-SCHEMA")
        if item["schema"] != "hnd.operator-ack" or type(item["schema_version"]) is not int or item["schema_version"] != 1: _fail("ACK-E-SCHEMA-VERSION")
        if item["chain_id"] != expected_chain_id or item["profile_sha256"] != expected_profile_sha256: _fail("ACK-E-PROFILE-CONTEXT")
        if type(item["activation_height"]) is not int or item["activation_height"] != expected_activation_height: _fail("ACK-E-ACTIVATION")
        op = item["operator_id"]
        if type(op) is not str or not IDENT.fullmatch(op): _fail("ACK-E-OPERATOR-ID")
        nonce = item["nonce"]
        if type(nonce) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", nonce, re.ASCII): _fail("ACK-E-NONCE")
        signature = _b64(item["signature"])
        try:
            Ed25519PublicKey.from_public_bytes(expected_operator_keys[op]).verify(
                signature, acknowledgement_message(chain_id=expected_chain_id,
                    profile_sha256=expected_profile_sha256,
                    activation_height=expected_activation_height, operator_id=op, nonce=nonce))
        except (InvalidSignature, ValueError) as exc:
            raise OperatorAckError("ACK-E-SIGNATURE-VERIFY") from exc
    digest = hashlib.sha256(ACK_SET_DOMAIN + rfc8785.dumps(value)).hexdigest()
    return {"profile_sha256":expected_profile_sha256,"activation_height":expected_activation_height,
        "operator_count":len(ids),"acknowledged_operator_ids":ids,"ack_set_sha256":digest,
        "unanimous":True}
