"""Canonical transaction encoding and Ed25519 verification for HND v0.2."""

from __future__ import annotations

from dataclasses import dataclass

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

PROTOCOL_VERSION = 2
CHAIN_ID = b"HND-LOCAL-V2" + bytes(32 - len(b"HND-LOCAL-V2"))
MAX_U64 = (1 << 64) - 1
MAX_SUPPLY = 1_000_000 * (10 ** 8)

ACCOUNT_PREFIX = b"HND-ACCOUNT-V2\x00"
SIGN_PREFIX = b"HND-TX-SIGN-V2\x00"
TXID_PREFIX = b"HND-TX-ID-V2\x00"


class ProtocolError(ValueError):
    """Raised when a transaction is malformed or invalid."""


@dataclass(frozen=True, slots=True)
class Transaction:
    chain_id: bytes
    sender: bytes
    recipient: bytes
    amount: int
    nonce: int
    public_key: bytes
    signature: bytes


def _uint(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"{field} must be an integer")
    if value < minimum or value > MAX_U64:
        raise ProtocolError(f"{field} is outside the uint64 range")
    return value


def canonical_cbor(value: object) -> bytes:
    return cbor2.dumps(value, canonical=True)


def _decode_canonical(raw: bytes) -> object:
    try:
        value = cbor2.loads(raw)
    except Exception as exc:
        raise ProtocolError("invalid CBOR") from exc
    if canonical_cbor(value) != raw:
        raise ProtocolError("non-canonical CBOR")
    return value


def account_id(public_key: bytes) -> bytes:
    if not isinstance(public_key, bytes) or len(public_key) != 32:
        raise ProtocolError("Ed25519 public key must be 32 bytes")
    import hashlib
    return hashlib.sha256(ACCOUNT_PREFIX + public_key).digest()


def signing_payload(tx: Transaction) -> list[object]:
    return [
        PROTOCOL_VERSION, tx.chain_id, tx.sender, tx.recipient,
        tx.amount, tx.nonce,
    ]


def signing_message(tx: Transaction) -> bytes:
    return SIGN_PREFIX + canonical_cbor(signing_payload(tx))


def transaction_array(tx: Transaction) -> list[object]:
    return [
        PROTOCOL_VERSION, tx.chain_id, tx.sender, tx.recipient,
        tx.amount, tx.nonce, tx.public_key, tx.signature,
    ]


def transaction_id(tx: Transaction) -> bytes:
    import hashlib
    return hashlib.sha256(TXID_PREFIX + canonical_cbor(transaction_array(tx))).digest()


def create_transaction(
    private_key: Ed25519PrivateKey,
    recipient: bytes,
    amount: int,
    nonce: int,
    chain_id: bytes = CHAIN_ID,
) -> Transaction:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ProtocolError("private_key must be an Ed25519 private key")
    if not isinstance(chain_id, bytes) or len(chain_id) != 32:
        raise ProtocolError("chain_id must be 32 bytes")
    if not isinstance(recipient, bytes) or len(recipient) != 32:
        raise ProtocolError("recipient must be a 32-byte account id")
    _uint(amount, "amount", minimum=1)
    _uint(nonce, "nonce")
    pub = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    sender_id = account_id(pub)
    if sender_id == recipient:
        raise ProtocolError("self-transfer is not allowed")
    tx = Transaction(
        chain_id=chain_id,
        sender=sender_id,
        recipient=recipient,
        amount=amount,
        nonce=nonce,
        public_key=pub,
        signature=bytes(64),
    )
    signature = private_key.sign(signing_message(tx))
    return Transaction(
        chain_id=chain_id, sender=tx.sender, recipient=recipient,
        amount=amount, nonce=nonce, public_key=pub, signature=signature,
    )


def verify_transaction(tx: Transaction, expected_chain_id: bytes = CHAIN_ID) -> None:
    if not isinstance(tx, Transaction):
        raise ProtocolError("transaction has an invalid type")
    if not isinstance(expected_chain_id, bytes) or len(expected_chain_id) != 32:
        raise ProtocolError("expected chain id must be 32 bytes")
    if tx.chain_id != expected_chain_id:
        raise ProtocolError("wrong chain id")
    if not isinstance(tx.sender, bytes) or len(tx.sender) != 32:
        raise ProtocolError("sender must be 32 bytes")
    if not isinstance(tx.recipient, bytes) or len(tx.recipient) != 32:
        raise ProtocolError("recipient must be 32 bytes")
    if tx.sender == tx.recipient:
        raise ProtocolError("self-transfer is not allowed")
    if not isinstance(tx.public_key, bytes) or len(tx.public_key) != 32:
        raise ProtocolError("public key must be 32 bytes")
    if not isinstance(tx.signature, bytes) or len(tx.signature) != 64:
        raise ProtocolError("signature must be 64 bytes")
    _uint(tx.amount, "amount", minimum=1)
    _uint(tx.nonce, "nonce")
    if account_id(tx.public_key) != tx.sender:
        raise ProtocolError("sender does not match public key")
    try:
        Ed25519PublicKey.from_public_bytes(tx.public_key).verify(
            tx.signature, signing_message(tx)
        )
    except (InvalidSignature, ValueError) as exc:
        raise ProtocolError("invalid transaction signature") from exc


def encode_transaction(tx: Transaction) -> bytes:
    verify_transaction(tx, tx.chain_id)
    return canonical_cbor(transaction_array(tx))


def decode_transaction(raw: bytes, expected_chain_id: bytes = CHAIN_ID) -> Transaction:
    if not isinstance(raw, bytes):
        raise ProtocolError("encoded transaction must be bytes")
    value = _decode_canonical(raw)
    if not isinstance(value, list) or len(value) != 8:
        raise ProtocolError("transaction must be an eight-element CBOR array")
    version, chain_id, sender, recipient, amount, nonce, public_key, signature = value
    if isinstance(version, bool) or not isinstance(version, int) or version != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    tx = Transaction(chain_id, sender, recipient, amount, nonce, public_key, signature)
    verify_transaction(tx, expected_chain_id)
    return tx
