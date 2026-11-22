"""Strict decoder for the HND v0.2 restricted deterministic-CBOR profile.

Only unsigned integers, byte strings, and one fixed-length top-level array are
accepted. Indefinite lengths, non-shortest encodings, nested values, unsupported
major types, and trailing bytes are rejected.
"""
from __future__ import annotations

from .canonical import (
    ACCOUNT_ID_SIZE,
    CHAIN_ID_SIZE,
    PROTOCOL_VERSION,
    PUBLIC_KEY_SIZE,
    SIGNATURE_SIZE,
    UINT64_MAX,
    EncodingError,
    signed_transaction,
    transaction_payload,
)


def _argument(data: bytes, offset: int, additional: int) -> tuple[int, int]:
    if additional < 24:
        return additional, offset
    widths = {24: 1, 25: 2, 26: 4, 27: 8}
    width = widths.get(additional)
    if width is None:
        raise EncodingError("indefinite or reserved CBOR additional information")
    end = offset + width
    if end > len(data):
        raise EncodingError("truncated CBOR argument")
    value = int.from_bytes(data[offset:end], "big")
    minimum = {1: 24, 2: 256, 4: 65536, 8: 1 << 32}[width]
    if value < minimum:
        raise EncodingError("non-minimal CBOR integer or length")
    return value, end


def _item(data: bytes, offset: int) -> tuple[object, int]:
    if offset >= len(data):
        raise EncodingError("truncated CBOR item")
    initial = data[offset]
    major, additional = initial >> 5, initial & 31
    value, cursor = _argument(data, offset + 1, additional)
    if major == 0:
        if value > UINT64_MAX:
            raise EncodingError("unsigned integer exceeds uint64")
        return value, cursor
    if major == 2:
        end = cursor + value
        if end > len(data):
            raise EncodingError("truncated CBOR byte string")
        return data[cursor:end], end
    if major == 4:
        items = []
        for _ in range(value):
            item, cursor = _item(data, cursor)
            items.append(item)
        return items, cursor
    raise EncodingError("unsupported CBOR major type")


def _decode_array(encoded: bytes, expected_length: int) -> list[object]:
    if not isinstance(encoded, bytes):
        raise EncodingError("encoded CBOR value must be bytes")
    value, end = _item(encoded, 0)
    if end != len(encoded):
        raise EncodingError("trailing bytes after CBOR value")
    if not isinstance(value, list) or len(value) != expected_length:
        raise EncodingError("unexpected CBOR array shape")
    if any(isinstance(item, list) for item in value):
        raise EncodingError("nested arrays are not permitted in transaction fields")
    return value


def decode_transaction_payload(encoded: bytes) -> dict[str, object]:
    """Decode and validate the exact six-field unsigned transaction payload."""
    fields = _decode_array(encoded, 6)
    version, chain_id, sender, recipient, amount, nonce = fields
    if version != PROTOCOL_VERSION or isinstance(version, bool):
        raise EncodingError("unsupported protocol version")
    if not isinstance(chain_id, bytes) or len(chain_id) != CHAIN_ID_SIZE:
        raise EncodingError("chain_id must be exactly 32 bytes")
    if not isinstance(sender, bytes) or len(sender) != ACCOUNT_ID_SIZE:
        raise EncodingError("sender must be exactly 32 bytes")
    if not isinstance(recipient, bytes) or len(recipient) != ACCOUNT_ID_SIZE:
        raise EncodingError("recipient must be exactly 32 bytes")
    if isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= UINT64_MAX:
        raise EncodingError("amount must be a positive uint64")
    if isinstance(nonce, bool) or not isinstance(nonce, int) or not 0 <= nonce <= UINT64_MAX:
        raise EncodingError("nonce must be a uint64")
    if transaction_payload(chain_id, sender, recipient, amount, nonce) != encoded:
        raise EncodingError("transaction payload is not canonical")
    return {
        "version": version,
        "chain_id": chain_id,
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "nonce": nonce,
    }


def decode_signed_transaction(encoded: bytes) -> dict[str, object]:
    """Decode and validate the exact eight-field complete signed transaction."""
    fields = _decode_array(encoded, 8)
    version, chain_id, sender, recipient, amount, nonce, public_key, signature = fields
    base = transaction_payload(
        chain_id, sender, recipient, amount, nonce
    ) if (
        isinstance(chain_id, bytes)
        and isinstance(sender, bytes)
        and isinstance(recipient, bytes)
        and isinstance(amount, int) and not isinstance(amount, bool)
        and isinstance(nonce, int) and not isinstance(nonce, bool)
    ) else None
    if base is None:
        raise EncodingError("malformed signed transaction payload")
    if version != PROTOCOL_VERSION or isinstance(version, bool):
        raise EncodingError("unsupported protocol version")
    if not isinstance(public_key, bytes) or len(public_key) != PUBLIC_KEY_SIZE:
        raise EncodingError("public_key must be exactly 32 bytes")
    if not isinstance(signature, bytes) or len(signature) != SIGNATURE_SIZE:
        raise EncodingError("signature must be exactly 64 bytes")
    if signed_transaction(
        chain_id, sender, recipient, amount, nonce, public_key, signature
    ) != encoded:
        raise EncodingError("signed transaction is not canonical")
    return {
        "version": version,
        "chain_id": chain_id,
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "nonce": nonce,
        "public_key": public_key,
        "signature": signature,
    }
