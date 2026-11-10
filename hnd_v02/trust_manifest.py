"""Strict offline VSP trust-manifest bootstrap verifier."""
from __future__ import annotations
import base64, hashlib, json, re
from typing import Any, Mapping
import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from hnd_v02.vsp_canonical import _validate_tree, _reject_duplicate_pairs

MANIFEST_DOMAIN = b"HND-VSP-TRUST-MANIFEST-v1\x00"
POP_DOMAIN = b"HND-VSP-GOVERNANCE-POP-v1\x00"
WITNESS_DOMAIN = b"HND-VSP-TRUST-WITNESS-v1\x00"
MAX_MANIFEST_BYTES = 262144
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
HEX40 = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
CHAIN = re.compile(r"^[A-Za-z0-9._-]{1,50}$", re.ASCII)
IDENT = re.compile(r"^[A-Za-z0-9._:-]{1,128}$", re.ASCII)

class TrustManifestError(ValueError):
    """Stable fail-closed trust-manifest rejection."""

def _fail(code: str) -> None:
    raise TrustManifestError(code)

def _exact(value: Any, fields: set[str], code: str) -> dict:
    if type(value) is not dict or set(value) != fields: _fail(code)
    return value

def _b64(value: Any, size: int, code: str) -> bytes:
    if type(value) is not str: _fail(code)
    try: decoded = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc: raise TrustManifestError(code) from exc
    if len(decoded) != size or base64.b64encode(decoded).decode("ascii") != value: _fail(code)
    return decoded

def _jcs(value: Any) -> bytes:
    try: return rfc8785.dumps(value)
    except (TypeError, ValueError, OverflowError) as exc: raise TrustManifestError("TM-E-CANONICALIZATION") from exc

def _manifest_core(manifest: dict) -> dict:
    return {key: value for key, value in manifest.items() if key != "witnesses"}

def trust_manifest_digest(manifest: dict) -> bytes:
    return hashlib.sha256(MANIFEST_DOMAIN + _jcs(_manifest_core(manifest))).digest()

def governance_pop_message(*, chain_id: str, hnd_genesis_sha256: str,
                           cometbft_genesis_sha256: str, nonce: str,
                           key_id: str, public_key: str, role_id: str) -> bytes:
    challenge = {"chain_id": chain_id, "hnd_genesis_sha256": hnd_genesis_sha256,
        "cometbft_genesis_sha256": cometbft_genesis_sha256, "nonce": nonce,
        "key_id": key_id, "public_key": public_key, "role_id": role_id}
    return POP_DOMAIN + _jcs(challenge)

def witness_message(digest: bytes) -> bytes:
    if type(digest) is not bytes or len(digest) != 32: _fail("TM-E-DIGEST")
    return WITNESS_DOMAIN + digest

