"""Isolated HND v0.2 transaction-envelope reference implementation.

This module is intentionally separate from the frozen v0.1 prototype. It is a
single-process signing/validation primitive, not a ledger, block format, node,
network, or consensus implementation.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

MAX_NONCE = (1 << 64) - 1
TX_SIGNING_DOMAIN = b"HND-LEDGER/TX\x00"
_REQUIRED_TX_KEYS = {
    "protocol_version",
    "network_id",
    "sender",
    "recipient",
    "amount",
    "nonce",
    "signature",
}
_NETWORK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$", re.ASCII)


def canonical_json(value: Any) -> bytes:
    """Return the v0.2 canonical JSON encoding for supported payload values."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def signing_bytes(payload: Mapping[str, Any]) -> bytes:
    """Apply a fixed protocol domain prefix before canonical payload bytes."""
    return TX_SIGNING_DOMAIN + canonical_json(dict(payload))


def _is_u64(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_NONCE


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode_canonical(value: Any, expected_length: int) -> bytes:
    if type(value) is not str:
        raise ValueError("base64 type")
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ValueError("base64 encoding") from exc
    if len(raw) != expected_length or _b64encode(raw) != value:
        raise ValueError("base64 length or canonical form")
    return raw


@dataclass(frozen=True)
class ProtocolConfig:
    """Explicit protocol parameters; no project-wide monetary cap is assumed."""

    network_id: str
    protocol_version: int
    max_amount: int

    def __post_init__(self) -> None:
        if type(self.network_id) is not str or not _NETWORK_ID_RE.fullmatch(self.network_id):
            raise ValueError("network_id")
        if type(self.protocol_version) is not int or self.protocol_version <= 0:
            raise ValueError("protocol_version")
        if type(self.max_amount) is not int or self.max_amount <= 0:
            raise ValueError("max_amount")


def signing_payload(
    *,
    protocol_version: int,
    network_id: str,
    sender: str,
    recipient: str,
    amount: int,
    nonce: int,
) -> dict[str, Any]:
    """Build the exact field set signed by an Ed25519 key."""
    return {
        "protocol_version": protocol_version,
        "network_id": network_id,
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "nonce": nonce,
    }


def create_signed_transaction(
    private_key: Ed25519PrivateKey,
    *,
    config: ProtocolConfig,
    sender: str,
    recipient: str,
    amount: int,
    nonce: int,
) -> dict[str, Any]:
    """Create a signed envelope; validation remains the receiver's responsibility."""
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be Ed25519PrivateKey")
    payload = signing_payload(
        protocol_version=config.protocol_version,
        network_id=config.network_id,
        sender=sender,
        recipient=recipient,
        amount=amount,
        nonce=nonce,
    )
    signature = private_key.sign(signing_bytes(payload))
    return {**payload, "signature": _b64encode(signature)}


def transaction_id(tx: Mapping[str, Any]) -> str:
    """Return the v0.2 transaction ID over the complete unsigned domain payload."""
    if type(tx) is not dict or set(tx) != _REQUIRED_TX_KEYS:
        raise ValueError("schema")
    payload = {key: tx[key] for key in _REQUIRED_TX_KEYS if key != "signature"}
    return hashlib.sha256(signing_bytes(payload)).hexdigest()


def validate_transaction(
    tx: Any,
    *,
    config: ProtocolConfig,
    expected_nonce: int,
    sender_balance: int,
    sender_public_key: str,
) -> tuple[bool, str]:
    """Validate shape, strict numeric types/ranges, domain, funds, and signature.

    Account lookup and binding of \`sender\` to \`sender_public_key\` are provided by
    the caller. A cryptographic account-ID derivation rule is still a separate,
    unresolved protocol decision.
    """
    if type(tx) is not dict or set(tx) != _REQUIRED_TX_KEYS:
        return False, "schema"

    # Exact types matter: bool is a subclass of int and float 1.0 compares equal
    # to integer 1 in Python, so \`isinstance\`/equality alone are insufficient.
    if type(tx["protocol_version"]) is not int or tx["protocol_version"] <= 0:
        return False, "protocol_version"
    if tx["protocol_version"] != config.protocol_version:
        return False, "protocol_version"
    if type(tx["network_id"]) is not str or tx["network_id"] != config.network_id:
        return False, "network_id"
    if not _NETWORK_ID_RE.fullmatch(tx["network_id"]):
        return False, "network_id"

    for field in ("sender", "recipient"):
        if type(tx[field]) is not str or not tx[field] or len(tx[field]) > 128:
            return False, field
    if tx["sender"] == tx["recipient"]:
        return False, "self-transfer"

    if type(tx["amount"]) is not int or tx["amount"] <= 0 or tx["amount"] > config.max_amount:
        return False, "amount"
    if not _is_u64(tx["nonce"]):
        return False, "nonce-type-or-range"
    if not _is_u64(expected_nonce):
        return False, "expected-nonce"
    if tx["nonce"] != expected_nonce:
        return False, "nonce"
    if type(sender_balance) is not int or sender_balance < 0:
        return False, "sender-balance"
    if tx["amount"] > sender_balance:
        return False, "balance"

    try:
        public_key_raw = _b64decode_canonical(sender_public_key, 32)
        signature_raw = _b64decode_canonical(tx["signature"], 64)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_raw)
        payload = signing_payload(
            protocol_version=tx["protocol_version"],
            network_id=tx["network_id"],
            sender=tx["sender"],
            recipient=tx["recipient"],
            amount=tx["amount"],
            nonce=tx["nonce"],
        )
        public_key.verify(signature_raw, signing_bytes(payload))
    except (ValueError, InvalidSignature, TypeError):
        return False, "signature"
    return True, "ok"


def public_key_b64(private_key: Ed25519PrivateKey) -> str:
    """Serialize an Ed25519 public key as canonical Base64 raw bytes."""
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b64encode(raw)
