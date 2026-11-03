"""Ed25519 helpers. Private keys are caller-owned and never stored by the ledger."""

from __future__ import annotations

import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_keypair() -> tuple[Ed25519PrivateKey, bytes]:
    """Return a new private key and its raw 32-byte public key."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_key, public_key


def address_from_public_key(public_key: bytes) -> str:
    """Derive a lowercase hex account address from a raw Ed25519 public key."""
    if not isinstance(public_key, bytes) or len(public_key) != 32:
        raise ValueError("public_key must be exactly 32 raw bytes")
    return hashlib.sha256(public_key).hexdigest()


def sign_transaction(private_key: Ed25519PrivateKey, payload: bytes) -> str:
    """Sign canonical transaction payload bytes; return a hex signature."""
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be an Ed25519PrivateKey")
    return private_key.sign(payload).hex()


def verify_signature(public_key: bytes, payload: bytes, signature: str) -> bool:
    """Return False for malformed keys/signatures or invalid signatures."""
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            bytes.fromhex(signature), payload
        )
        return True
    except (ValueError, TypeError):
        return False
    except Exception as exc:
        # cryptography's InvalidSignature is intentionally converted to False.
        if exc.__class__.__name__ == "InvalidSignature":
            return False
        raise
