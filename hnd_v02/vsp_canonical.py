"""Strict VSP v1 envelope parsing and JCS digest primitives.

This module is deliberately side-effect free. It does not verify governance
signatures, load a trust root, persist anti-rollback state, or start services.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any

import rfc8785


MAX_ENVELOPE_BYTES = 1_048_576
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 20_000
MAX_STRING_LENGTH = 4_096
MAX_ARRAY_LENGTH = 1_024
MAX_SIGNATURES = 3
MAX_SAFE_INTEGER = (2**53) - 1

_KEY_ID_RE = re.compile(r"^gk1-[0-9a-f]{64}$", re.ASCII)


class VSPInputError(ValueError):
    """Stable, fail-closed VSP input rejection."""


def _fail(code: str) -> None:
    raise VSPInputError(code)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("VSP-E-DUPLICATE-KEY")
        result[key] = value
    return result


def _parse_integer(token: str) -> int:
    # VSP v1 uses unsigned JSON integer tokens only. parse_int receives the
    # original token, so negative values and unsafe integers are rejected
    # before conversion/canonicalization.
    if token.startswith("-"):
        _fail("VSP-E-INTEGER-RANGE")
    value = int(token, 10)
    if value > MAX_SAFE_INTEGER:
        _fail("VSP-E-INTEGER-RANGE")
    return value


def _reject_float(_token: str) -> None:
    _fail("VSP-E-NON-INTEGER-NUMBER")


def _reject_constant(_token: str) -> None:
    _fail("VSP-E-NONSTANDARD-NUMBER")


def _validate_tree(root: Any) -> None:
    stack: list[tuple[Any, int]] = [(root, 0)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            _fail("VSP-E-NODE-LIMIT")
        if depth > MAX_JSON_DEPTH:
            _fail("VSP-E-DEPTH-LIMIT")
        if isinstance(value, str):
            if len(value) > MAX_STRING_LENGTH:
                _fail("VSP-E-STRING-LIMIT")
            if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
                _fail("VSP-E-UNICODE-SURROGATE")
        elif type(value) is dict:
            for key, child in value.items():
                if len(key) > MAX_STRING_LENGTH:
                    _fail("VSP-E-STRING-LIMIT")
                if any(0xD800 <= ord(char) <= 0xDFFF for char in key):
                    _fail("VSP-E-UNICODE-SURROGATE")
                stack.append((child, depth + 1))
        elif type(value) is list:
            if len(value) > MAX_ARRAY_LENGTH:
                _fail("VSP-E-ARRAY-LIMIT")
            for child in value:
                stack.append((child, depth + 1))


def _jcs(value: Any) -> bytes:
    try:
        return rfc8785.dumps(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise VSPInputError("VSP-E-JCS-REJECTED") from exc


def canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    if type(payload) is not dict:
        _fail("VSP-E-PAYLOAD-TYPE")
    _validate_tree(payload)
    return _jcs(payload)


def profile_digest(payload: dict[str, Any]) -> bytes:
    """Return the raw 32-byte HND-VSP-v1 domain-separated payload digest."""
    return hashlib.sha256(
        b"HND-VSP-v1\x00" + canonical_payload_bytes(payload)
    ).digest()


def governance_signature_message(digest: bytes) -> bytes:
    """Return the exact Ed25519 message for a 32-byte profile digest."""
    if type(digest) is not bytes or len(digest) != 32:
        _fail("VSP-E-DIGEST-LENGTH")
    return b"HND-VSP-AUTH-v1\x00" + digest


def parse_vsp_envelope(raw: bytes) -> dict[str, Any]:
    """Parse and validate canonical VSP envelope framing, not its trust.

    The payload's complete protocol schema and cryptographic authorization are
    intentionally separate verification stages.
    """
    if type(raw) is not bytes:
        _fail("VSP-E-INPUT-TYPE")
    if len(raw) > MAX_ENVELOPE_BYTES:
        _fail("VSP-E-BYTE-LIMIT")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("VSP-E-UTF8-BOM")
    try:
        source = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise VSPInputError("VSP-E-INVALID-UTF8") from exc

    try:
        envelope = json.loads(
            source,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_int=_parse_integer,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except VSPInputError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise VSPInputError("VSP-E-INVALID-JSON") from exc

    if type(envelope) is not dict or set(envelope) != {"payload", "signatures"}:
        _fail("VSP-E-ENVELOPE-SCHEMA")
    payload = envelope["payload"]
    signatures = envelope["signatures"]
    if type(payload) is not dict:
        _fail("VSP-E-PAYLOAD-TYPE")
    if type(signatures) is not list or len(signatures) not in (2, 3):
        _fail("VSP-E-SIGNATURE-COUNT")

    _validate_tree(envelope)

    seen_key_ids: set[str] = set()
    ordered_key_ids: list[str] = []
    for record in signatures:
        if type(record) is not dict or set(record) != {"key_id", "algorithm", "signature"}:
            _fail("VSP-E-SIGNATURE-SCHEMA")
        key_id = record["key_id"]
        algorithm = record["algorithm"]
        signature = record["signature"]
        if type(key_id) is not str or not _KEY_ID_RE.fullmatch(key_id):
            _fail("VSP-E-KEY-ID")
        if key_id in seen_key_ids:
            _fail("VSP-E-DUPLICATE-SIGNER")
        seen_key_ids.add(key_id)
        ordered_key_ids.append(key_id)
        if algorithm != "ed25519":
            _fail("VSP-E-SIGNATURE-ALGORITHM")
        if type(signature) is not str:
            _fail("VSP-E-SIGNATURE-ENCODING")
        try:
            decoded = base64.b64decode(signature, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise VSPInputError("VSP-E-SIGNATURE-ENCODING") from exc
        if len(decoded) != 64 or base64.b64encode(decoded).decode("ascii") != signature:
            _fail("VSP-E-SIGNATURE-ENCODING")

    if ordered_key_ids != sorted(ordered_key_ids):
        _fail("VSP-E-SIGNATURE-ORDER")

    if _jcs(envelope) != raw:
        _fail("VSP-E-NONCANONICAL-ENVELOPE")
    return envelope
