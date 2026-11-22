"""Ed25519 helpers. Private keys are caller-owned and never stored by the ledger."""

from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .canonical import account_id


def generate_keypair() -> tuple[Ed25519PrivateKey, bytes]:
    """Return a new private key and its raw 32-byte public key."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_key, public_key


def address_from_public_key(public_key: bytes) -> str:
    """Derive the v0.2 lowercase hex account ID from a raw Ed25519 public key."""
    return account_id(public_key).hex()


def sign_transaction(private_key: Ed25519PrivateKey, message: bytes) -> str:
    """Sign the exact domain-separated v0.2 message; return a hex signature."""
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be an Ed25519PrivateKey")
    if not isinstance(message, bytes):
        raise TypeError("message must be bytes")
    return private_key.sign(message).hex()


def verify_signature(public_key: bytes, message: bytes, signature: str) -> bool:
    """Return False for malformed keys/signatures or an invalid Ed25519 signature."""
    if not isinstance(public_key, bytes) or len(public_key) != 32:
        return False
    if not isinstance(message, bytes) or not isinstance(signature, str):
        return False
    try:
        raw_signature = bytes.fromhex(signature)
        if len(raw_signature) != 64:
            return False
        Ed25519PublicKey.from_public_bytes(public_key).verify(raw_signature, message)
        return True
    except (ValueError, TypeError, InvalidSignature):
        return False