def parse_trust_manifest(raw: bytes, *, expected_context: Mapping[str, str],
                         trusted_witness_keys: Mapping[str, bytes]) -> dict:
    """Validate sequence-zero bootstrap against externally pinned witness keys."""
    if type(raw) is not bytes or not raw or len(raw) > MAX_MANIFEST_BYTES: _fail("TM-E-BYTE-LIMIT")
    if raw.startswith(b"\xef\xbb\xbf"): _fail("TM-E-UTF8-BOM")
    try:
        source = raw.decode("utf-8", errors="strict")
        manifest = json.loads(source, object_pairs_hook=_reject_duplicate_pairs,
            parse_int=lambda token: int(token, 10),
            parse_float=lambda _token: (_ for _ in ()).throw(ValueError("float")),
            parse_constant=lambda _token: (_ for _ in ()).throw(ValueError("constant")))
    except Exception as exc:
        if isinstance(exc, TrustManifestError): raise
        raise TrustManifestError("TM-E-INVALID-JSON") from exc
    _validate_tree(manifest)
    _exact(manifest, {"schema","schema_version","chain_id","hnd_genesis_sha256",
        "cometbft_genesis_sha256","cometbft_source_commit","vsp_schema_version",
        "sequence","previous_manifest_sha256","nonce","governance_threshold",
        "governance_keys","witnesses"}, "TM-E-SCHEMA")
    if manifest["schema"] != "hnd.vsp-trust-manifest" or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1: _fail("TM-E-SCHEMA-VERSION")
    if type(manifest["vsp_schema_version"]) is not int or manifest["vsp_schema_version"] != 1: _fail("TM-E-VSP-SCHEMA")
    if type(manifest["sequence"]) is not int or manifest["sequence"] != 0 or manifest["previous_manifest_sha256"] is not None: _fail("TM-E-INITIAL-SEQUENCE")
    if type(manifest["governance_threshold"]) is not int or manifest["governance_threshold"] != 2: _fail("TM-E-THRESHOLD")
    chain = manifest["chain_id"]
    if type(chain) is not str or not CHAIN.fullmatch(chain): _fail("TM-E-CHAIN-ID")
    for field, pattern, code in (("hnd_genesis_sha256",HEX64,"TM-E-HND-GENESIS"),
        ("cometbft_genesis_sha256",HEX64,"TM-E-COMETBFT-GENESIS"),
        ("cometbft_source_commit",HEX40,"TM-E-COMETBFT-SOURCE")):
        value = manifest[field]
        if type(value) is not str or not pattern.fullmatch(value): _fail(code)
    for field in ("chain_id","hnd_genesis_sha256","cometbft_genesis_sha256","cometbft_source_commit"):
        if manifest[field] != expected_context.get(field): _fail("TM-E-EXPECTED-CONTEXT")
    _b64(manifest["nonce"], 32, "TM-E-NONCE")
    keys = manifest["governance_keys"]
    if type(keys) is not list or len(keys) != 3: _fail("TM-E-GOVERNANCE-KEY-COUNT")
    if [item.get("key_id") for item in keys if type(item) is dict] != sorted(item.get("key_id") for item in keys if type(item) is dict): _fail("TM-E-GOVERNANCE-ORDER")
    core_digest = trust_manifest_digest(manifest)
    seen_ids, seen_public, seen_roles = set(), set(), set()
    for entry in keys:
        _exact(entry, {"key_id","algorithm","public_key","role_id","proof_of_possession"}, "TM-E-GOVERNANCE-KEY-SCHEMA")
        if entry["algorithm"] != "ed25519": _fail("TM-E-GOVERNANCE-ALGORITHM")
        pub = _b64(entry["public_key"], 32, "TM-E-GOVERNANCE-PUBLIC-KEY")
        key_id = entry["key_id"]
        expected_id = "gk1-" + hashlib.sha256(b"HND-GOV-KEY-v1\x00" + pub).hexdigest()
        if type(key_id) is not str or key_id != expected_id: _fail("TM-E-GOVERNANCE-KEY-ID")
        role = entry["role_id"]
        if type(role) is not str or not IDENT.fullmatch(role): _fail("TM-E-GOVERNANCE-ROLE")
        if key_id in seen_ids or pub in seen_public or role in seen_roles: _fail("TM-E-GOVERNANCE-DUPLICATE")
        seen_ids.add(key_id); seen_public.add(pub); seen_roles.add(role)
        proof = _b64(entry["proof_of_possession"], 64, "TM-E-GOVERNANCE-POP")
        message = governance_pop_message(chain_id=chain, hnd_genesis_sha256=manifest["hnd_genesis_sha256"],
            cometbft_genesis_sha256=manifest["cometbft_genesis_sha256"], nonce=manifest["nonce"],
            key_id=key_id, public_key=entry["public_key"], role_id=role)
        try: Ed25519PublicKey.from_public_bytes(pub).verify(proof, message)
        except (InvalidSignature, ValueError) as exc: raise TrustManifestError("TM-E-GOVERNANCE-POP") from exc
    witnesses = manifest["witnesses"]
    if type(witnesses) is not list or len(witnesses) != 2 or type(trusted_witness_keys) is not dict: _fail("TM-E-WITNESS-COUNT")
    if [item.get("witness_id") for item in witnesses if type(item) is dict] != sorted(item.get("witness_id") for item in witnesses if type(item) is dict): _fail("TM-E-WITNESS-ORDER")
    seen_witnesses = set()
    seen_witness_public_keys = set()
    for witness in witnesses:
        _exact(witness, {"witness_id","signature"}, "TM-E-WITNESS-SCHEMA")
        wid = witness["witness_id"]
        if type(wid) is not str or not IDENT.fullmatch(wid) or wid in seen_witnesses: _fail("TM-E-WITNESS-ID")
        pub = trusted_witness_keys.get(wid)
        if type(pub) is not bytes or len(pub) != 32: _fail("TM-E-UNTRUSTED-WITNESS")
        if pub in seen_witness_public_keys: _fail("TM-E-WITNESS-KEY-DUPLICATE")
        seen_witness_public_keys.add(pub)
        signature = _b64(witness["signature"], 64, "TM-E-WITNESS-SIGNATURE")
        try: Ed25519PublicKey.from_public_bytes(pub).verify(signature, witness_message(core_digest))
        except (InvalidSignature, ValueError) as exc: raise TrustManifestError("TM-E-WITNESS-SIGNATURE") from exc
        seen_witnesses.add(wid)
    if _jcs(manifest) != raw: _fail("TM-E-NONCANONICAL")
    return {"manifest_digest": hashlib.sha256(MANIFEST_DOMAIN + _jcs(manifest)).hexdigest(),
        "sequence": 0, "governance_key_ids": sorted(seen_ids),
        "witness_ids": sorted(seen_witnesses), "threshold": 2}
