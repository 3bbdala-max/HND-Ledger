"""Normative byte encodings for the HND v0.2 transaction core.

This module deliberately implements only the restricted CBOR data model used by
HND v0.2: unsigned integers, byte strings, and fixed-length arrays. It does not
accept arbitrary Python objects or encode CBOR maps/floats/tags.
"""
from __future__ import annotations

import hashlib

PROTOCOL_VERSION = 2
UINT64_MAX = (1 << 64) - 1
CHAIN_ID_SIZE = 32
ACCOUNT_ID_SIZE = 32
PUBLIC_KEY_SIZE = 32
SIGNATURE_SIZE = 64

ACCOUNT_DOMAIN = b"HND-ACCOUNT-V2\x00"
SIGN_DOMAIN = b"HND-TX-SIGN-V2\x00"
TX_ID_DOMAIN = b"HND-TX-ID-V2\x00"
LOCAL_CHAIN_ID = b"HND-LOCAL-V2" + bytes(20)


class EncodingError(ValueError):
    """A value cannot be represented by the HND v0.2 canonical profile."""


def _head(major: int, value: int) -> bytes:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EncodingError("CBOR argument must be a non-negative integer")
    if value < 24:
        return bytes([(major << 5) | value])
    if value <= 0xFF:
        return bytes([(major << 5) | 24, value])
    if value <= 0xFFFF:
        return bytes([(major << 5) | 25]) + value.to_bytes(2, "big")
    if value <= 0xFFFFFFFF:
        return bytes([(major << 5) | 26]) + value.to_bytes(4, "big")
    if value <= UINT64_MAX:
        return bytes([(major << 5) | 27]) + value.to_bytes(8, "big")
    raise EncodingError("integer exceeds the unsigned 64-bit CBOR range")


def encode_uint(value: int) -> bytes:
    """Encode one unsigned 64-bit integer using shortest-form CBOR."""
    return _head(0, value)


def encode_bytes(value: bytes) -> bytes:
    """Encode one byte string."""
    if not isinstance(value, bytes):
        raise EncodingError("byte string value must be bytes")
    return _head(2, len(value)) + value


def encode_array(items: tuple[bytes, ...] | list[bytes]) -> bytes:
    """Encode an array whose members are already canonical CBOR items."""
    if not isinstance(items, (tuple, list)):
        raise EncodingError("array items must be a tuple or list")
    if any(not isinstance(item, bytes) for item in items):
        raise EncodingError("encoded array members must be bytes")
    return _head(4, len(items)) + b"".join(items)


def _fixed_bytes(name: str, value: bytes, size: int) -> bytes:
    if not isinstance(value, bytes) or len(value) != size:
        raise EncodingError(f"{name} must be exactly {size} bytes")
    return value


def _uint(name: str, value: int, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EncodingError(f"{name} must be an integer")
    if value < minimum or value > UINT64_MAX:
        raise EncodingError(f"{name} is outside the permitted unsigned 64-bit range")
    return value


def account_id(public_key: bytes) -> bytes:
    """Return SHA-256(HND-ACCOUNT-V2\0 || raw Ed25519 public key)."""
    public_key = _fixed_bytes("public_key", public_key, PUBLIC_KEY_SIZE)
    return hashlib.sha256(ACCOUNT_DOMAIN + public_key).digest()


def transaction_payload(
    chain_id: bytes,
    sender: bytes,
    recipient: bytes,
    amount: int,
    nonce: int,
) -> bytes:
    """Canonical six-element unsigned transaction array."""
    chain_id = _fixed_bytes("chain_id", chain_id, CHAIN_ID_SIZE)
    sender = _fixed_bytes("sender", sender, ACCOUNT_ID_SIZE)
    recipient = _fixed_bytes("recipient", recipient, ACCOUNT_ID_SIZE)
    amount = _uint("amount", amount, minimum=1)
    nonce = _uint("nonce", nonce)
    return encode_array([
        encode_uint(PROTOCOL_VERSION),
        encode_bytes(chain_id),
        encode_bytes(sender),
        encode_bytes(recipient),
        encode_uint(amount),
        encode_uint(nonce),
    ])


def signing_message(
    chain_id: bytes,
    sender: bytes,
    recipient: bytes,
    amount: int,
    nonce: int,
) -> bytes:
    """Return the exact domain-separated Ed25519 signing message."""
    return SIGN_DOMAIN + transaction_payload(chain_id, sender, recipient, amount, nonce)


def signed_transaction(
    chain_id: bytes,
    sender: bytes,
    recipient: bytes,
    amount: int,
    nonce: int,
    public_key: bytes,
    signature: bytes,
) -> bytes:
    """Canonical eight-element complete signed transaction array."""
    payload = transaction_payload(chain_id, sender, recipient, amount, nonce)
    public_key = _fixed_bytes("public_key", public_key, PUBLIC_KEY_SIZE)
    signature = _fixed_bytes("signature", signature, SIGNATURE_SIZE)
    # The six payload members are already encoded. Rebuild the array with the
    # public key and signature appended, preserving the exact positional schema.
    prefix = payload[:-1] if False else None
    return encode_array([
        encode_uint(PROTOCOL_VERSION),
        encode_bytes(chain_id),
        encode_bytes(sender),
        encode_bytes(recipient),
        encode_uint(amount),
        encode_uint(nonce),
        encode_bytes(public_key),
        encode_bytes(signature),
    ])


def transaction_id(
    chain_id: bytes,
    sender: bytes,
    recipient: bytes,
    amount: int,
    nonce: int,
    public_key: bytes,
    signature: bytes,
) -> bytes:
    """Return SHA-256(HND-TX-ID-V2\0 || canonical complete signed transaction)."""
    encoded = signed_transaction(
        chain_id, sender, recipient, amount, nonce, public_key, signature
    )
    return hashlib.sha256(TX_ID_DOMAIN + encoded).digest()
