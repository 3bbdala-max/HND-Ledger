"""Chainable Trust Manifest v1 rotation verifier (offline, fail-closed)."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from hnd_v02.trust_manifest import (
    TrustManifestError, _b64, _exact, _fail, _jcs, _validate_tree,
    governance_pop_message, witness_message, parse_trust_manifest,
)

ROTATION_SCHEMA = "hnd.vsp-trust-manifest-rotation"
ROTATION_DOMAIN = b"HND-VSP-TRUST-MANIFEST-ROTATION-v1\x00"
ROTATION_AUTH_DOMAIN = b"HND-VSP-TRUST-MANIFEST-ROTATION-AUTH-v1\x00"
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
HEX40 = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
IDENT = re.compile(r"^[A-Za-z0-9._:-]{1,128}$", re.ASCII)
MAX_ROTATION_BYTES = 262144


def _rotation_core(manifest: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in manifest.items()
            if k not in {"witnesses", "authorizations"}}


def _rotation_digest(manifest: dict[str, Any]) -> bytes:
    return hashlib.sha256(ROTATION_DOMAIN + _jcs(_rotation_core(manifest))).digest()


def _rotation_auth_message(digest: bytes) -> bytes:
    if type(digest) is not bytes or len(digest) != 32:
        _fail("TMR-E-DIGEST")
    return ROTATION_AUTH_DOMAIN + digest


def _parse_canonical(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_ROTATION_BYTES:
        _fail("TMR-E-BYTE-LIMIT")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("TMR-E-UTF8-BOM")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=lambda pairs: _unique_pairs(pairs),
            parse_int=lambda token: _strict_int(token),
            parse_float=lambda _token: (_ for _ in ()).throw(ValueError("float")),
            parse_constant=lambda _token: (_ for _ in ()).throw(ValueError("constant")),
        )
    except TrustManifestError:
        raise
    except Exception as exc:
        raise TrustManifestError("TMR-E-INVALID-JSON") from exc
    _validate_tree(value)
    if type(value) is not dict:
        _fail("TMR-E-SCHEMA")
    if _jcs(value) != raw:
        _fail("TMR-E-NONCANONICAL")
    return value


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("TMR-E-DUPLICATE-KEY")
        result[key] = value
    return result


def _strict_int(token: str) -> int:
    if token.startswith("-"):
        _fail("TMR-E-INTEGER-RANGE")
    value = int(token, 10)
    if value > (1 << 53) - 1:
        _fail("TMR-E-INTEGER-RANGE")
    return value


def _public_keys(entries: list[dict[str, Any]]) -> dict[str, bytes]:
    result = {}
    for entry in entries:
        result[entry["key_id"]] = _b64(
            entry["public_key"], 32, "TMR-E-GOVERNANCE-PUBLIC-KEY"
        )
    return result


def verify_trust_manifest_rotation(
    raw: bytes,
    *,
    previous_sequence: int,
    previous_manifest_sha256: str,
    previous_governance_public_keys: Mapping[str, bytes],
    expected_context: Mapping[str, str],
    trusted_witness_keys: Mapping[str, bytes],
) -> dict[str, Any]:
    """Verify exactly one successor manifest against an already verified predecessor.

    The caller must obtain predecessor values from verify_trust_manifest_chain;
    this function never treats caller-supplied unverified keys as a trust root.
    """
    manifest = _parse_canonical(raw)
    _exact(manifest, {
        "schema", "schema_version", "chain_id", "hnd_genesis_sha256",
        "cometbft_genesis_sha256", "cometbft_source_commit",
        "vsp_schema_version", "sequence", "previous_manifest_sha256",
        "nonce", "governance_threshold", "governance_keys",
        "authorizations", "witnesses",
    }, "TMR-E-SCHEMA")
    if manifest["schema"] != ROTATION_SCHEMA or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        _fail("TMR-E-SCHEMA-VERSION")
    if type(manifest["vsp_schema_version"]) is not int or manifest["vsp_schema_version"] != 1:
        _fail("TMR-E-VSP-SCHEMA")
    if type(previous_sequence) is not int or previous_sequence < 0:
        _fail("TMR-E-PREVIOUS-SEQUENCE")
    if type(manifest["sequence"]) is not int or manifest["sequence"] != previous_sequence + 1:
        _fail("TMR-E-SEQUENCE")
    if type(previous_manifest_sha256) is not str or not HEX64.fullmatch(previous_manifest_sha256):
        _fail("TMR-E-PREVIOUS-DIGEST")
    if manifest["previous_manifest_sha256"] != previous_manifest_sha256:
        _fail("TMR-E-PREVIOUS-DIGEST")
    if type(manifest["governance_threshold"]) is not int or manifest["governance_threshold"] != 2:
        _fail("TMR-E-THRESHOLD")
    for field, pattern in (
        ("hnd_genesis_sha256", HEX64),
        ("cometbft_genesis_sha256", HEX64),
        ("cometbft_source_commit", HEX40),
    ):
        if type(manifest[field]) is not str or not pattern.fullmatch(manifest[field]):
            _fail("TMR-E-CONTEXT-FORMAT")
    for field in ("chain_id", "hnd_genesis_sha256", "cometbft_genesis_sha256", "cometbft_source_commit"):
        if manifest[field] != expected_context.get(field):
            _fail("TMR-E-CONTEXT")
    _b64(manifest["nonce"], 32, "TMR-E-NONCE")

    new_keys = manifest["governance_keys"]
    if type(new_keys) is not list or len(new_keys) != 3:
        _fail("TMR-E-GOVERNANCE-KEY-COUNT")
    if any(type(item) is not dict for item in new_keys):
        _fail("TMR-E-GOVERNANCE-KEY-SCHEMA")
    ids = [item.get("key_id") for item in new_keys]
    if ids != sorted(ids) or len(set(ids)) != 3:
        _fail("TMR-E-GOVERNANCE-ORDER")
    digest = _rotation_digest(manifest)
    seen_pub, seen_roles = set(), set()
    for entry in new_keys:
        _exact(entry, {"key_id", "algorithm", "public_key", "role_id", "proof_of_possession"}, "TMR-E-GOVERNANCE-KEY-SCHEMA")
        if entry["algorithm"] != "ed25519":
            _fail("TMR-E-GOVERNANCE-ALGORITHM")
        pub = _b64(entry["public_key"], 32, "TMR-E-GOVERNANCE-PUBLIC-KEY")
        expected_id = "gk1-" + hashlib.sha256(b"HND-GOV-KEY-v1\x00" + pub).hexdigest()
        if entry["key_id"] != expected_id:
            _fail("TMR-E-GOVERNANCE-KEY-ID")
        role = entry["role_id"]
        if type(role) is not str or not IDENT.fullmatch(role):
            _fail("TMR-E-GOVERNANCE-ROLE")
        if pub in seen_pub or role in seen_roles:
            _fail("TMR-E-GOVERNANCE-DUPLICATE")
        seen_pub.add(pub)
        seen_roles.add(role)
        proof = _b64(entry["proof_of_possession"], 64, "TMR-E-GOVERNANCE-POP")
        message = governance_pop_message(
            chain_id=manifest["chain_id"],
            hnd_genesis_sha256=manifest["hnd_genesis_sha256"],
            cometbft_genesis_sha256=manifest["cometbft_genesis_sha256"],
            nonce=manifest["nonce"], key_id=entry["key_id"],
            public_key=entry["public_key"], role_id=role,
        )
        try:
            Ed25519PublicKey.from_public_bytes(pub).verify(proof, message)
        except (InvalidSignature, ValueError) as exc:
            raise TrustManifestError("TMR-E-GOVERNANCE-POP") from exc

    authorizations = manifest["authorizations"]
    if type(authorizations) is not list or len(authorizations) < 2 or len(authorizations) > 3:
        _fail("TMR-E-AUTHORIZATION-COUNT")
    auth_ids = [item.get("key_id") for item in authorizations if type(item) is dict]
    if len(auth_ids) != len(authorizations) or auth_ids != sorted(auth_ids) or len(set(auth_ids)) != len(auth_ids):
        _fail("TMR-E-AUTHORIZATION-ORDER")
    auth_message = _rotation_auth_message(digest)
    valid = 0
    for auth in authorizations:
        _exact(auth, {"key_id", "algorithm", "signature"}, "TMR-E-AUTHORIZATION-SCHEMA")
        if auth["algorithm"] != "ed25519":
            _fail("TMR-E-AUTHORIZATION-ALGORITHM")
        pub = previous_governance_public_keys.get(auth["key_id"])
        if type(pub) is not bytes or len(pub) != 32:
            _fail("TMR-E-UNAUTHORIZED-ROTATION-KEY")
        signature = _b64(auth["signature"], 64, "TMR-E-AUTHORIZATION-SIGNATURE")
        try:
            Ed25519PublicKey.from_public_bytes(pub).verify(signature, auth_message)
        except (InvalidSignature, ValueError) as exc:
            raise TrustManifestError("TMR-E-AUTHORIZATION-SIGNATURE") from exc
        valid += 1
    if valid < 2:
        _fail("TMR-E-AUTHORIZATION-THRESHOLD")

    witnesses = manifest["witnesses"]
    if type(witnesses) is not list or len(witnesses) != 2:
        _fail("TMR-E-WITNESS-COUNT")
    witness_ids = [item.get("witness_id") for item in witnesses if type(item) is dict]
    if len(witness_ids) != len(witnesses) or witness_ids != sorted(witness_ids) or len(set(witness_ids)) != 2:
        _fail("TMR-E-WITNESS-ORDER")
    seen_witness_pub = set()
    for witness in witnesses:
        _exact(witness, {"witness_id", "signature"}, "TMR-E-WITNESS-SCHEMA")
        wid = witness["witness_id"]
        if type(wid) is not str or not IDENT.fullmatch(wid):
            _fail("TMR-E-WITNESS-ID")
        pub = trusted_witness_keys.get(wid)
        if type(pub) is not bytes or len(pub) != 32 or pub in seen_witness_pub:
            _fail("TMR-E-UNTRUSTED-WITNESS")
        seen_witness_pub.add(pub)
        signature = _b64(witness["signature"], 64, "TMR-E-WITNESS-SIGNATURE")
        try:
            Ed25519PublicKey.from_public_bytes(pub).verify(signature, witness_message(digest))
        except (InvalidSignature, ValueError) as exc:
            raise TrustManifestError("TMR-E-WITNESS-SIGNATURE") from exc

    full_digest = hashlib.sha256(ROTATION_DOMAIN + _jcs(manifest)).hexdigest()
    return {
        "manifest_digest": full_digest,
        "sequence": manifest["sequence"],
        "governance_key_ids": ids,
        "governance_public_keys": _public_keys(new_keys),
        "witness_ids": witness_ids,
        "threshold": 2,
    }


def verify_trust_manifest_chain(
    manifests: Sequence[bytes],
    *,
    expected_context: Mapping[str, str],
    trusted_witness_keys: Mapping[str, bytes],
) -> dict[str, Any]:
    """Verify bootstrap plus every consecutive rotation in order."""
    if not isinstance(manifests, (list, tuple)) or not manifests:
        _fail("TMR-E-EMPTY-CHAIN")
    from hnd_v02.trust_manifest import parse_trust_manifest
    bootstrap = parse_trust_manifest(
        manifests[0], expected_context=expected_context,
        trusted_witness_keys=trusted_witness_keys,
    )
    raw0 = manifests[0]
    initial = json.loads(raw0.decode("utf-8"))
    current = {
        "sequence": 0,
        "manifest_digest": bootstrap["manifest_digest"],
        "governance_public_keys": _public_keys(initial["governance_keys"]),
    }
    for raw in manifests[1:]:
        current = verify_trust_manifest_rotation(
            raw,
            previous_sequence=current["sequence"],
            previous_manifest_sha256=current["manifest_digest"],
            previous_governance_public_keys=current["governance_public_keys"],
            expected_context=expected_context,
            trusted_witness_keys=trusted_witness_keys,
        )
    return {
        "sequence": current["sequence"],
        "manifest_digest": current["manifest_digest"],
        "governance_key_ids": sorted(current["governance_public_keys"]),
        "witness_ids": sorted(trusted_witness_keys),
        "threshold": 2,
        "rotation_count": len(manifests) - 1,
    }
